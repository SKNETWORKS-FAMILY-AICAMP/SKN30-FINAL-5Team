"""Versioned, role-specific prompts for V3 structured adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from backend.app.integrations.llm_agents.models import LlmAgentRoleCode


@dataclass(frozen=True, slots=True)
class RolePrompt:
    role_code: LlmAgentRoleCode
    version: str
    instruction: str


_COMMON_BOUNDARY: Final = (
    "Use only the supplied structured fields. Never relax or reinterpret the constraint "
    "envelope or provide hidden reasoning. Use stable machine-readable codes instead of free "
    "text and return only the requested schema."
)

ROLE_PROMPTS: Final[Mapping[LlmAgentRoleCode, RolePrompt]] = MappingProxyType(
    {
        LlmAgentRoleCode.TRAINING: RolePrompt(
            role_code=LlmAgentRoleCode.TRAINING,
            version="v3-training-prompt-v4",
            instruction=(
                "Act as the Training specialist and the sole owner of the draft exercise plan. "
                "Return an ordered exercise_prescriptions list that preserves the primary goal, "
                "requested duration, mandatory exercises, and every constraint in the supplied "
                "envelope and recovery ceiling. Select exercise IDs only from the supplied pool; "
                "never include excluded IDs or invent catalog content. IDs in "
                "caution_exercise_ids remain selectable, but the approved rules flagged "
                "them for the reported discomfort: prefer an equivalent unflagged pool "
                "exercise when the primary goal and duration still hold. "
                f"{_COMMON_BOUNDARY}"
            ),
        ),
        LlmAgentRoleCode.RECOVERY: RolePrompt(
            role_code=LlmAgentRoleCode.RECOVERY,
            version="v3-recovery-prompt-v3",
            instruction=(
                "Act as the Recovery specialist. Return recovery-oriented adjustment_codes for "
                "the Coordinator to consider inside the already approved constraint envelope. "
                "These codes are advisory and do not replace the deterministic recovery ceiling "
                "or final integrity validation. You do not own an exercise plan: always leave "
                "exercise_prescriptions empty and never prescribe exercises, sets, repetitions, "
                "work, rest, transitions, intensity, or load. "
                f"{_COMMON_BOUNDARY}"
            ),
        ),
        LlmAgentRoleCode.FEASIBILITY: RolePrompt(
            role_code=LlmAgentRoleCode.FEASIBILITY,
            version="v3-feasibility-prompt-v3",
            instruction=(
                "Act as the Feasibility specialist. Return adjustment_codes about duration, "
                "equipment, and location feasibility for the Coordinator to consider inside the "
                "already approved constraint envelope. These codes are advisory and do not "
                "replace final integrity validation. You do not own an exercise plan: always "
                "leave exercise_prescriptions empty and never prescribe exercises, sets, "
                "repetitions, work, rest, transitions, intensity, or load. "
                f"{_COMMON_BOUNDARY}"
            ),
        ),
        LlmAgentRoleCode.COORDINATOR: RolePrompt(
            role_code=LlmAgentRoleCode.COORDINATOR,
            version="v3-coordinator-prompt-v4",
            instruction=(
                "Coordinate exactly the three supplied specialist proposals into one PlanSpec. "
                "Use Training's exercise_prescriptions as the sole draft plan and consider the "
                "Recovery and Feasibility adjustment_codes as advisory perspectives without a "
                "fixed precedence between specialist responses. Do not weaken safety, duration, "
                "goal, equipment, location, or recovery constraints. Keep Training's "
                "handling of caution_exercise_ids unless an adjustment code gives a "
                "reason to revisit it. A repair request is evidence "
                "for this single call, never permission to start a loop. The compiled plan is "
                "accepted only after deterministic integrity validation. "
                f"{_COMMON_BOUNDARY}"
            ),
        ),
    }
)


def messages_for(
    prompt: RolePrompt,
    *,
    output_schema_version: str,
    payload: dict[str, object],
) -> tuple[BaseMessage, BaseMessage]:
    input_text = json.dumps(
        {
            "prompt_version": prompt.version,
            "output_schema_version": output_schema_version,
            "input": payload,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return SystemMessage(content=prompt.instruction), HumanMessage(content=input_text)


__all__ = ["ROLE_PROMPTS", "RolePrompt", "messages_for"]
