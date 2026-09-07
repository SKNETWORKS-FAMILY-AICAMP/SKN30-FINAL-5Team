"""Kakao OAuth/OIDC adapter; secrets and raw tokens stay inside this module."""

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

_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
_JWKS_URL = "https://kauth.kakao.com/.well-known/jwks.json"
_ISSUER = "https://kauth.kakao.com"


class UnavailableKakaoOAuthClient:
    def build_authorization_url(self, **_: str) -> str:
        raise ProviderExchangeError(ProviderFailureKindCode.INVALID_CLIENT_CONFIGURATION)

    def exchange_authorization_code(self, **_: str) -> ProviderTokenEvidence:
        raise ProviderExchangeError(ProviderFailureKindCode.INVALID_CLIENT_CONFIGURATION)


class KakaoOAuthClient:
    def __init__(
        self,
        *,
        rest_api_key: str,
        client_secret: str | None,
        timeout_seconds: float,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not rest_api_key.strip():
            raise ValueError("Kakao REST API key must not be empty")
        self._rest_api_key = rest_api_key.strip()
        self._client_secret = client_secret.strip() if client_secret else None
        self._http = http_client or httpx.Client(timeout=timeout_seconds)

    def build_authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        return f"{_AUTHORIZE_URL}?{urlencode({
            'response_type': 'code', 'client_id': self._rest_api_key,
            'redirect_uri': redirect_uri, 'state': state, 'nonce': nonce,
            'code_challenge': code_challenge, 'code_challenge_method': 'S256', 'scope': 'openid',
        })}"

    def exchange_authorization_code(
        self,
        *,
        authorization_code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> ProviderTokenEvidence:
        form: dict[str, str] = {
            "grant_type": "authorization_code",
            "client_id": self._rest_api_key,
            "redirect_uri": redirect_uri,
            "code": authorization_code,
            "code_verifier": code_verifier,
        }
        if self._client_secret:
            form["client_secret"] = self._client_secret
        try:
            response = self._http.post(_TOKEN_URL, data=form)
        except httpx.TimeoutException as exc:
            raise ProviderExchangeError(ProviderFailureKindCode.TIMEOUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderExchangeError(ProviderFailureKindCode.HTTP_5XX) from exc
        if response.status_code == 400:
            # Kakao's KOE320 is fail-closed without exposing provider details.
            raise ProviderExchangeError(ProviderFailureKindCode.AUTHORIZATION_CODE_INVALID_GRANT)
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
        audience_matches = audience == self._rest_api_key or (
            isinstance(audience, list) and self._rest_api_key in audience
        )
        exp = claims.get("exp")
        token_not_expired = isinstance(exp, (int, float)) and exp > datetime.now(UTC).timestamp()
        subject = claims.get("sub")
        return ProviderTokenEvidence(
            provider_code=AuthProviderCode.KAKAO,
            issuer_matches=claims.get("iss") == _ISSUER,
            audience_matches=audience_matches,
            signature_valid=True,
            token_not_expired=token_not_expired,
            provider_subject=subject if isinstance(subject, str) and subject else None,
            nonce_matches=None,
            token_nonce_claim=claims.get("nonce") if isinstance(claims.get("nonce"), str) else None,
        )


__all__ = ["KakaoOAuthClient", "UnavailableKakaoOAuthClient"]
