"""PHASE 1: the dataset itself has to be trustworthy before it judges anything."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.tests.evaluation import catalog
from backend.tests.evaluation.dataset import (
    DATASETS_DIR,
    CaseCategory,
    EvaluationCase,
    assert_no_identifiers,
    load_smoke_dataset,
)
from backend.tests.evaluation.harness import BUILD_ERROR_CASES, SMOKE_DATASET
from backend.tests.evaluation.scenario import ScenarioBuildError, build_scenario

MINIMUM_SMOKE_CASES = 10
MAXIMUM_SMOKE_CASES = 20


def test_smoke_dataset_loads_and_is_smoke_sized() -> None:
    assert MINIMUM_SMOKE_CASES <= len(SMOKE_DATASET) <= MAXIMUM_SMOKE_CASES


@pytest.mark.parametrize("category", list(CaseCategory))
def test_every_required_category_is_represented(category: CaseCategory) -> None:
    """The master specification names nine categories; none may be skipped."""

    assert SMOKE_DATASET.by_category(category), f"no case for category {category.value}"


def test_case_ids_are_unique() -> None:
    ids = [case.case_id for case in SMOKE_DATASET]
    assert len(ids) == len(set(ids))


def test_dataset_carries_no_identifying_or_health_fields() -> None:
    """`AGENTS.md` section 8. A fixture is not exempt from the privacy rules."""

    raw = json.loads((DATASETS_DIR / "smoke_cases.json").read_text(encoding="utf-8"))
    assert_no_identifiers(raw)


def test_privacy_scan_rejects_a_forbidden_field() -> None:
    """The scan has to actually catch something, or it proves nothing above."""

    with pytest.raises(ValueError, match="forbidden identifying or health field"):
        assert_no_identifiers({"cases": [{"user_input": {"birth_date": "1990-01-01"}}]})


def test_every_referenced_exercise_exists_in_the_evaluation_catalog() -> None:
    for case in SMOKE_DATASET:
        for code in (
            *case.pool.exercise_codes,
            *case.expected_constraints.excluded_exercise_codes,
            *case.expected_constraints.mandatory_exercise_codes,
            *case.prohibited_actions.exercise_codes,
            *case.expected_relevant_exercise_codes,
        ):
            assert code in catalog.CATALOG, f"{case.case_id} references unknown {code}"


def test_excluded_exercises_are_also_prohibited() -> None:
    """An exclusion nobody checks for is an exclusion that can silently return."""

    for case in SMOKE_DATASET:
        excluded = set(case.expected_constraints.excluded_exercise_codes)
        assert excluded.issubset(case.prohibited_actions.exercise_codes), case.case_id


def test_safety_critical_cases_name_what_must_not_happen() -> None:
    """A safety case that prohibits nothing cannot detect a single bad recommendation."""

    for case in SMOKE_DATASET.by_category(CaseCategory.SAFETY_CRITICAL):
        forbids_planning = not case.expected_constraints.plan_generation_allowed
        names_exercises = bool(case.prohibited_actions.exercise_codes)
        assert forbids_planning or names_exercises, case.case_id


def test_scenario_building_is_deterministic() -> None:
    """Same case in, same hashes out. Without this no result is replayable."""

    for case in SMOKE_DATASET:
        if case.expected_scenario_build_error:
            continue
        first = build_scenario(case)
        second = build_scenario(case)
        assert first.constraint_envelope.envelope_hash == second.constraint_envelope.envelope_hash
        assert first.exercise_pool.pool_hash == second.exercise_pool.pool_hash


def test_pool_is_bound_to_its_envelope() -> None:
    for case in SMOKE_DATASET:
        if case.expected_scenario_build_error:
            continue
        scenario = build_scenario(case)
        assert (
            scenario.exercise_pool.constraint_envelope_hash
            == scenario.constraint_envelope.envelope_hash
        )


@pytest.mark.parametrize("case", BUILD_ERROR_CASES, ids=lambda case: case.case_id)
def test_incomplete_input_is_refused_before_the_graph(case: EvaluationCase) -> None:
    """A missing required input never becomes a graph run, in tests or production."""

    with pytest.raises(ScenarioBuildError) as error:
        build_scenario(case)
    assert error.value.code == case.expected_scenario_build_error


def test_case_schema_rejects_an_unknown_field() -> None:
    """Strict cases. A typo in a dataset must fail loudly, not be ignored."""

    body = SMOKE_DATASET.cases[0].model_dump(mode="json")
    body["unexpected_field"] = True
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate_json(json.dumps(body))


def test_case_schema_rejects_a_veto_that_allows_planning() -> None:
    body = SMOKE_DATASET.cases[0].model_dump(mode="json")
    body["expected_safety_result"] = {
        "status_code": "BLOCKED",
        "required_action_code": "REST",
        "veto": True,
    }
    body["expected_constraints"]["plan_generation_allowed"] = True
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate_json(json.dumps(body))


def test_reloading_the_dataset_produces_equal_cases() -> None:
    assert load_smoke_dataset() == SMOKE_DATASET
