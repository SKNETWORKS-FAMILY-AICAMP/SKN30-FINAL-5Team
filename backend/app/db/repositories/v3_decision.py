"""Persistence boundary for immutable V3 decision artifacts.

The write DTOs contain only framework-independent Python values. This module
does not accept LangGraph state or provider SDK objects and never reconstructs
retrieval artifacts from an ExercisePoolSnapshot.
"""

from copy import deepcopy
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.decision import AgentProposalRecord, DecisionRun, PlanCandidate
from backend.app.db.models.v3_decision import (
    DecisionConstraintEnvelopeRecord,
    DecisionCoordinationAttemptRecord,
    DecisionExercisePoolRecord,
    DecisionExerciseRetrievalRecord,
    PlanIntegrityValidationRecord,
)

_SPECIALIST_ROLES = ("TRAINING", "RECOVERY", "FEASIBILITY")
_HASH_LENGTH = 64
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "api_key",
        "calendar",
        "calendar_data",
        "chain_of_thought",
        "date",
        "date_of_birth",
        "email",
        "embedding_query",
        "exception",
        "full_name",
        "health",
        "intensity_score",
        "name",
        "pain",
        "pain_area",
        "pain_areas",
        "pain_intensity_score",
        "prompt",
        "prompt_text",
        "provider_exception",
        "provider_response",
        "query_text",
        "raw_health",
        "raw_response",
        "raw_wearable",
        "reasoning",
        "severity",
        "token",
        "user_id",
        "wearable",
        "wearable_data",
    }
)


class V3PersistenceConflictError(ValueError):
    """A retry reused an immutable identity with different content."""


@dataclass(frozen=True)
class ConstraintEnvelopeWrite:
    input_hash: str
    envelope_schema_version: str
    safety_policy_version: str
    policy_version_id: UUID
    safety_rule_version: str
    duration_rule_version: str
    plan_generation_allowed: bool
    required_action_code: str | None
    veto: bool
    envelope_payload: dict[str, Any]
    envelope_hash: str
    expires_at: datetime


@dataclass(frozen=True)
class ExercisePoolWrite:
    catalog_version_id: UUID
    pool_schema_version: str
    filter_codes: tuple[str, ...]
    constraint_envelope_hash: str
    exercise_payload: tuple[dict[str, Any], ...]
    mandatory_exercise_ids: tuple[UUID, ...]
    vector_ranked_exercise_ids: tuple[UUID, ...]
    retrieval_metadata: dict[str, Any]
    pool_hash: str


@dataclass(frozen=True)
class ExerciseRetrievalWrite:
    vector_index_registry_id: UUID | None
    request_schema_version: str
    request_hash: str
    eligible_exercise_ids_hash: str
    mandatory_exercise_ids_hash: str
    normalized_query_codes_hash: str
    retrieval_mode_code: str
    requested_limit: int
    result_schema_version: str
    collection_name: str | None
    vector_index_version: str | None
    embedding_model_version: str | None
    query_hash: str
    retrieval_status_code: str
    retrieval_failure_codes: tuple[str, ...]
    returned_ranked_ids_and_scores: tuple[dict[str, Any], ...]
    revalidated_ranked_exercise_ids: tuple[UUID, ...]
    fallback_used: bool
    fallback_policy_version: str | None
    retrieval_latency_ms: int | None
    result_hash: str


@dataclass(frozen=True)
class RootArtifactsWrite:
    envelope: ConstraintEnvelopeWrite
    pool: ExercisePoolWrite
    retrieval: ExerciseRetrievalWrite


@dataclass(frozen=True)
class RootArtifactIds:
    envelope_id: UUID
    pool_id: UUID
    retrieval_id: UUID


