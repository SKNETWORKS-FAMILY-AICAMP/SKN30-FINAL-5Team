"""Concrete application and SQLAlchemy adapters for authoritative V3 decisions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Self, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models.catalog import Exercise
from backend.app.db.models.decision import (
    DecisionExplanationRecord,
    DecisionOption,
    DecisionPolicyVersion,
    DecisionRun,
    PlanCandidate,
    PlanItem,
    SafetyReview,
)
from backend.app.db.models.profile import MutationIdempotencyRecord
from backend.app.db.models.v3_decision import DecisionConstraintEnvelopeRecord
from backend.app.db.repositories.decision import DecisionRepository
from backend.app.db.repositories.vector_index import VectorIndexRepository
from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExerciseRetrievalResult,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, RecoveryCeiling
from backend.app.domain.agents.v3_duration import (
    pool_size_for_duration,
    prescription_item_duration,
)
from backend.app.domain.agents.v3_orchestration import GraphTerminalStatusCode
from backend.app.domain.agents.v3_persistence import V3DecisionPersistenceBundle
from backend.app.domain.rules.duration import DURATION_RULE_VERSION
from backend.app.domain.rules.safety import (
    SafetyCandidate,
    SafetyCandidateItem,
    SafetyEvaluation,
    SafetyRequiredActionCode,
    SafetyStatusCode,
    evaluate_safety,
)
from backend.app.domain.rules.training_level import is_exercise_allowed_for_user
from backend.app.integrations.qdrant.snapshot_loader import (
    EligibleExerciseProjection,
    PostgreSQLExercisePoolSourcePort,
)
from backend.app.modules.decisions.codes import (
    DECISION_INPUT_SCHEMA_VERSION,
    DECISION_POLICY_VERSION,
)
from backend.app.modules.decisions.ports import DecisionAssembly
from backend.app.modules.decisions.schemas import (
    DecisionOptionResponse,
    DecisionPlan,
    DecisionPlanItem,
    DecisionResponse,
    Guidance,
    SafetySummary,
)
from backend.app.modules.decisions.service import (
    DecisionFailedError,
    IdempotencyKeyReusedError,
    _prepare_safety,
    _safety_context,
    _safety_rule_version,
)
from backend.app.modules.decisions.v3_creation import (
    V3CreationIdempotencyRecord,
    V3CreationSource,
)
from backend.app.modules.decisions.v3_regeneration import (
    V3DecisionEngineCode,
    V3IdempotencyKeyReusedError,
    V3RegenerationIdempotencyRecord,
    V3RegenerationResult,
    V3RegenerationVersionSnapshot,
    V3StoredRegenerationSource,
)
from backend.app.modules.decisions.v3_sql_persistence import (
    V3InvocationSqlMetadata,
    V3SqlAlchemyPersistenceAdapter,
    V3SqlPersistenceMetadata,
)

_SNAPSHOT_TTL = timedelta(hours=1)
_TEMPLATE_VERSION = "v3-demo-public-template-v1"


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(slots=True)
class V3ApplicationContext:
    assembly: DecisionAssembly
    exercises: tuple[ExercisePoolExerciseRecord, ...]
    exercise_names: dict[UUID, str] = field(default_factory=dict)
    safety_evaluation: SafetyEvaluation | None = None
    pool_safety_evaluation: SafetyEvaluation | None = None


def _context(source: V3CreationSource) -> V3ApplicationContext:
    value = source.application_context
    if not isinstance(value, V3ApplicationContext):
        raise RuntimeError("V3_CREATION_SOURCE_INCOMPLETE")
    return value


class SqlAlchemyV3CreationUnitOfWork:
    """Use the API request session for one atomic creation transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._transaction: Any = None
        self.decisions = SqlAlchemyV3CreationRepository(session)

    def __enter__(self) -> Self:
        self._transaction = self._session.begin()
        self._transaction.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool | None:
        return self._transaction.__exit__(exc_type, exc, traceback)


