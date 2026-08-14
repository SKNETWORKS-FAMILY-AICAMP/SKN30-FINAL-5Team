from __future__ import annotations

import pytest

from backend.app.domain.agents.coordinator import CoordinatorStatusCode, coordinate
from backend.app.domain.agents.reproducibility import (
    DecisionInputSnapshot,
    DecisionReplayEnvelope,
    DecisionVersionBundle,
    FinalRoutineOptionLink,
    decision_input_hash,
    successful_decision_response_allowed,
)
from backend.app.domain.rules.safety import SafetyStatusCode
from backend.tests.scenarios.decision_golden_fixtures import (
    DECISION_GOLDEN_CASES,
    DecisionGoldenCase,
)


def _envelope(case: DecisionGoldenCase) -> DecisionReplayEnvelope:
    coordinator_input = case.coordinator_input
    result = coordinate(coordinator_input)
    final_option = None
    if result.selected_candidate_id is not None and result.final_action_code is not None:
        final_option = FinalRoutineOptionLink(
            action_code=result.final_action_code,
            selected_candidate_id=result.selected_candidate_id,
        )
    return DecisionReplayEnvelope(
        input_snapshot=DecisionInputSnapshot(
            context_reference_codes=case.context_reference_codes,
            profile_duration_minutes=coordinator_input.profile_duration_minutes,
            requested_duration_minutes=coordinator_input.requested_duration_minutes,
            duration_adjustment_source_code=(coordinator_input.duration_adjustment_source_code),
        ),
        versions=DecisionVersionBundle(
            catalog_version=case.versions.catalog_version,
            policy_version=case.versions.policy_version,
            safety_rule_version=case.versions.safety_rule_version,
            duration_rule_version=case.versions.duration_rule_version,
            graph_version=case.versions.graph_version,
            coordinator_version=case.versions.coordinator_version,
            proposal_schema_version=case.versions.proposal_schema_version,
        ),
        proposals=coordinator_input.proposals,
        candidates=coordinator_input.candidates,
        coordinator_result=result,
        final_routine_option=final_option,
    )


@pytest.mark.parametrize(
    "golden_case",
    DECISION_GOLDEN_CASES,
    ids=lambda case: case.case_code,
)
def test_saved_records_round_trip_and_replay_same_decision(
    golden_case: DecisionGoldenCase,
) -> None:
    stored = _envelope(golden_case)
    retrieved = DecisionReplayEnvelope.model_validate_json(stored.model_dump_json())

    assert retrieved.versions == stored.versions
    assert retrieved.proposals == stored.proposals
    assert coordinate(retrieved.to_coordinator_input()) == stored.coordinator_result
    assert decision_input_hash(retrieved.input_snapshot) == decision_input_hash(
        stored.input_snapshot
    )


@pytest.mark.parametrize(
    "golden_case",
    DECISION_GOLDEN_CASES,
    ids=lambda case: case.case_code,
)
def test_proposal_and_candidate_input_order_does_not_change_replay(
    golden_case: DecisionGoldenCase,
) -> None:
    stored = _envelope(golden_case)
    reordered = DecisionReplayEnvelope(
        input_snapshot=DecisionInputSnapshot(
            **{
                **stored.input_snapshot.model_dump(),
                "context_reference_codes": tuple(
                    reversed(stored.input_snapshot.context_reference_codes)
                ),
            }
        ),
        versions=stored.versions,
        proposals=tuple(reversed(stored.proposals)),
        candidates=tuple(reversed(stored.candidates)),
        coordinator_result=stored.coordinator_result,
        final_routine_option=stored.final_routine_option,
    )

    assert decision_input_hash(reordered.input_snapshot) == decision_input_hash(
        stored.input_snapshot
    )
    assert coordinate(reordered.to_coordinator_input()) == stored.coordinator_result


def test_required_agent_failure_remains_non_publishable_after_retrieval() -> None:
    case = next(
        item for item in DECISION_GOLDEN_CASES if item.case_code == "REQUIRED_AGENT_FAILURE"
    )
    retrieved = DecisionReplayEnvelope.model_validate_json(_envelope(case).model_dump_json())

    assert retrieved.coordinator_result.status_code is CoordinatorStatusCode.FAILED
    assert retrieved.final_routine_option is None
    assert not successful_decision_response_allowed(
        result=retrieved.coordinator_result,
        persistence_succeeded=True,
    )


@pytest.mark.parametrize(
    "case_code",
    ("KNEE_SEVERE_REST", "SAFETY_VETO_BYPASS_BLOCKED", "SERIOUS_ADVERSE_STOP"),
)
def test_safety_blocked_and_veto_remain_planless_after_retrieval(case_code: str) -> None:
    case = next(item for item in DECISION_GOLDEN_CASES if item.case_code == case_code)
    retrieved = DecisionReplayEnvelope.model_validate_json(_envelope(case).model_dump_json())

    assert retrieved.coordinator_result.status_code is CoordinatorStatusCode.BLOCKED
    assert retrieved.coordinator_result.safety_status_code is SafetyStatusCode.BLOCKED
    assert retrieved.coordinator_result.selected_candidate_id is None
    assert retrieved.final_routine_option is None


@pytest.mark.parametrize(
    "golden_case",
    DECISION_GOLDEN_CASES,
    ids=lambda case: case.case_code,
)
def test_database_failure_blocks_success_publication(
    golden_case: DecisionGoldenCase,
) -> None:
    result = _envelope(golden_case).coordinator_result

    assert not successful_decision_response_allowed(
        result=result,
        persistence_succeeded=False,
    )
