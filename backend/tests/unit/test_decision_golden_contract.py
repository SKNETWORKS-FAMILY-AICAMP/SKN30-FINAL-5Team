from __future__ import annotations

from backend.app.domain.agents.contracts import REQUIRED_AGENT_TYPES
from backend.app.domain.agents.coordinator import CoordinatorStatusCode
from backend.app.domain.rules.safety import SAFETY_ENGINE_VERSION
from backend.app.modules.decisions.codes import DECISION_POLICY_VERSION
from backend.tests.scenarios.decision_golden_fixtures import DECISION_GOLDEN_CASES
from backend.tests.scenarios.decision_service_golden_fixtures import (
    SERVICE_DECISION_GOLDEN_CASES,
)

_FORBIDDEN_KEYS = {
    "age",
    "date_of_birth",
    "email",
    "full_name",
    "name",
    "raw_health_data",
    "raw_health_record",
    "token",
    "user_id",
}
_REQUIRED_CASE_CODES = {
    "CHRONIC_KNEE_ATTENTION_CAUTION",
    "HEALTHY_KEEP",
    "KNEE_MILD_CAUTION_DOWNSHIFT",
    "KNEE_MILD_APPROVED_REPLACEMENT",
    "KNEE_MODERATE_APPROVED_REPLACEMENT",
    "KNEE_SEVERE_REST",
    "LLM_DISABLED_OR_FAILED_SAME_DECISION",
    "REQUESTED_DURATION_PRESERVING_DOWNSHIFT",
    "REQUIRED_AGENT_FAILURE",
    "SAFETY_VETO_BYPASS_BLOCKED",
    "SERIOUS_ADVERSE_STOP",
    "USER_OVERRIDE_DURATION",
    "WEARABLE_MISSING_MANUAL_FALLBACK",
}


def _all_mapping_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested_key
            for nested_value in value.values()
            for nested_key in _all_mapping_keys(nested_value)
        }
    if isinstance(value, list):
        return {
            nested_key for nested_value in value for nested_key in _all_mapping_keys(nested_value)
        }
    return set()


def test_golden_cases_have_unique_codes_and_complete_version_references() -> None:
    case_codes = tuple(case.case_code for case in DECISION_GOLDEN_CASES)

    assert len(case_codes) == len(set(case_codes))
    assert set(case_codes) == _REQUIRED_CASE_CODES
    for case in DECISION_GOLDEN_CASES:
        versions = case.versions
        coordinator_input = case.coordinator_input
        assert versions.catalog_version == coordinator_input.catalog_version
        assert versions.policy_version == coordinator_input.policy_version
        assert versions.safety_rule_version == coordinator_input.safety_rule_version
        assert versions.duration_rule_version == coordinator_input.duration_rule_version
        assert versions.coordinator_version == coordinator_input.coordinator_version
        assert versions.graph_version
        assert versions.proposal_schema_version
        assert versions.policy_version == DECISION_POLICY_VERSION
        assert versions.safety_rule_version == SAFETY_ENGINE_VERSION


def test_golden_proposals_and_final_result_are_separate_records() -> None:
    final_only_fields = {
        "applied_agent_types",
        "blocked_reason_codes",
        "final_action_code",
        "selected_candidate_id",
        "status_code",
    }
    proposal_only_fields = {
        "agent_type_code",
        "evidence_reference_codes",
        "proposal_status_code",
    }

    for case in DECISION_GOLDEN_CASES:
        assert tuple(proposal.agent_type_code for proposal in case.expected_proposals) == (
            REQUIRED_AGENT_TYPES
        )
        final_fields = set(type(case.expected_final_result).model_fields)
        assert final_only_fields <= final_fields
        assert final_fields.isdisjoint(proposal_only_fields)
        for proposal in case.expected_proposals:
            proposal_fields = set(type(proposal).model_fields)
            assert proposal_only_fields <= proposal_fields
            assert proposal_fields.isdisjoint(final_only_fields)


def test_golden_fixture_contains_no_direct_identifiers_or_raw_health_fields() -> None:
    for case in DECISION_GOLDEN_CASES:
        payload = case.model_dump(mode="json")
        assert _all_mapping_keys(payload).isdisjoint(_FORBIDDEN_KEYS)


def test_plan_and_non_plan_duration_shapes_are_contract_exact() -> None:
    plan_statuses = {CoordinatorStatusCode.PASS, CoordinatorStatusCode.REVISE}

    for case in DECISION_GOLDEN_CASES:
        expected = case.expected_final_result
        if expected.status_code in plan_statuses:
            assert expected.selected_candidate_id is not None
            assert expected.estimated_duration_seconds == expected.requested_duration_minutes * 60
        else:
            assert expected.selected_candidate_id is None
            assert expected.estimated_duration_seconds is None


def test_service_golden_matrix_covers_required_wave_4_paths() -> None:
    case_codes = {case.case_code for case in SERVICE_DECISION_GOLDEN_CASES}

    assert case_codes == {
        "CHRONIC_KNEE_ATTENTION_CAUTION",
        "HEALTHY_KEEP",
        "KNEE_MILD_CAUTION_DOWNSHIFT",
        "KNEE_MODERATE_APPROVED_ALTERNATIVE",
        "KNEE_MODERATE_APPROVED_REPLACEMENT",
        "LLM_DISABLED_OR_FAILED_SAME_DECISION",
        "REQUESTED_DURATION_PRESERVING_DOWNSHIFT",
        "SAFETY_VETO_BYPASS_BLOCKED",
        "WEARABLE_MISSING_MANUAL_FALLBACK",
    }
    assert len(case_codes) == len(SERVICE_DECISION_GOLDEN_CASES)
    for case in SERVICE_DECISION_GOLDEN_CASES:
        assert case.requested_duration_minutes > 0
        assert case.profile_duration_minutes > 0
        assert case.expected.action_code


def test_manual_wearable_fallback_machine_codes_remain_in_golden_contract() -> None:
    case = next(
        item
        for item in DECISION_GOLDEN_CASES
        if item.case_code == "WEARABLE_MISSING_MANUAL_FALLBACK"
    )
    feasibility = next(
        proposal
        for proposal in case.expected_proposals
        if proposal.agent_type_code.value == "FEASIBILITY"
    )

    assert feasibility.reason_codes == (
        "MANUAL_CHECK_IN_FALLBACK",
        "WEARABLE_UNAVAILABLE",
    )
    assert feasibility.requested_duration_minutes == 40
    assert feasibility.estimated_duration_seconds == 2400
