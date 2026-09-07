import base64
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.domain.rules.auth_provider import (
    AuthFailureCode,
    AuthorizationFlow,
    AuthProviderCode,
    AuthProviderContractError,
    ProviderFailureKindCode,
    ProviderTokenEvidence,
    RateLimitDimensionCode,
)
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.ports import IdentityUserRecord
from backend.app.modules.social_auth.ports import ProviderExchangeError
from backend.app.modules.social_auth.service import SocialOAuthService

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
REDIRECT_URI = "https://app.example.test/oauth/kakao/callback"
GOOGLE_REDIRECT_URI = "https://app.example.test/oauth/google/callback"
VERIFIER = "a" * 43
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
)


class FakeRepository:
    def __init__(self) -> None:
        self.flows: dict[str, AuthorizationFlow] = {}
        self.counts: dict[tuple[RateLimitDimensionCode, str, datetime], int] = {}
        self.resolved_subjects: list[str] = []

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
    ) -> int:
        del session, provider_code, window_seconds, attempted_at
        key = (dimension_code, key_digest_hex, window_started_at)
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def create_flow(self, session: Session, flow: AuthorizationFlow) -> None:
        del session
        self.flows[flow.state_digest.hex()] = flow

    def claim_flow(self, session: Session, state_digest_hex: str) -> AuthorizationFlow | None:
        del session
        return self.flows.pop(state_digest_hex, None)

    def resolve_social_identity(
        self,
        session: Session,
        *,
        provider_code: AuthProviderCode,
        provider_subject: str,
        now: datetime,
    ) -> IdentityUserRecord:
        del session, provider_code
        self.resolved_subjects.append(provider_subject)
        return IdentityUserRecord(uuid4(), UserStatusCode.ACTIVE, now)


class FakeKakao:
    def __init__(self, evidence: ProviderTokenEvidence) -> None:
        self.evidence = evidence
        self.exchange_calls = 0

    def build_authorization_url(self, **kwargs: str) -> str:
        return f"https://kauth.kakao.com/oauth/authorize?state={kwargs['state']}"

    def exchange_authorization_code(self, **_: str) -> ProviderTokenEvidence:
        self.exchange_calls += 1
        return self.evidence


class FakeGoogle(FakeKakao):
    def build_authorization_url(self, **kwargs: str) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={kwargs['state']}"


class FailingGoogle(FakeGoogle):
    def exchange_authorization_code(self, **_: str) -> ProviderTokenEvidence:
        raise ProviderExchangeError(ProviderFailureKindCode.AUTHORIZATION_CODE_INVALID_GRANT)


class FakeFirebaseTokens:
    def __init__(self) -> None:
        self.subjects: list[str] = []

    def create_custom_token(self, firebase_subject: str) -> str:
        self.subjects.append(firebase_subject)
        return "firebase-custom-token"


def _evidence(*, nonce: str = "nonce") -> ProviderTokenEvidence:
    return ProviderTokenEvidence(
        provider_code=AuthProviderCode.KAKAO,
        issuer_matches=True,
        audience_matches=True,
        signature_valid=True,
        token_not_expired=True,
        provider_subject="opaque-kakao-subject",
        nonce_matches=None,
        token_nonce_claim=nonce,
    )


def _service(
    repository: FakeRepository,
    kakao: FakeKakao,
    *,
    google: FakeGoogle | None = None,
    now: datetime = NOW,
) -> SocialOAuthService:
    return SocialOAuthService(
        repository,
        kakao,
        FakeFirebaseTokens(),
        redirect_uris=frozenset({REDIRECT_URI}),
        rate_limit_hmac_key=b"test-rate-limit-key",
        google=google,
        google_redirect_uris=frozenset({GOOGLE_REDIRECT_URI})
        if google is not None
        else frozenset(),
        clock=lambda: now,
    )


def _session() -> Session:
    return Session(create_engine("sqlite://"))


