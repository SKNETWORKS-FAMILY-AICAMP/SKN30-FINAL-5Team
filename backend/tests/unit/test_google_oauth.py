from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from backend.app.domain.rules.auth_provider import AuthProviderCode, ProviderFailureKindCode
from backend.app.integrations.oauth.google import GoogleOAuthClient
from backend.app.modules.social_auth.ports import ProviderExchangeError


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class FakeHttpClient:
    def __init__(self, post_response: FakeResponse, jwks: dict[str, object]) -> None:
        self._post_response = post_response
        self._jwks = jwks
        self.posted_form: dict[str, str] | None = None

    def post(self, _: str, *, data: dict[str, str]) -> FakeResponse:
        self.posted_form = data
        return self._post_response

    def get(self, _: str) -> FakeResponse:
        return FakeResponse(200, self._jwks)


def _signed_token(*, claims: dict[str, object]) -> tuple[str, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk["kid"] = "test-key"
    return token, {"keys": [public_jwk]}


def _client(post_response: FakeResponse, jwks: dict[str, object]) -> GoogleOAuthClient:
    return GoogleOAuthClient(
        client_id="google-client-id.apps.exampleusercontent.com",
        client_secret="test-only-non-production-value",
        timeout_seconds=1,
        http_client=FakeHttpClient(post_response, jwks),  # type: ignore[arg-type]
    )


def test_google_adapter_uses_openid_pkce_and_verifies_rs256_claims() -> None:
    now = datetime.now(UTC)
    token, jwks = _signed_token(
        claims={
            "iss": "https://accounts.google.com",
            "aud": "google-client-id.apps.exampleusercontent.com",
            "sub": "opaque-google-subject",
            "nonce": "nonce-value",
            "exp": now + timedelta(minutes=5),
        }
    )
    http = FakeHttpClient(FakeResponse(200, {"id_token": token}), jwks)
    client = GoogleOAuthClient(
        client_id="google-client-id.apps.exampleusercontent.com",
        client_secret="test-only-non-production-value",
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
    assert http.posted_form["code_verifier"] == "a" * 43
    assert evidence.provider_code is AuthProviderCode.GOOGLE
    assert evidence.issuer_matches is True
    assert evidence.audience_matches is True
    assert evidence.token_not_expired is True
    assert evidence.provider_subject == "opaque-google-subject"
    assert evidence.token_nonce_claim == "nonce-value"


@pytest.mark.parametrize(
    ("claim_overrides", "field"),
    [
        ({"iss": "https://issuer.example.test"}, "issuer_matches"),
        ({"aud": "other-client.apps.exampleusercontent.com"}, "audience_matches"),
        (
            {
                "aud": [
                    "google-client-id.apps.exampleusercontent.com",
                    "another-client.apps.exampleusercontent.com",
                ]
            },
            "audience_matches",
        ),
        ({"exp": datetime.now(UTC) - timedelta(minutes=1)}, "token_not_expired"),
        ({"sub": ""}, "provider_subject"),
    ],
)
def test_google_adapter_marks_invalid_claims_without_retaining_them(
    claim_overrides: dict[str, object], field: str
) -> None:
    claims: dict[str, object] = {
        "iss": "https://accounts.google.com",
        "aud": "google-client-id.apps.exampleusercontent.com",
        "sub": "opaque-google-subject",
        "nonce": "nonce-value",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    claims.update(claim_overrides)
    token, jwks = _signed_token(claims=claims)

    evidence = _client(FakeResponse(200, {"id_token": token}), jwks).exchange_authorization_code(
        authorization_code="authorization-code",
        redirect_uri="https://app.example.test/callback",
        code_verifier="a" * 43,
    )

    assert getattr(evidence, field) in {False, None}


def test_google_adapter_maps_invalid_grant_to_reused_authorization_code() -> None:
    with pytest.raises(ProviderExchangeError) as captured:
        _client(
            FakeResponse(400, {"error": "invalid_grant"}), {"keys": []}
        ).exchange_authorization_code(
            authorization_code="authorization-code",
            redirect_uri="https://app.example.test/callback",
            code_verifier="a" * 43,
        )

    assert captured.value.kind is ProviderFailureKindCode.AUTHORIZATION_CODE_INVALID_GRANT
