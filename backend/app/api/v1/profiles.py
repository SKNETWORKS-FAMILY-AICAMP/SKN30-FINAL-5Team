import logging
import re
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_birthdate_cipher,
    get_current_user,
    get_db_session,
    get_profile_repository,
)
from backend.app.core.errors import AppError
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.profiles.age import (
    AgeRequirementNotMetError,
    InvalidBirthdateError,
    InvalidTimezoneError,
)
from backend.app.modules.profiles.ports import BirthdateCipher, ProfileRepositoryPort
from backend.app.modules.profiles.schemas import (
    ConsentResponse,
    ConsentValues,
    MeResponse,
    OnboardingResponse,
    OnboardingUpsertRequest,
    ProfileSettingsUpdateRequest,
    ProfileSettingsUpdateResponse,
)
from backend.app.modules.profiles.service import (
    IdempotencyKeyReusedError,
    InvalidOnboardingCodeError,
    InvalidProfileSettingsError,
    ProfileConfigurationError,
    ProfileNotFoundError,
    ProfileService,
    RequiredConsentMissingError,
    StaleProfileError,
    UserNotFoundError,
)

router = APIRouter(prefix="/me", tags=["profile"])
logger = logging.getLogger("backend.profile")
_PROFILE_VERSION_ETAG = re.compile(r'^"([1-9][0-9]*)"$')
_PROFILE_CONFIGURATION_SETTINGS = (
    ("CONSENT_POLICY_VERSION", "consent_policy_version"),
    ("ONBOARDING_PRIMARY_GOAL_CODES", "onboarding_primary_goal_codes"),
    ("ONBOARDING_EXPERIENCE_LEVEL_CODES", "onboarding_experience_level_codes"),
)


def _service(
    request: Request,
    repository: ProfileRepositoryPort,
    birthdate_cipher: BirthdateCipher | None,
) -> ProfileService:
    settings = request.app.state.settings
    return ProfileService(
        repository,
        birthdate_cipher,
        primary_goal_codes=settings.onboarding_primary_goal_codes,
        experience_level_codes=settings.onboarding_experience_level_codes,
        consent_policy_version=settings.consent_policy_version,
    )


def _missing_profile_configuration_keys(request: Request) -> list[str]:
    settings = request.app.state.settings
    missing_keys: list[str] = []
    for environment_key, setting_name in _PROFILE_CONFIGURATION_SETTINGS:
        value = getattr(settings, setting_name)
        if value is None or (isinstance(value, str) and not value.strip()) or value == ():
            missing_keys.append(environment_key)
    return missing_keys


def _log_profile_configuration_error(request: Request) -> None:
    logger.error(
        "profile_configuration_unavailable",
        extra={
            "event_code": "PROFILE_CONFIGURATION_UNAVAILABLE",
            "request_id": str(getattr(request.state, "request_id", "unavailable")),
            "missing_keys": _missing_profile_configuration_keys(request),
        },
    )


def _translate_profile_error(exc: Exception, *, request: Request | None = None) -> AppError:
    if isinstance(exc, AgeRequirementNotMetError):
        return AppError(
            status_code=HTTPStatus.FORBIDDEN,
            code="AGE_REQUIREMENT_NOT_MET",
            message="만 14세 미만은 이용할 수 없습니다.",
        )
    if isinstance(exc, InvalidBirthdateError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="INVALID_DATE_OF_BIRTH",
            message="생년월일이 올바르지 않습니다.",
        )
    if isinstance(exc, InvalidTimezoneError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="INVALID_TIMEZONE",
            message="시간대가 올바르지 않습니다.",
        )
    if isinstance(exc, InvalidOnboardingCodeError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="INVALID_ONBOARDING_CODE",
            message="온보딩 코드가 허용된 값이 아닙니다.",
        )
    if isinstance(exc, RequiredConsentMissingError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="REQUIRED_CONSENT_MISSING",
            message="필수 동의가 필요합니다.",
        )
    if isinstance(exc, IdempotencyKeyReusedError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="IDEMPOTENCY_KEY_REUSED",
            message="동일한 멱등성 키를 다른 요청에 사용할 수 없습니다.",
        )
    if isinstance(exc, (ProfileConfigurationError, SQLAlchemyError)):
        if isinstance(exc, ProfileConfigurationError) and request is not None:
            _log_profile_configuration_error(request)
        return AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code=(
                "PROFILE_CONFIGURATION_UNAVAILABLE"
                if isinstance(exc, ProfileConfigurationError)
                else "DATABASE_UNAVAILABLE"
            ),
            message="온보딩 기능을 일시적으로 사용할 수 없습니다.",
        )
    return AppError(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="PROFILE_OPERATION_FAILED",
        message="온보딩 요청을 처리하지 못했습니다.",
    )


