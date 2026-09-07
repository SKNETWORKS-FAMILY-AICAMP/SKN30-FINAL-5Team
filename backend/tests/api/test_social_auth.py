import base64
import hashlib
from contextlib import nullcontext
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.api.dependencies import (
    get_db_session,
    get_google_oauth_client,
    get_social_oauth_repository,
)
from backend.app.core.config import Settings
from backend.app.domain.rules.auth_provider import (
    AuthorizationFlow,
    AuthProviderCode,
    ProviderTokenEvidence,
    RateLimitDimensionCode,
)
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.ports import IdentityUserRecord

GOOGLE_REDIRECT_URI = "https://app.example.test/oauth/google/callback"
VERIFIER = "a" * 43
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
)


class FakeSession:
    def begin(self) -> nullcontext[None]:
        return nullcontext()


class FakeRepository:
    def __init__(self) -> None:
        self.flows: dict[str, AuthorizationFlow] = {}

    def consume_rate_limit(
        self,
        session: FakeSession,
        *,
        provider_code: AuthProviderCode,
        dimension_code: RateLimitDimensionCode,
        key_digest_hex: str,
        window_started_at: datetime,
        window_seconds: int,
        attempted_at: datetime,
    ) -> int:
        del (
            session,
            provider_code,
            dimension_code,
            key_digest_hex,
            window_started_at,
            window_seconds,
            attempted_at,
        )
        return 1

    def create_flow(self, session: FakeSession, flow: AuthorizationFlow) -> None:
        del session
        self.flows[flow.state_digest.hex()] = flow

    def claim_flow(self, session: FakeSession, state_digest_hex: str) -> AuthorizationFlow | None:
        del session
        return self.flows.pop(state_digest_hex, None)

    def resolve_social_identity(
        self,
        session: FakeSession,
        *,
        provider_code: AuthProviderCode,
        provider_subject: str,
        now: datetime,
    ) -> IdentityUserRecord:
        del session, provider_code, provider_subject
        return IdentityUserRecord(uuid4(), UserStatusCode.ACTIVE, now)


class FakeGoogle:
    def __init__(self) -> None:
        self.nonce: str | None = None

    def build_authorization_url(self, **kwargs: str) -> str:
        self.nonce = kwargs["nonce"]
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={kwargs['state']}"

    def exchange_authorization_code(self, **_: str) -> ProviderTokenEvidence:
        return ProviderTokenEvidence(
            provider_code=AuthProviderCode.GOOGLE,
            issuer_matches=True,
            audience_matches=True,
            signature_valid=True,
            token_not_expired=True,
            provider_subject="opaque-google-subject",
            nonce_matches=None,
            token_nonce_claim=self.nonce,
        )


class FakeFirebaseTokens:
    def create_custom_token(self, firebase_subject: str) -> str:
        del firebase_subject
        return "test-firebase-custom-token"


def _app() -> TestClient:
    application = create_app(
        settings=Settings(
            app_env="test",
            database_url="postgresql+psycopg://test_user:test_password@localhost:5432/test_db",
            kakao_redirect_uris=("https://app.example.test/oauth/kakao/callback",),
            google_oauth_redirect_uris=(GOOGLE_REDIRECT_URI,),
            social_oauth_rate_limit_hmac_key=SecretStr("test-only-hmac-key"),
        ),
        readiness_probe=lambda: None,
        firebase_custom_token_issuer=FakeFirebaseTokens(),
    )
    repository = FakeRepository()
    google = FakeGoogle()

    def session_override():
        yield FakeSession()

    application.dependency_overrides[get_db_session] = session_override
    application.dependency_overrides[get_social_oauth_repository] = lambda: repository
    application.dependency_overrides[get_google_oauth_client] = lambda: google
    return TestClient(application)


def test_google_social_oauth_api_returns_only_the_firebase_custom_token() -> None:
    with _app() as client:
        initialized = client.post(
            "/api/v1/auth/social/GOOGLE/authorize-init",
            json={
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "code_challenge": CHALLENGE,
                "code_challenge_method": "S256",
            },
        )
        assert initialized.status_code == 200
        body = initialized.json()
        assert body["provider_code"] == "GOOGLE"
        assert "nonce" in body

        exchanged = client.post(
            "/api/v1/auth/social/GOOGLE/exchange",
            json={
                "authorization_code": "one-time-code",
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "state": body["state"],
                "nonce": body["nonce"],
                "code_verifier": VERIFIER,
            },
        )

    assert exchanged.status_code == 200
    assert exchanged.json() == {
        "token_type": "FIREBASE_CUSTOM_TOKEN",
        "firebase_custom_token": "test-firebase-custom-token",
    }
