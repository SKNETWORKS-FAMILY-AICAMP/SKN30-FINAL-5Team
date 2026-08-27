import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from backend.app.domain.agents.exercise_pool import (
    CanonicalExerciseRevalidation,
    DeterministicExerciseCandidates,
    DeterministicExercisePoolBuilder,
    ExercisePoolBuildError,
    ExercisePoolBuildInput,
    ExerciseRetrievalPolicy,
    SafetyRetrievalGate,
)
from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    RetrievalFailureCode,
    RetrievalModeCode,
    RetrievalStatusCode,
)
from backend.app.domain.rules.safety import SafetyRequiredActionCode, SafetyStatusCode

ENVELOPE_HASH = "a" * 64
QUERY_HASH = "b" * 64
A = UUID("00000000-0000-0000-0000-000000000001")
B = UUID("00000000-0000-0000-0000-000000000002")
C = UUID("00000000-0000-0000-0000-000000000003")
D = UUID("00000000-0000-0000-0000-000000000004")


class FakeExerciseRetriever:
    def __init__(self, result: ExerciseRetrievalResult) -> None:
        self.result = result
        self.requests: list[ExerciseRetrievalRequest] = []

    def retrieve(self, request: ExerciseRetrievalRequest) -> ExerciseRetrievalResult:
        self.requests.append(request)
        return self.result


def _exercise(exercise_id: UUID) -> ExercisePoolExerciseRecord:
    return ExercisePoolExerciseRecord(
        exercise_id=exercise_id,
        catalog_version="catalog-v1",
        content_version=f"instruction-{exercise_id.int}",
        stable_code=f"exercise-{exercise_id.int}",
        training_type_code="STRENGTH",
        body_focus_code="FULL_BODY",
        movement_pattern_codes=("PUSH",),
        difficulty_code="BEGINNER",
        timing_mode_code="REPS",
        recovery_eligible=False,
        goal_codes=("GENERAL_FITNESS",),
        equipment_codes=("BODYWEIGHT",),
        location_codes=("HOME",),
        prescription_reference_codes=("prescription-v1",),
        source_reference_codes=("catalog-source-v1",),
        review_reference_codes=("domain-review-v1",),
    )


def _revalidation(
    exercise_id: UUID,
    *,
    content_version: str = "catalog-content-v1",
    review_version: str = "catalog-review-v1",
    production_approved: bool = True,
) -> CanonicalExerciseRevalidation:
    return CanonicalExerciseRevalidation(
        exercise=_exercise(exercise_id),
        catalog_content_version=content_version,
        catalog_review_version=review_version,
        production_approved=production_approved,
    )


def _candidates(
    *,
    revalidated: tuple[CanonicalExerciseRevalidation, ...] | None = None,
) -> DeterministicExerciseCandidates:
    return DeterministicExerciseCandidates(
        catalog_version="catalog-v1",
        catalog_content_version="catalog-content-v1",
        catalog_review_version="catalog-review-v1",
        constraint_envelope_hash=ENVELOPE_HASH,
        eligible_exercise_ids=(A, B, C, D),
        mandatory_goal_exercise_ids=(A,),
        approved_safe_alternative_ids=(B,),
        deterministic_fallback_order=(C, D, A, B),
        revalidated_exercises=(
            (_revalidation(A), _revalidation(B), _revalidation(C), _revalidation(D))
            if revalidated is None
            else revalidated
        ),
    )


def _policy(**changes: object) -> ExerciseRetrievalPolicy:
    values: dict[str, object] = {
        "policy_version": "exercise-retrieval-policy-v1",
        "allowed_query_codes": frozenset({"BEGINNER", "GENERAL_FITNESS", "HOME"}),
        "requested_limit_max": 8,
        "minimum_vector_candidates": 2,
        "deterministic_fallback_version": "deterministic-pool-v1",
        "expected_collection_name": "exercise-catalog-v1",
        "expected_vector_index_version": "vector-index-v1",
        "expected_embedding_model_version": "embedding-v1",
    }
    values.update(changes)
    return ExerciseRetrievalPolicy(**values)


def _gate(
    status: SafetyStatusCode = SafetyStatusCode.PASS,
    *,
    action: SafetyRequiredActionCode | None = None,
    allowed: bool = True,
) -> SafetyRetrievalGate:
    return SafetyRetrievalGate(
        status_code=status,
        required_action_code=action,
        plan_generation_allowed=allowed,
    )


