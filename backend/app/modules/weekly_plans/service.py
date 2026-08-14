import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.domain.rules.safety import SafetyStatusCode
from backend.app.domain.rules.weekly_plan import (
    MAX_SUCCESSFUL_AI_REVISIONS,
    WEEKLY_PLAN_POLICY_VERSION,
    PlanConstraints,
    PlanFinalizationContext,
    PlanRevisionEndpointCode,
    PlanRevisionPolicyInput,
    PlanRevisionReasonCode,
    PlanRevisionSourceCode,
    PlanRoutineEvidence,
    RoutineDecisionAuthorityCode,
    SafetyDecisionAuthorityCode,
    evaluate_plan_finalization,
    evaluate_plan_revision,
)
from backend.app.domain.rules.weekly_report import WeeklyReportStatusCode
from backend.app.modules.routines.ports import RoutineRepositoryPort
from backend.app.modules.routines.schemas import RoutineResponse
from backend.app.modules.weekly_plans.codes import (
    WEEKLY_PLAN_ENDPOINT_CODE,
    WEEKLY_PLAN_INPUT_SCHEMA_VERSION,
    WEEKLY_PLAN_REVISION_ENDPOINT_CODE,
)
from backend.app.modules.weekly_plans.ports import (
    PlanContext,
    PlanRevisionValues,
    RoutinePlanEvidence,
    WeeklyPlanRepositoryPort,
)
from backend.app.modules.weekly_plans.schemas import (
    InitialWeeklyPlanRequest,
    WeeklyPlanRevisionRequest,
    WeeklyPlanRevisionResponse,
)
from backend.app.modules.weekly_reports.schemas import WeekResponse

_ROUTINE_STATUSES = frozenset({SafetyStatusCode.PASS, SafetyStatusCode.REVISE})


class WeekResolverPort(Protocol):
    def get_week(self, session: Session, user_id: UUID, week_start: date) -> WeekResponse: ...


class WeeklyPlanError(Exception):
    pass


class TargetWeekClosedError(WeeklyPlanError):
    pass


class InitialPlanAlreadyExistsError(WeeklyPlanError):
    pass


class InitialPlanRequiredError(WeeklyPlanError):
    pass


class PreviousWeeklyReportRequiredError(WeeklyPlanError):
    pass


class WeeklyPlanContextUnavailableError(WeeklyPlanError):
    pass


class WeeklyPlanRoutineNotFoundError(WeeklyPlanError):
    pass


class StalePlanRevisionError(WeeklyPlanError):
    pass


class AiRevisionLimitReachedError(WeeklyPlanError):
    pass


class PlanRevisionRejectedError(WeeklyPlanError):
    def __init__(self, reason_codes: tuple[str, ...]) -> None:
        super().__init__("plan revision rejected")
        self.reason_codes = reason_codes


