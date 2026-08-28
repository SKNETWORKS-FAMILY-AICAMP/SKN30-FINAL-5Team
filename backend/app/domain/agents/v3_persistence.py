"""Framework-independent persistence and replay contracts for V3 decisions."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.domain.agents.retrieval import (
    ExercisePoolSnapshot,
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
)
from backend.app.domain.agents.v3_compiler import CompiledPlan
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    PlanSpec,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
    _canonical_codes,
    _canonical_hash,
    _hash_value,
)
from backend.app.domain.agents.v3_orchestration import (
    GraphTerminalStatusCode,
    RegenerationDifferenceResult,
    TerminalResult,
    V3GraphResult,
)
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationResult,
    IntegrityValidationStatusCode,
)

PERSISTENCE_BUNDLE_SCHEMA_VERSION: Final[Literal["v3-decision-persistence-bundle-v1"]] = (
    "v3-decision-persistence-bundle-v1"
)
REPLAY_RESULT_SCHEMA_VERSION: Final[Literal["v3-replay-result-v1"]] = "v3-replay-result-v1"


class V3PersistenceFailureCode(StrEnum):
    PERSISTENCE_CONTRACT_INVALID = "PERSISTENCE_CONTRACT_INVALID"
    AUDIT_ARTIFACT_INCOMPLETE = "AUDIT_ARTIFACT_INCOMPLETE"
    UNSUPPORTED_SCHEMA_VERSION = "UNSUPPORTED_SCHEMA_VERSION"
    CANONICAL_HASH_MISMATCH = "CANONICAL_HASH_MISMATCH"
    DUPLICATE_DECISION_EXECUTION = "DUPLICATE_DECISION_EXECUTION"
    TRANSACTION_FAILED = "TRANSACTION_FAILED"
    ROOT_SNAPSHOT_MISSING = "ROOT_SNAPSHOT_MISSING"
    INVALID_FINAL_LINKAGE = "INVALID_FINAL_LINKAGE"


class V3PersistenceError(RuntimeError):
    def __init__(self, code: V3PersistenceFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class V3RootSnapshotPersistence(_FrozenModel):
    constraint_envelope: ConstraintEnvelope
    exercise_pool: ExercisePoolSnapshot
    retrieval_request: ExerciseRetrievalRequest
    retrieval_result: ExerciseRetrievalResult

    @model_validator(mode="after")
    def validate_lineage(self) -> Self:
        if self.exercise_pool.constraint_envelope_hash != self.constraint_envelope.envelope_hash:
            raise ValueError("pool does not reference the persisted envelope")
        if (
            self.retrieval_request.constraint_envelope_hash
            != self.constraint_envelope.envelope_hash
        ):
            raise ValueError("retrieval request does not reference the persisted envelope")
        if self.retrieval_request.catalog_version != self.exercise_pool.catalog_version:
            raise ValueError("retrieval request and pool catalog versions differ")
        self.retrieval_result.validate_against(self.retrieval_request)
        metadata = self.exercise_pool.retrieval_metadata
        result = self.retrieval_result
        if (
            metadata.query_hash != result.query_hash
            or metadata.retrieval_status_code is not result.retrieval_status_code
            or metadata.deterministic_pool_fallback_used != result.fallback_used
            or metadata.collection_name != result.collection_name
            or metadata.vector_index_version != result.vector_index_version
            or metadata.embedding_model_version != result.embedding_model_version
        ):
            raise ValueError("retrieval result and persisted pool metadata differ")
        return self


class V3AgentProposalPersistence(_FrozenModel):
    agent_type_code: SpecialistAgentTypeCode
    proposal: SpecialistAgentProposal
    prompt_version: str
    model_version: str

    @model_validator(mode="after")
    def validate_role(self) -> Self:
        if self.proposal.agent_type_code is not self.agent_type_code:
            raise ValueError("proposal role mismatch")
        _canonical_codes((self.prompt_version,), field_name="prompt version")
        _canonical_codes((self.model_version,), field_name="model version")
        return self


class V3CoordinatorAttemptPersistence(_FrozenModel):
    attempt_number: int = Field(ge=0, le=1)
    plan_spec: PlanSpec | None
    repair_codes: tuple[str, ...] = ()
    prompt_version: str
    model_version: str

    @model_validator(mode="after")
    def validate_attempt(self) -> Self:
        _canonical_codes(self.repair_codes, field_name="repair codes")
        if (self.attempt_number == 0) != (not self.repair_codes):
            raise ValueError("only repair attempt 1 may contain repair codes")
        return self


class V3ValidationPersistence(_FrozenModel):
    attempt_number: int = Field(ge=0, le=1)
    compiled_plan_candidate: CompiledPlan | None
    integrity_validation: IntegrityValidationResult
    meaningful_difference: RegenerationDifferenceResult | None = None

    @model_validator(mode="after")
    def validate_attempt(self) -> Self:
        if self.integrity_validation.repair_attempt != self.attempt_number:
            raise ValueError("validation attempt number mismatch")
        compiled_hash = (
            self.compiled_plan_candidate.compiled_plan_hash
            if self.compiled_plan_candidate is not None
            else None
        )
        if self.integrity_validation.compiled_plan_hash != compiled_hash:
            raise ValueError("validation does not reference its compiled candidate")
        return self


class V3DecisionPersistenceBundle(_FrozenModel):
    schema_version: Literal["v3-decision-persistence-bundle-v1"] = PERSISTENCE_BUNDLE_SCHEMA_VERSION
    decision_execution_id: UUID
    root_decision_execution_id: UUID
    parent_decision_execution_id: UUID | None = None
    graph_version: str
    policy_version: str
    prompt_version: str
    model_version: str
    catalog_version: str
    root_snapshot: V3RootSnapshotPersistence
    agent_proposals: tuple[V3AgentProposalPersistence, ...]
    coordinator_attempts: tuple[V3CoordinatorAttemptPersistence, ...]
    validations: tuple[V3ValidationPersistence, ...]
    fallback_used: bool
    fallback_version: str | None
    terminal_status_code: GraphTerminalStatusCode
    terminal_result: TerminalResult | None
    final_plan: CompiledPlan | None
    failure_codes: tuple[str, ...] = ()
    canonical_result_hash: str

    @field_validator("canonical_result_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="canonical result hash")

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        roles = tuple(item.agent_type_code for item in self.agent_proposals)
        expected = tuple(SpecialistAgentTypeCode)
        completed = self.terminal_status_code is GraphTerminalStatusCode.COMPLETED
        if completed and not self.fallback_used and roles != expected:
            raise ValueError("exactly three canonically ordered specialist proposals are required")
        if (not completed or self.fallback_used) and roles != tuple(
            role for role in expected if role in set(roles)
        ):
            raise ValueError("partial proposal artifacts must use canonical role order")
        if self.catalog_version != self.root_snapshot.exercise_pool.catalog_version:
            raise ValueError("bundle catalog version mismatch")
        if self.fallback_used != (self.fallback_version is not None):
            raise ValueError("fallback use requires a fallback version")
        attempts = tuple(item.attempt_number for item in self.coordinator_attempts)
        validations = tuple(item.attempt_number for item in self.validations)
        allowed_attempts = ((0,), (0, 1)) if completed else ((), (0,), (0, 1))
        if attempts not in allowed_attempts or validations != attempts:
            raise ValueError("coordinator and validation attempts must be aligned and bounded")
        if self.final_plan is not None:
            final_validation = self.validations[-1].integrity_validation
            envelope = self.root_snapshot.constraint_envelope
            if (
                self.terminal_status_code is not GraphTerminalStatusCode.COMPLETED
                or final_validation.status_code is not IntegrityValidationStatusCode.PASS
                or final_validation.compiled_plan_hash != self.final_plan.compiled_plan_hash
                or not envelope.plan_generation_allowed
                or envelope.safety_required_action_code is not None
                or self.terminal_result is not None
            ):
                raise ValueError("invalid final linkage")
        elif self.terminal_status_code is GraphTerminalStatusCode.COMPLETED:
            raise ValueError("COMPLETED requires a validated final plan")
        expected_hash = _canonical_hash(
            self.model_dump(mode="json", exclude={"canonical_result_hash"})
        )
        if self.canonical_result_hash != expected_hash:
            raise ValueError("canonical result hash mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": PERSISTENCE_BUNDLE_SCHEMA_VERSION, **values}
        payload["canonical_result_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


class V3ReplayResult(_FrozenModel):
    schema_version: Literal["v3-replay-result-v1"] = REPLAY_RESULT_SCHEMA_VERSION
    decision_execution_id: UUID
    terminal_status_code: GraphTerminalStatusCode
    final_plan: CompiledPlan | None
    failure_codes: tuple[str, ...]
    graph_version: str
    policy_version: str
    prompt_version: str
    model_version: str
    catalog_version: str
    canonical_result_hash: str


def map_v3_graph_result_to_persistence_bundle(
    graph_result: V3GraphResult,
    *,
    decision_execution_id: UUID,
    root_decision_execution_id: UUID,
    root_snapshot: V3RootSnapshotPersistence,
    coordinator_attempts: tuple[V3CoordinatorAttemptPersistence, ...],
    validations: tuple[V3ValidationPersistence, ...],
    policy_version: str,
    prompt_version: str,
    model_version: str,
    parent_decision_execution_id: UUID | None = None,
    failure_codes: tuple[str, ...] = (),
) -> V3DecisionPersistenceBundle:
    """Map a canonical graph result plus explicit retrieval artifacts; never reconstruct them."""

    if graph_result.envelope_hash != root_snapshot.constraint_envelope.envelope_hash:
        raise V3PersistenceError(V3PersistenceFailureCode.CANONICAL_HASH_MISMATCH)
    if graph_result.pool_hash != root_snapshot.exercise_pool.pool_hash:
        raise V3PersistenceError(V3PersistenceFailureCode.CANONICAL_HASH_MISMATCH)
    if graph_result.final_plan is not None:
        if not validations:
            raise V3PersistenceError(V3PersistenceFailureCode.INVALID_FINAL_LINKAGE)
        final_validation = validations[-1].integrity_validation
        if (
            graph_result.terminal_status_code is not GraphTerminalStatusCode.COMPLETED
            or final_validation.status_code is not IntegrityValidationStatusCode.PASS
            or final_validation.compiled_plan_hash != graph_result.final_plan.compiled_plan_hash
            or not root_snapshot.constraint_envelope.plan_generation_allowed
            or root_snapshot.constraint_envelope.safety_required_action_code is not None
        ):
            raise V3PersistenceError(V3PersistenceFailureCode.INVALID_FINAL_LINKAGE)
    elif graph_result.terminal_status_code is GraphTerminalStatusCode.COMPLETED:
        raise V3PersistenceError(V3PersistenceFailureCode.INVALID_FINAL_LINKAGE)
    proposals = tuple(
        V3AgentProposalPersistence(
            agent_type_code=item.agent_type_code,
            proposal=item,
            prompt_version=prompt_version,
            model_version=model_version,
        )
        for item in graph_result.round_one_proposals
    )
    try:
        return V3DecisionPersistenceBundle.create(
            decision_execution_id=decision_execution_id,
            root_decision_execution_id=root_decision_execution_id,
            parent_decision_execution_id=parent_decision_execution_id,
            graph_version=graph_result.graph_version,
            policy_version=policy_version,
            prompt_version=prompt_version,
            model_version=model_version,
            catalog_version=root_snapshot.exercise_pool.catalog_version,
            root_snapshot=root_snapshot,
            agent_proposals=proposals,
            coordinator_attempts=coordinator_attempts,
            validations=validations,
            fallback_used=graph_result.fallback_used,
            fallback_version=graph_result.fallback_version,
            terminal_status_code=graph_result.terminal_status_code,
            terminal_result=graph_result.terminal_result,
            final_plan=graph_result.final_plan,
            failure_codes=_canonical_codes(failure_codes, field_name="failure codes"),
        )
    except ValueError as exc:
        raise V3PersistenceError(V3PersistenceFailureCode.AUDIT_ARTIFACT_INCOMPLETE) from exc


__all__ = [
    "V3AgentProposalPersistence",
    "V3CoordinatorAttemptPersistence",
    "V3DecisionPersistenceBundle",
    "V3PersistenceError",
    "V3PersistenceFailureCode",
    "V3ReplayResult",
    "V3RootSnapshotPersistence",
    "V3ValidationPersistence",
    "map_v3_graph_result_to_persistence_bundle",
]
