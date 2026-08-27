import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExercisePoolSnapshot,
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    RetrievalFailureCode,
    RetrievalMetadata,
    RetrievalModeCode,
    RetrievalStatusCode,
)

ENVELOPE_HASH = "a" * 64
QUERY_HASH = "b" * 64
EXERCISE_A = UUID("00000000-0000-0000-0000-000000000001")
EXERCISE_B = UUID("00000000-0000-0000-0000-000000000002")
EXERCISE_C = UUID("00000000-0000-0000-0000-000000000003")


def _request(**changes: object) -> ExerciseRetrievalRequest:
    values: dict[str, object] = {
        "catalog_version": "catalog-v1",
        "constraint_envelope_hash": ENVELOPE_HASH,
        "eligible_exercise_ids": (EXERCISE_A, EXERCISE_B),
        "mandatory_exercise_ids": (EXERCISE_A,),
        "previous_plan_exercise_ids": (),
        "normalized_query_codes": ("BEGINNER", "GENERAL_FITNESS", "HOME"),
        "retrieval_mode": RetrievalModeCode.VECTOR_RANKED,
        "requested_limit": 8,
    }
    values.update(changes)
    return ExerciseRetrievalRequest(**values)


def _result(**changes: object) -> ExerciseRetrievalResult:
    values: dict[str, object] = {
        "ranked_exercise_ids": (EXERCISE_B, EXERCISE_A),
        "similarity_scores": (0.9, 0.8),
        "collection_name": "exercise-catalog-v1",
        "vector_index_version": "vector-index-v1",
        "embedding_model_version": "embedding-v1",
        "query_hash": QUERY_HASH,
        "retrieval_status_code": RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
        "fallback_used": False,
    }
    values.update(changes)
    return ExerciseRetrievalResult(**values)


def _exercise(exercise_id: UUID) -> ExercisePoolExerciseRecord:
    return ExercisePoolExerciseRecord(
        exercise_id=exercise_id,
        catalog_version="catalog-v1",
        content_version="instruction-v1",
        stable_code=f"exercise-{exercise_id.int}",
        training_type_code="STRENGTH",
        body_focus_code="FULL_BODY",
        movement_pattern_codes=("PUSH",),
        difficulty_code="BEGINNER",
        timing_mode_code="REPS",
        beginner_suitable=True,
        recovery_eligible=False,
        goal_codes=("GENERAL_FITNESS",),
        equipment_codes=("BODYWEIGHT",),
        location_codes=("HOME",),
        prescription_reference_codes=("prescription-v1",),
        source_reference_codes=("catalog-source-v1",),
        review_reference_codes=("domain-review-v1",),
    )


def _success_metadata() -> RetrievalMetadata:
    return RetrievalMetadata(
        collection_name="exercise-catalog-v1",
        vector_index_version="vector-index-v1",
        embedding_model_version="embedding-v1",
        query_hash=QUERY_HASH,
        retrieval_status_code=RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
        deterministic_pool_fallback_used=False,
    )


def test_request_and_result_are_versioned_and_compatible() -> None:
    request = _request()
    result = _result()

    result.validate_against(request)

    assert request.schema_version == "exercise-retrieval-request-v1"
    assert result.schema_version == "exercise-retrieval-result-v1"


def test_collection_reference_accepts_immutable_qdrant_name_up_to_255_chars() -> None:
    collection_name = "exercise_catalog__staging__" + "v" * 200

    result = _result(collection_name=collection_name)
    metadata = RetrievalMetadata(
        collection_name=collection_name,
        vector_index_version="vector-index-v1",
        embedding_model_version="embedding-v1",
        query_hash=QUERY_HASH,
        retrieval_status_code=RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
        deterministic_pool_fallback_used=False,
    )

    assert result.collection_name == collection_name
    assert metadata.collection_name == collection_name


def test_collection_reference_rejects_more_than_255_chars() -> None:
    with pytest.raises(ValidationError, match="structured collection reference"):
        _result(collection_name="c" * 256)


def test_version_reference_keeps_128_character_limit() -> None:
    with pytest.raises(ValidationError, match="structured machine reference"):
        _result(vector_index_version="v" * 129)


def test_request_rejects_mandatory_id_outside_eligible_pool() -> None:
    with pytest.raises(ValidationError, match="must be a subset"):
        _request(mandatory_exercise_ids=(EXERCISE_C,))


def test_result_rejects_ranked_id_outside_eligible_pool() -> None:
    result = _result(
        ranked_exercise_ids=(EXERCISE_C,),
        similarity_scores=(0.9,),
    )

    with pytest.raises(ValueError, match="must be a subset"):
        result.validate_against(_request())


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("eligible_exercise_ids", (EXERCISE_A, EXERCISE_A)),
        ("mandatory_exercise_ids", (EXERCISE_A, EXERCISE_A)),
    ],
)
def test_request_rejects_duplicate_exercise_ids(
    field_name: str,
    value: tuple[UUID, ...],
) -> None:
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        _request(**{field_name: value})


def test_result_rejects_duplicate_ranked_ids() -> None:
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        _result(
            ranked_exercise_ids=(EXERCISE_A, EXERCISE_A),
            similarity_scores=(0.9, 0.8),
        )


