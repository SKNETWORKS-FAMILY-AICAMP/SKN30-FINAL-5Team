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
    OnboardingResponse,
    OnboardingUpsertRequest,
)
from backend.app.modules.profiles.service import (
    IdempotencyKeyReusedError,
    InvalidOnboardingCodeError,
    ProfileConfigurationError,
    ProfileService,
    RequiredConsentMissingError,
)

router = APIRouter(prefix="/me", tags=["profile"])


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


def _translate_profile_error(exc: Exception) -> AppError:
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
        raise _translate_profile_error(exc) from None


__all__ = ["router"]