@dataclass(frozen=True)
class AgentProposalWrite:
    agent_type_code: str
    proposal_status_code: str
    proposal_schema_version: str
    proposal_payload: dict[str, Any]
    proposal_hash: str
    invocation_metadata_schema_version: str
    prompt_version: str
    provider_code: str
    model_code: str
    output_schema_version: str
    attempt_number: int
    invocation_status_code: str
    latency_ms: int


@dataclass(frozen=True)
class CoordinationAttemptWrite:
    attempt_number: int
    status_code: str
    input_hash: str
    coordinator_schema_version: str
    model_provider_code: str
    model_code: str
    prompt_version: str
    plan_spec: dict[str, Any] | None
    output_hash: str | None
    repair_violation_codes: tuple[str, ...] | None
    failure_code: str | None


@dataclass(frozen=True)
class IntegrityValidationWrite:
    coordination_attempt_number: int
    plan_candidate_id: UUID | None
    compiler_version: str
    validator_version: str
    status_code: str
    violation_codes: tuple[str, ...]
    meaningful_difference_codes: tuple[str, ...] | None
    validation_hash: str


@dataclass(frozen=True)
class V3AuditBundle:
    decision_run_id: UUID
    root_decision_run_id: UUID
    envelope: dict[str, Any]
    pool: dict[str, Any]
    retrieval: dict[str, Any]
    proposals: tuple[dict[str, Any], ...]
    coordination_attempts: tuple[dict[str, Any], ...]
    integrity_validations: tuple[dict[str, Any], ...]


