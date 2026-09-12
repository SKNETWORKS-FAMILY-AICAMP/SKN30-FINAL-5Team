"""The held-out set must be held out, and grounded in shipped data.

Round 1 could not answer whether the multi-agent composition earns its cost,
because the only dataset had been tuned against. That makes two properties
load-bearing here, and neither is self-evident from reading the JSON:

* **nothing was tuned on these cases** -- no case id, and no whole case, is
  shared with the tuning set
* **the domain content is the service's, not the harness author's** -- the
  exclusions come from the shipped safety rules and the pools from the deployed
  catalog

Everything is deterministic and costs nothing.
"""

from __future__ import annotations

import json

import pytest

from backend.tests.evaluation.catalog_source import DEPLOYED_SOURCE, SYNTHETIC_SOURCE
from backend.tests.evaluation.dataset import (
    DATASETS_DIR,
    CaseCategory,
    ExpectedOutcome,
    RequiredActionExpectation,
    load_dataset,
    load_smoke_dataset,
)
from backend.tests.evaluation.evaluators import evaluate_case
from backend.tests.evaluation.evaluators.findings import Severity
from backend.tests.evaluation.harness import run_case
from backend.tests.evaluation.heldout_builder import (
    EXPANDED_HELDOUT_DATASET_NAME,
    HELDOUT_DATASET_NAME,
    build_cases,
    build_expanded_dataset,
    excluded_codes,
    load_safety_rules,
)
from backend.tests.evaluation.scenario import build_scenario

HELDOUT = load_dataset(HELDOUT_DATASET_NAME)
EXPANDED_HELDOUT = load_dataset(EXPANDED_HELDOUT_DATASET_NAME)
TUNING = load_smoke_dataset()

# `ROUND2_IMPROVEMENT_PLAN` section 4 asks for at least 30, stratified.
MINIMUM_CASES = 30
EXPANDED_CASES = 60


# -- held out from the tuning set ---------------------------------------


def test_the_set_is_large_enough_to_stratify() -> None:
    assert len(HELDOUT) >= MINIMUM_CASES


def test_the_expanded_set_reaches_the_recommended_size() -> None:
    assert len(EXPANDED_HELDOUT) == EXPANDED_CASES
    expanded_cases = list(EXPANDED_HELDOUT)
    original_cases = list(HELDOUT)
    assert [case.model_dump(mode="json") for case in expanded_cases[: len(original_cases)]] == [
        case.model_dump(mode="json") for case in original_cases
    ]


def test_no_case_is_shared_with_the_tuning_set() -> None:
    """The point of a held-out set is that nothing was fitted to it."""

    tuning_ids = {case.case_id for case in TUNING}
    heldout_ids = {case.case_id for case in HELDOUT}
    assert not tuning_ids & heldout_ids

    # Identity is stronger than the id: two cases could differ by name and still
    # describe the same request.
    def fingerprint(case: object) -> tuple[object, ...]:
        return (
            case.expected_constraints.requested_duration_minutes,  # type: ignore[attr-defined]
            case.expected_constraints.primary_goal_code,  # type: ignore[attr-defined]
            case.expected_constraints.allowed_location_codes,  # type: ignore[attr-defined]
            case.expected_constraints.excluded_exercise_codes,  # type: ignore[attr-defined]
            case.pool.exercise_codes,  # type: ignore[attr-defined]
        )

    assert not {fingerprint(case) for case in TUNING} & {fingerprint(case) for case in HELDOUT}


def test_the_expanded_set_is_also_held_out_from_tuning() -> None:
    tuning_ids = {case.case_id for case in TUNING}
    expanded_ids = {case.case_id for case in EXPANDED_HELDOUT}
    assert not tuning_ids & expanded_ids


def test_the_two_sets_use_different_catalogs() -> None:
    """Tuning stays on the synthetic catalog; held-out uses what ships."""

    assert TUNING.catalog_source == SYNTHETIC_SOURCE
    assert HELDOUT.catalog_source == DEPLOYED_SOURCE


# -- stratification -----------------------------------------------------


@pytest.mark.parametrize(
    "category",
    [
        CaseCategory.SIMPLE,
        CaseCategory.MODERATE,
        CaseCategory.COMPLEX,
        CaseCategory.CONFLICT,
        CaseCategory.SAFETY_CRITICAL,
        CaseCategory.FAILURE_CASE,
    ],
)
def test_every_required_stratum_is_present(category: CaseCategory) -> None:
    assert HELDOUT.by_category(category), category.value


@pytest.mark.parametrize(
    ("category", "minimum"),
    [
        (CaseCategory.SIMPLE, 8),
        (CaseCategory.MODERATE, 14),
        (CaseCategory.COMPLEX, 16),
        (CaseCategory.CONFLICT, 12),
        (CaseCategory.SAFETY_CRITICAL, 6),
        (CaseCategory.FAILURE_CASE, 4),
    ],
)
def test_expanded_strata_have_meaningful_depth(category: CaseCategory, minimum: int) -> None:
    assert len(EXPANDED_HELDOUT.by_category(category)) >= minimum


