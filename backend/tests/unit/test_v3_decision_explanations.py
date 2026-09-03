from __future__ import annotations

from backend.app.domain.agents.v3_contracts import SpecialistAgentTypeCode
from backend.app.modules.decisions.explanations import (
    ExplanationSourceCode,
    build_v3_explanation,
)
from backend.app.modules.decisions.ports import NarrationCompletion
from backend.tests.unit.test_v3_agent_contracts import B, envelope, pool
from backend.tests.unit.test_v3_coordinator_contracts import proposals


class CapturingProvider:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.prompts = []

    def narrate(self, prompt):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return NarrationCompletion(
            model_code="narration-model-v1",
            sentences={
                slot: f"Reviewed sentence {index}." for index, slot in enumerate(prompt.slot_codes)
            },
        )


def _inputs(*, excluded=False):
    current_envelope = envelope(excluded_ids=(B,) if excluded else ())
    current_pool = pool(current_envelope)
    return current_envelope, proposals(current_envelope, current_pool)


def test_v3_template_uses_three_proposals_and_safety_policy_summary() -> None:
    current_envelope, current_proposals = _inputs(excluded=True)

    explanation = build_v3_explanation(
        action_code="CHANGE",
        safety_status_code="REVISE",
        safety_vetoed=True,
        safety_reason_codes=("DIRECT_JOINT_LOAD",),
        final_reason_codes=("GOAL_PRESERVED",),
        envelope=current_envelope,
        proposals=current_proposals,
        coaching_style_code="SUPPORTIVE",
        fallback_used=False,
    )

    assert [item.agent_type_code for item in explanation.agent_summaries] == [
        "TRAINING",
        "RECOVERY",
        "SAFETY",
        "FEASIBILITY",
        "COORDINATOR",
    ]
    assert "운동 1개" in explanation.safety_summary.summary
    assert "최대 3세트" in explanation.safety_summary.summary
    assert explanation.final_adjustment_reason is not None
    public_copy = " ".join(
        [explanation.summary, explanation.safety_summary.summary]
        + [item.summary for item in explanation.agent_summaries]
    )
    for machine_code in (
        "GOAL_PRESERVED",
        "RECOVERY_CONSTRAINTS_PRESERVED",
        "FEASIBILITY_CONSTRAINTS_PRESERVED",
        "ENVELOPE",
        "POOL",
    ):
        assert machine_code not in public_copy


def test_v3_narration_payload_connects_all_proposal_evidence_without_identifiers() -> None:
    current_envelope, current_proposals = _inputs()
    provider = CapturingProvider()

    explanation = build_v3_explanation(
        action_code="KEEP",
        safety_status_code="PASS",
        safety_vetoed=False,
        safety_reason_codes=(),
        final_reason_codes=("GOAL_PRESERVED",),
        envelope=current_envelope,
        proposals=current_proposals,
        coaching_style_code="CONCISE",
        fallback_used=False,
        provider=provider,
    )

    assert explanation.source_code is ExplanationSourceCode.LLM
    assert len(provider.prompts) == 1
    agents = provider.prompts[0].payload["agents"]
    assert [item["agent_type_code"] for item in agents] == [
        code.value for code in SpecialistAgentTypeCode
    ]
    assert agents[1]["adjustment_codes"] == ["RECOVERY_CONSTRAINTS_PRESERVED"]
    assert agents[0]["reason_codes"] == ["GOAL_PRESERVED"]
    assert agents[0]["evidence_reference_codes"] == ["ENVELOPE", "POOL"]
    assert "excluded_exercise_ids" not in provider.prompts[0].payload


def test_v3_narration_failure_returns_the_reviewed_template() -> None:
    current_envelope, current_proposals = _inputs()
    provider = CapturingProvider(error=RuntimeError("provider payload must stay private"))

    explanation = build_v3_explanation(
        action_code="DOWNSHIFT",
        safety_status_code="PASS",
        safety_vetoed=False,
        safety_reason_codes=(),
        final_reason_codes=("GOAL_PRESERVED",),
        envelope=current_envelope,
        proposals=current_proposals,
        coaching_style_code="SUPPORTIVE",
        fallback_used=False,
        provider=provider,
    )

    assert explanation.source_code is ExplanationSourceCode.TEMPLATE
    assert explanation.fallback_reason_code == "LLM_PROVIDER_FAILED"
    assert explanation.summary == "요청한 시간은 유지하고 현재 상태에 맞게 운동 부담을 낮췄습니다."
