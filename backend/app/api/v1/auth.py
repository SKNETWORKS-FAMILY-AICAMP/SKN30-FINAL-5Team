from http import HTTPStatus
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_db_session,
    get_firebase_custom_token_issuer,
    get_google_oauth_client,
    get_kakao_oauth_client,
    get_social_oauth_repository,
)
from backend.app.core.errors import AppError
from backend.app.domain.rules.auth_provider import AuthFailureCode, AuthProviderContractError
from backend.app.modules.social_auth.ports import (
    FirebaseCustomTokenIssuer,
    GoogleOAuthPort,
    KakaoOAuthPort,
    SocialOAuthRepositoryPort,
)
from backend.app.modules.social_auth.schemas import (
    SocialAuthorizationInitRequest,
    SocialAuthorizationInitResponse,
    SocialTokenExchangeRequest,
    SocialTokenExchangeResponse,
)
from backend.app.modules.social_auth.service import SocialOAuthService

router = APIRouter(prefix="/auth/social", tags=["auth"])


def _client_ip(request: Request) -> str:
    # Forwarded headers are intentionally ignored until trusted-proxy deployment
    # configuration exists. A user-controlled header must never choose the key.
    return request.client.host if request.client is not None else "unavailable"


def _service(
    request: Request,
    repository: SocialOAuthRepositoryPort,
    kakao: KakaoOAuthPort,
    google: GoogleOAuthPort,
    firebase_tokens: FirebaseCustomTokenIssuer,
) -> SocialOAuthService:
    settings = request.app.state.settings
    key = settings.social_oauth_rate_limit_hmac_key
    if key is None:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code=AuthFailureCode.PROVIDER_UNAVAILABLE,
            message="소셜 로그인을 일시적으로 사용할 수 없습니다.",
        )
    try:
        return SocialOAuthService(
            repository,
            kakao,
            firebase_tokens,
            redirect_uris=frozenset(settings.kakao_redirect_uris),
            rate_limit_hmac_key=key.get_secret_value().encode("utf-8"),
            google=google,
            google_redirect_uris=frozenset(settings.google_oauth_redirect_uris),
        )
    except ValueError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code=AuthFailureCode.PROVIDER_UNAVAILABLE,
            message="소셜 로그인을 일시적으로 사용할 수 없습니다.",
        ) from None


def _error(exc: AuthProviderContractError) -> AppError:
    status = {
        AuthFailureCode.OAUTH_STATE_EXPIRED: HTTPStatus.UNPROCESSABLE_ENTITY,
        AuthFailureCode.INVALID_OAUTH_STATE: HTTPStatus.UNPROCESSABLE_ENTITY,
        AuthFailureCode.INVALID_OAUTH_NONCE: HTTPStatus.UNPROCESSABLE_ENTITY,
        AuthFailureCode.INVALID_PKCE_VERIFIER: HTTPStatus.UNPROCESSABLE_ENTITY,
        AuthFailureCode.AUTHORIZATION_CODE_REUSED: HTTPStatus.CONFLICT,
        AuthFailureCode.IDENTITY_ALREADY_LINKED: HTTPStatus.CONFLICT,
        AuthFailureCode.RATE_LIMITED: HTTPStatus.TOO_MANY_REQUESTS,
        AuthFailureCode.PROVIDER_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    }.get(exc.code, HTTPStatus.UNPROCESSABLE_ENTITY)
    return AppError(
        status_code=status,
        code=exc.code,
        message="소셜 로그인 요청을 처리할 수 없습니다.",
    )


@router.post("/{provider_code}/authorize-init", response_model=SocialAuthorizationInitResponse)
def authorize_init(
    provider_code: str,
    payload: SocialAuthorizationInitRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[SocialOAuthRepositoryPort, Depends(get_social_oauth_repository)],
    kakao: Annotated[KakaoOAuthPort, Depends(get_kakao_oauth_client)],
    google: Annotated[GoogleOAuthPort, Depends(get_google_oauth_client)],
    firebase_tokens: Annotated[
        FirebaseCustomTokenIssuer,
        Depends(get_firebase_custom_token_issuer),
    ],
) -> SocialAuthorizationInitResponse:
    try:
        result = _service(request, repository, kakao, google, firebase_tokens).authorize_init(
            session,
            provider_code=provider_code,
            redirect_uri=payload.redirect_uri,
            code_challenge=payload.code_challenge,
            client_ip=_client_ip(request),
        )
    except AuthProviderContractError as exc:
        raise _error(exc) from None
    response_provider_code: Literal["GOOGLE", "KAKAO"] = (
        "GOOGLE" if provider_code == "GOOGLE" else "KAKAO"
    )
    return SocialAuthorizationInitResponse(
        provider_code=response_provider_code,
        authorization_url=result.authorization_url,
        state=result.state,
        nonce=result.nonce,
        expires_at=result.expires_at,
    )


@router.post("/{provider_code}/exchange", response_model=SocialTokenExchangeResponse)
def exchange(
    provider_code: str,
    payload: SocialTokenExchangeRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[SocialOAuthRepositoryPort, Depends(get_social_oauth_repository)],
    kakao: Annotated[KakaoOAuthPort, Depends(get_kakao_oauth_client)],
    google: Annotated[GoogleOAuthPort, Depends(get_google_oauth_client)],
    firebase_tokens: Annotated[
        FirebaseCustomTokenIssuer,
        Depends(get_firebase_custom_token_issuer),
    ],
) -> SocialTokenExchangeResponse:
    try:
        token = _service(request, repository, kakao, google, firebase_tokens).exchange(
            session,
            provider_code=provider_code,
            authorization_code=payload.authorization_code,
            redirect_uri=payload.redirect_uri,
            state=payload.state,
            nonce=payload.nonce,
            code_verifier=payload.code_verifier,
            client_ip=_client_ip(request),
        )
    except AuthProviderContractError as exc:
        raise _error(exc) from None
    return SocialTokenExchangeResponse(
        token_type="FIREBASE_CUSTOM_TOKEN",
        firebase_custom_token=token,
    )


__all__ = ["router"]
