"""PHASE 3: retriever behaviour, scored without any LLM in the loop.

The assertions here are the retriever's *guarantees* -- eligibility containment,
previous-plan exclusion, mandatory retention, canonical results, and the failure
path.  Those hold whatever the embedding is, so they are real tests.

Ranking quality (Recall@k, MRR) is **not** asserted.  With the offline fake
embedding the vectors are hash-derived, so a threshold would be pinning noise;
with a real embedding a threshold nobody has agreed to would become a target.
Ranking is measured and reported by `report_retrieval_cli`, not gated here.
"""

from __future__ import annotations

import pytest

from backend.app.domain.agents.retrieval import RetrievalModeCode, RetrievalStatusCode
from backend.tests.evaluation import catalog
from backend.tests.evaluation.evaluators.retrieval_evaluator import (
    RetrievalCase,
    is_successful,
    load_retrieval_dataset,
    score_case,
)
from backend.tests.evaluation.retrieval.index import build_evaluation_index
from backend.tests.evaluation.scenario import QUERY_HASH

DATASET = load_retrieval_dataset()


@pytest.fixture(scope="module")
def index():  # type: ignore[no-untyped-def]
    return build_evaluation_index()


def _ids(case: RetrievalCase) -> str:
    return case.case_id


def _retrieve(index, case: RetrievalCase):  # type: ignore[no-untyped-def]
    request = case.to_request(
        catalog_version=index.contract.catalog_version, envelope_hash=QUERY_HASH
    )
    return index.retriever.retrieve(request)


def test_dataset_loads_with_every_case_grounded() -> None:
    assert len(DATASET.cases) >= 5
    for case in DATASET.cases:
        assert set(case.relevant_exercise_codes).issubset(case.eligible_exercise_codes)


def test_index_covers_the_whole_evaluation_catalog(index) -> None:  # type: ignore[no-untyped-def]
    assert index.point_count == len(catalog.CATALOG)


@pytest.mark.parametrize("case", DATASET.cases, ids=_ids)
def test_retrieval_succeeds_without_falling_back(index, case: RetrievalCase) -> None:  # type: ignore[no-untyped-def]
    result = _retrieve(index, case)
    assert is_successful(result), result.retrieval_status_code


@pytest.mark.parametrize("case", DATASET.cases, ids=_ids)
def test_results_never_leave_the_eligible_set(index, case: RetrievalCase) -> None:  # type: ignore[no-untyped-def]
    """Qdrant ranks what PostgreSQL approved. It may not add to it.

    This is the one retrieval property with a safety reading: a result outside
    the eligible set is an exercise nobody approved for this user.
    """

    result = _retrieve(index, case)
    eligible = set(catalog.ids_for(case.eligible_exercise_codes))
    assert set(result.ranked_exercise_ids).issubset(eligible)


@pytest.mark.parametrize("case", DATASET.cases, ids=_ids)
def test_results_are_canonical(index, case: RetrievalCase) -> None:  # type: ignore[no-untyped-def]
    result = _retrieve(index, case)
    ids = result.ranked_exercise_ids
    assert len(ids) == len(set(ids)), "a ranked list may not repeat an exercise"
    assert (
        len(ids)
        <= case.to_request(
            catalog_version=index.contract.catalog_version, envelope_hash=QUERY_HASH
        ).requested_limit
    )


@pytest.mark.parametrize("case", DATASET.cases, ids=_ids)
def test_filter_guarantees_hold(index, case: RetrievalCase) -> None:  # type: ignore[no-untyped-def]
    """Previous-plan exclusion and mandatory retention, which are not ranking."""

    score = score_case(case, _retrieve(index, case))
    assert score.eligibility_respected
    assert score.previous_plan_excluded
    assert score.mandatory_retained


def test_a_mandatory_exercise_survives_previous_plan_exclusion(index) -> None:  # type: ignore[no-untyped-def]
    """The two rules meet in RQ-FILTER-002 and the mandatory one has to win."""

    case = next(item for item in DATASET.cases if item.case_id == "RQ-FILTER-002")
    result = _retrieve(index, case)
    mandatory = set(catalog.ids_for(case.mandatory_exercise_codes))
    previous = set(catalog.ids_for(case.previous_plan_exercise_codes)) - mandatory
    assert mandatory.issubset(result.ranked_exercise_ids)
    assert not (set(result.ranked_exercise_ids) & previous)


def test_deterministic_mode_bypasses_the_vector_index(index) -> None:  # type: ignore[no-untyped-def]
    """A request that asks for deterministic ordering must not query Qdrant."""

    case = DATASET.cases[0]
    request = case.to_request(
        catalog_version=index.contract.catalog_version, envelope_hash=QUERY_HASH
    ).model_copy(update={"retrieval_mode": RetrievalModeCode.DETERMINISTIC_ONLY})
    result = index.retriever.retrieve(request)
    assert result.fallback_used
    assert result.retrieval_status_code is RetrievalStatusCode.VECTOR_INDEX_NOT_READY
    assert set(result.ranked_exercise_ids).issubset(
        set(catalog.ids_for(case.eligible_exercise_codes))
    )


def test_a_catalog_version_mismatch_falls_back_rather_than_ranking(index) -> None:  # type: ignore[no-untyped-def]
    """A stale index must never rank against a catalog it was not built for."""

    case = DATASET.cases[0]
    request = case.to_request(catalog_version="eval-catalog-v999", envelope_hash=QUERY_HASH)
    result = index.retriever.retrieve(request)
    assert result.fallback_used
    assert result.retrieval_status_code is RetrievalStatusCode.VECTOR_INDEX_VERSION_MISMATCH


def test_fake_embedding_runs_are_marked_non_semantic(index) -> None:  # type: ignore[no-untyped-def]
    """A report built on hash vectors must say so, or its numbers will be misread."""

    assert index.is_semantic is False
    assert index.embedding_contract.provider_code == "DETERMINISTIC_FAKE"
