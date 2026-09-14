"""The three architectures PHASE 6 compares, and what each one can be asked.

Some of the PHASE 4 metrics are questions only a multi-agent run can answer.
"Did the advisory specialists refrain from prescribing exercises?" has no
referent when there are no advisory specialists, and reporting it as 1.0 for a
baseline would manufacture a tie out of a question that was never asked.

`MULTI_AGENT_ONLY_METRICS` names those, so the comparison reports them as
not-applicable rather than as a perfect score.
"""

from __future__ import annotations

from typing import Final

ARCHITECTURE_SINGLE_LLM: Final = "SINGLE_LLM"
ARCHITECTURE_SINGLE_AGENT_RAG: Final = "SINGLE_AGENT_RAG"
ARCHITECTURE_MULTI_AGENT: Final = "MULTI_AGENT"

# Ordered A, B, C to match the master specification's own naming.
COMPARED_ARCHITECTURES: Final[tuple[str, ...]] = (
    ARCHITECTURE_SINGLE_LLM,
    ARCHITECTURE_SINGLE_AGENT_RAG,
    ARCHITECTURE_MULTI_AGENT,
)

ARCHITECTURE_LABELS: Final[dict[str, str]] = {
    ARCHITECTURE_SINGLE_LLM: "A. Single LLM",
    ARCHITECTURE_SINGLE_AGENT_RAG: "B. Single Agent + RAG",
    ARCHITECTURE_MULTI_AGENT: "C. Multi-Agent + RAG",
}

# Metrics whose subject exists only when three specialists and a coordinator do.
MULTI_AGENT_ONLY_METRICS: Final[tuple[str, ...]] = (
    "agent_role_consistency",
    "state_consistency",
)


def is_multi_agent(architecture_code: str) -> bool:
    return architecture_code == ARCHITECTURE_MULTI_AGENT


__all__ = [
    "ARCHITECTURE_LABELS",
    "ARCHITECTURE_MULTI_AGENT",
    "ARCHITECTURE_SINGLE_AGENT_RAG",
    "ARCHITECTURE_SINGLE_LLM",
    "COMPARED_ARCHITECTURES",
    "MULTI_AGENT_ONLY_METRICS",
    "is_multi_agent",
]
