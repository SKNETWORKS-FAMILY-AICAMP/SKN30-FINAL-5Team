"""Bounded LLM interpretation for deterministic weekly report aggregates.

This module deliberately does not use the V3 exercise-planning specialists or
LangGraph coordinator: those contracts own plan construction and safety
constraints. A weekly report needs only optional, non-authoritative wording.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import Any, Final

from backend.app.modules.decisions.ports import (
    NarrationCompletion,
    NarrationPrompt,
    NarrationProviderPort,
    NarrationProviderUnavailableError,
)
from backend.app.modules.weekly_reports.ports import (
    ReportValues,
    WeeklyReportNarration,
    WeeklyReportNarrationAgentPort,
    WeeklyReportNarrationInput,
)

WEEKLY_REPORT_INTERPRETER_CODE: Final = "WEEKLY_REPORT_INTERPRETER"
WEEKLY_REPORT_NARRATION_PROMPT_VERSION: Final = "weekly-report-narration-prompt-v2"
_SLOT_CODES: Final = (
    "ADJUSTMENT_SUMMARY",
    "NEXT_WEEK_INTENSITY",
    "NEXT_WEEK_VOLUME",
    "NEXT_WEEK_DURATION",
    "NEXT_WEEK_PAIN_RESPONSE",
    "COACH_MESSAGE",
)
_MAX_SENTENCE_LENGTH: Final = 180
_DIGIT_PATTERN: Final = re.compile(r"\d")
_MACHINE_CODE_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_BANNED_TERMS: Final = (
    "diagnos",
    "treatment",
    "prescrib",
    "prompt",
    "system",
    "assistant",
    "진단",
    "치료",
    "처방",
)
_INSTRUCTION: Final = (
    "Write concise, supportive Korean copy for sections four, five, and six of a weekly "
    "exercise report. Use only the supplied deterministic aggregate and distinguish the "
    "recommendations actually shown this week from directions proposed for next week. "
    "For this week's adjustment, describe only action-and-context combinations present in "
    "recommendation_context_counts and do not invent an unrecorded causal reason. "
    "Do not invent facts, recalculate, estimate, or state any number. Do not diagnose, "
    "treat, prescribe, pressure, or shame. A safety stop or pain signal requires serious, "
    "non-playful wording. Low completion alone must not imply lower intensity or shorter "
    "duration. Preserve the requested duration unless the aggregate explicitly records a "
    "time or schedule reason. COACH_MESSAGE must combine one observed strength, a neutral "
    "weekly summary, and encouragement for next week in one or two sentences. Return exactly "
    "a JSON object with a sentences object containing every supplied slot code; each value "
    "must be a single line."
)


def _shareable_value(value: Any) -> bool:
    """Allow only normalized aggregate values, never identifiers or free text."""

    if value is None or isinstance(value, bool | int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, str):
        return bool(re.fullmatch(r"[A-Za-z0-9._:/+-]+", value))
    if isinstance(value, list):
        return all(_shareable_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str)
            and bool(re.fullmatch(r"[A-Za-z0-9._:/+-]+", key))
            and _shareable_value(item)
            for key, item in value.items()
        )
    return False


def _sentence_is_acceptable(value: object) -> bool:
    if not isinstance(value, str):
        return False
    sentence = value.strip()
    if not sentence or len(sentence) > _MAX_SENTENCE_LENGTH or "\n" in sentence:
        return False
    if _DIGIT_PATTERN.search(sentence):
        return False
    lowered = sentence.casefold()
    return not any(term in lowered for term in _BANNED_TERMS)


def _llm_narration_is_acceptable(narration: WeeklyReportNarration) -> bool:
    return (
        narration.source_code == "LLM"
        and narration.prompt_version == WEEKLY_REPORT_NARRATION_PROMPT_VERSION
        and isinstance(narration.model_code, str)
        and bool(_MACHINE_CODE_PATTERN.fullmatch(narration.model_code))
        and narration.fallback_reason_code is None
        and set(narration.next_week_recommendation)
        == {"intensity", "volume", "duration", "pain_response"}
        and all(
            _sentence_is_acceptable(sentence)
            for sentence in (
                narration.summary,
                narration.decision_summary,
                narration.next_action,
                *narration.next_week_recommendation.values(),
            )
        )
    )


def _template(report: WeeklyReportNarrationInput, reason_code: str) -> WeeklyReportNarration:
    return WeeklyReportNarration(
        summary=report.template_summary,
        decision_summary=report.template_decision_summary,
        next_action=report.template_next_action,
        source_code="TEMPLATE",
        next_week_recommendation=report.template_next_week_recommendation,
        fallback_reason_code=reason_code,
    )


def _prompt(report: WeeklyReportNarrationInput) -> NarrationPrompt | None:
    payload = {
        "input_snapshot": report.input_snapshot,
        "objective_metrics": report.objective_metrics,
    }
    if not _shareable_value(payload):
        return None
    return NarrationPrompt(
        prompt_version=WEEKLY_REPORT_NARRATION_PROMPT_VERSION,
        instruction=_INSTRUCTION,
        slot_codes=_SLOT_CODES,
        payload=payload,
    )


class WeeklyReportNarrationAgent:
    """Optional interpretation Agent that can replace only reviewed template wording."""

    def __init__(self, provider: NarrationProviderPort | None = None) -> None:
        self._provider = provider

    def interpret(self, report: WeeklyReportNarrationInput) -> WeeklyReportNarration:
        if self._provider is None:
            return _template(report, "LLM_DISABLED")
        prompt = _prompt(report)
        if prompt is None:
            return _template(report, "PAYLOAD_NOT_SHAREABLE")
        try:
            completion = self._provider.narrate(prompt)
        except NarrationProviderUnavailableError:
            return _template(report, "LLM_DISABLED")
        except Exception:
            # Provider and parsing failures are not exposed and never fail report creation.
            return _template(report, "LLM_PROVIDER_FAILED")
        if not isinstance(completion, NarrationCompletion):
            return _template(report, "LLM_OUTPUT_REJECTED")
        if not isinstance(completion.model_code, str) or not _MACHINE_CODE_PATTERN.fullmatch(
            completion.model_code
        ):
            return _template(report, "LLM_OUTPUT_REJECTED")
        if set(completion.sentences) != set(_SLOT_CODES):
            return _template(report, "LLM_OUTPUT_REJECTED")
        sentences = {code: completion.sentences[code].strip() for code in _SLOT_CODES}
        if not all(_sentence_is_acceptable(sentence) for sentence in sentences.values()):
            return _template(report, "LLM_OUTPUT_REJECTED")
        return WeeklyReportNarration(
            summary=sentences["COACH_MESSAGE"],
            decision_summary=sentences["ADJUSTMENT_SUMMARY"],
            next_action=" ".join(
                sentences[code]
                for code in (
                    "NEXT_WEEK_INTENSITY",
                    "NEXT_WEEK_VOLUME",
                    "NEXT_WEEK_DURATION",
                    "NEXT_WEEK_PAIN_RESPONSE",
                )
            ),
            source_code="LLM",
            next_week_recommendation={
                "intensity": sentences["NEXT_WEEK_INTENSITY"],
                "volume": sentences["NEXT_WEEK_VOLUME"],
                "duration": sentences["NEXT_WEEK_DURATION"],
                "pain_response": sentences["NEXT_WEEK_PAIN_RESPONSE"],
            },
            model_code=completion.model_code,
            prompt_version=prompt.prompt_version,
        )


def apply_narration(
    values: ReportValues,
    agent: WeeklyReportNarrationAgentPort | None,
) -> ReportValues:
    """Attach narration audit data while preserving every deterministic report value."""

    narration_snapshot: dict[str, Any] = {
        key: values.input_snapshot[key]
        for key in (
            "official_outcome_counts",
            "not_completed_reason_counts",
            "adjusted_selection_outcomes",
            "feedback_summary",
            "condition_summary",
            "outcome_reason_summary",
            "recommendation_action_counts",
            "recommendation_context_counts",
        )
        if key in values.input_snapshot
    }
    raw_metrics = values.input_snapshot.get("weekly_metrics")
    if isinstance(raw_metrics, dict):
        narration_snapshot["weekly_metrics"] = {
            key: value
            for key, value in raw_metrics.items()
            if key != "most_performed_exercise_name"
        }
    report = WeeklyReportNarrationInput(
        input_snapshot=narration_snapshot,
        objective_metrics={
            "counts": {
                "completed": values.completed_count,
                "partial": values.partial_count,
                "not_completed": values.not_completed_count,
                # Both names carry the same number this release; the legacy key stays so
                # a narration prompt written against v1 keeps working.
                "stopped_for_safety": values.stopped_for_safety,
                "safety_stopped_session_count": values.safety_stopped_session_count,
            },
            "completion_rate": values.completion_rate,
            "persistence_rate": values.persistence_rate,
            "negotiation_success_rate": values.negotiation_success_rate,
            "primary_miss_reason_code": values.primary_miss_reason_code,
            "adjustment_direction_code": values.adjustment_direction_code,
        },
        template_summary=values.summary,
        template_decision_summary=values.decision_summary,
        template_next_action=values.next_action,
        template_next_week_recommendation=values.next_week_recommendation,
    )
    narrator = agent or WeeklyReportNarrationAgent()
    try:
        narration = narrator.interpret(report)
    except Exception:
        narration = _template(report, "AGENT_FAILED")
    if not isinstance(narration, WeeklyReportNarration):
        narration = _template(report, "AGENT_OUTPUT_INVALID")
    elif narration.source_code == "LLM" and not _llm_narration_is_acceptable(narration):
        narration = _template(report, "AGENT_OUTPUT_INVALID")
    elif narration.source_code != "LLM" and narration.source_code != "TEMPLATE":
        narration = _template(report, "AGENT_OUTPUT_INVALID")
    return replace(
        values,
        summary=narration.summary,
        decision_summary=narration.decision_summary,
        # Keep the legacy field concise and within its existing DB column. New clients
        # read the four explicit recommendation axes stored in the narration audit JSON.
        next_action=values.next_action,
        next_week_recommendation=narration.next_week_recommendation,
        coach_message=narration.summary,
        agent_summaries={
            WEEKLY_REPORT_INTERPRETER_CODE: {
                "agent_type_code": WEEKLY_REPORT_INTERPRETER_CODE,
                "source_code": narration.source_code,
                "model_code": narration.model_code,
                "prompt_version": narration.prompt_version,
                "fallback_reason_code": narration.fallback_reason_code,
                "input_schema_version": values.input_schema_version,
                "input_hash": values.input_hash,
                "next_week_recommendation": narration.next_week_recommendation,
            }
        },
    )


__all__ = [
    "WEEKLY_REPORT_INTERPRETER_CODE",
    "WEEKLY_REPORT_NARRATION_PROMPT_VERSION",
    "WeeklyReportNarrationAgent",
    "apply_narration",
]