def _build_input(**changes: object) -> ExercisePoolBuildInput:
    values: dict[str, object] = {
        "safety_gate": _gate(),
        "candidates": _candidates(),
        "retrieval_policy": _policy(),
        "previous_plan_exercise_ids": (),
        "normalized_query_codes": ("BEGINNER", "GENERAL_FITNESS", "HOME"),
        "retrieval_mode": RetrievalModeCode.VECTOR_RANKED,
        "requested_limit": 2,
    }
    values.update(changes)
    return ExercisePoolBuildInput(**values)


def _success_result(
    ranked: tuple[UUID, ...] = (C, D),
    *,
    scores: tuple[float, ...] = (0.9, 0.8),
    vector_index_version: str = "vector-index-v1",
) -> ExerciseRetrievalResult:
    return ExerciseRetrievalResult(
        ranked_exercise_ids=ranked,
        similarity_scores=scores,
        collection_name="exercise-catalog-v1",
        vector_index_version=vector_index_version,
        embedding_model_version="embedding-v1",
        query_hash=QUERY_HASH,
        retrieval_status_code=RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
        fallback_used=False,
    )


def _failure_result(status: RetrievalStatusCode) -> ExerciseRetrievalResult:
    return ExerciseRetrievalResult(
        query_hash=QUERY_HASH,
        retrieval_status_code=status,
        fallback_used=True,
    )


@pytest.mark.parametrize(
    "gate",
    [
        _gate(SafetyStatusCode.NEEDS_INPUT, allowed=False),
        _gate(
            SafetyStatusCode.BLOCKED,
            action=SafetyRequiredActionCode.REST,
            allowed=False,
        ),
        _gate(
            SafetyStatusCode.BLOCKED,
            action=SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
            allowed=False,
        ),
        _gate(SafetyStatusCode.FAILED, allowed=False),
    ],
)
def test_safety_terminal_states_do_not_call_retriever(gate: SafetyRetrievalGate) -> None:
    retriever = FakeExerciseRetriever(_success_result())

    with pytest.raises(ExercisePoolBuildError, match="Safety gate"):
        DeterministicExercisePoolBuilder(retriever).build(
            _build_input(safety_gate=gate),
            created_at=datetime(2026, 8, 24, tzinfo=UTC),
        )

    assert retriever.requests == []


def test_mandatory_goal_and_safe_alternative_survive_vector_top_k() -> None:
    retriever = FakeExerciseRetriever(_success_result())

    snapshot = DeterministicExercisePoolBuilder(retriever).build(
        _build_input(), created_at=datetime(2026, 8, 24, tzinfo=UTC)
    )

    assert snapshot.mandatory_exercise_ids == (A, B)
    assert {item.exercise_id for item in snapshot.exercises} == {A, B, C, D}
    assert snapshot.vector_ranked_exercise_ids == (C, D)
    assert len(retriever.requests) == 1


def test_ineligible_vector_id_is_discarded_and_falls_back() -> None:
    outside = UUID("00000000-0000-0000-0000-000000000099")
    retriever = FakeExerciseRetriever(_success_result((outside,), scores=(0.9,)))

    snapshot = DeterministicExercisePoolBuilder(retriever).build(
        _build_input(), created_at=datetime(2026, 8, 24, tzinfo=UTC)
    )

    assert outside not in {item.exercise_id for item in snapshot.exercises}
    assert snapshot.retrieval_metadata.retrieval_status_code is (
        RetrievalStatusCode.VECTOR_RESULT_NOT_CANONICAL
    )
    assert snapshot.retrieval_metadata.deterministic_pool_fallback_used is True


def test_stale_content_revalidation_is_discarded() -> None:
    candidates = _candidates(
        revalidated=(
            _revalidation(A),
            _revalidation(B),
            _revalidation(C, content_version="catalog-content-stale"),
            _revalidation(D),
        )
    )
    retriever = FakeExerciseRetriever(_success_result((C,), scores=(0.9,)))

    snapshot = DeterministicExercisePoolBuilder(retriever).build(
        _build_input(candidates=candidates),
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
    )

    assert C not in {item.exercise_id for item in snapshot.exercises}
    assert RetrievalFailureCode.VECTOR_RESULT_STALE in (
        snapshot.retrieval_metadata.retrieval_failure_codes
    )


def test_index_version_mismatch_discards_vector_result() -> None:
    retriever = FakeExerciseRetriever(_success_result(vector_index_version="vector-index-stale"))

    snapshot = DeterministicExercisePoolBuilder(retriever).build(
        _build_input(), created_at=datetime(2026, 8, 24, tzinfo=UTC)
    )

    assert snapshot.vector_ranked_exercise_ids == ()
    assert snapshot.retrieval_metadata.retrieval_status_code is (
        RetrievalStatusCode.VECTOR_INDEX_VERSION_MISMATCH
    )


