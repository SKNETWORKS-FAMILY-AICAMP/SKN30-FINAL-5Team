from __future__ import annotations

import socket
from dataclasses import replace

import pytest

from backend.app.domain.agents.contracts import REQUIRED_AGENT_TYPES, AgentTypeCode
from backend.app.domain.agents.coordinator import CoordinatorInput, coordinate
from backend.app.domain.rules.duration import DURATION_RULE_VERSION
from backend.app.modules.decisions.codes import DECISION_POLICY_VERSION
from backend.app.modules.decisions.explanations import ExplanationSourceCode
from backend.app.modules.decisions.ports import NarrationCompletion, NarrationPrompt
from backend.tests.scenarios.decision_service_golden_fixtures import (
    SERVICE_DECISION_GOLDEN_CASES,
    ServiceDecisionGoldenCase,
    case_by_code,
    execute_service_case,
    safety_proposal,
)


@pytest.mark.parametrize(
    "golden_case",
    SERVICE_DECISION_GOLDEN_CASES,
    ids=lambda case: case.case_code,
)
def test_production_service_matches_scenario_matrix(
    golden_case: ServiceDecisionGoldenCase,
) -> None:
    response, repository = execute_service_case(golden_case)
    assert repository.persisted is not None
    result = repository.persisted["result"]
    proposals = repository.persisted["proposals"]
    prepared = repository.persisted["assembly"]
    safety = safety_proposal(repository)
    requested_seconds = golden_case.requested_duration_minutes * 60

    assert tuple(proposal.agent_type_code for proposal in proposals) == REQUIRED_AGENT_TYPES
    assert all(
        proposal.requested_duration_minutes == golden_case.requested_duration_minutes
        for proposal in proposals
    )
    assert all(proposal.estimated_duration_seconds == requested_seconds for proposal in proposals)
    assert result.requested_duration_minutes == golden_case.requested_duration_minutes
    assert result.final_action_code.value == golden_case.expected.action_code
    assert result.safety_status_code is golden_case.expected.safety_status_code
    assert safety.safety_status_code is golden_case.expected.safety_status_code
    assert safety.safety_vetoed is golden_case.expected.safety_vetoed
    assert safety.excluded_exercise_ids == golden_case.expected.excluded_exercise_ids

    if golden_case.expected.selected_candidate_suffix is None:
        assert result.selected_candidate_id is None
        assert response.final_plan is None
        assert result.estimated_duration_seconds is None
        assert all(
            candidate.estimated_duration_seconds == requested_seconds
            for candidate in prepared.coordinator_candidates
        )
    else:
        assert result.selected_candidate_id is not None
        assert result.selected_candidate_id.endswith(golden_case.expected.selected_candidate_suffix)
        assert result.estimated_duration_seconds == requested_seconds
        assert response.final_plan is not None
        assert (
            response.final_plan.requested_duration_minutes == golden_case.requested_duration_minutes
        )
        assert response.final_plan.estimated_duration_seconds == requested_seconds
        selected = next(
            candidate
            for candidate in prepared.coordinator_candidates
            if candidate.candidate_id == result.selected_candidate_id
        )
        assert selected.estimated_duration_seconds == requested_seconds
        assert all(
            candidate.estimated_duration_seconds == requested_seconds
            for candidate in prepared.coordinator_candidates
        )

    if golden_case.expected.replacement_exercise_id is not None:
        selected = next(
            candidate
            for candidate in prepared.coordinator_candidates
            if candidate.candidate_id == result.selected_candidate_id
        )
        assert golden_case.expected.replacement_exercise_id in selected.exercise_ids
        assert not set(selected.exercise_ids) & set(golden_case.expected.excluded_exercise_ids)
        assert "ALTERNATIVE/golden-approved-relation" in safety.evidence_reference_codes


def test_wearable_missing_uses_identifier_free_manual_checkin_path() -> None:
    case = case_by_code("WEARABLE_MISSING_MANUAL_FALLBACK")
    response, repository = execute_service_case(case)
    assert repository.persisted is not None
    snapshot = repository.persisted["input_snapshot"]

    assert case.wearable_input_mode == "MANUAL_CHECK_IN_ONLY"
    assert response.action_code == "KEEP"
    assert response.requested_duration_minutes == 40
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 2400
    assert "wearable" not in str(snapshot).lower()
    assert all(
        proposal.requested_duration_minutes == 40 for proposal in repository.persisted["proposals"]
    )