def _expected_profile_version(if_match: str | None) -> int:
    match = _PROFILE_VERSION_ETAG.fullmatch(if_match or "")
    if match is None:
        raise AppError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="INVALID_REQUEST",
            message='If-Match는 현재 profile_version을 "1" 형식으로 포함해야 합니다.',
        )
    return int(match.group(1))


def _translate_profile_update_error(exc: Exception, *, request: Request) -> AppError:
    if isinstance(exc, ProfileNotFoundError):
        return AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            message="수정할 프로필을 찾을 수 없습니다.",
        )
    if isinstance(exc, StaleProfileError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="STALE_PROFILE",
            message="프로필이 변경되었습니다. 최신 상태로 다시 시도해주세요.",
        )
    if isinstance(exc, InvalidProfileSettingsError):
        return AppError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="INVALID_REQUEST",
            message="프로필 설정 조합이 올바르지 않습니다.",
        )
    if isinstance(exc, IntegrityError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="INVALID_DOMAIN_CODE",
            message="프로필에 허용되지 않은 코드가 포함되어 있습니다.",
        )
    return _translate_profile_error(exc, request=request)


@router.get("", response_model=MeResponse)
def get_me(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[ProfileRepositoryPort, Depends(get_profile_repository)],
    birthdate_cipher: Annotated[BirthdateCipher | None, Depends(get_birthdate_cipher)],
) -> MeResponse:
    try:
        return _service(request, repository, birthdate_cipher).get_me(session, current_user.user_id)
    except UserNotFoundError:
        raise AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            message="사용자를 찾을 수 없습니다.",
        ) from None
    except SQLAlchemyError as exc:
        raise _translate_profile_error(exc, request=request) from None


@router.put("/onboarding", response_model=OnboardingResponse)
def upsert_onboarding(
    payload: OnboardingUpsertRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[ProfileRepositoryPort, Depends(get_profile_repository)],
    birthdate_cipher: Annotated[BirthdateCipher | None, Depends(get_birthdate_cipher)],
) -> OnboardingResponse:
    try:
        return _service(request, repository, birthdate_cipher).upsert_onboarding(
            session, current_user.user_id, payload, idempotency_key
        )
    except (
        AgeRequirementNotMetError,
        InvalidBirthdateError,
        InvalidTimezoneError,
        InvalidOnboardingCodeError,
        RequiredConsentMissingError,
        IdempotencyKeyReusedError,
        ProfileConfigurationError,
        IntegrityError,
        SQLAlchemyError,
    ) as exc:
        raise _translate_profile_error(exc, request=request) from None


@router.get("/consents", response_model=ConsentResponse)
def get_consents(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[ProfileRepositoryPort, Depends(get_profile_repository)],
    birthdate_cipher: Annotated[BirthdateCipher | None, Depends(get_birthdate_cipher)],
) -> ConsentResponse:
    try:
        return _service(request, repository, birthdate_cipher).get_consents(
            session, current_user.user_id
        )
    except SQLAlchemyError as exc:
        raise _translate_profile_error(exc) from None


@router.put("/consents", response_model=ConsentResponse)
def replace_consents(
    payload: ConsentValues,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[ProfileRepositoryPort, Depends(get_profile_repository)],
    birthdate_cipher: Annotated[BirthdateCipher | None, Depends(get_birthdate_cipher)],
) -> ConsentResponse:
    try:
        return _service(request, repository, birthdate_cipher).replace_consents(
            session, current_user.user_id, payload, idempotency_key
        )
    except (
        IdempotencyKeyReusedError,
        ProfileConfigurationError,
        IntegrityError,
        SQLAlchemyError,
    ) as exc:
        raise _translate_profile_error(exc, request=request) from None


@router.patch("/profile", response_model=ProfileSettingsUpdateResponse)
def update_profile_settings(
    payload: ProfileSettingsUpdateRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[ProfileRepositoryPort, Depends(get_profile_repository)],
    birthdate_cipher: Annotated[BirthdateCipher | None, Depends(get_birthdate_cipher)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProfileSettingsUpdateResponse:
    try:
        return _service(request, repository, birthdate_cipher).update_profile_settings(
            session,
            current_user.user_id,
            payload,
            idempotency_key,
            _expected_profile_version(if_match),
        )
    except (
        AgeRequirementNotMetError,
        InvalidBirthdateError,
        InvalidTimezoneError,
        InvalidOnboardingCodeError,
        InvalidProfileSettingsError,
        IdempotencyKeyReusedError,
        ProfileConfigurationError,
        ProfileNotFoundError,
        StaleProfileError,
        IntegrityError,
        SQLAlchemyError,
    ) as exc:
        raise _translate_profile_update_error(exc, request=request) from None


__all__ = ["router"]
