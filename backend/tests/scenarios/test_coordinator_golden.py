from __future__ import annotations

import pytest

from backend.app.domain.agents.coordinator import coordinate
from backend.tests.scenarios.decision_golden_fixtures import (
    DECISION_GOLDEN_CASES,
    DecisionGoldenCase,
)


@pytest.mark.parametrize(
    "golden_case",
    DECISION_GOLDEN_CASES,
    ids=lambda case: case.case_code,
)
def test_decision_matches_versioned_golden_contract(
    golden_case: DecisionGoldenCase,
) -> None:
    results = tuple(
        coordinate(golden_case.coordinator_input)
        for _execution_mode in golden_case.explanation_execution_modes
    )

    assert results
    assert all(result == results[0] for result in results)
    expected_fields = set(type(golden_case.expected_final_result).model_fields)
    assert results[0].model_dump(include=expected_fields) == (
        golden_case.expected_final_result.model_dump()
    )
    assert golden_case.coordinator_input.proposals == golden_case.expected_proposals


@pytest.mark.parametrize(
    "golden_case",
    DECISION_GOLDEN_CASES,
    ids=lambda case: case.case_code,
)
def test_same_input_and_versions_repeat_exactly(
    golden_case: DecisionGoldenCase,
) -> None:
    first = coordinate(golden_case.coordinator_input)
    second = coordinate(golden_case.coordinator_input)

    assert first == second