def test_exchange_consumes_flow_before_provider_call_and_returns_custom_token() -> None:
    repository = FakeRepository()
    kakao = FakeKakao(_evidence())
    service = _service(repository, kakao)
    session = _session()
    started = service.authorize_init(
        session,
        provider_code="KAKAO",
        redirect_uri=REDIRECT_URI,
        code_challenge=CHALLENGE,
        client_ip="192.0.2.1",
    )
    kakao.evidence = _evidence(nonce=started.nonce)

    token = service.exchange(
        session,
        provider_code="KAKAO",
        authorization_code="one-time-code",
        redirect_uri=REDIRECT_URI,
        state=started.state,
        nonce=started.nonce,
        code_verifier=VERIFIER,
        client_ip="192.0.2.1",
    )

    assert token == "firebase-custom-token"
    assert kakao.exchange_calls == 1
    assert repository.flows == {}
    assert repository.resolved_subjects == ["opaque-kakao-subject"]


def test_reused_state_is_rejected_without_provider_call() -> None:
    repository = FakeRepository()
    kakao = FakeKakao(_evidence())
    service = _service(repository, kakao)
    session = _session()
    started = service.authorize_init(
        session,
        provider_code="KAKAO",
        redirect_uri=REDIRECT_URI,
        code_challenge=CHALLENGE,
        client_ip="192.0.2.1",
    )
    kakao.evidence = _evidence(nonce=started.nonce)
    service.exchange(
        session,
        provider_code="KAKAO",
        authorization_code="code",
        redirect_uri=REDIRECT_URI,
        state=started.state,
        nonce=started.nonce,
        code_verifier=VERIFIER,
        client_ip="192.0.2.1",
    )

    with pytest.raises(AuthProviderContractError) as captured:
        service.exchange(
            session,
            provider_code="KAKAO",
            authorization_code="code",
            redirect_uri=REDIRECT_URI,
            state=started.state,
            nonce=started.nonce,
            code_verifier=VERIFIER,
            client_ip="192.0.2.1",
        )
    assert captured.value.code is AuthFailureCode.INVALID_OAUTH_STATE
    assert kakao.exchange_calls == 1


def test_nonce_mismatch_consumes_flow_without_creating_identity() -> None:
    repository = FakeRepository()
    kakao = FakeKakao(_evidence(nonce="different-nonce"))
    service = _service(repository, kakao)
    session = _session()
    started = service.authorize_init(
        session,
        provider_code="KAKAO",
        redirect_uri=REDIRECT_URI,
        code_challenge=CHALLENGE,
        client_ip="192.0.2.1",
    )

    with pytest.raises(AuthProviderContractError) as captured:
        service.exchange(
            session,
            provider_code="KAKAO",
            authorization_code="code",
            redirect_uri=REDIRECT_URI,
            state=started.state,
            nonce=started.nonce,
            code_verifier=VERIFIER,
            client_ip="192.0.2.1",
        )
    assert captured.value.code is AuthFailureCode.INVALID_OAUTH_NONCE
    assert repository.flows == {}
    assert repository.resolved_subjects == []


def test_changed_redirect_uri_consumes_flow_without_provider_call() -> None:
    repository = FakeRepository()
    kakao = FakeKakao(_evidence())
    service = _service(repository, kakao)
    session = _session()
    started = service.authorize_init(
        session,
        provider_code="KAKAO",
        redirect_uri=REDIRECT_URI,
        code_challenge=CHALLENGE,
        client_ip="192.0.2.1",
    )
    with pytest.raises(AuthProviderContractError) as captured:
        service.exchange(
            session,
            provider_code="KAKAO",
            authorization_code="code",
            redirect_uri="https://attacker.example.test/callback",
            state=started.state,
            nonce=started.nonce,
            code_verifier=VERIFIER,
            client_ip="192.0.2.1",
        )
    assert captured.value.code is AuthFailureCode.INVALID_OAUTH_STATE
    assert repository.flows == {}
    assert kakao.exchange_calls == 0


def test_rate_limit_blocks_the_eleventh_request_without_provider_call() -> None:
    repository = FakeRepository()
    kakao = FakeKakao(_evidence())
    service = _service(repository, kakao)
    session = _session()
    for _ in range(10):
        service.authorize_init(
            session,
            provider_code="KAKAO",
            redirect_uri=REDIRECT_URI,
            code_challenge=CHALLENGE,
            client_ip="192.0.2.1",
        )

    with pytest.raises(AuthProviderContractError) as captured:
        service.authorize_init(
            session,
            provider_code="KAKAO",
            redirect_uri=REDIRECT_URI,
            code_challenge=CHALLENGE,
            client_ip="192.0.2.1",
        )
    assert captured.value.code is AuthFailureCode.RATE_LIMITED