class IdempotencyKeyReusedError(WeeklyPlanError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _request_hash(week_start: date, request: BaseModel) -> str:
    return _hash({"week_start": week_start.isoformat(), "body": request.model_dump(mode="json")})


class WeeklyPlanService:
    def __init__(
        self,
        repository: WeeklyPlanRepositoryPort,
        routine_repository: RoutineRepositoryPort,
        week_resolver: WeekResolverPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository = repository
        self._routine_repository = routine_repository
        self._week_resolver = week_resolver
        self._clock = clock
        self._uuid_factory = uuid_factory

    def create_initial(
        self,
        session: Session,
        user_id: UUID,
        week_start: date,
        request: InitialWeeklyPlanRequest,
        idempotency_key: UUID,
    ) -> WeeklyPlanRevisionResponse:
        week = self._week_resolver.get_week(session, user_id, week_start)
        if week.status_code == "CLOSED":
            raise TargetWeekClosedError
        now = self._clock()
        request_hash = _request_hash(week_start, request)
        with session.begin():
            self._repository.acquire_week_lock(session, user_id, week_start)
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=WEEKLY_PLAN_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            if prior is not None:
                return prior
            context = self._context(session, user_id, week)
            if self._repository.get_latest_revision(session, week.week_id) is not None:
                raise InitialPlanAlreadyExistsError
            response = self._create_revision(
                session=session,
                user_id=user_id,
                context=context,
                source_code=PlanRevisionSourceCode.INITIAL,
                revision_sequence=1,
                successful_ai_revision_count=0,
                requested_routine_id=context.current_routine_id,
                requested_location_code=None,
                now=now,
            )
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=WEEKLY_PLAN_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
            return response

    def create_revision(
        self,
        session: Session,
        user_id: UUID,
        week_start: date,
        request: WeeklyPlanRevisionRequest,
        idempotency_key: UUID,
    ) -> WeeklyPlanRevisionResponse:
        week = self._week_resolver.get_week(session, user_id, week_start)
        if week.status_code == "CLOSED":
            raise TargetWeekClosedError
        now = self._clock()
        request_hash = _request_hash(week_start, request)
        with session.begin():
            self._repository.acquire_week_lock(session, user_id, week_start)
            prior = self._prior_response(
                session,
                user_id=user_id,
                endpoint_code=WEEKLY_PLAN_REVISION_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            if prior is not None:
                return prior
            context = self._context(session, user_id, week)
            latest = self._repository.get_latest_revision(session, week.week_id)
            if latest is None:
                raise InitialPlanRequiredError
            if latest.revision_sequence != request.expected_revision_sequence:
                raise StalePlanRevisionError
            source_code = PlanRevisionSourceCode(request.source_code)
            routine_id: UUID | None
            if source_code is PlanRevisionSourceCode.USER:
                assert request.user_edits is not None
                routine_id = request.user_edits.routine_id
                location_code = request.user_edits.location_code
            else:
                routine_id = context.current_routine_id or latest.routine_id
                location_code = None
            response = self._create_revision(
                session=session,
                user_id=user_id,
                context=context,
                source_code=source_code,
                revision_sequence=latest.revision_sequence + 1,
                successful_ai_revision_count=latest.successful_ai_revision_count,
                requested_routine_id=routine_id,
                requested_location_code=location_code,
                now=now,
            )
            self._save_response(
                session,
                user_id=user_id,
                endpoint_code=WEEKLY_PLAN_REVISION_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
                now=now,
            )
            return response

    def _context(self, session: Session, user_id: UUID, week: WeekResponse) -> PlanContext:
        context = self._repository.get_plan_context(session, user_id, week.week_id, week.week_start)
        if context is None:
            raise WeeklyPlanContextUnavailableError
        if context.cold_start_applied:
            if not context.is_first_user_week or context.source_weekly_report_id is not None:
                raise WeeklyPlanContextUnavailableError
        elif context.is_first_user_week or context.source_weekly_report_id is None:
            raise PreviousWeeklyReportRequiredError
        return context

    def _create_revision(
        self,
        *,
        session: Session,
        user_id: UUID,
        context: PlanContext,
        source_code: PlanRevisionSourceCode,
        revision_sequence: int,
        successful_ai_revision_count: int,
        requested_routine_id: UUID | None,
        requested_location_code: str | None,
        now: datetime,
    ) -> WeeklyPlanRevisionResponse:
        if (
            source_code is PlanRevisionSourceCode.AI
            and successful_ai_revision_count >= MAX_SUCCESSFUL_AI_REVISIONS
        ):
            raise AiRevisionLimitReachedError
        safety_status = SafetyStatusCode(context.safety_status_code)
        routine_evidence: RoutinePlanEvidence | None = None
        selected_location: str | None = None
        domain_routine: PlanRoutineEvidence | None = None
        allowed_locations = context.allowed_location_codes
        applied_safety_opinions: tuple[str, ...] = ()
        if safety_status in _ROUTINE_STATUSES:
            if requested_routine_id is None:
                raise WeeklyPlanRoutineNotFoundError
            routine_evidence = self._repository.get_routine_evidence(
                session, user_id, requested_routine_id
            )
            if routine_evidence is None:
                raise WeeklyPlanRoutineNotFoundError
            allowed_locations = tuple(
                sorted(
                    set(context.allowed_location_codes)
                    & set(routine_evidence.supported_location_codes)
                )
            )
            if not allowed_locations:
                raise PlanRevisionRejectedError(("LOCATION_CONSTRAINT_NOT_SATISFIED",))
            if requested_location_code is None:
                selected_location = (
                    context.preferred_location_code
                    if context.preferred_location_code in allowed_locations
                    else allowed_locations[0]
                )
            else:
                selected_location = requested_location_code
            excludes_conflict = bool(
                set(context.excluded_exercise_ids) & set(routine_evidence.exercise_ids)
            )
            if excludes_conflict:
                raise PlanRevisionRejectedError(("SAFETY_OPINION_NOT_APPLIED",))
            applied_safety_opinions = context.safety_opinion_codes
            domain_routine = PlanRoutineEvidence(
                routine_reference=f"routine-v{routine_evidence.routine_version}",
                requested_duration_minutes=routine_evidence.requested_duration_minutes,
                location_code=selected_location,
                required_equipment_codes=routine_evidence.required_equipment_codes,
                applied_safety_opinion_codes=applied_safety_opinions,
                routine_decision_authority_code=(
                    RoutineDecisionAuthorityCode.USER
                    if source_code is PlanRevisionSourceCode.USER
                    else RoutineDecisionAuthorityCode.COORDINATOR
                ),
                safety_decision_authority_code=SafetyDecisionAuthorityCode.SAFETY_AGENT,
            )

        constraints = PlanConstraints(
            requested_duration_minutes=context.requested_duration_minutes,
            allowed_location_codes=allowed_locations,
            available_equipment_codes=context.available_equipment_codes,
            required_safety_opinion_codes=context.safety_opinion_codes,
        )
        revision = evaluate_plan_revision(
            PlanRevisionPolicyInput(
                endpoint_code=(
                    PlanRevisionEndpointCode.INITIAL_PLAN
                    if source_code is PlanRevisionSourceCode.INITIAL
                    else PlanRevisionEndpointCode.PLAN_REVISIONS
                ),
                source_code=source_code,
                safety_status_code=safety_status,
                successful_ai_revision_count=successful_ai_revision_count,
                constraints=constraints,
                routine=domain_routine,
            )
        )
        if not revision.revision_allowed:
            reasons = tuple(code.value for code in revision.reason_codes)
            if PlanRevisionReasonCode.AI_REVISION_LIMIT_REACHED in revision.reason_codes:
                raise AiRevisionLimitReachedError
            raise PlanRevisionRejectedError(reasons)
        report_status = (
            None
            if context.previous_report_status_code is None
            else WeeklyReportStatusCode(context.previous_report_status_code)
        )
        finalization = evaluate_plan_finalization(
            revision_decision=revision,
            safety_status_code=safety_status,
            routine_present=domain_routine is not None,
            context=PlanFinalizationContext(
                is_first_user_week=context.is_first_user_week,
                cold_start_applied=context.cold_start_applied,
                previous_report_status_code=report_status,
            ),
        )
        snapshot: dict[str, Any] = {
            "input_schema_version": WEEKLY_PLAN_INPUT_SCHEMA_VERSION,
            "weekly_plan_policy_version": WEEKLY_PLAN_POLICY_VERSION,
            "week": {
                "week_start": context.week_start.isoformat(),
                "week_end": context.week_end.isoformat(),
                "is_first_user_week": context.is_first_user_week,
                "cold_start_applied": context.cold_start_applied,
            },
            "source_report": {
                "report_id": (
                    None
                    if context.source_weekly_report_id is None
                    else str(context.source_weekly_report_id)
                ),
                "status_code": context.previous_report_status_code,
            },
            "revision": {
                "source_code": source_code.value,
                "revision_sequence": revision_sequence,
                "prior_successful_ai_revision_count": successful_ai_revision_count,
            },
            "constraints": {
                "requested_duration_minutes": context.requested_duration_minutes,
                "allowed_location_codes": list(allowed_locations),
                "available_equipment_codes": list(context.available_equipment_codes),
                "required_safety_opinion_codes": list(context.safety_opinion_codes),
            },
            "safety": {
                "status_code": safety_status.value,
                "excluded_exercise_ids": [str(value) for value in context.excluded_exercise_ids],
            },
            "routine": (
                None
                if routine_evidence is None
                else {
                    "routine_id": str(routine_evidence.routine_id),
                    "routine_version": routine_evidence.routine_version,
                    "requested_duration_minutes": (routine_evidence.requested_duration_minutes),
                    "selected_location_code": selected_location,
                    "required_equipment_codes": list(routine_evidence.required_equipment_codes),
                    "applied_safety_opinion_codes": list(applied_safety_opinions),
                }
            ),
        }
        ai_revision_number = (
            revision.resulting_ai_revision_count
            if source_code is PlanRevisionSourceCode.AI
            and revision.resulting_ai_revision_count > successful_ai_revision_count
            else None
        )
        values = PlanRevisionValues(
            revision_id=self._uuid_factory(),
            target_user_week_id=context.week_id,
            source_weekly_report_id=context.source_weekly_report_id,
            revision_sequence=revision_sequence,
            ai_revision_number=ai_revision_number,
            revision_source_code=source_code.value,
            routine_id=None if routine_evidence is None else routine_evidence.routine_id,
            selected_location_code=selected_location,
            safety_status_code=safety_status.value,
            input_schema_version=WEEKLY_PLAN_INPUT_SCHEMA_VERSION,
            input_snapshot=snapshot,
            input_hash=_hash(snapshot),
            weekly_plan_policy_version=WEEKLY_PLAN_POLICY_VERSION,
            revision_reason_codes=[code.value for code in revision.reason_codes],
            finalization_reason_codes=[code.value for code in finalization.reason_codes],
            finalized_at=now if finalization.finalized else None,
            created_at=now,
        )
        self._repository.create_revision(session, values)
        routine_response = self._routine_response(
            session, user_id, None if routine_evidence is None else routine_evidence.routine_id
        )
        return WeeklyPlanRevisionResponse(
            revision_id=values.revision_id,
            week_start=context.week_start,
            week_end=context.week_end,
            revision_sequence=values.revision_sequence,
            ai_revision_count=cast(Literal[0, 1, 2], revision.resulting_ai_revision_count),
            source_code=source_code.value,
            source_weekly_report_id=context.source_weekly_report_id,
            safety_status_code=safety_status.value,
            routine=routine_response,
            selected_location_code=selected_location,
            finalized=finalization.finalized,
            finalized_at=values.finalized_at,
            revision_reason_codes=values.revision_reason_codes,
            finalization_reason_codes=values.finalization_reason_codes,
            created_at=now,
        )

    def _routine_response(
        self, session: Session, user_id: UUID, routine_id: UUID | None
    ) -> RoutineResponse | None:
        if routine_id is None:
            return None
        payload = self._routine_repository.get_routine_response_payload(
            session, user_id, routine_id
        )
        if payload is None:
            raise WeeklyPlanRoutineNotFoundError
        return RoutineResponse.model_validate(payload)

    def _prior_response(
        self,
        session: Session,
        *,
        user_id: UUID,
        endpoint_code: str,
        idempotency_key: UUID,
        request_hash: str,
    ) -> WeeklyPlanRevisionResponse | None:
        self._repository.acquire_idempotency_lock(session, user_id, endpoint_code, idempotency_key)
        prior = self._repository.get_idempotency_record(
            session, user_id, endpoint_code, idempotency_key
        )
        if prior is None:
            return None
        if prior.request_hash != request_hash:
            raise IdempotencyKeyReusedError
        return WeeklyPlanRevisionResponse.model_validate(prior.response_payload)

    def _save_response(
        self,
        session: Session,
        *,
        user_id: UUID,
        endpoint_code: str,
        idempotency_key: UUID,
        request_hash: str,
        response: WeeklyPlanRevisionResponse,
        now: datetime,
    ) -> None:
        self._repository.save_idempotency_record(
            session,
            user_id=user_id,
            endpoint_code=endpoint_code,
            key=idempotency_key,
            request_hash=request_hash,
            response_payload=response.model_dump(mode="json"),
            now=now,
        )


__all__ = [
    "AiRevisionLimitReachedError",
    "IdempotencyKeyReusedError",
    "InitialPlanAlreadyExistsError",
    "InitialPlanRequiredError",
    "PlanRevisionRejectedError",
    "PreviousWeeklyReportRequiredError",
    "StalePlanRevisionError",
    "TargetWeekClosedError",
    "WeeklyPlanContextUnavailableError",
    "WeeklyPlanRoutineNotFoundError",
    "WeeklyPlanService",
]
