"""LangSmith tracing for evaluation runs, and an honest account of its limits.

**What a trace shows, measured rather than assumed.** Running the shipped graph
inside a tracing context produces 15 spans for a healthy plan: `validate_entry`,
every routing decision, the three specialist nodes running in parallel,
`collect_proposals`, `coordinator_agent`, `compile`, `validate`, `finalize`. Node
inputs and outputs carry the constraint envelope, the exercise pool, the three
proposals and the coordinator's PlanSpec.

**What it does not show: the LLM calls themselves.** `provider.py` wraps every
provider invocation in `tracing_context(enabled=False)`, explicitly so ambient
tracing settings cannot export prompt content, and `openai.py` passes
`callbacks=[]`. So prompts, raw model output and provider token usage never reach
LangSmith. Token counts are still available -- `InvocationAudit` records them
inside the graph -- but from the audit, not from the trace.

That gap is deliberate (`docs/TECHNICAL_PLAN.md` lines 65 and 346: LangSmith SaaS
transmission is out of scope without separate approval). Closing it would mean
changing `provider.py`, which is an owner-restricted area *and* a privacy policy
decision, so this module does not do it. See `docs/test/LANGSMITH_TRACING.md`.

**What is still sent.** Node state contains no direct identifiers -- no birth
date, age, name, email or user id -- but it does carry health-adjacent inferences:
the excluded exercise IDs imply a discomfort area, and the recovery ceiling
implies fatigue. Enabling this exports that to a third-party SaaS. Nothing here
turns tracing on by itself: it activates only when the caller supplies a key.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final

from langchain_core.tracers.base import BaseTracer

LANGSMITH_API_KEY_ENV: Final = "LANGSMITH_API_KEY"
LANGSMITH_PROJECT_ENV: Final = "LANGSMITH_PROJECT"
LANGSMITH_ENDPOINT_ENV: Final = "LANGSMITH_ENDPOINT"

DEFAULT_PROJECT: Final = "helkki-service-quality"

# Experiment names the master specification asks for, so runs stay comparable.
EXPERIMENT_MULTI_AGENT: Final = "multi-agent-v1"
EXPERIMENT_SINGLE_AGENT: Final = "baseline-single-agent-v1"
EXPERIMENT_SCRIPTED: Final = "multi-agent-scripted-offline-v1"

# Measured, not assumed: `_probe_traced_runs` in the tests asserts this list.
EXPECTED_TRACED_NODES: Final[tuple[str, ...]] = (
    "LangGraph",
    "validate_entry",
    "after_entry",
    "parallel_agents",
    "agent_training",
    "agent_recovery",
    "agent_feasibility",
    "collect_proposals",
    "after_agents",
    "coordinator_agent",
    "compile",
    "after_compile",
    "validate",
    "after_validation",
    "finalize",
)


class TracingUnavailableError(RuntimeError):
    """Raised only when tracing was explicitly requested and cannot be provided."""


@dataclass(frozen=True, slots=True)
class TracingStatus:
    enabled: bool
    project_name: str | None
    experiment_name: str | None
    reason: str | None = None

    @property
    def summary(self) -> str:
        if self.enabled:
            return f"LangSmith tracing on: project={self.project_name} run={self.experiment_name}"
        return f"LangSmith tracing off: {self.reason}"


def langsmith_configured() -> bool:
    """Whether a key is present. Absence is a normal state, never an error."""

    return bool(os.environ.get(LANGSMITH_API_KEY_ENV))


@contextmanager
def langsmith_run(
    experiment_name: str,
    *,
    project_name: str | None = None,
    required: bool = False,
    metadata: dict[str, Any] | None = None,
) -> Iterator[TracingStatus]:
    """Run a block with LangSmith tracing when a key is configured.

    Without a key this yields a disabled status and runs the block normally, so
    the whole local evaluation still works offline -- which the master
    specification requires. Pass `required=True` to make a missing key an error
    instead, for the run whose entire purpose is to produce a trace.
    """

    if not langsmith_configured():
        status = TracingStatus(
            enabled=False,
            project_name=None,
            experiment_name=experiment_name,
            reason=f"{LANGSMITH_API_KEY_ENV} is not set",
        )
        if required:
            raise TracingUnavailableError(status.summary)
        yield status
        return

    from langsmith.run_helpers import tracing_context

    resolved_project = project_name or os.environ.get(LANGSMITH_PROJECT_ENV, DEFAULT_PROJECT)
    with tracing_context(
        enabled=True,
        project_name=resolved_project,
        tags=[experiment_name],
        metadata={"experiment_name": experiment_name, **(metadata or {})},
    ):
        yield TracingStatus(
            enabled=True,
            project_name=resolved_project,
            experiment_name=experiment_name,
        )


class RunRecorder(BaseTracer):
    """Collect the runs a tracer would see, locally and without any network.

    Used to prove what a LangSmith trace would and would not contain, so the
    claim in this module's docstring is measured rather than asserted.
    """

    name = "evaluation_run_recorder"

    def __init__(self) -> None:
        super().__init__()
        self.observed: list[tuple[str, str]] = []

    def _persist_run(self, run: Any) -> None:
        return None

    def _on_run_create(self, run: Any) -> None:
        self.observed.append((str(run.run_type), str(run.name)))

    @property
    def node_names(self) -> tuple[str, ...]:
        return tuple(name for _, name in self.observed)

    @property
    def llm_run_count(self) -> int:
        return sum(1 for run_type, _ in self.observed if run_type in {"llm", "chat_model"})


@contextmanager
def record_runs() -> Iterator[RunRecorder]:
    """Attach a local recorder for the duration of the block.

    Registers through the same configure hook LangSmith's tracer uses, so what
    it sees is what a LangSmith trace would receive.
    """

    from contextvars import ContextVar

    from langchain_core.tracers.context import register_configure_hook

    recorder = RunRecorder()
    variable: ContextVar[RunRecorder | None] = ContextVar("evaluation_recorder", default=None)
    register_configure_hook(variable, True)
    token = variable.set(recorder)
    try:
        yield recorder
    finally:
        variable.reset(token)


__all__ = [
    "DEFAULT_PROJECT",
    "EXPECTED_TRACED_NODES",
    "EXPERIMENT_MULTI_AGENT",
    "EXPERIMENT_SCRIPTED",
    "EXPERIMENT_SINGLE_AGENT",
    "LANGSMITH_API_KEY_ENV",
    "LANGSMITH_ENDPOINT_ENV",
    "LANGSMITH_PROJECT_ENV",
    "RunRecorder",
    "TracingStatus",
    "TracingUnavailableError",
    "langsmith_configured",
    "langsmith_run",
    "record_runs",
]
