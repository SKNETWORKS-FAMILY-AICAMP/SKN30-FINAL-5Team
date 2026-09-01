"""Server-owned selection of the decision creation application service."""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.modules.decisions.schemas import DecisionCreateRequest, DecisionResponse

logger = logging.getLogger(__name__)


class V3ExecutionProfile(StrEnum):
    LEGACY = "LEGACY"
    SHADOW = "SHADOW"
    DEMO = "DEMO"
    PRODUCTION = "PRODUCTION"


class DecisionCreationServicePort(Protocol):
    async def create(
        self,
        session: Session,
        user_id: UUID,
        request: DecisionCreateRequest,
        idempotency_key: UUID,
    ) -> DecisionResponse: ...


class LegacyDecisionServicePort(Protocol):
    def create(
        self,
        session: Session,
        user_id: UUID,
        request: DecisionCreateRequest,
        idempotency_key: UUID,
    ) -> DecisionResponse: ...


class V3ShadowCreationPort(Protocol):
    async def shadow(
        self,
        *,
        user_id: UUID,
        request: DecisionCreateRequest,
        idempotency_key: UUID,
    ) -> None: ...


class V3ProductionPromotionGatePort(Protocol):
    def allows_v3(self) -> bool: ...


class LegacyDecisionCreationService:
    """Async application adapter around the unchanged deterministic service."""

    def __init__(self, service: LegacyDecisionServicePort) -> None:
        self._service = service

    async def create(
        self,
        session: Session,
        user_id: UUID,
        request: DecisionCreateRequest,
        idempotency_key: UUID,
    ) -> DecisionResponse:
        return self._service.create(session, user_id, request, idempotency_key)


class StaticV3ProductionPromotionGate:
    def __init__(self, approved: bool = False) -> None:
        self._approved = approved

    def allows_v3(self) -> bool:
        return self._approved


class ProfiledDecisionCreationService:
    """Select a use case without putting profile rules in the API route."""

    def __init__(
        self,
        *,
        profile: V3ExecutionProfile,
        legacy: DecisionCreationServicePort,
        v3: DecisionCreationServicePort | None,
        promotion_gate: V3ProductionPromotionGatePort,
        shadow: V3ShadowCreationPort | None = None,
    ) -> None:
        self._profile = profile
        self._legacy = legacy
        self._v3 = v3
        self._promotion_gate = promotion_gate
        self._shadow = shadow

    async def create(
        self,
        session: Session,
        user_id: UUID,
        request: DecisionCreateRequest,
        idempotency_key: UUID,
    ) -> DecisionResponse:
        if self._profile is V3ExecutionProfile.DEMO:
            return await self._selected_v3().create(session, user_id, request, idempotency_key)
        if self._profile is V3ExecutionProfile.PRODUCTION and self._promotion_gate.allows_v3():
            return await self._selected_v3().create(session, user_id, request, idempotency_key)

        response = await self._legacy.create(session, user_id, request, idempotency_key)
        if self._profile is V3ExecutionProfile.SHADOW and self._shadow is not None:
            try:
                await self._shadow.shadow(
                    user_id=user_id,
                    request=request,
                    idempotency_key=idempotency_key,
                )
            except Exception:
                # Shadow failures never change the public response. No exception
                # details are logged because provider errors may contain payloads.
                logger.warning(
                    "V3 shadow execution failed",
                    extra={"failure_code": "V3_SHADOW_FAILED"},
                )
        return response

    def _selected_v3(self) -> DecisionCreationServicePort:
        if self._v3 is None:
            # The profile is explicit operator intent. Missing composition is a
            # startup/deployment defect and must not silently claim V3 output.
            raise V3CompositionUnavailableError
        return self._v3


class V3CompositionUnavailableError(RuntimeError):
    pass


__all__ = [
    "DecisionCreationServicePort",
    "LegacyDecisionCreationService",
    "LegacyDecisionServicePort",
    "ProfiledDecisionCreationService",
    "StaticV3ProductionPromotionGate",
    "V3CompositionUnavailableError",
    "V3ExecutionProfile",
    "V3ProductionPromotionGatePort",
    "V3ShadowCreationPort",
]