class SqlAlchemyV3CreationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._legacy = DecisionRepository()
        self._vectors = VectorIndexRepository()

    def acquire_lock(self, *, user_id: UUID, idempotency_key: UUID) -> None:
        self._legacy.acquire_lock(self._session, user_id, idempotency_key)

    def get_idempotency(
        self, *, user_id: UUID, idempotency_key: UUID
    ) -> V3CreationIdempotencyRecord | None:
        stored = self._legacy.get_idempotency(self._session, user_id, idempotency_key)
        if stored is None:
            return None
        payload = stored.response_payload.get("response")
        if not isinstance(payload, dict):
            raise IdempotencyKeyReusedError
        return V3CreationIdempotencyRecord(
            request_hash=stored.request_hash,
            response=DecisionResponse.model_validate(payload),
        )

    def load_source(self, *, user_id: UUID, daily_context_id: UUID) -> V3CreationSource | None:
        assembly = self._legacy.assemble(self._session, user_id, daily_context_id)
        if assembly is None:
            return None
        records = self._vectors.list_indexable_exercises(self._session, assembly.catalog_version)
        records = tuple(
            item
            for item in records
            if is_exercise_allowed_for_user(
                exercise_difficulty_code=item.difficulty_code,
                user_experience_level_code=assembly.context.experience_level_code,
            )
            and assembly.context.experience_level_code in item.prescription_experience_level_codes
        )
        exercises = tuple(
            sorted(
                (
                    ExercisePoolExerciseRecord(
                        exercise_id=item.exercise_id,
                        catalog_version=item.catalog_version_code,
                        content_version=item.instruction_content_version,
                        stable_code=item.stable_code or f"exercise-{item.exercise_id}",
                        training_type_code=item.training_type_code,
                        body_focus_code=item.body_focus_code,
                        movement_pattern_codes=(item.primary_movement_pattern_code,),
                        difficulty_code=item.difficulty_code,
                        timing_mode_code=item.timing_mode_code,
                        default_seconds_per_rep=item.default_seconds_per_rep,
                        default_work_seconds=item.default_work_seconds,
                        default_rest_seconds=item.default_rest_seconds,
                        default_transition_seconds=item.default_transition_seconds,
                        recovery_eligible=item.recovery_eligible,
                        goal_codes=tuple(sorted(item.goal_codes)),
                        equipment_codes=tuple(sorted(item.equipment_codes)),
                        location_codes=tuple(sorted(item.location_codes)),
                        prescription_reference_codes=(
                            f"prescription/{item.stable_code or item.exercise_id}",
                        ),
                        source_reference_codes=(f"catalog/{item.catalog_version_code}",),
                        review_reference_codes=("DOMAIN_APPROVED",),
                    )
                    for item in records
                ),
                key=lambda item: str(item.exercise_id),
            )
        )
        context = assembly.context
        normalized = {
            "fatigue_level_code": context.fatigue_level_code,
            "requested_duration_minutes": context.requested_duration_minutes,
            "duration_adjustment_source_code": context.duration_adjustment_source_code,
            "location_code": context.location_code,
            "primary_goal_code": context.primary_goal_code,
            "experience_level_code": context.experience_level_code,
            "equipment_codes": list(context.equipment_codes),
        }
        return V3CreationSource(
            local_date=context.local_date,
            context_version=context.context_version,
            normalized_values=normalized,
            application_context=V3ApplicationContext(
                assembly,
                exercises,
                {item.exercise_id: item.name_ko for item in records},
            ),
        )

    def persist_terminal(
        self,
        *,
        user_id: UUID,
        source: V3CreationSource,
        envelope: ConstraintEnvelope,
        response: DecisionResponse,
    ) -> None:
        application = _context(source)
        run, candidate = _persist_public_decision(
            self._session,
            user_id=user_id,
            assembly=application.assembly,
            response=response,
            decision_id=response.decision_id,
            bundle=None,
        )
        run.root_decision_run_id = run.id
        run.generation_mode_code = "ORIGINAL"
        run.regeneration_sequence = 0
        run.decision_engine_code = "DETERMINISTIC"
        run.langchain_contract_version = "v3-langchain-contract-v1"
        run.langgraph_contract_version = "v3-safety-terminal-v1"
        self._session.add(
            DecisionConstraintEnvelopeRecord(
                root_decision_run_id=run.id,
                input_hash=run.input_hash,
                envelope_schema_version=envelope.schema_version,
                safety_policy_version=envelope.policy_version,
                policy_version_id=run.policy_version_id,
                safety_rule_version=envelope.safety_rule_version,
                duration_rule_version=run.duration_rule_version,
                plan_generation_allowed=False,
                required_action_code=(
                    envelope.safety_required_action_code.value
                    if envelope.safety_required_action_code is not None
                    else None
                ),
                veto=True,
                envelope_payload=envelope.model_dump(mode="json"),
                envelope_hash=envelope.envelope_hash,
                expires_at=datetime.now(UTC) + _SNAPSHOT_TTL,
            )
        )
        del candidate
        self._session.flush()

    def persist_success(
        self,
        *,
        user_id: UUID,
        source: V3CreationSource,
        bundle: V3DecisionPersistenceBundle,
        response: DecisionResponse,
    ) -> None:
        run, candidate = _persist_public_decision(
            self._session,
            user_id=user_id,
            assembly=_context(source).assembly,
            response=response,
            decision_id=bundle.decision_execution_id,
            bundle=bundle,
        )
        _persist_v3_bundle(self._session, run, candidate, bundle)

    def save_idempotency(
        self,
        *,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
        response: DecisionResponse,
    ) -> None:
        self._legacy.save_idempotency(
            self._session,
            user_id=user_id,
            key=idempotency_key,
            request_hash=request_hash,
            payload={"outcome_code": "COMPLETED", "response": response.model_dump(mode="json")},
            now=datetime.now(UTC),
        )