def test_healthy_case_keeps_original_candidate_and_duration_for_all_agents() -> None:
    case = case_by_code("HEALTHY_KEEP")
    response, repository = execute_service_case(case)
    assert repository.persisted is not None
    result = repository.persisted["result"]
    proposals = repository.persisted["proposals"]
    safety = safety_proposal(repository)

    assert response.action_code == "KEEP"
    assert response.safety_status_code == "PASS"
    assert response.requested_duration_minutes == 40
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 2400
    assert result.selected_candidate_id == "candidate-original"
    assert result.requested_duration_minutes == 40
    assert result.estimated_duration_seconds == 2400
    assert tuple(proposal.agent_type_code for proposal in proposals) == REQUIRED_AGENT_TYPES
    assert all(proposal.requested_duration_minutes == 40 for proposal in proposals)
    assert all(proposal.estimated_duration_seconds == 2400 for proposal in proposals)
    assert safety.safety_status_code.value == "PASS"
    assert safety.safety_vetoed is False
    assert safety.excluded_exercise_ids == ()


def test_downshift_uses_explicit_override_without_reapplying_profile_duration() -> None:
    case = case_by_code("REQUESTED_DURATION_PRESERVING_DOWNSHIFT")
    response, repository = execute_service_case(case)
    assert repository.persisted is not None
    result = repository.persisted["result"]
    proposals = repository.persisted["proposals"]
    prepared = repository.persisted["assembly"]
    training = next(
        proposal for proposal in proposals if proposal.agent_type_code is AgentTypeCode.TRAINING
    )
    selected = next(
        candidate
        for candidate in prepared.coordinator_candidates
        if candidate.candidate_id == result.selected_candidate_id
    )

    assert case.profile_duration_minutes == 40
    assert case.requested_duration_minutes == 30
    assert case.duration_source.value == "USER_OVERRIDE"
    assert response.action_code == "DOWNSHIFT"
    assert response.requested_duration_minutes == 30
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 1800
    assert result.requested_duration_minutes == 30
    assert result.estimated_duration_seconds == 1800
    assert training.required_goal_tags == ("GENERAL_FITNESS",)
    assert selected.goal_tags == ("GENERAL_FITNESS",)
    assert tuple(code.value for code in selected.downshift_adjustment_codes) == (
        "INTENSITY_REDUCED",
    )
    assert all(proposal.requested_duration_minutes == 30 for proposal in proposals)
    assert all(proposal.estimated_duration_seconds == 1800 for proposal in proposals)


def test_mild_caution_lowers_load_without_removing_maintainable_exercise() -> None:
    case = case_by_code("KNEE_MILD_CAUTION_DOWNSHIFT")
    response, repository = execute_service_case(case)
    assert repository.persisted is not None
    prepared = repository.persisted["assembly"]
    result = repository.persisted["result"]
    safety = safety_proposal(repository)
    selected = next(
        candidate
        for candidate in prepared.adjusted_candidates
        if candidate.candidate.candidate_id == result.selected_candidate_id
    )

    assert response.action_code == "DOWNSHIFT"
    assert response.safety_status_code == "REVISE"
    assert response.requested_duration_minutes == 40
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 2400
    assert safety.safety_vetoed is False
    assert safety.excluded_exercise_ids == ()
    assert safety.reason_codes == ("SAFETY_CAUTION_APPLIED",)
    assert selected.candidate.exercise_ids == prepared.candidate.exercise_ids
    assert all(item.intensity_code == "LOW" for item in selected.items)
    assert prepared.items[0].intensity_code == "MODERATE"


def test_moderate_exclusion_uses_only_approved_replacement_and_preserves_duration() -> None:
    case = case_by_code("KNEE_MODERATE_APPROVED_ALTERNATIVE")
    response, repository = execute_service_case(case)
    assert repository.persisted is not None
    prepared = repository.persisted["assembly"]
    result = repository.persisted["result"]
    proposals = repository.persisted["proposals"]
    safety = safety_proposal(repository)
    selected = next(
        candidate
        for candidate in prepared.coordinator_candidates
        if candidate.candidate_id == result.selected_candidate_id
    )

    assert response.action_code == "CHANGE"
    assert response.safety_status_code == "REVISE"
    assert response.requested_duration_minutes == 40
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 2400
    assert safety.safety_vetoed is True
    assert safety.excluded_exercise_ids == case.expected.excluded_exercise_ids
    assert case.expected.replacement_exercise_id in selected.exercise_ids
    assert not set(selected.exercise_ids) & set(safety.excluded_exercise_ids)
    assert "ALTERNATIVE/golden-approved-relation" in safety.evidence_reference_codes
    assert all(proposal.requested_duration_minutes == 40 for proposal in proposals)
    assert all(proposal.estimated_duration_seconds == 2400 for proposal in proposals)


class UnreachableNarrationProvider:
    """Stands in for any provider outage: timeout, quota, malformed response."""

    def __init__(self) -> None:
        self.calls = 0

    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        self.calls += 1
        raise TimeoutError("provider timeout")