@pytest.mark.parametrize(
    "status",
    [
        RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE,
        RetrievalStatusCode.VECTOR_INDEX_NOT_READY,
        RetrievalStatusCode.VECTOR_SEARCH_TIMEOUT,
    ],
)
def test_vector_failure_uses_deterministic_fallback(status: RetrievalStatusCode) -> None:
    retriever = FakeExerciseRetriever(_failure_result(status))

    snapshot = DeterministicExercisePoolBuilder(retriever).build(
        _build_input(), created_at=datetime(2026, 8, 24, tzinfo=UTC)
    )

    assert {item.exercise_id for item in snapshot.exercises} == {A, B, C, D}
    assert snapshot.retrieval_metadata.retrieval_status_code is status
    assert snapshot.retrieval_metadata.deterministic_pool_fallback_used is True


def test_insufficient_vector_result_is_supplemented_deterministically() -> None:
    retriever = FakeExerciseRetriever(_success_result((C,), scores=(0.9,)))

    snapshot = DeterministicExercisePoolBuilder(retriever).build(
        _build_input(), created_at=datetime(2026, 8, 24, tzinfo=UTC)
    )

    assert {item.exercise_id for item in snapshot.exercises} == {A, B, C, D}
    assert snapshot.vector_ranked_exercise_ids == (C,)
    assert snapshot.retrieval_metadata.retrieval_status_code is (
        RetrievalStatusCode.VECTOR_RESULT_INSUFFICIENT
    )


def test_fallback_never_includes_non_production_exercise() -> None:
    candidates = _candidates(
        revalidated=(
            _revalidation(A),
            _revalidation(B),
            _revalidation(C, production_approved=False),
            _revalidation(D),
        )
    )
    retriever = FakeExerciseRetriever(_failure_result(RetrievalStatusCode.VECTOR_SEARCH_TIMEOUT))

    snapshot = DeterministicExercisePoolBuilder(retriever).build(
        _build_input(candidates=candidates),
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
    )

    assert C not in {item.exercise_id for item in snapshot.exercises}


def test_required_exercise_failing_revalidation_fails_closed() -> None:
    candidates = _candidates(
        revalidated=(
            _revalidation(A, production_approved=False),
            _revalidation(B),
            _revalidation(C),
            _revalidation(D),
        )
    )
    retriever = FakeExerciseRetriever(_success_result())

    with pytest.raises(ExercisePoolBuildError, match="mandatory"):
        DeterministicExercisePoolBuilder(retriever).build(
            _build_input(candidates=candidates),
            created_at=datetime(2026, 8, 24, tzinfo=UTC),
        )


def test_same_input_has_stable_order_and_hash_without_created_at() -> None:
    build_input = _build_input()
    first = DeterministicExercisePoolBuilder(FakeExerciseRetriever(_success_result())).build(
        build_input, created_at=datetime(2026, 8, 24, tzinfo=UTC)
    )
    second = DeterministicExercisePoolBuilder(FakeExerciseRetriever(_success_result())).build(
        build_input,
        created_at=datetime(2026, 8, 24, tzinfo=UTC) + timedelta(minutes=10),
    )

    assert first.exercises == second.exercises
    assert first.pool_hash == second.pool_hash


def test_policy_rejects_unknown_query_code_and_excess_limit_before_retrieval() -> None:
    retriever = FakeExerciseRetriever(_success_result())
    builder = DeterministicExercisePoolBuilder(retriever)

    with pytest.raises(ValueError, match="non-allowlisted"):
        builder.build(
            _build_input(normalized_query_codes=("FREE_TEXT",)),
            created_at=datetime(2026, 8, 24, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="policy maximum"):
        builder.build(
            _build_input(requested_limit=9),
            created_at=datetime(2026, 8, 24, tzinfo=UTC),
        )

    assert retriever.requests == []


def test_snapshot_and_request_do_not_project_pain_or_health_fields() -> None:
    retriever = FakeExerciseRetriever(_success_result())
    snapshot = DeterministicExercisePoolBuilder(retriever).build(
        _build_input(), created_at=datetime(2026, 8, 24, tzinfo=UTC)
    )
    serialized = str(
        {
            "request": retriever.requests[0].model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
        }
    ).upper()

    for forbidden in ("PAIN", "BODY_AREA_CODE", "INTENSITY_SCORE", "SEVERITY_CODE"):
        assert forbidden not in serialized


def test_exercise_pool_domain_has_no_infrastructure_or_agent_framework_imports() -> None:
    module_path = Path(__file__).parents[2] / "app" / "domain" / "agents" / "exercise_pool.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_roots = {"fastapi", "langchain", "langgraph", "qdrant_client", "sqlalchemy"}
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", maxsplit=1)[0])

    assert imported_roots.isdisjoint(forbidden_roots)
