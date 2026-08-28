import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.domain.rules.duration import (
    DURATION_TOLERANCE_SECONDS,
    DurationPlan,
    DurationRequest,
    DurationTargetMismatchError,
    PlanItemDuration,
    require_exact_duration,
    validate_requested_duration,
)
from backend.app.modules.routines.codes import RoutinePhaseCode, RoutineTierCode
from backend.app.modules.routines.ports import (
    RoutineCandidate,
    RoutineCreationContext,
    RoutineDayValues,
    RoutineItemValues,
    RoutineRepositoryPort,
)
from backend.app.modules.routines.schemas import RoutineCreateRequest, RoutineResponse


class RoutineError(Exception):
    """Base class for safe routine creation failures."""


class IdempotencyKeyReusedError(RoutineError):
    """The same key was used with a different request."""


class ApprovedCatalogUnavailableError(RoutineError):
    """No production-approved active catalog can support the use case."""


class RoutineContentUnavailableError(RoutineError):
    """Approved content cannot form all required routine phases."""


class RoutineDurationUnavailableError(RoutineError):
    """Approved prescriptions cannot exactly preserve the requested duration."""


class RoutineNotFoundError(RoutineError):
    """No active routine exists in the authenticated user's scope."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request_hash(request: RoutineCreateRequest) -> str:
    raw = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _candidate_duration(candidate: RoutineCandidate) -> PlanItemDuration:
    if candidate.reps is not None:
        if candidate.seconds_per_rep is None:
            raise RoutineContentUnavailableError
        work_per_set = candidate.reps * candidate.seconds_per_rep
    else:
        if candidate.work_seconds_per_set is None:
            raise RoutineContentUnavailableError
        work_per_set = candidate.work_seconds_per_set
    return PlanItemDuration(
        work_seconds=candidate.sets * work_per_set,
        rest_seconds=max(candidate.sets - 1, 0) * candidate.rest_seconds_per_set,
        transition_seconds=candidate.transition_seconds,
    )


def _subsets(
    candidates: tuple[RoutineCandidate, ...], target_seconds: int
) -> dict[tuple[int, bool], tuple[RoutineCandidate, ...]]:
    states: dict[tuple[int, bool], tuple[RoutineCandidate, ...]] = {(0, False): ()}
    for candidate in sorted(
        candidates, key=lambda item: (item.exercise_name, str(item.exercise_id))
    ):
        seconds = _candidate_duration(candidate).estimated_item_seconds
        additions: dict[tuple[int, bool], tuple[RoutineCandidate, ...]] = {}
        for (current, has_core), selected in states.items():
            total = current + seconds
            if total > target_seconds:
                continue
            key = (total, has_core or candidate.tier_code == RoutineTierCode.CORE)
            proposed = (*selected, candidate)
            existing = states.get(key) or additions.get(key)
            if existing is None or len(proposed) < len(existing):
                additions[key] = proposed
        states.update(additions)
    return states


def _select_exact_plan(
    context: RoutineCreationContext,
) -> tuple[int, tuple[RoutineCandidate, ...], DurationRequest]:
    duration_request = validate_requested_duration(
        profile_duration_minutes=context.profile_duration_minutes,
        requested_duration_minutes=context.profile_duration_minutes,
        adjustment_source_code="PROFILE",
    )
    target = duration_request.target_duration_seconds
    by_phase = {
        phase: tuple(item for item in context.candidates if item.phase_code == phase)
        for phase in RoutinePhaseCode
    }
    if any(not by_phase[phase] for phase in RoutinePhaseCode):
        raise RoutineContentUnavailableError

    warmups = _subsets(by_phase[RoutinePhaseCode.WARMUP], min(target, 180))
    mains = _subsets(by_phase[RoutinePhaseCode.MAIN], target + DURATION_TOLERANCE_SECONDS)
    cooldowns = _subsets(by_phase[RoutinePhaseCode.COOLDOWN], min(target, 120))
    matches: list[tuple[int, int, tuple[RoutineCandidate, ...]]] = []
    for (warmup_seconds, _), warmup_items in warmups.items():
        if not 60 <= warmup_seconds <= 180:
            continue
        for (main_seconds, has_core), main_items in mains.items():
            if not has_core or main_seconds <= 0:
                continue
            for (cooldown_seconds, _), cooldown_items in cooldowns.items():
                if not 45 <= cooldown_seconds <= 120:
                    continue
                content_seconds = warmup_seconds + main_seconds + cooldown_seconds
                # Setup still occupies at most a minute; it absorbs a shortfall
                # but never stretches to cover the whole tolerance.
                setup_seconds = min(max(target - content_seconds, 0), 60)
                deviation = abs(content_seconds + setup_seconds - target)
                if deviation <= DURATION_TOLERANCE_SECONDS:
                    selected = (*warmup_items, *main_items, *cooldown_items)
                    matches.append((deviation, setup_seconds, selected))
    if not matches:
        raise RoutineDurationUnavailableError
    matches.sort(
        key=lambda match: (
            # Closest to the requested duration wins; the tolerance is a
            # fallback, not a licence to drift.
            match[0],
            sum(item.tier_code == RoutineTierCode.OPTIONAL for item in match[2]),
            len(match[2]),
            tuple(
                (item.phase_code, item.exercise_name, str(item.exercise_id)) for item in match[2]
            ),
        )
    )
    return matches[0][1], matches[0][2], duration_request


def _build_days(context: RoutineCreationContext) -> tuple[RoutineDayValues, ...]:
    setup_seconds, selected, duration_request = _select_exact_plan(context)
    warmup_seconds = sum(
        _candidate_duration(item).estimated_item_seconds
        for item in selected
        if item.phase_code == RoutinePhaseCode.WARMUP
    )
    cooldown_seconds = sum(
        _candidate_duration(item).estimated_item_seconds
        for item in selected
        if item.phase_code == RoutinePhaseCode.COOLDOWN
    )
    main_durations = tuple(
        _candidate_duration(item) for item in selected if item.phase_code == RoutinePhaseCode.MAIN
    )
    try:
        assessment = require_exact_duration(
            duration_request,
            DurationPlan(
                setup_seconds=setup_seconds,
                warmup_seconds=warmup_seconds,
                items=main_durations,
                cooldown_seconds=cooldown_seconds,
            ),
            tolerance_seconds=DURATION_TOLERANCE_SECONDS,
        )
    except DurationTargetMismatchError:
        raise RoutineDurationUnavailableError from None
    items = tuple(
        RoutineItemValues(
            exercise_id=item.exercise_id,
            sequence=sequence,
            phase_code=item.phase_code,
            tier_code=(
                item.tier_code
                if item.phase_code == RoutinePhaseCode.MAIN
                else RoutineTierCode.SUPPORT
            ),
            sets=item.sets,
            reps=item.reps,
            work_seconds_per_set=item.work_seconds_per_set,
            rest_seconds_per_set=item.rest_seconds_per_set,
            intensity_code=item.intensity_code,
        )
        for sequence, item in enumerate(selected, start=1)
    )
    main = next(item for item in selected if item.phase_code == RoutinePhaseCode.MAIN)
    return tuple(
        RoutineDayValues(
            sequence=sequence,
            title=f"루틴 {sequence}",
            training_type_code=main.training_type_code,
            body_focus_code=main.body_focus_code,
            requested_duration_minutes=context.profile_duration_minutes,
            estimated_duration_seconds=assessment.estimated_duration_seconds,
            setup_seconds=setup_seconds,
            items=items,
        )
        for sequence in range(1, context.desired_weekly_workout_count + 1)
    )


class RoutineService:
    def __init__(
        self,
        repository: RoutineRepositoryPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def create(
        self,
        session: Session,
        user_id: UUID,
        request: RoutineCreateRequest,
        idempotency_key: UUID,
    ) -> RoutineResponse:
        request_hash = _request_hash(request)
        now = self._clock()
        with session.begin():
            self._repository.acquire_creation_lock(session, user_id)
            existing = self._repository.get_idempotency_record(session, user_id, idempotency_key)
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise IdempotencyKeyReusedError
                return RoutineResponse.model_validate(existing.response_payload)
            context = self._repository.get_creation_context(session, user_id, request.goal_code)
            if context is None:
                raise ApprovedCatalogUnavailableError
            days = _build_days(context)
            routine_id = self._repository.create_routine(
                session,
                user_id,
                request.goal_code,
                request.effective_from,
                context.catalog_version_id,
                days,
                now,
            )
            payload = self._repository.get_routine_response_payload(session, user_id, routine_id)
            if payload is None:
                raise RuntimeError("created routine could not be reloaded")
            response = RoutineResponse.model_validate(payload)
            self._repository.save_idempotency_record(
                session,
                user_id,
                idempotency_key,
                request_hash,
                response.model_dump(mode="json"),
                now,
            )
            return response

    def get_current(self, session: Session, user_id: UUID, local_date: date) -> RoutineResponse:
        payload = self._repository.get_current_routine_payload(session, user_id, local_date)
        if payload is None:
            raise RoutineNotFoundError
        return RoutineResponse.model_validate(payload)


__all__ = [
    "ApprovedCatalogUnavailableError",
    "IdempotencyKeyReusedError",
    "RoutineContentUnavailableError",
    "RoutineDurationUnavailableError",
    "RoutineNotFoundError",
    "RoutineService",
]
