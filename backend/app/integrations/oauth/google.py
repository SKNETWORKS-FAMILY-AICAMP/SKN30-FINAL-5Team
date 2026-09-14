"""Google OAuth/OIDC adapter; secrets and raw tokens stay inside this module."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt.algorithms import RSAAlgorithm

from backend.app.domain.rules.auth_provider import (
    AuthProviderCode,
    ProviderFailureKindCode,
    ProviderTokenEvidence,
)
from backend.app.modules.social_auth.ports import ProviderExchangeError

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})


class UnavailableGoogleOAuthClient:
    def build_authorization_url(self, **_: str) -> str:
        raise ProviderExchangeError(ProviderFailureKindCode.INVALID_CLIENT_CONFIGURATION)

    def exchange_authorization_code(self, **_: str) -> ProviderTokenEvidence:
        raise ProviderExchangeError(ProviderFailureKindCode.INVALID_CLIENT_CONFIGURATION)


class GoogleOAuthClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        timeout_seconds: float,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not client_id.strip() or not client_secret.strip():
            raise ValueError("Google OAuth client credentials must not be empty")
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._http = http_client or httpx.Client(timeout=timeout_seconds)

    def build_authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        return f"{_AUTHORIZE_URL}?{
            urlencode(
                {
                    'response_type': 'code',
                    'client_id': self._client_id,
                    'redirect_uri': redirect_uri,
                    'state': state,
                    'nonce': nonce,
                    'code_challenge': code_challenge,
                    'code_challenge_method': 'S256',
                    'scope': 'openid',
                }
            )
        }"

    def exchange_authorization_code(
        self,
        *,
        authorization_code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> ProviderTokenEvidence:
        form = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": redirect_uri,
            "code": authorization_code,
            "code_verifier": code_verifier,
        }
        try:
            response = self._http.post(_TOKEN_URL, data=form)
        except httpx.TimeoutException as exc:
            raise ProviderExchangeError(ProviderFailureKindCode.TIMEOUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderExchangeError(ProviderFailureKindCode.HTTP_5XX) from exc
        if response.status_code == 400:
            try:
                is_invalid_grant = response.json().get("error") == "invalid_grant"
            except (ValueError, AttributeError):
                is_invalid_grant = False
            kind = (
                ProviderFailureKindCode.AUTHORIZATION_CODE_INVALID_GRANT
                if is_invalid_grant
                else ProviderFailureKindCode.INVALID_TOKEN
            )
            raise ProviderExchangeError(kind)
        if response.status_code == 429:
            raise ProviderExchangeError(ProviderFailureKindCode.RATE_LIMITED)
        if response.status_code >= 500:
            raise ProviderExchangeError(ProviderFailureKindCode.HTTP_5XX)
        if response.status_code >= 400:
            raise ProviderExchangeError(ProviderFailureKindCode.INVALID_TOKEN)
        try:
            id_token = response.json().get("id_token")
        except (ValueError, AttributeError) as exc:
            raise ProviderExchangeError(ProviderFailureKindCode.INVALID_TOKEN) from exc
        if not isinstance(id_token, str) or not id_token:
            raise ProviderExchangeError(ProviderFailureKindCode.INVALID_TOKEN)
        return self._verify_id_token(id_token)

    def _verify_id_token(self, id_token: str) -> ProviderTokenEvidence:
        try:
            header = jwt.get_unverified_header(id_token)
            kid = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(kid, str):
                raise ValueError
            jwks_response = self._http.get(_JWKS_URL)
            if jwks_response.status_code >= 400:
                raise ProviderExchangeError(ProviderFailureKindCode.HTTP_5XX)
            jwks = jwks_response.json().get("keys", [])
            jwk = next((item for item in jwks if item.get("kid") == kid), None)
            if not isinstance(jwk, dict):
                raise ValueError
            public_key = cast(RSAPublicKey, RSAAlgorithm.from_jwk(json.dumps(jwk)))
            claims: dict[str, Any] = jwt.decode(
                id_token,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_iss": False, "verify_exp": False},
            )
        except ProviderExchangeError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderExchangeError(ProviderFailureKindCode.TIMEOUT) from exc
        except (httpx.HTTPError, jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise ProviderExchangeError(ProviderFailureKindCode.INVALID_TOKEN) from exc
        audience = claims.get("aud")
        audience_matches = audience == self._client_id or (
            isinstance(audience, list)
            and self._client_id in audience
            and claims.get("azp") == self._client_id
        )
        exp = claims.get("exp")
        token_not_expired = isinstance(exp, (int, float)) and exp > datetime.now(UTC).timestamp()
        subject = claims.get("sub")
        return ProviderTokenEvidence(
            provider_code=AuthProviderCode.GOOGLE,
            issuer_matches=claims.get("iss") in _ISSUERS,
            audience_matches=audience_matches,
            signature_valid=True,
            token_not_expired=token_not_expired,
            provider_subject=subject if isinstance(subject, str) and subject else None,
            nonce_matches=None,
            token_nonce_claim=claims.get("nonce") if isinstance(claims.get("nonce"), str) else None,
        )


__all__ = ["GoogleOAuthClient", "UnavailableGoogleOAuthClient"]