def _pool_safety_evaluation(
    assembly: DecisionAssembly,
    exercises: tuple[ExercisePoolExerciseRecord, ...],
) -> SafetyEvaluation | None:
    """Evaluate the reviewed safety rules against the pool the agents choose from.

    The base routine candidate only covers exercises already scheduled in the
    user's routine day. V3 selects from a catalog-wide pool, so every pool
    exercise outside that day reached the agents without ever being matched
    against the reported discomfort. Returns None only when there is no pool to
    evaluate; a missing rule set still yields the engine's fail-closed result.
    """

    if not exercises:
        return None
    candidate = SafetyCandidate(
        items=tuple(
            SafetyCandidateItem(
                str(record.exercise_id),
                record.catalog_version,
                # Movement-pattern rules match on the primary pattern the catalog
                # records. Without it only exercise-scoped rules can ever fire.
                record.movement_pattern_codes[0]
                if record.movement_pattern_codes
                else "UNSPECIFIED",
            )
            for record in exercises
        )
    )
    return evaluate_safety(
        _safety_context(assembly.context),
        candidate,
        assembly.safety_rule_set,
    )


class DeterministicV3SafetyPolicyAdapter:
    """Project the reviewed deterministic Safety engine into a V3 envelope."""

    def evaluate(self, source: V3CreationSource) -> ConstraintEnvelope:
        application = _context(source)
        prepared, evaluations = _prepare_safety(application.assembly)
        application.assembly = prepared
        base = next(value for code, value in evaluations if code == prepared.candidate.candidate_id)
        application.safety_evaluation = base
        pool_evaluation = _pool_safety_evaluation(prepared, application.exercises)
        application.pool_safety_evaluation = pool_evaluation
        safe_change_available = any(
            candidate.candidate.action_code.value == "CHANGE"
            for candidate in prepared.adjusted_candidates
        )
        allowed = base.status_code is SafetyStatusCode.PASS or (
            base.status_code is SafetyStatusCode.REVISE and bool(prepared.adjusted_candidates)
        )
        if base.excluded_exercise_codes and not safe_change_available:
            allowed = False
        excluded_codes = set(base.excluded_exercise_codes)
        if pool_evaluation is not None:
            # A pool exclusion is enforced by removing the exercise from the pool,
            # so unlike a base-routine exclusion it filters rather than blocks.
            excluded_codes |= set(pool_evaluation.excluded_exercise_codes)
        excluded = tuple(
            sorted(
                (UUID(value) for value in excluded_codes),
                key=str,
            )
        )
        if application.exercises and not {
            record.exercise_id for record in application.exercises
        } - set(excluded):
            # Nothing survived the rules; fail closed rather than plan from nothing.
            allowed = False
        items = tuple(item for item in prepared.items if item.exercise_id not in set(excluded))
        intensities = tuple(sorted({item.intensity_code for item in items}))
        ceiling = RecoveryCeiling(
            policy_version="v3-recovery-ceiling-from-approved-routine-v1",
            allowed_intensity_codes=intensities,
            maximum_sets_per_exercise=max((item.sets for item in items), default=None),
            maximum_repetitions_per_set=max(
                (item.reps for item in items if item.reps is not None), default=None
            ),
            maximum_work_seconds_per_set=max(
                (
                    item.work_seconds_per_set
                    for item in items
                    if item.work_seconds_per_set is not None
                ),
                default=None,
            ),
            minimum_rest_seconds_between_sets=min(
                (item.rest_seconds_per_set for item in items), default=None
            ),
        )
        required_action = base.required_action_code
        if not allowed and required_action is None:
            required_action = SafetyRequiredActionCode.REST
        context = prepared.context
        return ConstraintEnvelope.create(
            requested_duration_minutes=context.requested_duration_minutes,
            primary_goal_code=context.primary_goal_code,
            allowed_location_codes=(context.location_code,),
            allowed_equipment_codes=tuple(sorted(context.equipment_codes)),
            excluded_exercise_ids=excluded,
            mandatory_exercise_ids=(),
            recovery_ceiling=ceiling,
            plan_generation_allowed=allowed,
            safety_required_action_code=(None if allowed else required_action),
            policy_version=DECISION_POLICY_VERSION,
            catalog_version=prepared.catalog_version,
            safety_rule_version=_safety_rule_version(prepared),
        )


