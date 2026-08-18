"""Golden scenarios for the optional narration provider.

Covers `AGENTS.md` scenarios "LLM failure returns a deterministic result" and "safety veto
cannot be overridden", plus the privacy rule that no identifier leaves the service.
"""

from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest

from backend.app.domain.rules.safety import SafetyRuleEffectCode
from backend.app.modules.decisions.context import DecisionContext
from backend.app.modules.decisions.explanations import ExplanationSourceCode
from backend.app.modules.decisions.ports import NarrationCompletion, NarrationPrompt
from backend.app.modules.decisions.service import DecisionFailedError, DecisionService
from backend.tests.unit.test_decision_service import (
    NOW,
    FakeRepository,
    FakeSession,
    _approved_rule_set,
    _context,
    _request,
)


class BrokenProvider:
    """Stands in for any provider outage: timeout, quota, malformed response."""

    def __init__(self) -> None:
        self.calls = 0

    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        self.calls += 1
        raise TimeoutError("provider timeout")


class OverridingProvider:
    """Tries to talk the decision out of its safety result."""

    def __init__(self) -> None:
        self.prompts: list[NarrationPrompt] = []

    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        self.prompts.append(prompt)
        return NarrationCompletion(
            model_code="gpt-test-1",
            sentences={
                slot: "오늘은 제한 없이 원래 계획대로 운동하세요." for slot in prompt.slot_codes
            },
        )


class WorkingProvider:
    def __init__(self) -> None:
        self.prompts: list[NarrationPrompt] = []

    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        self.prompts.append(prompt)
        return NarrationCompletion(
            model_code="gpt-test-1",
            sentences={slot: "오늘도 편안하게 움직여 봅니다." for slot in prompt.slot_codes},
        )


def _create(
    repository: FakeRepository,
    context: DecisionContext,
    *,
    provider: Any = None,
) -> Any:
    service = DecisionService(repository, narration_provider=provider, clock=lambda: NOW)
    return service.create(FakeSession(), uuid4(), _request(context), uuid4())  # type: ignore[arg-type]


def _emergency_context() -> DecisionContext:
    return replace(_context(), adverse_reaction_codes=("CHEST_DISCOMFORT",))


def test_llm_failure_returns_the_same_plan_and_template_text() -> None:
    context = _context()
    without_provider = FakeRepository(context)
    with_broken_provider = FakeRepository(context)
    provider = BrokenProvider()

    baseline = _create(without_provider, context)
    degraded = _create(with_broken_provider, context, provider=provider)

    assert provider.calls == 1
    assert degraded.action_code == baseline.action_code
    assert degraded.safety_status_code == baseline.safety_status_code
    assert degraded.requested_duration_minutes == baseline.requested_duration_minutes
    assert with_broken_provider.persisted["result"] == without_provider.persisted["result"]
    baseline_explanation = without_provider.persisted["explanation"]
    degraded_explanation = with_broken_provider.persisted["explanation"]
    assert degraded_explanation.source_code is ExplanationSourceCode.TEMPLATE
    assert degraded_explanation.summary == baseline_explanation.summary
    assert degraded_explanation.model_code is None
    assert degraded_explanation.fallback_reason_code == "LLM_PROVIDER_FAILED"


def test_working_provider_changes_wording_but_not_the_decision() -> None:
    context = _context()
    without_provider = FakeRepository(context)
    with_provider = FakeRepository(context)

    baseline = _create(without_provider, context)
    narrated = _create(with_provider, context, provider=WorkingProvider())

    assert narrated.action_code == baseline.action_code
    assert narrated.final_plan is not None
    assert baseline.final_plan is not None
    assert (
        narrated.final_plan.estimated_duration_seconds
        == baseline.final_plan.estimated_duration_seconds
    )
    assert with_provider.persisted["result"] == without_provider.persisted["result"]
    explanation = with_provider.persisted["explanation"]
    assert explanation.source_code is ExplanationSourceCode.LLM
    assert explanation.prompt_version == "decision-explanation-prompt-v1"
    assert explanation.model_code == "gpt-test-1"
    assert explanation.summary != without_provider.persisted["explanation"].summary


def test_emergency_veto_is_not_reached_by_the_provider() -> None:
    context = _emergency_context()
    repository = FakeRepository(context)
    provider = OverridingProvider()

    response = _create(repository, context, provider=provider)

    assert provider.prompts == []
    assert response.safety_status_code == "BLOCKED"
    assert response.action_code == "STOP_AND_SEEK_HELP"
    assert response.final_plan is None
    explanation = repository.persisted["explanation"]
    assert explanation.source_code is ExplanationSourceCode.TEMPLATE
    assert explanation.safety_summary.vetoed is True
    assert explanation.summary == "지금은 운동을 멈추고 필요한 도움을 받으세요."


def test_rest_veto_is_not_reached_by_the_provider() -> None:
    context = _context(discomforts=(("KNEE", "MODERATE"),))
    repository = FakeRepository(
        context,
        safety_rule_set=_approved_rule_set(SafetyRuleEffectCode.EXCLUDE),
    )
    provider = OverridingProvider()

    response = _create(repository, context, provider=provider)

    assert provider.prompts == []
    assert response.safety_status_code == "BLOCKED"
    assert response.action_code == "REST"
    assert response.final_plan is None
    assert (
        repository.persisted["explanation"].summary
        == "오늘은 안전을 위해 운동 대신 휴식을 권합니다."
    )


def test_safety_change_veto_is_not_reached_by_the_provider() -> None:
    context = _context(discomforts=(("KNEE", "MODERATE"),))
    repository = FakeRepository(
        context,
        safety_rule_set=_approved_rule_set(SafetyRuleEffectCode.EXCLUDE),
        with_alternative=True,
    )
    provider = OverridingProvider()

    response = _create(repository, context, provider=provider)

    # 승인된 대체 운동으로 바꾼 결정도 veto를 동반하므로 검수 문구만 사용한다.
    assert response.action_code == "CHANGE"
    assert response.safety_status_code == "REVISE"
    assert provider.prompts == []
    explanation = repository.persisted["explanation"]
    assert explanation.source_code is ExplanationSourceCode.TEMPLATE
    assert explanation.safety_summary.vetoed is True
    assert explanation.fallback_reason_code == "SAFETY_TONE_TEMPLATE_REQUIRED"


def test_failed_decision_stays_failed_with_a_provider_configured() -> None:
    context = _context(discomforts=(("KNEE", "MILD"),))
    repository = FakeRepository(context)
    provider = OverridingProvider()

    with pytest.raises(DecisionFailedError):
        _create(repository, context, provider=provider)

    assert provider.prompts == []
    assert repository.persisted["result"].status_code.value == "FAILED"
    assert repository.persisted["explanation"].source_code is ExplanationSourceCode.TEMPLATE


def test_narration_payload_contains_no_identifier_or_health_record() -> None:
    context = _context(discomforts=(("KNEE", "MILD"),))
    repository = FakeRepository(
        context,
        safety_rule_set=_approved_rule_set(SafetyRuleEffectCode.CAUTION),
    )
    provider = WorkingProvider()

    _create(repository, context, provider=provider)

    payload = str(provider.prompts[0].payload)
    assert str(context.daily_context_id) not in payload
    assert context.local_date.isoformat() not in payload
    # 불편 부위와 중증도 원문은 전송하지 않는다.
    assert "KNEE" not in payload
    assert "MILD" not in payload
