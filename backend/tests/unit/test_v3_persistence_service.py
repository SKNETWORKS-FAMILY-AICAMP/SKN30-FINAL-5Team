from __future__ import annotations

from copy import copy
from uuid import UUID, uuid4

import pytest

from backend.app.domain.agents.retrieval import (
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    RetrievalModeCode,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_compiler import compile_plan
from backend.app.domain.agents.v3_conflicts import detect_proposal_conflicts
from backend.app.domain.agents.v3_orchestration import GraphTerminalStatusCode, V3GraphResult
from backend.app.domain.agents.v3_persistence import (
    V3CoordinatorAttemptPersistence,
    V3DecisionPersistenceBundle,
    V3PersistenceError,
    V3PersistenceFailureCode,
    V3RootSnapshotPersistence,
    V3ValidationPersistence,
    map_v3_graph_result_to_persistence_bundle,
)
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationContext,
    validate_plan_integrity,
)
from backend.app.modules.decisions.v3_persistence import V3DecisionPersistenceService
from backend.tests.unit.test_v3_agent_contracts import B, envelope, pool
from backend.tests.unit.test_v3_coordinator_contracts import coordinator_input, plan, proposals

COMPILER_VERSION = "plan-compiler-v1"
VALIDATOR_VERSION = "integrity-validator-v1"


def make_bundle() -> V3DecisionPersistenceBundle:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_proposals = proposals(current_envelope, current_pool)
    conflicts = detect_proposal_conflicts(current_proposals, current_envelope, current_pool)
    current_input = coordinator_input(current_envelope, current_pool)
    current_plan = plan(current_input)
    compiled = compile_plan(
        current_plan,
        envelope=current_envelope,
        pool=current_pool,
        compiler_version=COMPILER_VERSION,
        coordinator_input=current_input,
    )
    validation = validate_plan_integrity(
        compiled,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=IntegrityValidationContext(approved_safe_alternative_ids=(B,)),
    )
    graph_result = V3GraphResult.create(
        graph_version="v3-orchestration-domain-v1",
        terminal_status_code=GraphTerminalStatusCode.COMPLETED,
        envelope_hash=current_envelope.envelope_hash,
        pool_hash=current_pool.pool_hash,
        round_one_proposals=current_proposals,
        conflict_codes=(),
        review_target_agent_types=(),
        review_results=(),
        coordinator_initial_plan=current_plan,
        compiled_plan=compiled,
        integrity_violation_codes=(),
        final_plan=compiled,
    )
    exercise_ids = tuple(item.exercise_id for item in current_pool.exercises)
    request = ExerciseRetrievalRequest(
        catalog_version=current_pool.catalog_version,
        constraint_envelope_hash=current_envelope.envelope_hash,
        eligible_exercise_ids=exercise_ids,
        mandatory_exercise_ids=current_pool.mandatory_exercise_ids,
        normalized_query_codes=("GOAL.STRENGTH",),
        retrieval_mode=RetrievalModeCode.DETERMINISTIC_ONLY,
        requested_limit=len(exercise_ids),
    )
    result = ExerciseRetrievalResult(
        query_hash=current_pool.retrieval_metadata.query_hash,
        retrieval_status_code=RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE,
        fallback_used=True,
    )
    root = V3RootSnapshotPersistence(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
        retrieval_request=request,
        retrieval_result=result,
    )
    decision_id = uuid4()
    return map_v3_graph_result_to_persistence_bundle(
        graph_result,
        decision_execution_id=decision_id,
        root_decision_execution_id=decision_id,
        root_snapshot=root,
        conflict_result=conflicts,
        coordinator_attempts=(
            V3CoordinatorAttemptPersistence(
                attempt_number=0,
                plan_spec=current_plan,
                prompt_version="prompt-v1",
                model_version="model-v1",
            ),
        ),
        validations=(
            V3ValidationPersistence(
                attempt_number=0,
                compiled_plan_candidate=compiled,
                integrity_validation=validation,
            ),
        ),
        policy_version=current_envelope.policy_version,
        prompt_version="prompt-v1",
        model_version="model-v1",
    )


class FakeRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, V3DecisionPersistenceBundle] = {}
        self.fail_after_add = False

    def add(self, bundle: V3DecisionPersistenceBundle) -> None:
        self.records[bundle.decision_execution_id] = bundle
        if self.fail_after_add:
            raise RuntimeError("database detail must not escape")

    def get(self, decision_execution_id: UUID) -> V3DecisionPersistenceBundle | None:
        return self.records.get(decision_execution_id)

    def get_root_snapshot(
        self, root_decision_execution_id: UUID
    ) -> V3RootSnapshotPersistence | None:
        for bundle in self.records.values():
            if bundle.root_decision_execution_id == root_decision_execution_id:
                return bundle.root_snapshot
        return None


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.repository = FakeRepository()
        self._before: dict[UUID, V3DecisionPersistenceBundle] = {}

    def __enter__(self) -> FakeUnitOfWork:
        self._before = copy(self.repository.records)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if exc_type is not None:
            self.repository.records = self._before
        return False


def test_full_bundle_preserves_artifacts_and_replays_without_external_ports() -> None:
    bundle = make_bundle()
    work = FakeUnitOfWork()
    service = V3DecisionPersistenceService(work)

    service.persist(bundle)
    replay = service.replay(bundle.decision_execution_id)

    assert len(bundle.agent_proposals) == 3
    assert bundle.conflict_result.violations == ()
    assert bundle.coordinator_attempts[0].attempt_number == 0
    assert bundle.validations[0].integrity_validation.status_code.value == "PASS"
    assert replay.final_plan == bundle.final_plan
    assert replay.canonical_result_hash == bundle.canonical_result_hash
    assert service.load_regeneration_root(bundle.root_decision_execution_id) == bundle.root_snapshot


def test_transaction_failure_rolls_back_and_exposes_only_machine_code() -> None:
    bundle = make_bundle()
    work = FakeUnitOfWork()
    work.repository.fail_after_add = True
    service = V3DecisionPersistenceService(work)

    with pytest.raises(V3PersistenceError) as captured:
        service.persist(bundle)

    assert captured.value.code is V3PersistenceFailureCode.TRANSACTION_FAILED
    assert work.repository.records == {}
    assert "database detail" not in str(captured.value)


def test_duplicate_execution_and_tampered_hash_fail_closed() -> None:
    bundle = make_bundle()
    work = FakeUnitOfWork()
    service = V3DecisionPersistenceService(work)
    service.persist(bundle)
    with pytest.raises(V3PersistenceError) as duplicate:
        service.persist(bundle)
    assert duplicate.value.code is V3PersistenceFailureCode.DUPLICATE_DECISION_EXECUTION

    work.repository.records[bundle.decision_execution_id] = bundle.model_copy(
        update={"canonical_result_hash": "0" * 64}
    )
    with pytest.raises(V3PersistenceError) as tampered:
        service.replay(bundle.decision_execution_id)
    assert tampered.value.code is V3PersistenceFailureCode.CANONICAL_HASH_MISMATCH


def test_bundle_contains_no_forbidden_raw_or_reasoning_fields() -> None:
    serialized = make_bundle().model_dump_json().lower()
    for forbidden in (
        "email",
        "raw_health",
        "raw_wearable",
        "hidden_reasoning",
        "chain_of_thought",
        "provider_exception",
        "prompt_text",
        "pain_intensity_score",
    ):
        assert forbidden not in serialized


def test_mapper_rejects_incomplete_attempt_artifacts() -> None:
    bundle = make_bundle()
    graph = V3GraphResult.create(
        graph_version=bundle.graph_version,
        terminal_status_code=bundle.terminal_status_code,
        envelope_hash=bundle.root_snapshot.constraint_envelope.envelope_hash,
        pool_hash=bundle.root_snapshot.exercise_pool.pool_hash,
        round_one_proposals=tuple(item.proposal for item in bundle.agent_proposals),
        conflict_codes=(),
        review_target_agent_types=(),
        review_results=(),
        coordinator_initial_plan=bundle.coordinator_attempts[0].plan_spec,
        compiled_plan=bundle.final_plan,
        integrity_violation_codes=(),
        final_plan=bundle.final_plan,
    )
    with pytest.raises(V3PersistenceError) as captured:
        map_v3_graph_result_to_persistence_bundle(
            graph,
            decision_execution_id=uuid4(),
            root_decision_execution_id=uuid4(),
            root_snapshot=bundle.root_snapshot,
            conflict_result=bundle.conflict_result,
            coordinator_attempts=(),
            validations=(),
            policy_version=bundle.policy_version,
            prompt_version=bundle.prompt_version,
            model_version=bundle.model_version,
        )
    assert captured.value.code is V3PersistenceFailureCode.INVALID_FINAL_LINKAGE