def _validate_hash(value: str | None, field_name: str) -> None:
    if (
        value is None
        or len(value) != _HASH_LENGTH
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256")


def _validate_canonical_codes(values: tuple[str, ...], field_name: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be unique and canonical")


def _validate_unique_codes(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


def _validate_payload(payload: object, *, path: str) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized = key.lower()
            if normalized in _FORBIDDEN_PAYLOAD_KEYS:
                raise ValueError(f"{path} contains forbidden field: {key}")
            _validate_payload(value, path=f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            _validate_payload(value, path=f"{path}[{index}]")


def _record_payload(record: Any, excluded: frozenset[str] = frozenset()) -> dict[str, Any]:
    return {
        field.name: deepcopy(getattr(record, field.name))
        for field in fields(record)
        if field.name not in excluded
    }


class V3DecisionRepository:
    """Store validated V3 artifacts without committing the caller transaction."""

    def configure_lineage(
        self,
        session: Session,
        *,
        decision_run_id: UUID,
        root_decision_run_id: UUID,
        parent_decision_run_id: UUID | None,
        generation_mode_code: str,
        regeneration_sequence: int,
        decision_engine_code: str,
        langchain_contract_version: str,
        langgraph_contract_version: str,
    ) -> None:
        run = self._require_run(session, decision_run_id)
        root = self._require_run(session, root_decision_run_id)
        if run.user_id != root.user_id:
            raise ValueError("root decision run must belong to the same user")
        if generation_mode_code == "ORIGINAL":
            if decision_run_id != root_decision_run_id or parent_decision_run_id is not None:
                raise ValueError("ORIGINAL lineage must point to itself without a parent")
            if regeneration_sequence != 0:
                raise ValueError("ORIGINAL lineage sequence must be 0")
        elif generation_mode_code == "REGENERATED":
            if regeneration_sequence not in (1, 2) or parent_decision_run_id is None:
                raise ValueError("REGENERATED lineage requires sequence 1 or 2 and a parent")
            parent = self._require_run(session, parent_decision_run_id)
            if parent.user_id != run.user_id or parent.root_decision_run_id != root_decision_run_id:
                raise ValueError("regeneration parent must belong to the same root lineage")
        else:
            raise ValueError("unsupported generation mode")
        values = {
            "root_decision_run_id": root_decision_run_id,
            "parent_decision_run_id": parent_decision_run_id,
            "generation_mode_code": generation_mode_code,
            "regeneration_sequence": regeneration_sequence,
            "decision_engine_code": decision_engine_code,
            "langchain_contract_version": langchain_contract_version,
            "langgraph_contract_version": langgraph_contract_version,
        }
        populated = run.root_decision_run_id is not None
        if populated and any(getattr(run, key) != value for key, value in values.items()):
            raise V3PersistenceConflictError(
                "decision lineage already exists with different values"
            )
        for key, value in values.items():
            setattr(run, key, value)
        session.flush()

    def save_root_artifacts(
        self,
        session: Session,
        *,
        root_decision_run_id: UUID,
        artifacts: RootArtifactsWrite,
        now: datetime,
    ) -> RootArtifactIds:
        root = self._require_run(session, root_decision_run_id)
        if root.root_decision_run_id != root.id or root.generation_mode_code != "ORIGINAL":
            raise ValueError("root artifacts require configured ORIGINAL V3 lineage")
        self._validate_root_artifacts(root, artifacts)
        existing = session.scalar(
            select(DecisionConstraintEnvelopeRecord).where(
                DecisionConstraintEnvelopeRecord.root_decision_run_id == root_decision_run_id
            )
        )
        if existing is not None:
            return self._match_existing_root(session, existing, artifacts)

        with session.begin_nested():
            envelope = DecisionConstraintEnvelopeRecord(
                id=uuid4(),
                root_decision_run_id=root_decision_run_id,
                created_at=now,
                **_record_payload(artifacts.envelope),
            )
            session.add(envelope)
            session.flush()
            pool_values = _record_payload(artifacts.pool)
            pool_values["filter_codes"] = list(artifacts.pool.filter_codes)
            pool_values["exercise_payload"] = deepcopy(list(artifacts.pool.exercise_payload))
            pool_values["mandatory_exercise_ids"] = [
                str(value) for value in artifacts.pool.mandatory_exercise_ids
            ]
            pool_values["vector_ranked_exercise_ids"] = [
                str(value) for value in artifacts.pool.vector_ranked_exercise_ids
            ]
            pool_values["exercise_count"] = len(artifacts.pool.exercise_payload)
            pool = DecisionExercisePoolRecord(
                id=uuid4(),
                constraint_envelope_id=envelope.id,
                created_at=now,
                **pool_values,
            )
            session.add(pool)
            session.flush()
            retrieval_values = _record_payload(artifacts.retrieval)
            retrieval_values["retrieval_failure_codes"] = list(
                artifacts.retrieval.retrieval_failure_codes
            )
            retrieval_values["returned_ranked_ids_and_scores"] = deepcopy(
                list(artifacts.retrieval.returned_ranked_ids_and_scores)
            )
            retrieval_values["revalidated_ranked_exercise_ids"] = [
                str(value) for value in artifacts.retrieval.revalidated_ranked_exercise_ids
            ]
            retrieval = DecisionExerciseRetrievalRecord(
                id=uuid4(),
                constraint_envelope_id=envelope.id,
                exercise_pool_id=pool.id,
                created_at=now,
                **retrieval_values,
            )
            session.add(retrieval)
            session.flush()
        return RootArtifactIds(envelope.id, pool.id, retrieval.id)

    def save_agent_proposals(
        self,
        session: Session,
        *,
        decision_run_id: UUID,
        proposals: tuple[AgentProposalWrite, ...],
        now: datetime,
    ) -> tuple[UUID, ...]:
        run = self._require_v3_run(session, decision_run_id)
        roles = tuple(item.agent_type_code for item in proposals)
        if roles != tuple(role for role in _SPECIALIST_ROLES if role in set(roles)):
            raise ValueError("V3 proposals must use canonical specialist order")
        for proposal in proposals:
            self._validate_proposal(proposal)
        existing = tuple(
            session.scalars(
                select(AgentProposalRecord)
                .where(AgentProposalRecord.decision_run_id == run.id)
                .order_by(AgentProposalRecord.agent_type_code)
            )
        )
        if existing:
            by_role = {item.agent_type_code: item for item in existing}
            if set(by_role) != set(_SPECIALIST_ROLES):
                raise V3PersistenceConflictError("decision run contains a non-V3 proposal set")
            for write in proposals:
                record = by_role[write.agent_type_code]
                if record.proposal_hash != write.proposal_hash:
                    raise V3PersistenceConflictError("proposal retry changed immutable output")
            return tuple(by_role[role].id for role in _SPECIALIST_ROLES)
        with session.begin_nested():
            records = [
                AgentProposalRecord(
                    id=uuid4(),
                    decision_run_id=run.id,
                    agent_type_code=item.agent_type_code,
                    proposal_status_code=item.proposal_status_code,
                    schema_version=item.proposal_schema_version,
                    proposal_payload=deepcopy(item.proposal_payload),
                    invocation_metadata_schema_version=item.invocation_metadata_schema_version,
                    proposal_hash=item.proposal_hash,
                    prompt_version=item.prompt_version,
                    provider_code=item.provider_code,
                    model_code=item.model_code,
                    output_schema_version=item.output_schema_version,
                    attempt_number=item.attempt_number,
                    invocation_status_code=item.invocation_status_code,
                    latency_ms=item.latency_ms,
                    created_at=now,
                )
                for item in proposals
            ]
            session.add_all(records)
            session.flush()
        return tuple(record.id for record in records)

    def save_coordination_attempt(
        self,
        session: Session,
        *,
        decision_run_id: UUID,
        attempt: CoordinationAttemptWrite,
        now: datetime,
    ) -> UUID:
        self._require_v3_run(session, decision_run_id)
        self._validate_coordination_attempt(attempt)
        existing = session.scalar(
            select(DecisionCoordinationAttemptRecord).where(
                DecisionCoordinationAttemptRecord.decision_run_id == decision_run_id,
                DecisionCoordinationAttemptRecord.attempt_number == attempt.attempt_number,
            )
        )
        if existing is not None:
            if (
                existing.input_hash != attempt.input_hash
                or existing.output_hash != attempt.output_hash
            ):
                raise V3PersistenceConflictError("coordination retry changed immutable hashes")
            return existing.id
        if (
            attempt.attempt_number == 1
            and session.scalar(
                select(DecisionCoordinationAttemptRecord.id).where(
                    DecisionCoordinationAttemptRecord.decision_run_id == decision_run_id,
                    DecisionCoordinationAttemptRecord.attempt_number == 0,
                )
            )
            is None
        ):
            raise ValueError("repair attempt requires an initial coordination attempt")
        record = DecisionCoordinationAttemptRecord(
            id=uuid4(),
            decision_run_id=decision_run_id,
            repair_violation_codes=(
                list(attempt.repair_violation_codes)
                if attempt.repair_violation_codes is not None
                else None
            ),
            plan_spec=deepcopy(attempt.plan_spec),
            created_at=now,
            **_record_payload(attempt, frozenset({"repair_violation_codes", "plan_spec"})),
        )
        session.add(record)
        session.flush()
        return record.id

    def save_integrity_validation(
        self,
        session: Session,
        *,
        decision_run_id: UUID,
        validation: IntegrityValidationWrite,
        now: datetime,
    ) -> UUID:
        self._require_v3_run(session, decision_run_id)
        self._validate_integrity(validation)
        attempt = session.scalar(
            select(DecisionCoordinationAttemptRecord).where(
                DecisionCoordinationAttemptRecord.decision_run_id == decision_run_id,
                DecisionCoordinationAttemptRecord.attempt_number
                == validation.coordination_attempt_number,
            )
        )
        if attempt is None:
            raise ValueError("integrity validation requires its coordination attempt")
        if validation.plan_candidate_id is not None:
            candidate = session.get(PlanCandidate, validation.plan_candidate_id)
            if candidate is None or candidate.decision_run_id != decision_run_id:
                raise ValueError("plan candidate must belong to the validated decision run")
        existing = session.scalar(
            select(PlanIntegrityValidationRecord).where(
                PlanIntegrityValidationRecord.coordination_attempt_id == attempt.id
            )
        )
        if existing is not None:
            if existing.validation_hash != validation.validation_hash:
                raise V3PersistenceConflictError("validation retry changed immutable output")
            return existing.id
        record = PlanIntegrityValidationRecord(
            id=uuid4(),
            decision_run_id=decision_run_id,
            coordination_attempt_id=attempt.id,
            violation_codes=list(validation.violation_codes),
            meaningful_difference_codes=(
                list(validation.meaningful_difference_codes)
                if validation.meaningful_difference_codes is not None
                else None
            ),
            created_at=now,
            **_record_payload(
                validation,
                frozenset({"violation_codes", "meaningful_difference_codes"}),
            ),
        )
        session.add(record)
        session.flush()
        return record.id

    def get_audit_bundle(self, session: Session, decision_run_id: UUID) -> V3AuditBundle:
        run = self._require_v3_run(session, decision_run_id)
        root_id = run.root_decision_run_id
        if root_id is None:
            raise ValueError("V3 run is missing root lineage")
        envelope = session.scalar(
            select(DecisionConstraintEnvelopeRecord).where(
                DecisionConstraintEnvelopeRecord.root_decision_run_id == root_id
            )
        )
        if envelope is None:
            raise ValueError("root constraint envelope does not exist")
        pool = session.scalar(
            select(DecisionExercisePoolRecord).where(
                DecisionExercisePoolRecord.constraint_envelope_id == envelope.id
            )
        )
        if pool is None:
            raise ValueError("root exercise pool does not exist")
        retrieval = session.scalar(
            select(DecisionExerciseRetrievalRecord).where(
                DecisionExerciseRetrievalRecord.exercise_pool_id == pool.id
            )
        )
        if retrieval is None:
            raise ValueError("root exercise retrieval does not exist")
        proposal_rows = tuple(
            session.scalars(
                select(AgentProposalRecord).where(
                    AgentProposalRecord.decision_run_id == decision_run_id
                )
            )
        )
        proposals_by_role = {item.agent_type_code: item for item in proposal_rows}
        proposals = tuple(
            proposals_by_role[role] for role in _SPECIALIST_ROLES if role in proposals_by_role
        )
        attempts = tuple(
            session.scalars(
                select(DecisionCoordinationAttemptRecord)
                .where(DecisionCoordinationAttemptRecord.decision_run_id == decision_run_id)
                .order_by(DecisionCoordinationAttemptRecord.attempt_number)
            )
        )
        validations = tuple(
            session.scalars(
                select(PlanIntegrityValidationRecord)
                .where(PlanIntegrityValidationRecord.decision_run_id == decision_run_id)
                .order_by(PlanIntegrityValidationRecord.coordination_attempt_number)
            )
        )
        return V3AuditBundle(
            decision_run_id=decision_run_id,
            root_decision_run_id=root_id,
            envelope=self._envelope_payload(envelope),
            pool=self._pool_payload(pool),
            retrieval=self._retrieval_payload(retrieval),
            proposals=tuple(self._proposal_payload(item) for item in proposals),
            coordination_attempts=tuple(self._coordination_payload(item) for item in attempts),
            integrity_validations=tuple(self._validation_payload(item) for item in validations),
        )

    @staticmethod
    def _require_run(session: Session, decision_run_id: UUID) -> DecisionRun:
        run = session.get(DecisionRun, decision_run_id)
        if run is None:
            raise ValueError("decision run does not exist")
        return run

    def _require_v3_run(self, session: Session, decision_run_id: UUID) -> DecisionRun:
        run = self._require_run(session, decision_run_id)
        if run.root_decision_run_id is None or run.generation_mode_code is None:
            raise ValueError("decision run is not configured for V3 persistence")
        return run

    @staticmethod
    def _validate_root_artifacts(root: DecisionRun, artifacts: RootArtifactsWrite) -> None:
        envelope, pool, retrieval = artifacts.envelope, artifacts.pool, artifacts.retrieval
        for value, name in (
            (envelope.input_hash, "input_hash"),
            (envelope.envelope_hash, "envelope_hash"),
            (pool.constraint_envelope_hash, "constraint_envelope_hash"),
            (pool.pool_hash, "pool_hash"),
            (retrieval.request_hash, "request_hash"),
            (retrieval.eligible_exercise_ids_hash, "eligible_exercise_ids_hash"),
            (retrieval.mandatory_exercise_ids_hash, "mandatory_exercise_ids_hash"),
            (retrieval.normalized_query_codes_hash, "normalized_query_codes_hash"),
            (retrieval.query_hash, "query_hash"),
            (retrieval.result_hash, "result_hash"),
        ):
            _validate_hash(value, name)
        if (
            root.input_hash != envelope.input_hash
            or root.policy_version_id != envelope.policy_version_id
        ):
            raise ValueError("root run and envelope lineage do not match")
        if root.catalog_version_id != pool.catalog_version_id:
            raise ValueError("root run and exercise pool catalog do not match")
        if pool.constraint_envelope_hash != envelope.envelope_hash:
            raise ValueError("exercise pool envelope hash does not match")
        if len(pool.exercise_payload) != len(
            {str(item.get("exercise_id")) for item in pool.exercise_payload}
        ):
            raise ValueError("exercise payload must contain unique exercise IDs")
        pool_ids = {str(item.get("exercise_id")) for item in pool.exercise_payload}
        if not {str(value) for value in pool.mandatory_exercise_ids}.issubset(pool_ids):
            raise ValueError("mandatory exercise IDs must be present in the pool")
        _validate_canonical_codes(pool.filter_codes, "filter_codes")
        _validate_unique_codes(retrieval.retrieval_failure_codes, "retrieval_failure_codes")
        if retrieval.requested_limit <= 0:
            raise ValueError("requested_limit must be positive")
        if retrieval.retrieval_latency_ms is not None and retrieval.retrieval_latency_ms < 0:
            raise ValueError("retrieval_latency_ms must be non-negative")
        succeeded = retrieval.retrieval_status_code == "VECTOR_RETRIEVAL_SUCCEEDED"
        if envelope.envelope_schema_version != "constraint-envelope-v3":
            raise ValueError("unsupported envelope schema version")
        if pool.pool_schema_version != "exercise-pool-snapshot-v3":
            raise ValueError("unsupported pool schema version")
        if (
            retrieval.request_schema_version != "exercise-retrieval-request-v1"
            or retrieval.result_schema_version != "exercise-retrieval-result-v1"
        ):
            raise ValueError("unsupported retrieval schema version")
        vector_versions = (
            retrieval.collection_name,
            retrieval.vector_index_version,
            retrieval.embedding_model_version,
            retrieval.vector_index_registry_id,
        )
        if succeeded and (
            retrieval.fallback_used or any(value is None for value in vector_versions)
        ):
            raise ValueError("successful retrieval requires index lineage without fallback")
        if not succeeded and (
            not retrieval.fallback_used or retrieval.fallback_policy_version is None
        ):
            raise ValueError("failed retrieval requires deterministic fallback lineage")
        if (
            not succeeded
            and retrieval.retrieval_status_code not in retrieval.retrieval_failure_codes
        ):
            raise ValueError("failed retrieval must retain its primary failure code")
        _validate_payload(envelope.envelope_payload, path="envelope_payload")
        _validate_payload(pool.exercise_payload, path="exercise_payload")
        _validate_payload(pool.retrieval_metadata, path="retrieval_metadata")
        _validate_payload(
            retrieval.returned_ranked_ids_and_scores,
            path="returned_ranked_ids_and_scores",
        )

    @staticmethod
    def _validate_proposal(proposal: AgentProposalWrite) -> None:
        _validate_hash(proposal.proposal_hash, "proposal_hash")
        if proposal.agent_type_code not in _SPECIALIST_ROLES:
            raise ValueError("V3 proposal role is invalid")
        if proposal.attempt_number not in (0, 1) or proposal.latency_ms < 0:
            raise ValueError("invocation attempt/latency is invalid")
        if proposal.invocation_status_code not in {
            "SUCCEEDED",
            "FAILED",
            "TIMEOUT",
            "INVALID_OUTPUT",
        }:
            raise ValueError("invocation status is invalid")
        _validate_payload(proposal.proposal_payload, path="proposal_payload")

    @staticmethod
    def _validate_coordination_attempt(attempt: CoordinationAttemptWrite) -> None:
        _validate_hash(attempt.input_hash, "coordination input_hash")
        if attempt.output_hash is not None:
            _validate_hash(attempt.output_hash, "coordination output_hash")
        if attempt.attempt_number not in (0, 1):
            raise ValueError("coordination attempt must be 0 or 1")
        if (attempt.attempt_number == 1) != (attempt.repair_violation_codes is not None):
            raise ValueError("only repair attempt 1 carries violation codes")
        if attempt.status_code == "READY":
            if (
                attempt.plan_spec is None
                or attempt.output_hash is None
                or attempt.failure_code is not None
            ):
                raise ValueError("READY coordination requires a PlanSpec and output hash")
        elif attempt.status_code == "FAILED":
            if (
                attempt.plan_spec is not None
                or attempt.output_hash is not None
                or not attempt.failure_code
            ):
                raise ValueError("FAILED coordination requires only a fixed failure code")
        else:
            raise ValueError("unsupported coordination status")
        _validate_payload(attempt.plan_spec, path="plan_spec")

    @staticmethod
    def _validate_integrity(validation: IntegrityValidationWrite) -> None:
        _validate_hash(validation.validation_hash, "validation_hash")
        if validation.coordination_attempt_number not in (0, 1):
            raise ValueError("validation attempt must be 0 or 1")
        if validation.status_code not in {"PASS", "REPAIRABLE", "FAILED"}:
            raise ValueError("unsupported validation status")
        if validation.status_code == "PASS" and (
            validation.plan_candidate_id is None or validation.violation_codes
        ):
            raise ValueError("PASS validation requires a candidate and no violations")
        if validation.status_code != "PASS" and not validation.violation_codes:
            raise ValueError("non-PASS validation requires violation codes")
        _validate_unique_codes(validation.violation_codes, "violation_codes")
        if validation.meaningful_difference_codes is not None:
            _validate_unique_codes(
                validation.meaningful_difference_codes, "meaningful_difference_codes"
            )

    @staticmethod
    def _match_existing_root(
        session: Session,
        envelope: DecisionConstraintEnvelopeRecord,
        artifacts: RootArtifactsWrite,
    ) -> RootArtifactIds:
        pool = session.scalar(
            select(DecisionExercisePoolRecord).where(
                DecisionExercisePoolRecord.constraint_envelope_id == envelope.id
            )
        )
        retrieval = (
            None
            if pool is None
            else session.scalar(
                select(DecisionExerciseRetrievalRecord).where(
                    DecisionExerciseRetrievalRecord.exercise_pool_id == pool.id
                )
            )
        )
        if pool is None or retrieval is None:
            raise V3PersistenceConflictError("root artifact graph is incomplete")
        if (
            envelope.envelope_hash != artifacts.envelope.envelope_hash
            or pool.pool_hash != artifacts.pool.pool_hash
            or retrieval.request_hash != artifacts.retrieval.request_hash
            or retrieval.result_hash != artifacts.retrieval.result_hash
        ):
            raise V3PersistenceConflictError("root artifact retry changed immutable hashes")
        return RootArtifactIds(envelope.id, pool.id, retrieval.id)

    @staticmethod
    def _envelope_payload(record: DecisionConstraintEnvelopeRecord) -> dict[str, Any]:
        return {
            "schema_version": record.envelope_schema_version,
            "input_hash": record.input_hash,
            "envelope_hash": record.envelope_hash,
            "payload": deepcopy(record.envelope_payload),
            "expires_at": record.expires_at,
        }

    @staticmethod
    def _pool_payload(record: DecisionExercisePoolRecord) -> dict[str, Any]:
        return {
            "schema_version": record.pool_schema_version,
            "constraint_envelope_hash": record.constraint_envelope_hash,
            "pool_hash": record.pool_hash,
            "exercises": deepcopy(record.exercise_payload),
            "mandatory_exercise_ids": list(record.mandatory_exercise_ids),
            "vector_ranked_exercise_ids": list(record.vector_ranked_exercise_ids),
            "retrieval_metadata": deepcopy(record.retrieval_metadata),
        }

    @staticmethod
    def _retrieval_payload(record: DecisionExerciseRetrievalRecord) -> dict[str, Any]:
        return {
            "request_schema_version": record.request_schema_version,
            "request_hash": record.request_hash,
            "result_schema_version": record.result_schema_version,
            "result_hash": record.result_hash,
            "retrieval_status_code": record.retrieval_status_code,
            "retrieval_failure_codes": list(record.retrieval_failure_codes),
            "returned_ranked_ids_and_scores": deepcopy(record.returned_ranked_ids_and_scores),
            "revalidated_ranked_exercise_ids": list(record.revalidated_ranked_exercise_ids),
            "fallback_used": record.fallback_used,
        }

    @staticmethod
    def _proposal_payload(record: AgentProposalRecord) -> dict[str, Any]:
        return {
            "agent_type_code": record.agent_type_code,
            "proposal_schema_version": record.schema_version,
            "proposal_hash": record.proposal_hash,
            "proposal": deepcopy(record.proposal_payload),
            "prompt_version": record.prompt_version,
            "provider_code": record.provider_code,
            "model_code": record.model_code,
            "output_schema_version": record.output_schema_version,
            "attempt_number": record.attempt_number,
            "invocation_status_code": record.invocation_status_code,
            "latency_ms": record.latency_ms,
        }

    @staticmethod
    def _coordination_payload(record: DecisionCoordinationAttemptRecord) -> dict[str, Any]:
        return {
            "attempt_number": record.attempt_number,
            "status_code": record.status_code,
            "input_hash": record.input_hash,
            "plan_spec": deepcopy(record.plan_spec),
            "output_hash": record.output_hash,
            "repair_violation_codes": deepcopy(record.repair_violation_codes),
            "failure_code": record.failure_code,
        }

    @staticmethod
    def _validation_payload(record: PlanIntegrityValidationRecord) -> dict[str, Any]:
        return {
            "coordination_attempt_number": record.coordination_attempt_number,
            "plan_candidate_id": record.plan_candidate_id,
            "compiler_version": record.compiler_version,
            "validator_version": record.validator_version,
            "status_code": record.status_code,
            "violation_codes": list(record.violation_codes),
            "meaningful_difference_codes": deepcopy(record.meaningful_difference_codes),
            "validation_hash": record.validation_hash,
        }


__all__ = [
    "AgentProposalWrite",
    "ConstraintEnvelopeWrite",
    "CoordinationAttemptWrite",
    "ExercisePoolWrite",
    "ExerciseRetrievalWrite",
    "IntegrityValidationWrite",
    "RootArtifactIds",
    "RootArtifactsWrite",
    "V3AuditBundle",
    "V3DecisionRepository",
    "V3PersistenceConflictError",
]
