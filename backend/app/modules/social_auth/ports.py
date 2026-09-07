from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from backend.app.domain.rules.auth_provider import (
    AuthorizationFlow,
    AuthProviderCode,
    ProviderFailureKindCode,
    ProviderTokenEvidence,
    RateLimitDimensionCode,
)
from backend.app.modules.identity.ports import IdentityUserRecord


class ProviderExchangeError(Exception):
    def __init__(self, kind: ProviderFailureKindCode) -> None:
        self.kind = kind
        super().__init__(kind)


class FirebaseCustomTokenUnavailableError(Exception):
    """Firebase could not mint a custom token after the identity commit."""


@dataclass(frozen=True)
class ClaimedAuthorizationFlow:
    flow: AuthorizationFlow | None


class SocialOAuthRepositoryPort(Protocol):
    def consume_rate_limit(
        self,
        session: Session,
        *,
        provider_code: AuthProviderCode,
        dimension_code: RateLimitDimensionCode,
        key_digest_hex: str,
        window_started_at: datetime,
        window_seconds: int,
        attempted_at: datetime,
    ) -> int: ...

    def create_flow(self, session: Session, flow: AuthorizationFlow) -> None: ...

    def claim_flow(self, session: Session, state_digest_hex: str) -> AuthorizationFlow | None: ...

    def resolve_social_identity(
        self,
        session: Session,
        *,
        provider_code: AuthProviderCode,
        provider_subject: str,
        now: datetime,
    ) -> IdentityUserRecord: ...


class KakaoOAuthPort(Protocol):
    def build_authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str: ...

    def exchange_authorization_code(
        self,
        *,
        authorization_code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> ProviderTokenEvidence: ...


class FirebaseCustomTokenIssuer(Protocol):
    def create_custom_token(self, firebase_subject: str) -> str: ...


__all__ = [
    "ClaimedAuthorizationFlow",
    "FirebaseCustomTokenIssuer",
    "FirebaseCustomTokenUnavailableError",
    "KakaoOAuthPort",
    "ProviderExchangeError",
    "SocialOAuthRepositoryPort",
]
