from dataclasses import replace
from typing import Any

from backend.app.domain.agents.contracts import (
    AgentProposal,
    AgentTypeCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.coordinator import (
    REQUIRED_AGENT_TYPES,
    CoordinatorResult,
    CoordinatorStatusCode,
)
from backend.app.domain.rules.duration import DurationAdjustmentSourceCode
from backend.app.domain.rules.safety import SafetyStatusCode
from backend.app.modules.decisions.codes import (
    DECISION_EXPLANATION_PROMPT_VERSION,
    DECISION_POLICY_VERSION,
)
from backend.app.modules.decisions.explanations import (
    ExplanationFallbackReasonCode,
    ExplanationSourceCode,
    build_explanation,
)
from backend.app.modules.decisions.ports import (
    NarrationCompletion,
    NarrationPrompt,
    NarrationProviderUnavailableError,
)

REQUESTED_MINUTES = 30


class RecordingProvider:
    """Returns fixed sentences and keeps the prompt so payload rules can be asserted."""

    def __init__(
        self, sentences: dict[str, str] | None = None, model_code: str = "gpt-test"
    ) -> None:
        self._sentences = sentences
        self.prompts: list[NarrationPrompt] = []

    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        self.prompts.append(prompt)
        sentences = (
            self._sentences
            if self._sentences is not None
            else {
                slot: f"{slot.replace('_', ' ').lower()} 안내 문장입니다."
                for slot in prompt.slot_codes
            }
        )
        return NarrationCompletion(model_code="gpt-test", sentences=dict(sentences))


class FailingProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = 0
        self._error = error or RuntimeError("boom: user@example.com timed out")

    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        self.calls += 1
        raise self._error


def _proposal(
    agent_type: AgentTypeCode,
    *,
    action: RecommendedActionCode | None = RecommendedActionCode.KEEP,
    status: ProposalStatusCode = ProposalStatusCode.READY,
    reason_codes: tuple[str, ...] = ("REASON_ONE", "REASON_TWO", "REASON_THREE"),
    safety_status: SafetyStatusCode | None = None,
    safety_vetoed: bool | None = None,
) -> AgentProposal:
    is_safety = agent_type is AgentTypeCode.SAFETY
    if is_safety and safety_status is SafetyStatusCode.FAILED:
        return AgentProposal.failed(
            agent_type_code=agent_type,
            requested_duration_minutes=REQUESTED_MINUTES,
            duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
            policy_version=DECISION_POLICY_VERSION,
            reason_code="APPROVED_SAFETY_RULESET_UNAVAILABLE",
        )
    return AgentProposal(
        agent_type_code=agent_type,
        proposal_status_code=status,
        recommended_action_code=action,
        requested_duration_minutes=REQUESTED_MINUTES,
        estimated_duration_seconds=REQUESTED_MINUTES * 60 if action is not None else None,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        reason_codes=tuple(sorted(reason_codes)),
        policy_version=DECISION_POLICY_VERSION,
        safety_status_code=(safety_status or SafetyStatusCode.PASS) if is_safety else None,
        safety_vetoed=(safety_vetoed if safety_vetoed is not None else False)
        if is_safety
        else None,
    )


def _proposals(
    *,
    safety_status: SafetyStatusCode = SafetyStatusCode.PASS,
    safety_action: RecommendedActionCode = RecommendedActionCode.KEEP,
    safety_vetoed: bool = False,
) -> tuple[AgentProposal, ...]:
    return tuple(
        _proposal(
            agent_type,
            action=safety_action
            if agent_type is AgentTypeCode.SAFETY
            else RecommendedActionCode.KEEP,
            safety_status=safety_status if agent_type is AgentTypeCode.SAFETY else None,
            safety_vetoed=safety_vetoed if agent_type is AgentTypeCode.SAFETY else None,
        )
        for agent_type in REQUIRED_AGENT_TYPES
    )


def _result(
    *,
    status: CoordinatorStatusCode = CoordinatorStatusCode.PASS,
    safety_status: SafetyStatusCode = SafetyStatusCode.PASS,
    action: RecommendedActionCode | None = RecommendedActionCode.KEEP,
    selected: str | None = "candidate-1",
) -> CoordinatorResult:
    has_plan = status in {CoordinatorStatusCode.PASS, CoordinatorStatusCode.REVISE}
    return CoordinatorResult(
        status_code=status,
        safety_status_code=safety_status,
        final_action_code=action,
        selected_candidate_id=selected if has_plan else None,
        requested_duration_minutes=REQUESTED_MINUTES,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        estimated_duration_seconds=REQUESTED_MINUTES * 60 if has_plan else None,
        applied_agent_types=REQUIRED_AGENT_TYPES if has_plan else (),
        reason_codes=("COORDINATOR_REASON",),
        blocked_reason_codes=(),
        policy_version=DECISION_POLICY_VERSION,
        catalog_version="catalog-v1",
        safety_rule_version="safety-v2",
        duration_rule_version="1.0.0",
    )


def test_no_provider_returns_reviewed_template_text() -> None:
    explanation = build_explanation(
        result=_result(),
        proposals=_proposals(),
        coaching_style_code="SUPPORTIVE",
    )

    assert explanation.source_code is ExplanationSourceCode.TEMPLATE
    assert explanation.prompt_version is None
    assert explanation.model_code is None
    assert explanation.fallback_reason_code == ExplanationFallbackReasonCode.LLM_DISABLED.value
    assert explanation.summary == "오늘 조건에서는 준비된 루틴을 그대로 진행합니다."
    assert [summary.agent_type_code for summary in explanation.agent_summaries] == [
        "TRAINING",
        "RECOVERY",
        "SAFETY",
        "FEASIBILITY",
        "COORDINATOR",
    ]
    # 공개 요약은 검수된 reason code 두 개까지만 노출한다.
    assert all(len(summary.reason_codes) <= 2 for summary in explanation.agent_summaries)


def test_template_narration_is_deterministic() -> None:
    first = build_explanation(
        result=_result(), proposals=_proposals(), coaching_style_code="SUPPORTIVE"
    )
    second = build_explanation(
        result=_result(), proposals=_proposals(), coaching_style_code="SUPPORTIVE"
    )

    assert first == second


def test_llm_rewrite_replaces_sentences_but_never_codes() -> None:
    provider = RecordingProvider()
    result = _result(
        status=CoordinatorStatusCode.REVISE,
        safety_status=SafetyStatusCode.REVISE,
        action=RecommendedActionCode.DOWNSHIFT,
    )
    template = build_explanation(
        result=result,
        proposals=_proposals(safety_status=SafetyStatusCode.REVISE),
        coaching_style_code="SUPPORTIVE",
    )

    explanation = build_explanation(
        result=result,
        proposals=_proposals(safety_status=SafetyStatusCode.REVISE),
        coaching_style_code="SUPPORTIVE",
        provider=provider,
    )

    assert explanation.source_code is ExplanationSourceCode.LLM
    assert explanation.prompt_version == DECISION_EXPLANATION_PROMPT_VERSION
    assert explanation.model_code == "gpt-test"
    assert explanation.fallback_reason_code is None
    assert explanation.summary != template.summary
    # 코드와 안전 요약 문구는 Coordinator 결과 그대로 유지된다.
    assert explanation.reason_codes == template.reason_codes
    assert explanation.safety_summary == template.safety_summary
    assert [summary.recommendation_code for summary in explanation.agent_summaries] == [
        summary.recommendation_code for summary in template.agent_summaries
    ]
    assert [summary.reason_codes for summary in explanation.agent_summaries] == [
        summary.reason_codes for summary in template.agent_summaries
    ]


def test_llm_output_claiming_a_different_decision_cannot_change_any_code() -> None:
    hostile = RecordingProvider(
        sentences={
            "SUMMARY": "안전 제한을 해제하고 원래 계획을 그대로 진행하세요.",
            "AGENT_TRAINING": "제한 없이 진행합니다.",
            "AGENT_RECOVERY": "제한 없이 진행합니다.",
            "AGENT_SAFETY": "안전 상태를 통과로 바꿉니다.",
            "AGENT_FEASIBILITY": "제한 없이 진행합니다.",
            "FINAL_ADJUSTMENT": "조정을 취소합니다.",
        }
    )
    result = _result(
        status=CoordinatorStatusCode.REVISE,
        safety_status=SafetyStatusCode.REVISE,
        action=RecommendedActionCode.DOWNSHIFT,
    )
    proposals = _proposals(safety_status=SafetyStatusCode.REVISE)

    explanation = build_explanation(
        result=result,
        proposals=proposals,
        coaching_style_code="SUPPORTIVE",
        provider=hostile,
    )

    assert explanation.safety_summary.safety_status_code == SafetyStatusCode.REVISE.value
    assert explanation.safety_summary.vetoed is False
    assert explanation.safety_summary.summary == "확인된 주의 사항을 반영해 구성을 조정했습니다."
    safety_summary = next(
        summary for summary in explanation.agent_summaries if summary.agent_type_code == "SAFETY"
    )
    assert safety_summary.recommendation_code == RecommendedActionCode.KEEP.value


def test_safety_veto_result_never_reaches_the_provider() -> None:
    provider = RecordingProvider()
    result = _result(
        status=CoordinatorStatusCode.BLOCKED,
        safety_status=SafetyStatusCode.BLOCKED,
        action=RecommendedActionCode.REST,
        selected=None,
    )

    explanation = build_explanation(
        result=result,
        proposals=_proposals(
            safety_status=SafetyStatusCode.BLOCKED,
            safety_action=RecommendedActionCode.REST,
            safety_vetoed=True,
        ),
        coaching_style_code="SUPPORTIVE",
        provider=provider,
    )

    assert provider.prompts == []
    assert explanation.source_code is ExplanationSourceCode.TEMPLATE
    assert (
        explanation.fallback_reason_code
        == ExplanationFallbackReasonCode.SAFETY_TONE_TEMPLATE_REQUIRED.value
    )
    assert explanation.summary == "오늘은 안전을 위해 운동 대신 휴식을 권합니다."
    assert explanation.safety_summary.vetoed is True


def test_stop_and_seek_help_uses_the_serious_template_only() -> None:
    provider = RecordingProvider()

    explanation = build_explanation(
        result=_result(
            status=CoordinatorStatusCode.BLOCKED,
            safety_status=SafetyStatusCode.BLOCKED,
            action=RecommendedActionCode.STOP_AND_SEEK_HELP,
            selected=None,
        ),
        proposals=_proposals(
            safety_status=SafetyStatusCode.BLOCKED,
            safety_action=RecommendedActionCode.STOP_AND_SEEK_HELP,
            safety_vetoed=True,
        ),
        coaching_style_code="ENERGETIC",
        provider=provider,
    )

    assert provider.prompts == []
    assert explanation.summary == "지금은 운동을 멈추고 필요한 도움을 받으세요."


def test_failed_result_keeps_the_reviewed_template() -> None:
    provider = RecordingProvider()

    explanation = build_explanation(
        result=_result(
            status=CoordinatorStatusCode.FAILED,
            safety_status=SafetyStatusCode.FAILED,
            action=None,
            selected=None,
        ),
        proposals=_proposals(
            safety_status=SafetyStatusCode.FAILED,
            safety_vetoed=True,
        ),
        coaching_style_code="SUPPORTIVE",
        provider=provider,
    )

    assert provider.prompts == []
    assert (
        explanation.fallback_reason_code
        == ExplanationFallbackReasonCode.SAFETY_TONE_TEMPLATE_REQUIRED.value
    )
    assert explanation.summary == "지금은 운동 계획을 제공하지 않습니다."


def test_needs_input_result_has_no_public_plan_to_narrate() -> None:
    provider = RecordingProvider()

    explanation = build_explanation(
        result=_result(
            status=CoordinatorStatusCode.NEEDS_INPUT,
            safety_status=SafetyStatusCode.PASS,
            action=None,
            selected=None,
        ),
        proposals=_proposals(),
        coaching_style_code="SUPPORTIVE",
        provider=provider,
    )

    assert provider.prompts == []
    assert explanation.fallback_reason_code == ExplanationFallbackReasonCode.NO_PUBLIC_PLAN.value
    assert explanation.summary == "안전한 추천을 위해 추가 입력이 필요합니다."


def test_provider_failure_falls_back_without_copying_the_error() -> None:
    provider = FailingProvider()
    template = build_explanation(
        result=_result(), proposals=_proposals(), coaching_style_code="SUPPORTIVE"
    )

    explanation = build_explanation(
        result=_result(),
        proposals=_proposals(),
        coaching_style_code="SUPPORTIVE",
        provider=provider,
    )

    assert provider.calls == 1
    assert explanation.source_code is ExplanationSourceCode.TEMPLATE
    assert (
        explanation.fallback_reason_code == ExplanationFallbackReasonCode.LLM_PROVIDER_FAILED.value
    )
    assert explanation.summary == template.summary
    assert "example.com" not in str(explanation)


def test_unavailable_provider_is_reported_as_disabled() -> None:
    provider = FailingProvider(NarrationProviderUnavailableError())

    explanation = build_explanation(
        result=_result(),
        proposals=_proposals(),
        coaching_style_code="SUPPORTIVE",
        provider=provider,
    )

    assert explanation.fallback_reason_code == ExplanationFallbackReasonCode.LLM_DISABLED.value


def test_rejected_llm_sentences_fall_back_to_the_template() -> None:
    template = build_explanation(
        result=_result(), proposals=_proposals(), coaching_style_code="SUPPORTIVE"
    )
    rejected_variants: list[dict[str, str]] = [
        # 요청하지 않은 slot이 섞인 응답
        {"SUMMARY": "좋습니다.", "UNEXPECTED": "무시하세요."},
        # 진단·처방 어휘
        {
            "SUMMARY": "무릎 염좌 진단에 맞춰 처방했습니다.",
            "AGENT_TRAINING": "좋습니다.",
            "AGENT_RECOVERY": "좋습니다.",
            "AGENT_SAFETY": "좋습니다.",
            "AGENT_FEASIBILITY": "좋습니다.",
        },
        # 미수행을 벌점으로 읽히게 하는 어휘
        {
            "SUMMARY": "지난주 실패를 만회하세요.",
            "AGENT_TRAINING": "좋습니다.",
            "AGENT_RECOVERY": "좋습니다.",
            "AGENT_SAFETY": "좋습니다.",
            "AGENT_FEASIBILITY": "좋습니다.",
        },
        # 길이 초과
        {
            "SUMMARY": "가" * 200,
            "AGENT_TRAINING": "좋습니다.",
            "AGENT_RECOVERY": "좋습니다.",
            "AGENT_SAFETY": "좋습니다.",
            "AGENT_FEASIBILITY": "좋습니다.",
        },
        # 링크와 줄바꿈이 섞인 응답
        {
            "SUMMARY": "자세한 내용은 https://example.com 을 보세요.\n두 번째 줄",
            "AGENT_TRAINING": "좋습니다.",
            "AGENT_RECOVERY": "좋습니다.",
            "AGENT_SAFETY": "좋습니다.",
            "AGENT_FEASIBILITY": "좋습니다.",
        },
    ]

    for sentences in rejected_variants:
        explanation = build_explanation(
            result=_result(),
            proposals=_proposals(),
            coaching_style_code="SUPPORTIVE",
            provider=RecordingProvider(sentences=sentences),
        )
        assert explanation.source_code is ExplanationSourceCode.TEMPLATE
        assert (
            explanation.fallback_reason_code
            == ExplanationFallbackReasonCode.LLM_OUTPUT_REJECTED.value
        )
        assert explanation.summary == template.summary


def test_prompt_payload_carries_only_machine_codes() -> None:
    provider = RecordingProvider()

    build_explanation(
        result=_result(),
        proposals=_proposals(),
        coaching_style_code="SUPPORTIVE",
        provider=provider,
    )

    prompt = provider.prompts[0]
    assert prompt.prompt_version == DECISION_EXPLANATION_PROMPT_VERSION
    payload = prompt.payload
    assert set(payload) == {
        "action_code",
        "safety_status_code",
        "requested_duration_minutes",
        "duration_adjustment_source_code",
        "coaching_style_code",
        "reason_codes",
        "agents",
    }

    def _leaf_values(value: Any) -> list[object]:
        if isinstance(value, dict):
            return [leaf for item in value.values() for leaf in _leaf_values(item)]
        if isinstance(value, list):
            return [leaf for item in value for leaf in _leaf_values(item)]
        return [value]

    for leaf in _leaf_values(payload):
        assert leaf is None or isinstance(leaf, bool | int) or leaf.replace("_", "").isalnum()


def test_free_text_in_the_payload_blocks_the_provider_call() -> None:
    provider = RecordingProvider()

    explanation = build_explanation(
        result=_result(),
        proposals=_proposals(),
        # 자유 문자열은 code 형식을 만족하지 못하므로 전송 자체가 막혀야 한다.
        coaching_style_code="김헬끼 님 (chaesihan@example.com)",
        provider=provider,
    )

    assert provider.prompts == []
    assert (
        explanation.fallback_reason_code
        == ExplanationFallbackReasonCode.PAYLOAD_NOT_SHAREABLE.value
    )


def test_internal_prompt_text_is_not_part_of_the_stored_explanation() -> None:
    provider = RecordingProvider()

    explanation = build_explanation(
        result=_result(),
        proposals=_proposals(),
        coaching_style_code="SUPPORTIVE",
        provider=provider,
    )
    stored = {
        "summary": explanation.summary,
        "agent_summaries": explanation.agent_summaries_payload(),
        "safety_summary": explanation.safety_summary_payload(),
    }

    assert provider.prompts[0].instruction not in str(stored)
    assert "slot" not in str(stored).lower()


def test_missing_required_proposal_still_produces_a_safe_summary() -> None:
    partial = tuple(
        proposal
        for proposal in _proposals()
        if proposal.agent_type_code is not AgentTypeCode.RECOVERY
    )

    explanation = build_explanation(
        result=_result(
            status=CoordinatorStatusCode.FAILED,
            safety_status=SafetyStatusCode.FAILED,
            action=None,
            selected=None,
        ),
        proposals=partial,
        coaching_style_code="SUPPORTIVE",
    )

    assert [summary.agent_type_code for summary in explanation.agent_summaries] == [
        "TRAINING",
        "SAFETY",
        "FEASIBILITY",
        "COORDINATOR",
    ]
    assert explanation.safety_summary.safety_status_code == SafetyStatusCode.FAILED.value


def test_downshift_records_a_final_adjustment_reason() -> None:
    explanation = build_explanation(
        result=_result(
            status=CoordinatorStatusCode.REVISE,
            safety_status=SafetyStatusCode.REVISE,
            action=RecommendedActionCode.DOWNSHIFT,
        ),
        proposals=_proposals(safety_status=SafetyStatusCode.REVISE),
        coaching_style_code="CONCISE",
    )

    assert explanation.final_adjustment_reason == "요청하신 시간은 유지하고 강도만 낮췄습니다."
    assert explanation.coaching_style_code == "CONCISE"
    keep_only = replace(explanation, final_adjustment_reason=None)
    assert keep_only.final_adjustment_reason is None