class PostgreSQLV3ExercisePoolSource(PostgreSQLExercisePoolSourcePort):
    def __init__(self) -> None:
        self._current: ContextVar[tuple[ExercisePoolExerciseRecord, ...]] = ContextVar(
            "v3_eligible_exercises", default=()
        )

    def load_eligible(
        self, *, source: V3CreationSource, envelope: ConstraintEnvelope
    ) -> EligibleExerciseProjection:
        application = _context(source)
        experience_level_code = str(source.normalized_values["experience_level_code"])
        eligible = tuple(
            item
            for item in application.exercises
            if item.exercise_id not in set(envelope.excluded_exercise_ids)
            and is_exercise_allowed_for_user(
                exercise_difficulty_code=item.difficulty_code,
                user_experience_level_code=experience_level_code,
            )
            and set(item.equipment_codes).issubset(envelope.allowed_equipment_codes)
            and bool(set(item.location_codes) & set(envelope.allowed_location_codes))
        )
        goal_matched = tuple(
            item for item in eligible if envelope.primary_goal_code in item.goal_codes
        )
        selected = goal_matched or eligible
        if not selected:
            raise RuntimeError("NO_APPROVED_SAFE_EXERCISE")
        self._current.set(selected)
        return EligibleExerciseProjection(
            catalog_version=envelope.catalog_version,
            exercises=selected,
            mandatory_exercise_ids=envelope.mandatory_exercise_ids,
            normalized_query_codes=tuple(
                sorted(
                    {
                        envelope.primary_goal_code,
                        str(source.normalized_values["experience_level_code"]),
                        str(source.normalized_values["location_code"]),
                    }
                )
            ),
            requested_limit=pool_size_for_duration(
                requested_duration_minutes=envelope.requested_duration_minutes,
                exercises=selected,
            ),
        )

    def revalidate(
        self,
        *,
        catalog_version: str,
        exercise_ids: tuple[UUID, ...],
        envelope: ConstraintEnvelope,
    ) -> tuple[ExercisePoolExerciseRecord, ...]:
        records = tuple(
            item
            for item in self._current.get()
            if item.catalog_version == catalog_version
            and item.exercise_id in set(exercise_ids)
            and item.exercise_id not in set(envelope.excluded_exercise_ids)
        )
        return tuple(sorted(records, key=lambda item: str(item.exercise_id)))


