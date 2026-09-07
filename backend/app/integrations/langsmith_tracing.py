"""Opt-in LangSmith tracer for the staging shadow and demo runtimes.

ADR-0020 allows LangSmith only on those two surfaces. The production decision path
is never handed a tracer, and both the structured invoker and the graph runtime keep
`tracing_context(enabled=False)` around every call, so an ambient `LANGSMITH_TRACING`
environment variable cannot start an export on its own. Tracing happens when, and only
when, a composition passes the handler this module builds.

An explicitly injected `LangChainTracer` still records under a disabled tracing context:
`langchain_core` copies passed handlers into the callback manager unconditionally and
only consults the context flag when deciding whether to *add* an implicit tracer. That
asymmetry is what lets one switch stay permanently off while the other stays injectable.
"""

from __future__ import annotations

from langchain_core.tracers import LangChainTracer
from langsmith import Client

from backend.app.core.config import Settings

# The project name used when the deployment does not name one. LangSmith would
# otherwise fall back to its own "default" project and mix runs from unrelated
# services into one trace list.
DEFAULT_PROJECT_NAME = "helkki-shadow"


def build_langsmith_tracer(settings: Settings) -> LangChainTracer | None:
    """Return a tracer, or None when tracing is not configured for this deployment.

    Returning None rather than raising keeps the runtimes composable: a missing
    tracer degrades to the existing untraced behaviour. `Settings` already refuses
    to start when tracing is enabled without a key, so None here means the operator
    left it off, not that a credential went missing.
    """

    if not settings.langsmith_tracing_enabled or settings.langsmith_api_key is None:
        return None
    client = Client(
        api_url=settings.langsmith_endpoint,
        api_key=settings.langsmith_api_key.get_secret_value(),
    )
    return LangChainTracer(
        project_name=settings.langsmith_project or DEFAULT_PROJECT_NAME,
        client=client,
    )


__all__ = ["DEFAULT_PROJECT_NAME", "build_langsmith_tracer"]
