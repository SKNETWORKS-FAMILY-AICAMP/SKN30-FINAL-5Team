"""Single integration boundary for the teammate-owned V3 demo runtime factory."""

from __future__ import annotations

import logging
from typing import Protocol

from backend.app.core.config import Settings
from backend.app.modules.decisions.v3_creation import V3InitialGraphRuntimePort
from backend.app.modules.decisions.v3_regeneration import V3GraphRuntimePort

logger = logging.getLogger(__name__)


class V3DemoRuntimePort(V3InitialGraphRuntimePort, V3GraphRuntimePort, Protocol):
    """Application-facing surface expected from ``V3DemoRuntime``."""


def build_optional_v3_demo_runtime(settings: Settings) -> V3DemoRuntimePort | None:
    """Load the teammate factory without leaking LangGraph/provider types.

    The import remains here so domain, application services and API routes do
    not depend on the concrete graph/provider implementation.  Until the
    teammate module lands, explicit service test doubles can be injected into
    ``create_app`` and LEGACY startup remains unaffected.
    """

    if settings.v3_execution_profile == "LEGACY":
        return None
    try:
        from backend.app.integrations.langgraph.demo_runtime import (
            build_v3_demo_runtime,
        )
    except ImportError:
        return None
    try:
        return build_v3_demo_runtime(
            settings,
            execution_profile=settings.v3_execution_profile,
        )
    except (RuntimeError, ValueError):
        # Missing provider configuration must not prevent safe application
        # startup. Never log the exception because adapters may attach payloads.
        logger.warning(
            "V3 demo runtime is unavailable",
            extra={"failure_code": "V3_RUNTIME_UNAVAILABLE"},
        )
        return None


__all__ = ["V3DemoRuntimePort", "build_optional_v3_demo_runtime"]
