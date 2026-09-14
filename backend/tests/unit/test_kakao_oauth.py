from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from backend.app.domain.rules.auth_provider import AuthProviderCode
from backend.app.integrations.oauth.kakao import KakaoOAuthClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class FakeHttpClient:
    def __init__(self, id_token: str, jwks: dict[str, object]) -> None:
        self._id_token = id_token
        self._jwks = jwks
        self.posted_form: dict[str, str] | None = None

    def post(self, _: str, *, data: dict[str, str]) -> FakeResponse:
        self.posted_form = data
        return FakeResponse(200, {"id_token": self._id_token})

    def get(self, _: str) -> FakeResponse:
        return FakeResponse(200, self._jwks)


def test_kakao_adapter_uses_openid_pkce_and_verifies_rs256_claims() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "https://kauth.kakao.com",
            "aud": "rest-api-key",
            "sub": "opaque-kakao-subject",
            "nonce": "nonce-value",
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk["kid"] = "test-key"
    http = FakeHttpClient(token, {"keys": [public_jwk]})
    client = KakaoOAuthClient(
        rest_api_key="rest-api-key",
        client_secret="server-only-secret",
        timeout_seconds=1,
        http_client=http,  # type: ignore[arg-type]
    )

    authorization_url = client.build_authorization_url(
        redirect_uri="https://app.example.test/callback",
        state="state-value",
        nonce="nonce-value",
        code_challenge="A" * 43,
    )
    evidence = client.exchange_authorization_code(
        authorization_code="authorization-code",
        redirect_uri="https://app.example.test/callback",
        code_verifier="a" * 43,
    )

    assert "scope=openid" in authorization_url
    assert "code_challenge_method=S256" in authorization_url
    assert http.posted_form is not None
    assert http.posted_form["client_secret"] == "server-only-secret"
    assert evidence.provider_code is AuthProviderCode.KAKAO
    assert evidence.signature_valid is True
    assert evidence.issuer_matches is True
    assert evidence.audience_matches is True
    assert evidence.token_not_expired is True
    assert evidence.provider_subject == "opaque-kakao-subject"
    assert evidence.token_nonce_claim == "nonce-value"
