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
    "Use only the supplied structured fields and exercise IDs. Never invent an exercise ID, "
    "relax a constraint, or provide hidden reasoning. Return only the requested schema."
)

ROLE_PROMPTS: Final[Mapping[LlmAgentRoleCode, RolePrompt]] = MappingProxyType(
    {
        LlmAgentRoleCode.TRAINING: RolePrompt(
            role_code=LlmAgentRoleCode.TRAINING,
            version="v3-training-prompt-v1",
            instruction=(
                "Act as the Training specialist. Propose goal-preserving training content "
                "within the constraint envelope, recovery ceiling, and exercise pool. "
                f"{_COMMON_BOUNDARY}"
            ),
        ),
        LlmAgentRoleCode.RECOVERY: RolePrompt(
            role_code=LlmAgentRoleCode.RECOVERY,
            version="v3-recovery-prompt-v1",
            instruction=(
                "Act as the Recovery specialist. Enforce the supplied recovery ceiling and "
                "select only recovery-compatible pool content. "
                f"{_COMMON_BOUNDARY}"
            ),
        ),
        LlmAgentRoleCode.FEASIBILITY: RolePrompt(
            role_code=LlmAgentRoleCode.FEASIBILITY,
            version="v3-feasibility-prompt-v1",
            instruction=(
                "Act as the Feasibility specialist. Preserve requested duration and verify "
                "time, equipment, and location feasibility using only pool content. "
                f"{_COMMON_BOUNDARY}"
            ),
        ),
        LlmAgentRoleCode.COORDINATOR: RolePrompt(
            role_code=LlmAgentRoleCode.COORDINATOR,
            version="v3-coordinator-prompt-v1",
            instruction=(
                "Coordinate exactly the three supplied specialist proposals into one PlanSpec. "
                "Do not weaken safety, time, goal, equipment, or recovery constraints. A repair "
                "request is evidence for this single call, never permission to start a loop. "
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
