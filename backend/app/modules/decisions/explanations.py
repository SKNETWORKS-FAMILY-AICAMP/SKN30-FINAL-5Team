"""Deterministic decision narration with an optional, strictly bounded LLM rewrite.

The Coordinator result is the only source of action, safety status and veto. Narration
turns already-approved codes into sentences; it can never add, remove or change a code.
Every failure path returns the reviewed template text so the plan stays identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Final

from backend.app.domain.agents.contracts import (
    REQUIRED_AGENT_TYPES,
    AgentProposal,
    AgentTypeCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.coordinator import CoordinatorResult, CoordinatorStatusCode
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
)
from backend.app.domain.rules.safety import SafetyStatusCode
from backend.app.modules.decisions.codes import (
    DECISION_EXPLANATION_PROMPT_VERSION,
    DECISION_EXPLANATION_TEMPLATE_VERSION,
    V3_DECISION_EXPLANATION_PROMPT_VERSION,
    V3_DECISION_EXPLANATION_TEMPLATE_VERSION,
)
from backend.app.modules.decisions.ports import (
    NarrationCompletion,
    NarrationPrompt,
    NarrationProviderPort,
    NarrationProviderUnavailableError,
)

COORDINATOR_SUMMARY_CODE: Final = "COORDINATOR"
_MAX_PUBLIC_REASON_CODES: Final = 2
_MAX_SENTENCE_LENGTH: Final = 120
_MACHINE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
# Narration은 한국어 안내 문장만 허용한다. 줄바꿈·태그·URL 문자는 통과하지 못한다.
_SENTENCE_PATTERN = re.compile(r"^[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ .,!?~%()\-·:'\"]+$")
# 진단·처방 어휘와 미수행을 벌점으로 읽히게 하는 어휘를 차단한다.
_BANNED_SENTENCE_TERMS: Final = (
    "진단",
    "처방",
    "치료",
    "질환",
    "질병",
    "증후군",
    "복용",
    "투약",
    "골절",
    "염좌",
    "실패",
    "실망",
    "게으",
    "핑계",
    "prompt",
    "system",
    "assistant",
)

_PROMPT_INSTRUCTION: Final = (
    "너는 운동 코칭 앱의 안내 문구 작성기다. 입력은 이미 확정된 결정 코드다. "
    "각 slot에 대해 코드를 바꾸지 않고 한국어 안내 문장 하나만 작성한다. "
    "결정, 안전 상태, veto, 운동 시간, 운동 종류를 바꾸거나 새로 만들지 않는다. "
    "진단·처방·치료 표현을 쓰지 않고, 운동을 하지 못한 것을 탓하지 않는다. "
    "문장은 120자 이내 한 문장이며 줄바꿈을 넣지 않는다. "
    "sentences 객체에 slot 코드별 문장만 담은 JSON으로 답한다."
)


class ExplanationSourceCode(StrEnum):
    TEMPLATE = "TEMPLATE"
    LLM = "LLM"


class ExplanationFallbackReasonCode(StrEnum):
    """Audit code recording why the reviewed template text was used."""

    LLM_DISABLED = "LLM_DISABLED"
    SAFETY_TONE_TEMPLATE_REQUIRED = "SAFETY_TONE_TEMPLATE_REQUIRED"
    NO_PUBLIC_PLAN = "NO_PUBLIC_PLAN"
    PAYLOAD_NOT_SHAREABLE = "PAYLOAD_NOT_SHAREABLE"
    LLM_PROVIDER_FAILED = "LLM_PROVIDER_FAILED"
    LLM_OUTPUT_REJECTED = "LLM_OUTPUT_REJECTED"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


@dataclass(frozen=True, slots=True)
class ExplanationAgentSummary:
    agent_type_code: str
    recommendation_code: str | None
    reason_codes: tuple[str, ...]
    summary: str


@dataclass(frozen=True, slots=True)
class ExplanationSafetySummary:
    safety_status_code: str
    vetoed: bool
    reason_codes: tuple[str, ...]
    summary: str


@dataclass(frozen=True, slots=True)
class DecisionExplanation:
    """Public narration for one decision run; codes always come from the Coordinator."""

    source_code: ExplanationSourceCode
    summary: str
    reason_codes: tuple[str, ...]
    agent_summaries: tuple[ExplanationAgentSummary, ...]
    safety_summary: ExplanationSafetySummary
    final_adjustment_reason: str | None
    coaching_style_code: str
    template_version: str = DECISION_EXPLANATION_TEMPLATE_VERSION
    prompt_version: str | None = None
    model_code: str | None = None
    fallback_reason_code: str | None = None

    def agent_summaries_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "agent_type_code": summary.agent_type_code,
                "recommendation_code": summary.recommendation_code,
                "reason_codes": list(summary.reason_codes),
                "summary": summary.summary,
            }
            for summary in self.agent_summaries
        ]

    def safety_summary_payload(self) -> dict[str, Any]:
        return {
            "safety_status_code": self.safety_summary.safety_status_code,
            "vetoed": self.safety_summary.vetoed,
            "reason_codes": list(self.safety_summary.reason_codes),
            "summary": self.safety_summary.summary,
        }


_SUMMARY_TEMPLATES: Final[dict[RecommendedActionCode, str]] = {
    RecommendedActionCode.KEEP: "오늘 조건에서는 준비된 루틴을 그대로 진행합니다.",
    RecommendedActionCode.DOWNSHIFT: "요청하신 시간은 그대로 두고 강도만 낮춰 조정했습니다.",
    RecommendedActionCode.CHANGE: "요청하신 시간을 유지하면서 일부 동작을 바꿨습니다.",
    RecommendedActionCode.RECOVERY: "요청하신 시간을 회복 중심 구성으로 채웠습니다.",
    RecommendedActionCode.REST: "오늘은 안전을 위해 운동 대신 휴식을 권합니다.",
    RecommendedActionCode.STOP_AND_SEEK_HELP: "지금은 운동을 멈추고 필요한 도움을 받으세요.",
}
_STATUS_SUMMARY_TEMPLATES: Final[dict[CoordinatorStatusCode, str]] = {
    CoordinatorStatusCode.NEEDS_INPUT: "안전한 추천을 위해 추가 입력이 필요합니다.",
    CoordinatorStatusCode.FAILED: "지금은 운동 계획을 제공하지 않습니다.",
}
_AGENT_SUMMARY_TEMPLATES: Final[dict[tuple[AgentTypeCode, RecommendedActionCode | None], str]] = {
    (AgentTypeCode.TRAINING, RecommendedActionCode.KEEP): "목표에 맞는 구성을 유지했습니다.",
    (AgentTypeCode.TRAINING, RecommendedActionCode.DOWNSHIFT): "목표는 유지하고 부담을 낮췄습니다.",
    (
        AgentTypeCode.TRAINING,
        RecommendedActionCode.CHANGE,
    ): "목표를 지키는 범위에서 구성을 바꿨습니다.",
    (
        AgentTypeCode.RECOVERY,
        RecommendedActionCode.KEEP,
    ): "회복 상태에서 부담을 더 줄일 이유가 없었습니다.",
    (
        AgentTypeCode.RECOVERY,
        RecommendedActionCode.DOWNSHIFT,
    ): "회복 상태를 고려해 강도를 낮추자고 제안했습니다.",
    (AgentTypeCode.RECOVERY, RecommendedActionCode.RECOVERY): "회복 중심 구성을 제안했습니다.",
    (AgentTypeCode.SAFETY, RecommendedActionCode.KEEP): "확인된 제한 사항이 없었습니다.",
    (
        AgentTypeCode.SAFETY,
        RecommendedActionCode.DOWNSHIFT,
    ): "주의가 필요한 부위를 고려해 강도를 낮췄습니다.",
    (
        AgentTypeCode.SAFETY,
        RecommendedActionCode.CHANGE,
    ): "부담이 되는 동작을 승인된 대체 운동으로 바꿨습니다.",
    (AgentTypeCode.SAFETY, RecommendedActionCode.REST): "오늘은 운동을 권하지 않습니다.",
    (
        AgentTypeCode.SAFETY,
        RecommendedActionCode.STOP_AND_SEEK_HELP,
    ): "지금은 운동을 멈추어야 합니다.",
    (
        AgentTypeCode.FEASIBILITY,
        RecommendedActionCode.KEEP,
    ): "현재 장소와 장비로 진행할 수 있습니다.",
    (
        AgentTypeCode.FEASIBILITY,
        RecommendedActionCode.DOWNSHIFT,
    ): "현재 조건에 맞춰 구성을 조정했습니다.",
    (
        AgentTypeCode.FEASIBILITY,
        RecommendedActionCode.CHANGE,
    ): "현재 조건에서 가능한 동작으로 바꿨습니다.",
}
_AGENT_DEFAULT_SUMMARIES: Final[dict[AgentTypeCode, str]] = {
    AgentTypeCode.TRAINING: "목표 기준 검토 결과를 반영했습니다.",
    AgentTypeCode.RECOVERY: "회복 상태 검토 결과를 반영했습니다.",
    AgentTypeCode.SAFETY: "안전 검토 결과를 반영했습니다.",
    AgentTypeCode.FEASIBILITY: "장소와 장비 검토 결과를 반영했습니다.",
}
_SAFETY_SUMMARY_TEMPLATES: Final[dict[SafetyStatusCode, str]] = {
    SafetyStatusCode.PASS: "확인된 제한 사항이 없어 그대로 진행합니다.",
    SafetyStatusCode.REVISE: "확인된 주의 사항을 반영해 구성을 조정했습니다.",
    SafetyStatusCode.BLOCKED: "안전 기준에 따라 오늘은 운동을 권하지 않습니다.",
    SafetyStatusCode.NEEDS_INPUT: "안전 확인을 위해 추가 입력이 필요합니다.",
    SafetyStatusCode.FAILED: "안전 규칙을 확인하지 못해 운동 계획을 제공하지 않습니다.",
}
_FINAL_ADJUSTMENT_TEMPLATES: Final[dict[RecommendedActionCode, str]] = {
    RecommendedActionCode.DOWNSHIFT: "요청하신 시간은 유지하고 강도만 낮췄습니다.",
    RecommendedActionCode.CHANGE: "제외된 동작을 승인된 대체 운동으로 바꿨습니다.",
    RecommendedActionCode.RECOVERY: "회복 중심 구성으로 바꿨습니다.",
}
_COORDINATOR_SUMMARY_TEMPLATE: Final = "네 에이전트 제안을 규칙으로 조정해 최종 결정을 내렸습니다."
_TERMINAL_ACTIONS: Final = frozenset(
    {RecommendedActionCode.REST, RecommendedActionCode.STOP_AND_SEEK_HELP}
)
_PUBLIC_PLAN_STATUSES: Final = frozenset({CoordinatorStatusCode.PASS, CoordinatorStatusCode.REVISE})
_SUMMARY_SLOT: Final = "SUMMARY"
_FINAL_ADJUSTMENT_SLOT: Final = "FINAL_ADJUSTMENT"
_AGENT_SLOT_PREFIX: Final = "AGENT_"


def _public_reason_codes(reason_codes: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(reason_codes[:_MAX_PUBLIC_REASON_CODES])


def _agent_summary_text(proposal: AgentProposal) -> str:
    keyed = _AGENT_SUMMARY_TEMPLATES.get(
        (proposal.agent_type_code, proposal.recommended_action_code)
    )
    return keyed or _AGENT_DEFAULT_SUMMARIES[proposal.agent_type_code]


def _summary_text(result: CoordinatorResult) -> str:
    if result.final_action_code is not None:
        return _SUMMARY_TEMPLATES[result.final_action_code]
    return _STATUS_SUMMARY_TEMPLATES.get(
        result.status_code, _STATUS_SUMMARY_TEMPLATES[CoordinatorStatusCode.FAILED]
    )


def build_template_explanation(
    *,
    result: CoordinatorResult,
    proposals: tuple[AgentProposal, ...],
    coaching_style_code: str,
    fallback_reason_code: ExplanationFallbackReasonCode,
) -> DecisionExplanation:
    """Return reviewed narration built only from approved codes."""

    by_type = {proposal.agent_type_code: proposal for proposal in proposals}
    agent_summaries: list[ExplanationAgentSummary] = []
    for agent_type in REQUIRED_AGENT_TYPES:
        proposal = by_type.get(agent_type)
        if proposal is None:
            continue
        action = proposal.recommended_action_code
        agent_summaries.append(
            ExplanationAgentSummary(
                agent_type_code=agent_type.value,
                recommendation_code=action.value if action is not None else None,
                reason_codes=_public_reason_codes(proposal.reason_codes),
                summary=_agent_summary_text(proposal),
            )
        )
    agent_summaries.append(
        ExplanationAgentSummary(
            agent_type_code=COORDINATOR_SUMMARY_CODE,
            recommendation_code=(
                result.final_action_code.value if result.final_action_code is not None else None
            ),
            reason_codes=_public_reason_codes(result.reason_codes),
            summary=_COORDINATOR_SUMMARY_TEMPLATE,
        )
    )
    safety_proposal = by_type.get(AgentTypeCode.SAFETY)
    safety_summary = ExplanationSafetySummary(
        safety_status_code=result.safety_status_code.value,
        vetoed=bool(safety_proposal.safety_vetoed) if safety_proposal is not None else True,
        reason_codes=(
            _public_reason_codes(safety_proposal.reason_codes)
            if safety_proposal is not None
            else ()
        ),
        summary=_SAFETY_SUMMARY_TEMPLATES[result.safety_status_code],
    )
    final_adjustment_reason = (
        _FINAL_ADJUSTMENT_TEMPLATES.get(result.final_action_code)
        if result.final_action_code is not None
        else None
    )
    return DecisionExplanation(
        source_code=ExplanationSourceCode.TEMPLATE,
        summary=_summary_text(result),
        reason_codes=_public_reason_codes(result.reason_codes),
        agent_summaries=tuple(agent_summaries),
        safety_summary=safety_summary,
        final_adjustment_reason=final_adjustment_reason,
        coaching_style_code=coaching_style_code,
        fallback_reason_code=fallback_reason_code.value,
    )


def _llm_blocking_reason(
    result: CoordinatorResult,
    proposals: tuple[AgentProposal, ...],
) -> ExplanationFallbackReasonCode | None:
    """Return the blocking reason, or None when an optional rewrite is permitted."""

    # 안전 사유를 먼저 확인해 통증·이상 반응 화면이 항상 검수된 문구를 쓰게 한다.
    if result.safety_status_code not in {SafetyStatusCode.PASS, SafetyStatusCode.REVISE}:
        return ExplanationFallbackReasonCode.SAFETY_TONE_TEMPLATE_REQUIRED
    if result.final_action_code in _TERMINAL_ACTIONS:
        return ExplanationFallbackReasonCode.SAFETY_TONE_TEMPLATE_REQUIRED
    safety_proposal = next(
        (proposal for proposal in proposals if proposal.agent_type_code is AgentTypeCode.SAFETY),
        None,
    )
    if safety_proposal is None or safety_proposal.safety_vetoed is not False:
        # veto가 걸린 결정은 문구 품질보다 검수된 표현을 우선한다.
        return ExplanationFallbackReasonCode.SAFETY_TONE_TEMPLATE_REQUIRED
    if result.status_code not in _PUBLIC_PLAN_STATUSES or result.final_action_code is None:
        return ExplanationFallbackReasonCode.NO_PUBLIC_PLAN
    return None


def _shareable_code(value: str) -> bool:
    return bool(_MACHINE_REFERENCE_PATTERN.fullmatch(value))


def _payload_is_shareable(value: Any) -> bool:
    """Reject anything that is not an int, bool, None or an approved machine code.

    Direct identifiers, raw health records and free text cannot satisfy this check, so a
    payload that fails it is never sent to an external provider.
    """

    if value is None or isinstance(value, bool | int):
        return True
    if isinstance(value, str):
        return _shareable_code(value)
    if isinstance(value, list):
        return all(_payload_is_shareable(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _shareable_code(key) and _payload_is_shareable(item)
            for key, item in value.items()
        )
    return False


def _build_prompt(
    *,
    result: CoordinatorResult,
    template: DecisionExplanation,
) -> NarrationPrompt | None:
    """Build a codes-only prompt, or None when any value is not a machine reference."""

    slot_codes = [_SUMMARY_SLOT]
    agents_payload: list[dict[str, Any]] = []
    for summary in template.agent_summaries:
        slot_codes.append(f"{_AGENT_SLOT_PREFIX}{summary.agent_type_code}")
        agents_payload.append(
            {
                "agent_type_code": summary.agent_type_code,
                "recommendation_code": summary.recommendation_code,
                "reason_codes": list(summary.reason_codes),
            }
        )
    if template.final_adjustment_reason is not None:
        slot_codes.append(_FINAL_ADJUSTMENT_SLOT)
    payload: dict[str, Any] = {
        "action_code": result.final_action_code.value if result.final_action_code else None,
        "safety_status_code": result.safety_status_code.value,
        "requested_duration_minutes": result.requested_duration_minutes,
        "duration_adjustment_source_code": result.duration_adjustment_source_code.value,
        "coaching_style_code": template.coaching_style_code,
        "reason_codes": list(template.reason_codes),
        "agents": agents_payload,
    }
    if not _payload_is_shareable(payload):
        return None
    return NarrationPrompt(
        prompt_version=DECISION_EXPLANATION_PROMPT_VERSION,
        instruction=_PROMPT_INSTRUCTION,
        slot_codes=tuple(slot_codes),
        payload=payload,
    )


def _sentence_is_acceptable(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or len(text) > _MAX_SENTENCE_LENGTH:
        return False
    if not _SENTENCE_PATTERN.fullmatch(text):
        return False
    lowered = text.lower()
    return not any(term in lowered for term in _BANNED_SENTENCE_TERMS)


def _accepted_sentences(
    completion: NarrationCompletion,
    slot_codes: tuple[str, ...],
) -> dict[str, str] | None:
    """Return the rewritten sentences only when every requested slot is valid."""

    if not isinstance(completion, NarrationCompletion):
        return None
    if not _shareable_code(completion.model_code):
        return None
    sentences = completion.sentences
    if not isinstance(sentences, dict) or set(sentences) != set(slot_codes):
        return None
    accepted: dict[str, str] = {}
    for slot_code in slot_codes:
        candidate = sentences[slot_code]
        if not _sentence_is_acceptable(candidate):
            return None
        accepted[slot_code] = str(candidate).strip()
    return accepted


def _with_llm_sentences(
    template: DecisionExplanation,
    *,
    sentences: dict[str, str],
    model_code: str,
) -> DecisionExplanation:
    """Replace sentence text only; every code stays exactly as the Coordinator produced it."""

    agent_summaries = tuple(
        replace(summary, summary=sentences[f"{_AGENT_SLOT_PREFIX}{summary.agent_type_code}"])
        for summary in template.agent_summaries
    )
    return replace(
        template,
        source_code=ExplanationSourceCode.LLM,
        summary=sentences[_SUMMARY_SLOT],
        agent_summaries=agent_summaries,
        final_adjustment_reason=(
            sentences[_FINAL_ADJUSTMENT_SLOT]
            if template.final_adjustment_reason is not None
            else None
        ),
        prompt_version=DECISION_EXPLANATION_PROMPT_VERSION,
        model_code=model_code,
        fallback_reason_code=None,
    )


def build_explanation(
    *,
    result: CoordinatorResult,
    proposals: tuple[AgentProposal, ...],
    coaching_style_code: str,
    provider: NarrationProviderPort | None = None,
) -> DecisionExplanation:
    """Return narration for one decision run, falling back to reviewed template text.

    The safety summary is always template text. An LLM rewrite is attempted only for a
    non-vetoed plan result and is discarded as a whole when any sentence fails validation.
    """

    blocking_reason = _llm_blocking_reason(result, proposals)
    template = build_template_explanation(
        result=result,
        proposals=proposals,
        coaching_style_code=coaching_style_code,
        fallback_reason_code=blocking_reason or ExplanationFallbackReasonCode.LLM_DISABLED,
    )
    if blocking_reason is not None or provider is None:
        return template

    prompt = _build_prompt(result=result, template=template)
    if prompt is None:
        return replace(
            template,
            fallback_reason_code=ExplanationFallbackReasonCode.PAYLOAD_NOT_SHAREABLE.value,
        )
    try:
        completion = provider.narrate(prompt)
    except NarrationProviderUnavailableError:
        return replace(
            template,
            fallback_reason_code=ExplanationFallbackReasonCode.LLM_DISABLED.value,
        )
    except Exception:
        # Provider failures never change the plan; exception text is not copied out.
        return replace(
            template,
            fallback_reason_code=ExplanationFallbackReasonCode.LLM_PROVIDER_FAILED.value,
        )
    sentences = _accepted_sentences(completion, prompt.slot_codes)
    if sentences is None:
        return replace(
            template,
            fallback_reason_code=ExplanationFallbackReasonCode.LLM_OUTPUT_REJECTED.value,
        )
    # The safety summary keeps its reviewed sentence even on the LLM path.
    return _with_llm_sentences(template, sentences=sentences, model_code=completion.model_code)


_V3_AGENT_TEMPLATES: Final[dict[SpecialistAgentTypeCode, str]] = {
    SpecialistAgentTypeCode.TRAINING: "운동 목표와 요청 시간을 반영한 구성을 제안했습니다.",
    SpecialistAgentTypeCode.RECOVERY: "현재 회복 범위에 맞는 강도와 휴식 조정을 제안했습니다.",
    SpecialistAgentTypeCode.FEASIBILITY: "승인된 운동 풀 안에서 실행 가능한 구성을 확인했습니다.",
}
_V3_CODE_SENTENCE_TEMPLATES: Final[dict[str, str]] = {
    "TRAINING_READY": "운동 목표와 요청 시간을 반영한 구성을 제안했습니다.",
    "RECOVERY_READY": "현재 회복 범위에 맞는 강도와 휴식 조정을 제안했습니다.",
    "FEASIBILITY_READY": "승인된 운동 풀 안에서 실행 가능한 구성을 확인했습니다.",
    "GOAL_PRESERVED": "요청한 운동 목표를 유지하는 방향으로 제안했습니다.",
    "RECOVERY_CONSTRAINTS_PRESERVED": "회복을 위한 강도와 휴식 상한을 유지했습니다.",
    "FEASIBILITY_CONSTRAINTS_PRESERVED": "현재 조건에서 실행 가능한 범위를 유지했습니다.",
}
_V3_AGENT_FALLBACK_TEMPLATES: Final[dict[SpecialistAgentTypeCode, str]] = {
    SpecialistAgentTypeCode.TRAINING: "검증된 대체 규칙으로 운동 구성을 준비했습니다.",
    SpecialistAgentTypeCode.RECOVERY: "검증된 대체 규칙으로 회복 상한을 반영했습니다.",
    SpecialistAgentTypeCode.FEASIBILITY: "검증된 대체 규칙으로 실행 가능성을 확인했습니다.",
}
_V3_ACTION_SUMMARIES: Final[dict[str, str]] = {
    "KEEP": "오늘의 목표와 조건에 맞는 운동 계획을 준비했습니다.",
    "DOWNSHIFT": "요청한 시간은 유지하고 현재 상태에 맞게 운동 부담을 낮췄습니다.",
    "CHANGE": "요청한 시간과 목표를 지키면서 안전한 운동으로 구성을 바꿨습니다.",
    "RECOVERY": "요청한 시간에 맞춰 회복 중심 운동 계획을 준비했습니다.",
    "REST": "오늘은 안전을 위해 운동 대신 휴식을 권합니다.",
    "STOP_AND_SEEK_HELP": "지금은 운동을 중단하고 필요한 도움을 요청하세요.",
}
_V3_FINAL_ADJUSTMENTS: Final[dict[str, str]] = {
    "DOWNSHIFT": "요청 시간은 유지하고 강도, 반복 또는 휴식 구성을 낮춰 조정했습니다.",
    "CHANGE": "제외된 운동 대신 승인된 운동으로 교체해 최종 구성을 만들었습니다.",
    "RECOVERY": "회복에 맞는 강도와 동작으로 최종 구성을 조정했습니다.",
}


def _v3_safety_summary(
    envelope: ConstraintEnvelope,
    *,
    safety_status_code: str,
    safety_vetoed: bool,
    reason_codes: tuple[str, ...],
) -> ExplanationSafetySummary:
    excluded_count = len(envelope.excluded_exercise_ids)
    ceiling = envelope.recovery_ceiling
    caps: list[str] = []
    if ceiling.allowed_intensity_codes:
        caps.append("허용 강도 범위")
    if ceiling.allowed_load_codes:
        caps.append("허용 부하 범위")
    if ceiling.maximum_sets_per_exercise is not None:
        caps.append(f"운동별 최대 {ceiling.maximum_sets_per_exercise}세트")
    if ceiling.maximum_repetitions_per_set is not None:
        caps.append(f"세트당 최대 {ceiling.maximum_repetitions_per_set}회")
    if ceiling.maximum_work_seconds_per_set is not None:
        caps.append(f"세트당 최대 {ceiling.maximum_work_seconds_per_set}초")
    if ceiling.minimum_rest_seconds_between_sets is not None:
        caps.append(f"세트 사이 최소 {ceiling.minimum_rest_seconds_between_sets}초 휴식")
    exclusion = (
        f"운동 {excluded_count}개를 제외했습니다." if excluded_count else "제외한 운동은 없습니다."
    )
    cap_text = (
        f"적용한 회복 상한은 {'·'.join(caps)}입니다."
        if caps
        else "추가로 적용한 회복 상한은 없습니다."
    )
    return ExplanationSafetySummary(
        safety_status_code=safety_status_code,
        vetoed=safety_vetoed,
        reason_codes=_public_reason_codes(reason_codes),
        summary=f"{exclusion} {cap_text}",
    )


def build_v3_template_explanation(
    *,
    action_code: str,
    safety_status_code: str,
    safety_vetoed: bool,
    safety_reason_codes: tuple[str, ...],
    final_reason_codes: tuple[str, ...],
    envelope: ConstraintEnvelope,
    proposals: tuple[SpecialistAgentProposal, ...],
    coaching_style_code: str,
    fallback_used: bool,
    fallback_reason_code: ExplanationFallbackReasonCode,
) -> DecisionExplanation:
    """Build reviewed V3 copy from the three proposals and SafetyPolicyEngine output."""

    by_type = {proposal.agent_type_code: proposal for proposal in proposals}
    agent_summaries: list[ExplanationAgentSummary] = []
    for agent_type in SpecialistAgentTypeCode:
        proposal = by_type.get(agent_type)
        if proposal is None:
            continue
        signals = (
            *((proposal.public_summary_code,) if proposal.public_summary_code else ()),
            *proposal.reason_codes,
            *proposal.adjustment_codes,
            *proposal.evidence_reference_codes,
        )
        reviewed_summary = next(
            (
                _V3_CODE_SENTENCE_TEMPLATES[code]
                for code in signals
                if code in _V3_CODE_SENTENCE_TEMPLATES
            ),
            _V3_AGENT_TEMPLATES[agent_type],
        )
        agent_summaries.append(
            ExplanationAgentSummary(
                agent_type_code=agent_type.value,
                recommendation_code=action_code
                if agent_type is SpecialistAgentTypeCode.TRAINING
                else None,
                reason_codes=(_public_reason_codes(proposal.reason_codes)),
                summary=(
                    _V3_AGENT_FALLBACK_TEMPLATES[agent_type] if fallback_used else reviewed_summary
                ),
            )
        )
    safety_summary = _v3_safety_summary(
        envelope,
        safety_status_code=safety_status_code,
        safety_vetoed=safety_vetoed,
        reason_codes=safety_reason_codes,
    )
    safety_index = min(2, len(agent_summaries))
    agent_summaries.insert(
        safety_index,
        ExplanationAgentSummary(
            agent_type_code=AgentTypeCode.SAFETY.value,
            recommendation_code=action_code,
            reason_codes=safety_summary.reason_codes,
            summary=safety_summary.summary,
        ),
    )
    agent_summaries.append(
        ExplanationAgentSummary(
            agent_type_code=COORDINATOR_SUMMARY_CODE,
            recommendation_code=action_code,
            reason_codes=_public_reason_codes(final_reason_codes),
            summary="세 가지 제안과 안전 정책을 종합해 최종 운동 계획을 확정했습니다.",
        )
    )
    return DecisionExplanation(
        source_code=ExplanationSourceCode.TEMPLATE,
        summary=_V3_ACTION_SUMMARIES.get(
            action_code, "오늘의 조건에 맞는 운동 계획을 준비했습니다."
        ),
        reason_codes=_public_reason_codes(final_reason_codes),
        agent_summaries=tuple(agent_summaries),
        safety_summary=safety_summary,
        final_adjustment_reason=_V3_FINAL_ADJUSTMENTS.get(action_code),
        coaching_style_code=coaching_style_code,
        template_version=V3_DECISION_EXPLANATION_TEMPLATE_VERSION,
        fallback_reason_code=fallback_reason_code.value,
    )


def _build_v3_prompt(
    *,
    template: DecisionExplanation,
    action_code: str,
    envelope: ConstraintEnvelope,
    proposals: tuple[SpecialistAgentProposal, ...],
) -> NarrationPrompt | None:
    slot_codes = [_SUMMARY_SLOT]
    for summary in template.agent_summaries:
        slot_codes.append(f"{_AGENT_SLOT_PREFIX}{summary.agent_type_code}")
    if template.final_adjustment_reason is not None:
        slot_codes.append(_FINAL_ADJUSTMENT_SLOT)
    payload: dict[str, Any] = {
        "action_code": action_code,
        "safety_status_code": template.safety_summary.safety_status_code,
        "safety_vetoed": template.safety_summary.vetoed,
        "requested_duration_minutes": envelope.requested_duration_minutes,
        "excluded_exercise_count": len(envelope.excluded_exercise_ids),
        "coaching_style_code": template.coaching_style_code,
        "reason_codes": list(template.reason_codes),
        "agents": [
            {
                "agent_type_code": proposal.agent_type_code.value,
                "proposal_status_code": proposal.proposal_status_code.value,
                "public_summary_code": proposal.public_summary_code,
                "adjustment_codes": list(proposal.adjustment_codes),
                "reason_codes": list(proposal.reason_codes),
                "evidence_reference_codes": list(proposal.evidence_reference_codes),
            }
            for proposal in proposals
        ],
    }
    if not _payload_is_shareable(payload):
        return None
    return NarrationPrompt(
        prompt_version=V3_DECISION_EXPLANATION_PROMPT_VERSION,
        instruction=_PROMPT_INSTRUCTION,
        slot_codes=tuple(slot_codes),
        payload=payload,
    )


def build_v3_explanation(
    *,
    action_code: str,
    safety_status_code: str,
    safety_vetoed: bool,
    safety_reason_codes: tuple[str, ...],
    final_reason_codes: tuple[str, ...],
    envelope: ConstraintEnvelope,
    proposals: tuple[SpecialistAgentProposal, ...],
    coaching_style_code: str,
    fallback_used: bool,
    provider: NarrationProviderPort | None = None,
) -> DecisionExplanation:
    """Narrate an already validated V3 decision without allowing text to alter it."""

    llm_allowed = (
        safety_status_code in {SafetyStatusCode.PASS.value, SafetyStatusCode.REVISE.value}
        and not safety_vetoed
        and not fallback_used
        and len(proposals) == len(SpecialistAgentTypeCode)
    )
    if (
        safety_status_code not in {SafetyStatusCode.PASS.value, SafetyStatusCode.REVISE.value}
        or safety_vetoed
    ):
        template_fallback_reason = ExplanationFallbackReasonCode.SAFETY_TONE_TEMPLATE_REQUIRED
    elif fallback_used or len(proposals) != len(SpecialistAgentTypeCode):
        template_fallback_reason = ExplanationFallbackReasonCode.DETERMINISTIC_FALLBACK
    else:
        template_fallback_reason = ExplanationFallbackReasonCode.LLM_DISABLED
    template = build_v3_template_explanation(
        action_code=action_code,
        safety_status_code=safety_status_code,
        safety_vetoed=safety_vetoed,
        safety_reason_codes=safety_reason_codes,
        final_reason_codes=final_reason_codes,
        envelope=envelope,
        proposals=proposals,
        coaching_style_code=coaching_style_code,
        fallback_used=fallback_used,
        fallback_reason_code=template_fallback_reason,
    )
    if not llm_allowed or provider is None:
        return template
    prompt = _build_v3_prompt(
        template=template,
        action_code=action_code,
        envelope=envelope,
        proposals=proposals,
    )
    if prompt is None:
        return replace(
            template,
            fallback_reason_code=ExplanationFallbackReasonCode.PAYLOAD_NOT_SHAREABLE.value,
        )
    try:
        completion = provider.narrate(prompt)
    except NarrationProviderUnavailableError:
        return template
    except Exception:
        return replace(
            template,
            fallback_reason_code=ExplanationFallbackReasonCode.LLM_PROVIDER_FAILED.value,
        )
    sentences = _accepted_sentences(completion, prompt.slot_codes)
    if sentences is None:
        return replace(
            template,
            fallback_reason_code=ExplanationFallbackReasonCode.LLM_OUTPUT_REJECTED.value,
        )
    return replace(
        _with_llm_sentences(template, sentences=sentences, model_code=completion.model_code),
        prompt_version=V3_DECISION_EXPLANATION_PROMPT_VERSION,
    )


__all__ = [
    "COORDINATOR_SUMMARY_CODE",
    "DecisionExplanation",
    "ExplanationAgentSummary",
    "ExplanationFallbackReasonCode",
    "ExplanationSafetySummary",
    "ExplanationSourceCode",
    "build_explanation",
    "build_template_explanation",
    "build_v3_explanation",
    "build_v3_template_explanation",
]