class V3DecisionResponseProjector:
    def __init__(self, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock

    def project_terminal(
        self, *, source: V3CreationSource, envelope: ConstraintEnvelope
    ) -> DecisionResponse:
        action = envelope.safety_required_action_code or SafetyRequiredActionCode.REST
        guidance = Guidance(
            code=action.value,
            title=(
                "운동을 중단하고 도움을 요청하세요"
                if action.value == "STOP_AND_SEEK_HELP"
                else "오늘은 휴식하세요"
            ),
            message=(
                "안전을 위해 운동을 진행하지 않습니다. 필요한 경우 전문가의 도움을 요청하세요."
                if action.value == "STOP_AND_SEEK_HELP"
                else "안전을 위해 오늘은 회복과 휴식을 우선하세요."
            ),
            tone_code="SERIOUS" if action.value == "STOP_AND_SEEK_HELP" else "NEUTRAL",
        )
        option_id = uuid4()
        evaluation = _context(source).safety_evaluation
        reasons = list(evaluation.reason_codes if evaluation is not None else ())
        return DecisionResponse(
            decision_id=uuid4(),
            local_date=source.local_date,
            status_code="COMPLETED",
            safety_status_code="BLOCKED",
            action_code=action.value,
            requested_duration_minutes=envelope.requested_duration_minutes,
            duration_adjustment_source_code=str(
                source.normalized_values["duration_adjustment_source_code"]
            ),
            final_plan=None,
            options=[
                DecisionOptionResponse(
                    option_id=option_id,
                    option_code="REST",
                    action_code="REST",
                )
            ],
            reason_codes=reasons[:2] or [action.value],
            summary=guidance.message,
            guidance=guidance,
            safety_summary=SafetySummary(
                safety_status_code="BLOCKED",
                vetoed=True,
                reason_codes=reasons,
                summary=guidance.message,
            ),
            generation_mode_code="ORIGINAL",
            decision_engine_code="DETERMINISTIC",
            regeneration_sequence=0,
            created_at=self._clock(),
        )

    def project_success(
        self, *, source: V3CreationSource, bundle: V3DecisionPersistenceBundle
    ) -> DecisionResponse:
        plan = bundle.final_plan
        if plan is None:
            raise RuntimeError("V3_FINAL_PLAN_MISSING")
        plan_id = uuid5(NAMESPACE_URL, f"v3-plan:{bundle.decision_execution_id}")
        context = _context(source)
        names = {
            **context.exercise_names,
            **{item.exercise_id: item.display_name for item in context.assembly.items},
        }
        items = []
        for compiled in plan.exercises:
            prescription = compiled.prescription
            # Repetition-based exercises previously reported zero work seconds
            # because only work_seconds_per_set was read. The shared timing rules
            # convert repetitions through the catalog seconds-per-rep basis.
            timing = prescription_item_duration(prescription, compiled.catalog_record)
            work = timing.work_seconds
            rest = timing.rest_seconds
            item_id = uuid5(
                NAMESPACE_URL,
                f"v3-plan-item:{bundle.decision_execution_id}:{prescription.sequence}",
            )
            items.append(
                DecisionPlanItem(
                    plan_item_id=item_id,
                    exercise_id=prescription.exercise_id,
                    exercise_name=names.get(
                        prescription.exercise_id, compiled.catalog_record.stable_code
                    ),
                    sequence=prescription.sequence,
                    tier_code=compiled.catalog_record.difficulty_code,
                    sets=prescription.sets,
                    reps=prescription.repetitions_per_set,
                    work_seconds=work,
                    rest_seconds=rest,
                    transition_seconds=timing.transition_seconds,
                    estimated_item_seconds=timing.estimated_item_seconds,
                    instruction_available=bool(compiled.catalog_record.content_version),
                )
            )
        first = plan.exercises[0].catalog_record
        evaluation = context.safety_evaluation
        safety_code: Literal["PASS", "REVISE", "BLOCKED"] = (
            "REVISE" if evaluation and evaluation.status_code is SafetyStatusCode.REVISE else "PASS"
        )
        reason_codes = list(bundle.failure_codes[:2]) or ["V3_COMPLETED"]
        return DecisionResponse(
            decision_id=bundle.decision_execution_id,
            local_date=source.local_date,
            status_code="COMPLETED",
            safety_status_code=safety_code,
            action_code=plan.action_code.value,
            requested_duration_minutes=plan.requested_duration_minutes,
            duration_adjustment_source_code=str(
                source.normalized_values["duration_adjustment_source_code"]
            ),
            final_plan=DecisionPlan(
                plan_id=plan_id,
                action_code=plan.action_code.value,
                training_type_code=first.training_type_code,
                body_focus_code=first.body_focus_code,
                requested_duration_minutes=plan.requested_duration_minutes,
                estimated_duration_seconds=plan.estimated_duration_seconds,
                estimated_calories_burned=None,
                setup_seconds=0,
                warmup_seconds=0,
                cooldown_seconds=0,
                items=items,
            ),
            options=[
                DecisionOptionResponse(
                    option_id=uuid5(
                        NAMESPACE_URL, f"v3-option:final:{bundle.decision_execution_id}"
                    ),
                    option_code="FINAL_ROUTINE",
                    action_code=plan.action_code.value,
                    plan_id=plan_id,
                ),
                DecisionOptionResponse(
                    option_id=uuid5(
                        NAMESPACE_URL, f"v3-option:rest:{bundle.decision_execution_id}"
                    ),
                    option_code="REST",
                    action_code="REST",
                ),
            ],
            reason_codes=reason_codes,
            summary="오늘의 안전한 운동 루틴이 준비되었습니다.",
            safety_summary=SafetySummary(
                safety_status_code=safety_code,
                vetoed=False,
                reason_codes=list(evaluation.reason_codes if evaluation else ()),
                summary="결정적 안전 정책 검증을 통과했습니다.",
            ),
            generation_mode_code="ORIGINAL",
            decision_engine_code=(
                "DETERMINISTIC_FALLBACK" if bundle.fallback_used else "LLM_MULTI_AGENT"
            ),
            root_decision_id=bundle.root_decision_execution_id,
            regeneration_sequence=0,
            created_at=self._clock(),
        )


class FailClosedV3ApplicationFallback:
    """Runtime owns the deterministic fallback; never fabricate a bundle here."""

    def create(self, *, root_snapshot: object, failure_code: str) -> V3DecisionPersistenceBundle:
        del root_snapshot, failure_code
        raise DecisionFailedError


def _policy(session: Session, version: str) -> DecisionPolicyVersion:
    result = session.scalar(
        select(DecisionPolicyVersion).where(DecisionPolicyVersion.version_code == version)
    )
    if result is None:
        raise RuntimeError("V3_POLICY_VERSION_NOT_INSTALLED")
    return result


def _persist_public_decision(
    session: Session,
    *,
    user_id: UUID,
    assembly: DecisionAssembly,
    response: DecisionResponse,
    decision_id: UUID,
    bundle: V3DecisionPersistenceBundle | None,
) -> tuple[DecisionRun, PlanCandidate]:
    now = response.created_at
    policy_version = bundle.policy_version if bundle is not None else DECISION_POLICY_VERSION
    policy = _policy(session, policy_version)
    snapshot = assembly.context.snapshot()
    input_hash = _hash(snapshot)
    run = DecisionRun(
        id=decision_id,
        user_id=user_id,
        local_date=response.local_date,
        daily_context_id=assembly.context.daily_context_id,
        daily_context_version=assembly.context.context_version,
        base_routine_id=assembly.routine_id,
        input_schema_version=DECISION_INPUT_SCHEMA_VERSION,
        input_snapshot=snapshot,
        input_hash=input_hash,
        catalog_version_id=assembly.catalog_version_id,
        policy_version_id=policy.id,
        safety_rule_version=(
            bundle.root_snapshot.constraint_envelope.safety_rule_version
            if bundle
            else _safety_rule_version(assembly)
        ),
        duration_rule_version=DURATION_RULE_VERSION,
        graph_version=bundle.graph_version if bundle else "v3-safety-terminal-v1",
        coordinator_version=bundle.graph_version if bundle else "v3-safety-policy-v1",
        status_code="COMPLETED",
        safety_status_code=response.safety_status_code,
        recommended_action_code=response.action_code,
        coordinator_result={"reason_codes": response.reason_codes},
        failure_code=None,
        created_at=now,
        completed_at=now,
    )
    session.add(run)
    plan_response = response.final_plan
    if plan_response is None:
        base = assembly.items[0]
        candidate = PlanCandidate(
            id=uuid5(NAMESPACE_URL, f"v3-terminal-plan:{decision_id}"),
            decision_run_id=decision_id,
            candidate_code="SAFETY_TERMINAL",
            action_code="KEEP",
            training_type_code=str(assembly.candidate_data["training_type_code"]),
            body_focus_code=cast(str | None, assembly.candidate_data.get("body_focus_code")),
            requested_duration_minutes=assembly.context.requested_duration_minutes,
            duration_adjustment_source_code=assembly.context.duration_adjustment_source_code,
            estimated_duration_seconds=assembly.context.requested_duration_minutes * 60,
            estimated_calories_burned=None,
            setup_seconds=0,
            warmup_seconds=0,
            cooldown_seconds=0,
            goal_tags=[assembly.context.primary_goal_code],
            duration_rule_version=DURATION_RULE_VERSION,
            selected=False,
            created_at=now,
        )
        session.add(candidate)
        session.flush()
        session.add(
            PlanItem(
                id=uuid4(),
                plan_candidate_id=candidate.id,
                **{name: getattr(base, name) for name in base.__dataclass_fields__},
            )
        )
    else:
        candidate = PlanCandidate(
            id=plan_response.plan_id,
            decision_run_id=decision_id,
            candidate_code=(
                bundle.final_plan.compiled_plan_hash if bundle and bundle.final_plan else "FINAL"
            ),
            action_code=plan_response.action_code,
            training_type_code=plan_response.training_type_code,
            body_focus_code=plan_response.body_focus_code,
            requested_duration_minutes=plan_response.requested_duration_minutes,
            duration_adjustment_source_code=response.duration_adjustment_source_code,
            estimated_duration_seconds=plan_response.estimated_duration_seconds,
            estimated_calories_burned=plan_response.estimated_calories_burned,
            setup_seconds=plan_response.setup_seconds,
            warmup_seconds=plan_response.warmup_seconds,
            cooldown_seconds=plan_response.cooldown_seconds,
            goal_tags=[assembly.context.primary_goal_code],
            duration_rule_version=DURATION_RULE_VERSION,
            selected=True,
            created_at=now,
        )
        session.add(candidate)
        session.flush()
        catalog = {
            row.id: row
            for row in session.scalars(
                select(Exercise).where(
                    Exercise.id.in_([item.exercise_id for item in plan_response.items])
                )
            )
        }
        compiled_by_id = (
            {item.prescription.exercise_id: item for item in bundle.final_plan.exercises}
            if bundle and bundle.final_plan
            else {}
        )
        for item in plan_response.items:
            exercise = catalog[item.exercise_id]
            prescription = compiled_by_id[item.exercise_id].prescription
            session.add(
                PlanItem(
                    id=item.plan_item_id,
                    plan_candidate_id=candidate.id,
                    exercise_id=item.exercise_id,
                    sequence=item.sequence,
                    phase_code="MAIN",
                    tier_code=item.tier_code,
                    sets=item.sets,
                    reps=item.reps,
                    work_seconds_per_set=prescription.work_seconds_per_set,
                    rest_seconds_per_set=prescription.rest_seconds_between_sets,
                    work_seconds=item.work_seconds,
                    rest_seconds=item.rest_seconds,
                    transition_seconds=item.transition_seconds,
                    intensity_code=prescription.intensity_code,
                    instruction_content_version=exercise.instruction_content_version,
                    display_name=exercise.name_ko,
                )
            )
    session.flush()
    evaluation_status = response.safety_status_code
    session.add(
        SafetyReview(
            id=uuid4(),
            decision_run_id=run.id,
            plan_candidate_id=candidate.id,
            safety_status_code=evaluation_status,
            vetoed=evaluation_status == "BLOCKED",
            ruleset_version=run.safety_rule_version,
            reason_codes=response.safety_summary.reason_codes if response.safety_summary else [],
            excluded_exercise_ids=[],
            public_guidance=response.guidance.code if response.guidance else None,
        )
    )
    session.add(
        DecisionExplanationRecord(
            id=uuid4(),
            decision_run_id=run.id,
            source_code="TEMPLATE",
            summary=response.summary,
            reason_codes=response.reason_codes,
            agent_summaries=[],
            safety_summary=(
                response.safety_summary.model_dump(mode="json") if response.safety_summary else {}
            ),
            final_adjustment_reason=None,
            coaching_style_code=assembly.coaching_style_code,
            template_version=_TEMPLATE_VERSION,
            prompt_version=None,
            model_code=None,
            fallback_reason_code=(
                "V3_DETERMINISTIC_FALLBACK" if bundle and bundle.fallback_used else "V3_TEMPLATE"
            ),
            created_at=now,
        )
    )
    for index, option in enumerate(response.options, start=1):
        session.add(
            DecisionOption(
                id=option.option_id,
                decision_run_id=run.id,
                option_code=option.option_code,
                action_code=option.action_code,
                plan_candidate_id=option.plan_id,
                display_order=index,
                selectable=option.selectable,
                blocked_reason_code=option.blocked_reason_code,
            )
        )
    session.flush()
    return run, candidate


def resolve_vector_index_registry_id(
    session: Session, retrieval_result: ExerciseRetrievalResult
) -> UUID | None:
    """Resolve the registry row a succeeded retrieval used, or None for a fallback.

    The repository refuses to persist a root artifact whose retrieval says the
    vector index was used but carries no registry ID, because such a decision
    cannot be reproduced from its stored inputs. Resolution goes through the
    immutable index version named in the result rather than through whichever
    row is ACTIVE now, which may have moved since the request started.
    """

    if (
        retrieval_result.retrieval_status_code != RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
        or retrieval_result.fallback_used
        or retrieval_result.vector_index_version is None
    ):
        return None
    registry = VectorIndexRepository().get_by_version(
        session, retrieval_result.vector_index_version
    )
    if registry is None:
        raise RuntimeError("V3_VECTOR_INDEX_REGISTRY_MISSING")
    return registry.id


def _persist_v3_bundle(
    session: Session,
    run: DecisionRun,
    candidate: PlanCandidate,
    bundle: V3DecisionPersistenceBundle,
) -> None:
    invocations = tuple(
        V3InvocationSqlMetadata(
            provider_code="OPENAI" if not bundle.fallback_used else "DETERMINISTIC",
            model_code=item.model_version,
            attempt_number=0,
            invocation_status_code="SUCCEEDED",
            latency_ms=0,
        )
        for item in bundle.agent_proposals
    )
    candidate_ids = tuple(
        (
            candidate.id
            if item.compiled_plan_candidate is not None
            and bundle.final_plan is not None
            and item.compiled_plan_candidate.compiled_plan_hash
            == bundle.final_plan.compiled_plan_hash
            else None
        )
        for item in bundle.validations
    )
    metadata = V3SqlPersistenceMetadata(
        now=run.created_at,
        root_snapshot_expires_at=run.created_at + _SNAPSHOT_TTL,
        proposal_invocations=invocations,
        coordinator_provider_code="OPENAI" if not bundle.fallback_used else "DETERMINISTIC",
        plan_candidate_ids=candidate_ids,
        vector_index_registry_id=resolve_vector_index_registry_id(
            session, bundle.root_snapshot.retrieval_result
        ),
    )
    V3SqlAlchemyPersistenceAdapter(session, lambda _session, _bundle: metadata).add(bundle)


class SqlAlchemyV3RegenerationRepository:
    def __init__(
        self,
        session: Session,
        *,
        current_versions: V3RegenerationVersionSnapshot,
    ) -> None:
        self._session = session
        self._current_versions = current_versions
        self._locked_run: DecisionRun | None = None

    def lock_regeneration_source(
        self, *, user_id: UUID, decision_id: UUID
    ) -> V3StoredRegenerationSource | None:
        run = self._session.scalar(
            select(DecisionRun)
            .where(DecisionRun.id == decision_id, DecisionRun.user_id == user_id)
            .with_for_update()
        )
        if run is None or run.root_decision_run_id is None:
            return None
        bundle = V3SqlAlchemyPersistenceAdapter(self._session, _unused_metadata_provider).get(
            run.id
        )
        if bundle is None or bundle.final_plan is None:
            return None
        root_envelope = self._session.scalar(
            select(DecisionConstraintEnvelopeRecord).where(
                DecisionConstraintEnvelopeRecord.root_decision_run_id == run.root_decision_run_id
            )
        )
        if root_envelope is None:
            return None
        count = self._session.scalar(
            select(func.count(DecisionRun.id)).where(
                DecisionRun.root_decision_run_id == run.root_decision_run_id,
                DecisionRun.generation_mode_code == "REGENERATED",
                DecisionRun.status_code == "COMPLETED",
            )
        )
        plan = self._session.scalar(
            select(PlanCandidate).where(
                PlanCandidate.decision_run_id == run.id,
                PlanCandidate.selected.is_(True),
            )
        )
        if plan is None:
            return None
        self._locked_run = run
        return V3StoredRegenerationSource(
            decision_id=run.id,
            root_decision_id=run.root_decision_run_id,
            parent_decision_id=run.parent_decision_run_id,
            plan_id=plan.id,
            regeneration_sequence=run.regeneration_sequence or 0,
            successful_regeneration_count=int(count or 0),
            generation_mode_code=cast(Literal["ORIGINAL", "REGENERATED"], run.generation_mode_code),
            decision_engine_code=V3DecisionEngineCode(
                run.decision_engine_code or "DETERMINISTIC_FALLBACK"
            ),
            terminal_status_code=GraphTerminalStatusCode.COMPLETED,
            root_snapshot=bundle.root_snapshot,
            final_plan=bundle.final_plan,
            snapshot_expires_at=root_envelope.expires_at,
            versions=V3RegenerationVersionSnapshot(
                catalog_version=bundle.catalog_version,
                policy_version=bundle.policy_version,
                safety_rule_version=bundle.root_snapshot.constraint_envelope.safety_rule_version,
            ),
        )

    def get_idempotency_result(
        self, *, user_id: UUID, idempotency_key: UUID
    ) -> V3RegenerationIdempotencyRecord | None:
        record = self._session.scalar(
            select(MutationIdempotencyRecord).where(
                MutationIdempotencyRecord.user_id == user_id,
                MutationIdempotencyRecord.endpoint_code == "POST_DECISIONS",
                MutationIdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        if record is None:
            return None
        payload = record.response_payload.get("v3_regeneration_result")
        if not isinstance(payload, dict):
            raise V3IdempotencyKeyReusedError
        return V3RegenerationIdempotencyRecord(
            request_hash=record.request_hash,
            result=V3RegenerationResult.model_validate(payload),
        )

    def persist_regeneration(
        self,
        *,
        bundle: V3DecisionPersistenceBundle,
        result: V3RegenerationResult,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
    ) -> None:
        parent = self._locked_run
        if parent is None:
            raise RuntimeError("V3_REGENERATION_SOURCE_NOT_LOCKED")
        legacy = DecisionRepository()
        assembly = legacy.assemble(self._session, user_id, parent.daily_context_id)
        if assembly is None:
            raise RuntimeError("V3_REGENERATION_SOURCE_UNAVAILABLE")
        source = V3CreationSource(
            local_date=parent.local_date,
            context_version=parent.daily_context_version,
            normalized_values={
                "duration_adjustment_source_code": parent.input_snapshot[
                    "duration_adjustment_source_code"
                ]
            },
            application_context=V3ApplicationContext(assembly, ()),
        )
        response = V3DecisionResponseProjector().project_success(source=source, bundle=bundle)
        run, candidate = _persist_public_decision(
            self._session,
            user_id=user_id,
            assembly=assembly,
            response=response,
            decision_id=bundle.decision_execution_id,
            bundle=bundle,
        )
        _persist_v3_bundle(self._session, run, candidate, bundle)
        self._session.add(
            MutationIdempotencyRecord(
                id=uuid4(),
                user_id=user_id,
                endpoint_code="POST_DECISIONS",
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_payload={"v3_regeneration_result": result.model_dump(mode="json")},
                response_schema_version="v3-regeneration-result-v1",
                created_at=datetime.now(UTC),
            )
        )
        self._session.flush()


def _unused_metadata_provider(
    session: Session, bundle: V3DecisionPersistenceBundle
) -> V3SqlPersistenceMetadata:
    del session, bundle
    raise RuntimeError("V3_METADATA_PROVIDER_NOT_USED_FOR_READ")


class SqlAlchemyV3RegenerationUnitOfWork:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        current_versions: V3RegenerationVersionSnapshot,
    ) -> None:
        self._session_factory = session_factory
        self._current_versions = current_versions
        self._state: ContextVar[tuple[Session, Any, SqlAlchemyV3RegenerationRepository] | None] = (
            ContextVar("v3_regeneration_uow_state", default=None)
        )

    @property
    def decisions(self) -> SqlAlchemyV3RegenerationRepository:
        state = self._state.get()
        if state is None:
            raise RuntimeError("V3_REGENERATION_UOW_NOT_ENTERED")
        return state[2]

    def __enter__(self) -> Self:
        if self._state.get() is not None:
            raise RuntimeError("V3_REGENERATION_UOW_ALREADY_ENTERED")
        session = self._session_factory()
        transaction = session.begin()
        transaction.__enter__()
        repository = SqlAlchemyV3RegenerationRepository(
            session, current_versions=self._current_versions
        )
        self._state.set((session, transaction, repository))
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool | None:
        state = self._state.get()
        if state is None:
            raise RuntimeError("V3_REGENERATION_UOW_NOT_ENTERED")
        session, transaction, _repository = state
        try:
            return transaction.__exit__(exc_type, exc, traceback)
        finally:
            self._state.set(None)
            session.close()


__all__ = [
    "DeterministicV3SafetyPolicyAdapter",
    "FailClosedV3ApplicationFallback",
    "PostgreSQLV3ExercisePoolSource",
    "SqlAlchemyV3CreationRepository",
    "SqlAlchemyV3CreationUnitOfWork",
    "SqlAlchemyV3RegenerationRepository",
    "SqlAlchemyV3RegenerationUnitOfWork",
    "V3ApplicationContext",
    "V3DecisionResponseProjector",
]