def test_request_rejects_duplicate_previous_plan_ids_without_reordering() -> None:
    request = _request(previous_plan_exercise_ids=(EXERCISE_B, EXERCISE_A))

    assert request.previous_plan_exercise_ids == (EXERCISE_B, EXERCISE_A)
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        _request(previous_plan_exercise_ids=(EXERCISE_A, EXERCISE_A))


def test_request_applies_versioned_query_allowlist_and_limit_policy() -> None:
    request = _request()
    allowed = frozenset({"BEGINNER", "GENERAL_FITNESS", "HOME"})

    request.validate_policy(allowed_query_codes=allowed, requested_limit_max=8)

    with pytest.raises(ValueError, match="policy maximum"):
        request.validate_policy(allowed_query_codes=allowed, requested_limit_max=7)
    with pytest.raises(ValueError, match="non-allowlisted"):
        request.validate_policy(
            allowed_query_codes=frozenset({"BEGINNER"}),
            requested_limit_max=8,
        )


def test_result_rejects_score_length_mismatch() -> None:
    with pytest.raises(ValidationError, match="must have equal length"):
        _result(similarity_scores=(0.9,))


def test_result_rejects_more_ranked_ids_than_requested() -> None:
    with pytest.raises(ValueError, match="must not exceed requested_limit"):
        _result().validate_against(_request(requested_limit=1))


def test_success_metadata_requires_collection_and_versions() -> None:
    with pytest.raises(ValidationError, match="requires collection and versions"):
        RetrievalMetadata(
            query_hash=QUERY_HASH,
            retrieval_status_code=RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
            deterministic_pool_fallback_used=False,
        )


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_result_rejects_non_finite_score(score: float) -> None:
    with pytest.raises(ValidationError, match="finite"):
        _result(
            ranked_exercise_ids=(EXERCISE_A,),
            similarity_scores=(score,),
        )


def test_failed_result_requires_fallback_and_primary_failure_metadata() -> None:
    result = _result(
        ranked_exercise_ids=(),
        similarity_scores=(),
        collection_name=None,
        vector_index_version=None,
        embedding_model_version=None,
        retrieval_status_code=RetrievalStatusCode.VECTOR_SEARCH_TIMEOUT,
        fallback_used=True,
    )
    metadata = RetrievalMetadata(
        query_hash=QUERY_HASH,
        retrieval_status_code=RetrievalStatusCode.VECTOR_SEARCH_TIMEOUT,
        retrieval_failure_codes=(RetrievalFailureCode.VECTOR_SEARCH_TIMEOUT,),
        deterministic_fallback_version="deterministic-pool-v1",
        deterministic_pool_fallback_used=True,
    )

    result.validate_against(_request())

    assert metadata.deterministic_pool_fallback_used is True


def test_pool_hash_is_stable_and_excludes_created_at() -> None:
    exercises = (_exercise(EXERCISE_A), _exercise(EXERCISE_B))
    first = ExercisePoolSnapshot.create(
        catalog_version="catalog-v1",
        constraint_envelope_hash=ENVELOPE_HASH,
        exercises=exercises,
        mandatory_exercise_ids=(EXERCISE_A,),
        vector_ranked_exercise_ids=(EXERCISE_B, EXERCISE_A),
        retrieval_metadata=_success_metadata(),
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
    )
    second = ExercisePoolSnapshot.create(
        catalog_version="catalog-v1",
        constraint_envelope_hash=ENVELOPE_HASH,
        exercises=exercises,
        mandatory_exercise_ids=(EXERCISE_A,),
        vector_ranked_exercise_ids=(EXERCISE_B, EXERCISE_A),
        retrieval_metadata=_success_metadata(),
        created_at=datetime(2026, 8, 24, tzinfo=UTC) + timedelta(minutes=1),
    )

    assert first.pool_hash == second.pool_hash
    assert first.pool_hash == "612af45ced6771d8bc62ffcc0df59de2d51eff5a604a68c6062f28929c5fa76b"


@pytest.mark.parametrize(
    "forbidden_field",
    ["user_id", "email", "pain_present", "pain_intensity_score", "severity_code"],
)
def test_retrieval_request_rejects_sensitive_or_uncontracted_fields(
    forbidden_field: str,
) -> None:
    payload = _request().model_dump()
    payload[forbidden_field] = "SENSITIVE_SENTINEL"

    with pytest.raises(ValidationError):
        ExerciseRetrievalRequest(**payload)


@pytest.mark.parametrize("query_code", ["KNEE", "PAIN_MILD", "USER_ID:123"])
def test_normalized_query_codes_reject_health_and_identifier_data(query_code: str) -> None:
    with pytest.raises(ValidationError, match="must not contain health"):
        _request(normalized_query_codes=(query_code,))


def test_retrieval_domain_module_has_no_external_framework_imports() -> None:
    module_path = Path(__file__).parents[2] / "app" / "domain" / "agents" / "retrieval.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_roots = {"fastapi", "langchain", "langgraph", "qdrant_client", "sqlalchemy"}
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", maxsplit=1)[0])

    assert imported_roots.isdisjoint(forbidden_roots)