def test_expired_flow_is_deleted_and_rejected() -> None:
    repository = FakeRepository()
    kakao = FakeKakao(_evidence())
    earlier = NOW - timedelta(minutes=10)
    service = _service(repository, kakao, now=earlier)
    session = _session()
    started = service.authorize_init(
        session,
        provider_code="KAKAO",
        redirect_uri=REDIRECT_URI,
        code_challenge=CHALLENGE,
        client_ip="192.0.2.1",
    )
    expired_service = _service(repository, kakao, now=NOW)
    with pytest.raises(AuthProviderContractError) as captured:
        expired_service.exchange(
            session,
            provider_code="KAKAO",
            authorization_code="code",
            redirect_uri=REDIRECT_URI,
            state=started.state,
            nonce=started.nonce,
            code_verifier=VERIFIER,
            client_ip="192.0.2.1",
        )
    assert captured.value.code is AuthFailureCode.OAUTH_STATE_EXPIRED
    assert repository.flows == {}


def test_google_exchange_uses_the_same_single_use_state_nonce_and_pkce_guards() -> None:
    repository = FakeRepository()
    google = FakeGoogle(_evidence())
    service = _service(repository, FakeKakao(_evidence()), google=google)
    session = _session()
    started = service.authorize_init(
        session,
        provider_code="GOOGLE",
        redirect_uri=GOOGLE_REDIRECT_URI,
        code_challenge=CHALLENGE,
        client_ip="192.0.2.1",
    )
    google.evidence = ProviderTokenEvidence(
        provider_code=AuthProviderCode.GOOGLE,
        issuer_matches=True,
        audience_matches=True,
        signature_valid=True,
        token_not_expired=True,
        provider_subject="opaque-google-subject",
        nonce_matches=None,
        token_nonce_claim=started.nonce,
    )

    token = service.exchange(
        session,
        provider_code="GOOGLE",
        authorization_code="one-time-code",
        redirect_uri=GOOGLE_REDIRECT_URI,
        state=started.state,
        nonce=started.nonce,
        code_verifier=VERIFIER,
        client_ip="192.0.2.1",
    )

    assert token == "firebase-custom-token"
    assert google.exchange_calls == 1
    assert repository.flows == {}
    assert repository.resolved_subjects == ["opaque-google-subject"]


def test_google_invalid_grant_consumes_the_flow_and_fails_closed() -> None:
    repository = FakeRepository()
    google = FailingGoogle(_evidence())
    service = _service(repository, FakeKakao(_evidence()), google=google)
    session = _session()
    started = service.authorize_init(
        session,
        provider_code="GOOGLE",
        redirect_uri=GOOGLE_REDIRECT_URI,
        code_challenge=CHALLENGE,
        client_ip="192.0.2.1",
    )

    with pytest.raises(AuthProviderContractError) as captured:
        service.exchange(
            session,
            provider_code="GOOGLE",
            authorization_code="one-time-code",
            redirect_uri=GOOGLE_REDIRECT_URI,
            state=started.state,
            nonce=started.nonce,
            code_verifier=VERIFIER,
            client_ip="192.0.2.1",
        )

    assert captured.value.code is AuthFailureCode.AUTHORIZATION_CODE_REUSED
    assert repository.flows == {}
    assert repository.resolved_subjects == []


def test_google_rate_limit_blocks_the_eleventh_authorize_init() -> None:
    repository = FakeRepository()
    service = _service(repository, FakeKakao(_evidence()), google=FakeGoogle(_evidence()))
    session = _session()
    for _ in range(10):
        service.authorize_init(
            session,
            provider_code="GOOGLE",
            redirect_uri=GOOGLE_REDIRECT_URI,
            code_challenge=CHALLENGE,
            client_ip="192.0.2.1",
        )

    with pytest.raises(AuthProviderContractError) as captured:
        service.authorize_init(
            session,
            provider_code="GOOGLE",
            redirect_uri=GOOGLE_REDIRECT_URI,
            code_challenge=CHALLENGE,
            client_ip="192.0.2.1",
        )

    assert captured.value.code is AuthFailureCode.RATE_LIMITED
