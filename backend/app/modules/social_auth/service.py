"""Application service for the server-owned Kakao authorization-code flow."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.domain.rules.auth_provider import (
    AuthFailureCode,
    AuthProviderCode,
    AuthProviderContractError,
    RateLimitDimensionCode,
    claim_authorization_flow,
    create_authorization_flow,
    evaluate_fixed_window_limit,
    rate_limit_key_digest,
    validate_provider_nonce,
    validate_provider_token,
)
from backend.app.modules.social_auth.ports import (
    FirebaseCustomTokenIssuer,
    FirebaseCustomTokenUnavailableError,
    GoogleOAuthPort,
    KakaoOAuthPort,
    ProviderExchangeError,
    SocialOAuthRepositoryPort,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AuthorizationInitResult:
    authorization_url: str
    state: str
    nonce: str
    expires_at: datetime


class SocialOAuthService:
    def __init__(
        self,
        repository: SocialOAuthRepositoryPort,
        kakao: KakaoOAuthPort,
        firebase_tokens: FirebaseCustomTokenIssuer,
        *,
        redirect_uris: frozenset[str],
        rate_limit_hmac_key: bytes,
        google: GoogleOAuthPort | None = None,
        google_redirect_uris: frozenset[str] = frozenset(),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not (redirect_uris or google_redirect_uris) or not rate_limit_hmac_key:
            raise ValueError("Social OAuth requires approved redirects and rate-limit key material")
        self._repository = repository
        self._providers: dict[AuthProviderCode, KakaoOAuthPort | GoogleOAuthPort] = {
            AuthProviderCode.KAKAO: kakao,
        }
        if google is not None:
            self._providers[AuthProviderCode.GOOGLE] = google
        self._firebase_tokens = firebase_tokens
        self._redirect_uris = {
            AuthProviderCode.KAKAO: redirect_uris,
            AuthProviderCode.GOOGLE: google_redirect_uris,
        }
        self._rate_limit_hmac_key = rate_limit_hmac_key
        self._clock = clock

    def _require_provider(self, provider_code: str) -> AuthProviderCode:
        try:
            provider = AuthProviderCode(provider_code)
        except ValueError:
            raise AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_STATE) from None
        if provider not in self._providers:
            raise AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_STATE)
        return provider

    def _redirect_key(
        self,
        provider_code: AuthProviderCode,
        redirect_uri: str,
        *,
        require_registered: bool,
    ) -> str:
        if require_registered and redirect_uri not in self._redirect_uris[provider_code]:
            raise AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_STATE)
        return hashlib.sha256(redirect_uri.encode("utf-8")).hexdigest()

    @staticmethod
    def _window_start(now: datetime, seconds: int) -> datetime:
        epoch = int(now.timestamp())
        return datetime.fromtimestamp(epoch - (epoch % seconds), tz=UTC)

    def _apply_rate_limits(
        self,
        session: Session,
        *,
        provider_code: AuthProviderCode,
        client_ip: str,
        redirect_uri: str,
        now: datetime,
    ) -> None:
        attempts = (
            (RateLimitDimensionCode.CLIENT_IP, client_ip, 60),
            (RateLimitDimensionCode.PROVIDER_REDIRECT, redirect_uri, 3600),
        )
        failures: list[AuthProviderContractError] = []
        with session.begin():
            for dimension, raw_key, seconds in attempts:
                start = self._window_start(now, seconds)
                count = self._repository.consume_rate_limit(
                    session,
                    provider_code=provider_code,
                    dimension_code=dimension,
                    key_digest_hex=rate_limit_key_digest(
                        raw_key=raw_key,
                        hmac_key=self._rate_limit_hmac_key,
                    ).hex(),
                    window_started_at=start,
                    window_seconds=seconds,
                    attempted_at=now,
                )
                decision = evaluate_fixed_window_limit(
                    dimension_code=dimension,
                    count_before_attempt=count - 1,
                    attempted_at=now,
                    window_started_at=start,
                )
                if not decision.allowed:
                    failures.append(AuthProviderContractError(AuthFailureCode.RATE_LIMITED))
        if failures:
            raise failures[0]

    def authorize_init(
        self,
        session: Session,
        *,
        provider_code: str,
        redirect_uri: str,
        code_challenge: str,
        client_ip: str,
    ) -> AuthorizationInitResult:
        provider = self._require_provider(provider_code)
        redirect_key = self._redirect_key(provider, redirect_uri, require_registered=True)
        now = self._clock()
        self._apply_rate_limits(
            session,
            provider_code=provider,
            client_ip=client_ip,
            redirect_uri=redirect_uri,
            now=now,
        )
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        flow = create_authorization_flow(
            flow_id=uuid4(),
            provider_code=provider,
            state=state,
            nonce=nonce,
            pkce_challenge_s256=code_challenge,
            redirect_uri_key=redirect_key,
            created_at=now,
        )
        with session.begin():
            self._repository.create_flow(session, flow)
        return AuthorizationInitResult(
            authorization_url=self._providers[provider].build_authorization_url(
                redirect_uri=redirect_uri,
                state=state,
                nonce=nonce,
                code_challenge=code_challenge,
            ),
            state=state,
            nonce=nonce,
            expires_at=flow.expires_at,
        )

    def exchange(
        self,
        session: Session,
        *,
        provider_code: str,
        authorization_code: str,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_verifier: str,
        client_ip: str,
    ) -> str:
        provider = self._require_provider(provider_code)
        # Hash first so an otherwise-valid state is consumed even when an
        # attacker changes the callback URI.  The stored hash came only from a
        # registered init URI, so a mismatch cannot reach the provider.
        redirect_key = self._redirect_key(provider, redirect_uri, require_registered=False)
        now = self._clock()
        self._apply_rate_limits(
            session,
            provider_code=provider,
            client_ip=client_ip,
            redirect_uri=redirect_uri,
            now=now,
        )

        claim_error: AuthProviderContractError | None = None
        claim = None
        with session.begin():
            state_digest = hashlib.sha256(state.encode("utf-8")).hexdigest()
            flow = self._repository.claim_flow(session, state_digest)
            if flow is None or flow.redirect_uri_key != redirect_key:
                claim_error = AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_STATE)
            else:
                try:
                    claim = claim_authorization_flow(
                        flow,
                        returned_state=state,
                        returned_nonce=nonce,
                        code_verifier=code_verifier,
                        claimed_at=now,
                    )
                except AuthProviderContractError as exc:
                    claim_error = exc
        if claim_error is not None:
            raise claim_error
        if claim is None:  # defensive; flow is consumed on every exchange attempt.
            raise AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_STATE)

        try:
            evidence = self._providers[provider].exchange_authorization_code(
                authorization_code=authorization_code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        except ProviderExchangeError as exc:
            from backend.app.domain.rules.auth_provider import classify_provider_failure

            failure = classify_provider_failure(exc.kind)
            raise AuthProviderContractError(failure.public_error_code) from None
        validate_provider_nonce(
            claim, token_nonce_claim=(getattr(evidence, "token_nonce_claim", None))
        )
        subject = validate_provider_token(evidence)

        with session.begin():
            user = self._repository.resolve_social_identity(
                session,
                provider_code=provider,
                provider_subject=subject.provider_subject,
                now=now,
            )
        if user.status_code.value != "ACTIVE":
            raise AuthProviderContractError(AuthFailureCode.IDENTITY_TRANSACTION_FAILED)
        try:
            return self._firebase_tokens.create_custom_token(str(user.user_id))
        except FirebaseCustomTokenUnavailableError:
            raise AuthProviderContractError(AuthFailureCode.PROVIDER_UNAVAILABLE) from None


__all__ = ["AuthorizationInitResult", "SocialOAuthService"]