def test_llm_disabled_and_failure_modes_cannot_change_decision_or_use_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = case_by_code("LLM_DISABLED_OR_FAILED_SAME_DECISION")

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("golden decision attempted an external network call")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    disabled_response, disabled_repository = execute_service_case(case)
    provider = UnreachableNarrationProvider()
    failed_response, failed_repository = execute_service_case(case, narration_provider=provider)
    assert disabled_repository.persisted is not None
    assert failed_repository.persisted is not None

    assert case.explanation_execution_modes == ("LLM_DISABLED", "LLM_FAILED")
    assert provider.calls == 1
    assert disabled_repository.persisted["proposals"] == failed_repository.persisted["proposals"]
    assert disabled_repository.persisted["result"] == failed_repository.persisted["result"]
    assert disabled_repository.persisted["input_hash"] == failed_repository.persisted["input_hash"]
    assert disabled_response.action_code == failed_response.action_code == "KEEP"
    assert disabled_response.final_plan is not None
    assert failed_response.final_plan is not None
    assert disabled_response.final_plan.estimated_duration_seconds == 2400
    assert failed_response.final_plan.estimated_duration_seconds == 2400
    # 두 mode 모두 검수된 템플릿 문구를 남기고 model/prompt version을 기록하지 않는다.
    disabled_explanation = disabled_repository.persisted["explanation"]
    failed_explanation = failed_repository.persisted["explanation"]
    assert disabled_explanation.source_code is ExplanationSourceCode.TEMPLATE
    assert failed_explanation.source_code is ExplanationSourceCode.TEMPLATE
    assert failed_explanation.summary == disabled_explanation.summary
    assert failed_explanation.model_code is None
    assert failed_explanation.prompt_version is None
    assert disabled_explanation.fallback_reason_code == "LLM_DISABLED"
    assert failed_explanation.fallback_reason_code == "LLM_PROVIDER_FAILED"


@pytest.mark.parametrize(
    "case_code",
    ("SAFETY_VETO_BYPASS_BLOCKED",),
)
def test_safety_veto_survives_other_agent_keep_proposals_and_replay(case_code: str) -> None:
    case = case_by_code(case_code)
    response, repository = execute_service_case(case)
    assert repository.persisted is not None
    proposals = repository.persisted["proposals"]
    stored_result = repository.persisted["result"]
    prepared = repository.persisted["assembly"]
    safety = safety_proposal(repository)

    assert any(
        proposal.agent_type_code is not AgentTypeCode.SAFETY
        and proposal.recommended_action_code is not None
        for proposal in proposals
    )
    assert safety.safety_vetoed is True
    assert response.action_code == "REST"
    assert response.requested_duration_minutes == 40
    assert response.final_plan is None
    assert stored_result.selected_candidate_id is None
    replayed = coordinate(
        CoordinatorInput(
            proposals=tuple(reversed(proposals)),
            candidates=tuple(reversed(prepared.coordinator_candidates)),
            profile_duration_minutes=case.profile_duration_minutes,
            requested_duration_minutes=case.requested_duration_minutes,
            duration_adjustment_source_code=case.duration_source,
            policy_version=DECISION_POLICY_VERSION,
            catalog_version=prepared.catalog_version,
            catalog_status_code=prepared.catalog_status_code,
            catalog_review_status_code=prepared.catalog_review_status_code,
            catalog_production_eligible=prepared.catalog_production_eligible,
            catalog_activated=prepared.catalog_activated,
            safety_rule_version=stored_result.safety_rule_version,
            duration_rule_version=DURATION_RULE_VERSION,
        )
    )
    assert replayed == stored_result
    assert replayed.selected_candidate_id is None


def test_attention_area_order_and_duplicates_have_one_canonical_snapshot_and_hash() -> None:
    canonical = case_by_code("CHRONIC_KNEE_ATTENTION_CAUTION")
    reordered = replace(canonical, attention_area_codes=("KNEE", "KNEE"))
    canonical_response, canonical_repository = execute_service_case(canonical)
    reordered_response, reordered_repository = execute_service_case(reordered)
    assert canonical_repository.persisted is not None
    assert reordered_repository.persisted is not None

    assert canonical_repository.assembly.context.discomforts == ()
    assert reordered_repository.assembly.context.attention_area_codes == ("KNEE",)
    assert (
        canonical_repository.persisted["input_snapshot"]
        == reordered_repository.persisted["input_snapshot"]
    )
    assert (
        canonical_repository.persisted["input_hash"] == reordered_repository.persisted["input_hash"]
    )
    assert canonical_repository.persisted["result"] == reordered_repository.persisted["result"]
    assert canonical_response.action_code == reordered_response.action_code == "DOWNSHIFT"
    assert safety_proposal(canonical_repository).reason_codes == ("ATTENTION_AREA_CAUTION_APPLIED",)
    assert safety_proposal(canonical_repository).safety_vetoed is False
    assert safety_proposal(canonical_repository).excluded_exercise_ids == ()
    assert canonical_response.requested_duration_minutes == 40
    assert canonical_response.final_plan is not None
    assert reordered_response.final_plan is not None
    assert canonical_response.final_plan.estimated_duration_seconds == 2400
    assert reordered_response.final_plan.estimated_duration_seconds == 2400
