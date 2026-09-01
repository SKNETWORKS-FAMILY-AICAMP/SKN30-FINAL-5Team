"""Single integration boundary for the teammate-owned V3 demo runtime factory."""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Protocol, cast

from backend.app.core.config import Settings
from backend.app.modules.decisions.v3_creation import V3InitialGraphRuntimePort
from backend.app.modules.decisions.v3_regeneration import V3GraphRuntimePort

logger = logging.getLogger(__name__)


class V3DemoRuntimePort(V3InitialGraphRuntimePort, V3GraphRuntimePort, Protocol):
    """Application-facing surface expected from ``V3DemoRuntime``."""


def _implements_application_contract(runtime: object) -> bool:
    return callable(getattr(runtime, "create", None)) and callable(
        getattr(runtime, "regenerate", None)
    )


def build_optional_v3_demo_runtime(
    settings: Settings,
    *,
    identity_provider: object | None = None,
    production_promotion_approved: bool | None = None,
) -> V3DemoRuntimePort | None:
    """Load the teammate factory without leaking LangGraph/provider types.

    The import remains here so domain, application services and API routes do
    not depend on the concrete graph/provider implementation.  Until the
    teammate module lands, explicit service test doubles can be injected into
    ``create_app`` and LEGACY startup remains unaffected.
    """

    profile = settings.v3_execution_profile
    promotion_approved = (
        settings.v3_production_promotion_approved
        if production_promotion_approved is None
        else production_promotion_approved
    )
    authoritative = profile == "DEMO" or (profile == "PRODUCTION" and promotion_approved)
    if not authoritative:
        return None
    try:
        module = import_module("backend.app.integrations.langgraph.demo_runtime")
        build_v3_demo_runtime = module.build_v3_demo_runtime
    except (AttributeError, ImportError):
        return None
    try:
        kwargs = {"identity_provider": identity_provider} if identity_provider is not None else {}
        runtime = build_v3_demo_runtime(settings, execution_profile=profile, **kwargs)
        if not _implements_application_contract(runtime):
            raise TypeError("runtime application contract is unavailable")
        return cast(V3DemoRuntimePort, runtime)
    except (RuntimeError, TypeError, ValueError):
        # Missing provider configuration must not prevent safe application
        # startup. Never log the exception because adapters may attach payloads.
        logger.warning(
            "V3 demo runtime is unavailable",
            extra={"failure_code": "V3_RUNTIME_UNAVAILABLE"},
        )
        return None


__all__ = ["V3DemoRuntimePort", "build_optional_v3_demo_runtime"]