def test_the_strata_the_plan_names_are_actually_exercised() -> None:
    """Named conditions, not just category labels."""

    assert any(case.pool.retrieval_failed for case in HELDOUT), "no provider-failure case"
    assert any(case.expected_constraints.maximum_sets_per_exercise == 2 for case in HELDOUT), (
        "no tight recovery ceiling"
    )
    assert any(
        case.expected_constraints.requested_duration_minutes is not None
        and case.expected_constraints.requested_duration_minutes <= 15
        for case in HELDOUT
    ), "no limited-time case"
    assert any(case.prohibited_actions.equipment_codes for case in HELDOUT), "no equipment case"
    assert any(case.expected_constraints.excluded_exercise_codes for case in HELDOUT)
    # Supporting users without a wearable is a product invariant, so the default
    # must be the unconnected one rather than an afterthought.
    assert sum(1 for case in HELDOUT if not case.user_input.wearable_connected) >= len(HELDOUT) - 4


# -- the domain content is the service's --------------------------------


def test_exclusions_come_from_the_shipped_safety_rules() -> None:
    """Spot-check that a case's exclusions are the rules', not an invention."""

    rules = load_safety_rules()
    cases = [case for case in HELDOUT if case.expected_constraints.excluded_exercise_codes]
    assert cases

    for case in cases:
        area = case.user_input.discomfort_area_codes[0]
        severity = case.user_input.discomfort_severity_code
        assert severity is not None
        expected = excluded_codes(rules, body_area_code=area, severity_code=severity)
        assert set(case.expected_constraints.excluded_exercise_codes) == set(expected)


def test_every_excluded_exercise_is_also_prohibited() -> None:
    """An exclusion nobody checks for is not an exclusion."""

    for case in HELDOUT:
        excluded = set(case.expected_constraints.excluded_exercise_codes)
        assert excluded.issubset(set(case.prohibited_actions.exercise_codes)), case.case_id


# -- every case is runnable ---------------------------------------------


def test_every_case_builds_a_production_shaped_pool() -> None:
    """A pool with no cooldown candidate cannot produce a session at all."""

    for case in HELDOUT:
        pool = build_scenario(case).exercise_pool
        assert pool.exercises, case.case_id
        for phase in ("WARMUP", "MAIN", "COOLDOWN"):
            assert any(phase in item.phase_codes for item in pool.exercises), (
                f"{case.case_id} has no {phase} candidate"
            )


def test_pools_are_sized_like_a_live_request_not_like_the_whole_catalog() -> None:
    """The loader sizes a pool from the requested duration; 121 eligible is not a pool."""

    for case in HELDOUT:
        pool = build_scenario(case).exercise_pool
        assert len(pool.exercises) <= 40, case.case_id
        assert len(pool.exercises) < len(case.pool.exercise_codes), case.case_id


def test_a_blocked_safety_case_expects_no_plan() -> None:
    blocked = [
        case
        for case in HELDOUT
        if case.expected_safety_result.required_action_code is not RequiredActionExpectation.NONE
    ]
    assert blocked
    for case in blocked:
        assert case.expected_outcome is ExpectedOutcome.NO_PLAN
        assert not case.expected_constraints.plan_generation_allowed


# -- reproducible -------------------------------------------------------


def test_the_dataset_on_disk_matches_the_generator() -> None:
    """The file is reviewed as data, so it must still be derivable.

    A hand-edit here is how a held-out set quietly becomes something nobody can
    reproduce or explain the provenance of.
    """

    generated = build_cases()
    stored = [case.model_dump(mode="json", exclude_none=False) for case in HELDOUT]
    assert [item["case_id"] for item in generated] == [item["case_id"] for item in stored]
    for produced, on_disk in zip(generated, stored, strict=True):
        assert produced["expected_constraints"]["excluded_exercise_codes"] == list(
            on_disk["expected_constraints"]["excluded_exercise_codes"]
        )
        assert produced["pool"]["exercise_codes"] == list(on_disk["pool"]["exercise_codes"])


def test_the_expanded_dataset_on_disk_matches_the_generator() -> None:
    path = DATASETS_DIR / f"{EXPANDED_HELDOUT_DATASET_NAME}.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert build_expanded_dataset() == stored


def test_expanded_blocked_cases_stop_before_any_provider_call() -> None:
    blocked = [
        case
        for case in EXPANDED_HELDOUT
        if case.expected_safety_result.required_action_code is not RequiredActionExpectation.NONE
    ]
    assert len(blocked) == 6

    for case in blocked:
        run = run_case(case)
        evaluation = evaluate_case(run)
        assert not run.has_plan, case.case_id
        assert run.status_code == case.expected_safety_result.required_action_code.value
        assert run.llm_call_count == 0, f"{case.case_id} spent a provider call"
        assert not [
            finding for finding in evaluation.findings if finding.severity is Severity.CRITICAL
        ], case.case_id


# -- the blocked cases, which the paid comparison never runs --------------


def test_a_blocked_case_is_stopped_before_any_provider_call() -> None:
    """The safety gate is deterministic and pre-LLM, so this needs no budget.

    `budget.planning_cases` filters blocked cases out of the paid comparison --
    correctly, since they spend nothing -- but that also leaves them out of its
    safety numbers. The pre-registered gate is a safety pass rate of 1.000 over
    the held-out set, so the blocked stratum has to be checked somewhere, and
    this is the only place that does it.
    """

    blocked = [
        case
        for case in HELDOUT
        if case.expected_safety_result.required_action_code is not RequiredActionExpectation.NONE
    ]
    assert len(blocked) == 4

    for case in blocked:
        run = run_case(case)
        evaluation = evaluate_case(run)
        assert not run.has_plan, case.case_id
        assert run.status_code == case.expected_safety_result.required_action_code.value
        assert run.llm_call_count == 0, f"{case.case_id} spent a provider call"
        assert not [
            finding for finding in evaluation.findings if finding.severity is Severity.CRITICAL
        ], case.case_id
