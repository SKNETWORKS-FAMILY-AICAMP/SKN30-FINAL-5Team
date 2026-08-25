"""SQLAlchemy adapter for the framework-independent V3 persistence bundle.

The domain bundle deliberately has no ORM metadata. Values that cannot be
truthfully derived (provider latency, expiry and relational candidate IDs) are
required as explicit mapper metadata instead of being guessed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.db.models.decision import DecisionRun
from backend.app.db.repositories.v3_decision import (
    AgentProposalWrite,
    ConstraintEnvelopeWrite,
    CoordinationAttemptWrite,
    ExercisePoolWrite,
    ExerciseRetrievalWrite,
    IntegrityValidationWrite,
    RootArtifactsWrite,
    V3DecisionRepository,
)
from backend.app.domain.agents.v3_persistence import (
    V3DecisionPersistenceBundle,
    V3RootSnapshotPersistence,
)


def _hash(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class V3InvocationSqlMetadata:
    provider_code: str
    model_code: str
    attempt_number: int
    invocation_status_code: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class V3SqlPersistenceMetadata:
    now: datetime
    root_snapshot_expires_at: datetime
    proposal_invocations: tuple[V3InvocationSqlMetadata, ...]
    coordinator_provider_code: str
    plan_candidate_ids: tuple[UUID | None, ...]
    vector_index_registry_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.now.tzinfo is None or self.root_snapshot_expires_at.tzinfo is None:
            raise ValueError("V3 SQL persistence timestamps must include timezone")
        if len(self.proposal_invocations) != 3:
            raise ValueError("exactly three specialist invocation records are required")


class V3PersistenceSqlMapper:
    """Validated one-way mapping into the existing B1 repository DTOs."""

    def map_root(
        self,
        bundle: V3DecisionPersistenceBundle,
        run: DecisionRun,
        metadata: V3SqlPersistenceMetadata,
    ) -> RootArtifactsWrite:
        snapshot = bundle.root_snapshot
        envelope = snapshot.constraint_envelope
        pool = snapshot.exercise_pool
        request = snapshot.retrieval_request
        result = snapshot.retrieval_result
        retrieval_metadata = pool.retrieval_metadata
        return RootArtifactsWrite(
            envelope=ConstraintEnvelopeWrite(
                input_hash=run.input_hash,
                envelope_schema_version=envelope.schema_version,
                safety_policy_version=envelope.policy_version,
                policy_version_id=run.policy_version_id,
                safety_rule_version=envelope.safety_rule_version,
                duration_rule_version=run.duration_rule_version,
                plan_generation_allowed=envelope.plan_generation_allowed,
                required_action_code=(
                    envelope.safety_required_action_code.value
                    if envelope.safety_required_action_code is not None
                    else None
                ),
                veto=not envelope.plan_generation_allowed,
                envelope_payload=envelope.model_dump(mode="json"),
                envelope_hash=envelope.envelope_hash,
                expires_at=metadata.root_snapshot_expires_at,
            ),
            pool=ExercisePoolWrite(
                catalog_version_id=run.catalog_version_id,
                pool_schema_version=pool.schema_version,
                filter_codes=tuple(sorted(request.normalized_query_codes)),
                constraint_envelope_hash=pool.constraint_envelope_hash,
                exercise_payload=tuple(item.model_dump(mode="json") for item in pool.exercises),
                mandatory_exercise_ids=pool.mandatory_exercise_ids,
                vector_ranked_exercise_ids=pool.vector_ranked_exercise_ids,
                retrieval_metadata=retrieval_metadata.model_dump(mode="json"),
                pool_hash=pool.pool_hash,
            ),
            retrieval=ExerciseRetrievalWrite(
                vector_index_registry_id=metadata.vector_index_registry_id,
                request_schema_version=request.schema_version,
                request_hash=_hash(request.model_dump(mode="json")),
                eligible_exercise_ids_hash=_hash(
                    [str(value) for value in request.eligible_exercise_ids]
                ),
                mandatory_exercise_ids_hash=_hash(
                    [str(value) for value in request.mandatory_exercise_ids]
                ),
                normalized_query_codes_hash=_hash(request.normalized_query_codes),
                retrieval_mode_code=request.retrieval_mode.value,
                requested_limit=request.requested_limit,
                result_schema_version=result.schema_version,
                collection_name=result.collection_name,
                vector_index_version=result.vector_index_version,
                embedding_model_version=result.embedding_model_version,
                query_hash=result.query_hash,
                retrieval_status_code=result.retrieval_status_code.value,
                retrieval_failure_codes=tuple(
                    code.value for code in retrieval_metadata.retrieval_failure_codes
                ),
                returned_ranked_ids_and_scores=tuple(
                    {"exercise_id": str(exercise_id), "score": score}
                    for exercise_id, score in zip(
                        result.ranked_exercise_ids,
                        result.similarity_scores,
                        strict=True,
                    )
                ),
                revalidated_ranked_exercise_ids=pool.vector_ranked_exercise_ids,
                fallback_used=result.fallback_used,
                fallback_policy_version=retrieval_metadata.deterministic_fallback_version,
                retrieval_latency_ms=None,
                result_hash=_hash(result.model_dump(mode="json")),
            ),
        )

    def map_proposals(
        self,
        bundle: V3DecisionPersistenceBundle,
        metadata: V3SqlPersistenceMetadata,
    ) -> tuple[AgentProposalWrite, ...]:
        if any(
            item.model_version != invocation.model_code
            for item, invocation in zip(
                bundle.agent_proposals, metadata.proposal_invocations, strict=True
            )
        ):
            raise ValueError("invocation metadata model must match the persisted proposal")
        return tuple(
            AgentProposalWrite(
                agent_type_code=item.agent_type_code.value,
                proposal_status_code=item.proposal.proposal_status_code.value,
                proposal_schema_version=item.proposal.schema_version,
                proposal_payload=item.proposal.model_dump(mode="json"),
                proposal_hash=item.proposal.proposal_hash,
                invocation_metadata_schema_version="llm-invocation-metadata-v1",
                prompt_version=item.prompt_version,
                provider_code=invocation.provider_code,
                model_code=invocation.model_code,
                output_schema_version=item.proposal.schema_version,
                attempt_number=invocation.attempt_number,
                invocation_status_code=invocation.invocation_status_code,
                latency_ms=invocation.latency_ms,
            )
            for item, invocation in zip(
                bundle.agent_proposals, metadata.proposal_invocations, strict=True
            )
        )

    def map_coordination(
        self,
        bundle: V3DecisionPersistenceBundle,
        metadata: V3SqlPersistenceMetadata,
    ) -> tuple[CoordinationAttemptWrite, ...]:
        proposal_hashes = tuple(item.proposal.proposal_hash for item in bundle.agent_proposals)
        return tuple(
            CoordinationAttemptWrite(
                attempt_number=item.attempt_number,
                status_code="READY" if item.plan_spec is not None else "FAILED",
                input_hash=_hash(
                    {
                        "envelope_hash": bundle.root_snapshot.constraint_envelope.envelope_hash,
                        "pool_hash": bundle.root_snapshot.exercise_pool.pool_hash,
                        "proposal_hashes": proposal_hashes,
                        "repair_codes": item.repair_codes,
                    }
                ),
                coordinator_schema_version="plan-spec-v1",
                model_provider_code=metadata.coordinator_provider_code,
                model_code=item.model_version,
                prompt_version=item.prompt_version,
                plan_spec=(item.plan_spec.model_dump(mode="json") if item.plan_spec else None),
                output_hash=item.plan_spec.plan_hash if item.plan_spec else None,
                repair_violation_codes=(item.repair_codes or None),
                failure_code=None if item.plan_spec else "COORDINATOR_FAILED",
            )
            for item in bundle.coordinator_attempts
        )

    def map_validations(
        self,
        bundle: V3DecisionPersistenceBundle,
        metadata: V3SqlPersistenceMetadata,
    ) -> tuple[IntegrityValidationWrite, ...]:
        if len(metadata.plan_candidate_ids) != len(bundle.validations):
            raise ValueError("candidate IDs must align with validation attempts")
        return tuple(
            IntegrityValidationWrite(
                coordination_attempt_number=item.attempt_number,
                plan_candidate_id=candidate_id,
                compiler_version=(
                    item.compiled_plan_candidate.compiler_version
                    if item.compiled_plan_candidate is not None
                    else "v3-plan-compiler-v1"
                ),
                validator_version=item.integrity_validation.validator_version,
                status_code=item.integrity_validation.status_code.value,
                violation_codes=tuple(
                    violation.code.value for violation in item.integrity_validation.violations
                ),
                meaningful_difference_codes=(
                    tuple(code.value for code in item.meaningful_difference.difference_codes)
                    if item.meaningful_difference is not None
                    else None
                ),
                validation_hash=_hash(item.model_dump(mode="json")),
            )
            for item, candidate_id in zip(
                bundle.validations, metadata.plan_candidate_ids, strict=True
            )
        )


class V3SqlAlchemyPersistenceAdapter:
    """Implements the B1 persistence Protocol without committing per graph node."""

    def __init__(
        self,
        session: Session,
        metadata_provider: Callable[
            [Session, V3DecisionPersistenceBundle], V3SqlPersistenceMetadata
        ],
        *,
        repository: V3DecisionRepository | None = None,
        mapper: V3PersistenceSqlMapper | None = None,
    ) -> None:
        self._session = session
        self._metadata_provider = metadata_provider
        self._repository = repository or V3DecisionRepository()
        self._mapper = mapper or V3PersistenceSqlMapper()

    def add(self, bundle: V3DecisionPersistenceBundle) -> None:
        session = self._session
        run = session.get(DecisionRun, bundle.decision_execution_id)
        if run is None:
            raise ValueError("the caller transaction must create the decision run first")
        metadata = self._metadata_provider(session, bundle)
        root = session.get(DecisionRun, bundle.root_decision_execution_id)
        if root is None:
            raise ValueError("V3 root decision run does not exist")
        if bundle.decision_execution_id == bundle.root_decision_execution_id:
            sequence = 0
            mode = "ORIGINAL"
        else:
            if bundle.parent_decision_execution_id is None:
                raise ValueError("regeneration requires a parent decision")
            parent = session.get(DecisionRun, bundle.parent_decision_execution_id)
            if parent is None or parent.regeneration_sequence is None:
                raise ValueError("regeneration parent is not a persisted V3 run")
            sequence = parent.regeneration_sequence + 1
            mode = "REGENERATED"
        self._repository.configure_lineage(
            session,
            decision_run_id=run.id,
            root_decision_run_id=root.id,
            parent_decision_run_id=bundle.parent_decision_execution_id,
            generation_mode_code=mode,
            regeneration_sequence=sequence,
            decision_engine_code=(
                "DETERMINISTIC_FALLBACK" if bundle.fallback_used else "LLM_MULTI_AGENT"
            ),
            langchain_contract_version="v3-langchain-contract-v1",
            langgraph_contract_version=bundle.graph_version,
        )
        if mode == "ORIGINAL":
            self._repository.save_root_artifacts(
                session,
                root_decision_run_id=root.id,
                artifacts=self._mapper.map_root(bundle, run, metadata),
                now=metadata.now,
            )
        else:
            stored = self.get_root_snapshot(root.id)
            if stored != bundle.root_snapshot:
                raise ValueError("regeneration changed immutable root artifacts")
        self._repository.save_agent_proposals(
            session,
            decision_run_id=run.id,
            proposals=self._mapper.map_proposals(bundle, metadata),
            now=metadata.now,
        )
        for attempt in self._mapper.map_coordination(bundle, metadata):
            self._repository.save_coordination_attempt(
                session, decision_run_id=run.id, attempt=attempt, now=metadata.now
            )
        for validation in self._mapper.map_validations(bundle, metadata):
            self._repository.save_integrity_validation(
                session, decision_run_id=run.id, validation=validation, now=metadata.now
            )
        coordinator_result = dict(run.coordinator_result)
        coordinator_result["v3_persistence_bundle"] = bundle.model_dump(mode="json")
        run.coordinator_result = coordinator_result
        session.flush()

    def get(self, decision_execution_id: UUID) -> V3DecisionPersistenceBundle | None:
        run = self._session.get(DecisionRun, decision_execution_id)
        if run is None:
            return None
        payload = run.coordinator_result.get("v3_persistence_bundle")
        if not isinstance(payload, dict):
            return None
        return V3DecisionPersistenceBundle.model_validate(payload)

    def get_root_snapshot(
        self, root_decision_execution_id: UUID
    ) -> V3RootSnapshotPersistence | None:
        bundle = self.get(root_decision_execution_id)
        return bundle.root_snapshot if bundle is not None else None


class V3SqlAlchemyUnitOfWork:
    """One SQLAlchemy transaction for the complete immutable audit bundle."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        metadata_provider: Callable[
            [Session, V3DecisionPersistenceBundle], V3SqlPersistenceMetadata
        ],
    ) -> None:
        self._session_factory = session_factory
        self._metadata_provider = metadata_provider
        self._session: Session | None = None
        self._transaction: Any = None
        self.repository: V3SqlAlchemyPersistenceAdapter

    def __enter__(self) -> V3SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self._transaction = self._session.begin()
        self._transaction.__enter__()
        self.repository = V3SqlAlchemyPersistenceAdapter(self._session, self._metadata_provider)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool | None:
        assert self._session is not None
        try:
            return self._transaction.__exit__(exc_type, exc, traceback)
        finally:
            self._session.close()


__all__ = [
    "V3InvocationSqlMetadata",
    "V3PersistenceSqlMapper",
    "V3SqlAlchemyPersistenceAdapter",
    "V3SqlAlchemyUnitOfWork",
    "V3SqlPersistenceMetadata",
]
