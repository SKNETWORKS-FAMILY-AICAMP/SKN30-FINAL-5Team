import logging
import re
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Request, UploadFile
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_birthdate_cipher,
    get_current_user,
    get_db_session,
    get_profile_repository,
    get_routine_repository,
)
from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.profiles.age import (
    AgeRequirementNotMetError,
    InvalidBirthdateError,
    InvalidTimezoneError,
)
from backend.app.modules.profiles.images import (
    MAX_PROFILE_IMAGE_BYTES,
    InvalidProfileImageError,
    ProfileImageService,
    ProfileImageStorageUnavailableError,
)
from backend.app.modules.profiles.onboarding_completion import OnboardingCompletionService
from backend.app.modules.profiles.ports import (
    BirthdateCipher,
    ProfileRepositoryPort,
    StaleRoutinePort,
)
from backend.app.modules.profiles.schemas import (
    ConsentResponse,
    ConsentValues,
    MeResponse,
    OnboardingResponse,
    OnboardingUpsertRequest,
    ProfileImageMutationResponse,
    ProfileSettingsUpdateRequest,
    ProfileSettingsUpdateResponse,
)
from backend.app.modules.profiles.service import (
    IdempotencyKeyReusedError,
    InvalidOnboardingCodeError,
    InvalidProfileSettingsError,
    MedicalExerciseRestrictionError,
    ProfileConfigurationError,
    ProfileNotFoundError,
    ProfileService,
    RequiredConsentMissingError,
    StaleProfileError,
    UserNotFoundError,
)
from backend.app.modules.routines.ports import RoutineRepositoryPort
from backend.app.modules.routines.service import (
    ApprovedCatalogUnavailableError,
    RoutineContentUnavailableError,
    RoutineDurationUnavailableError,
    RoutineService,
)

router = APIRouter(prefix="/me", tags=["profile"])
logger = logging.getLogger("backend.profile")
_PROFILE_VERSION_ETAG = re.compile(r'^"([1-9][0-9]*)"$')
_PROFILE_CONFIGURATION_SETTINGS = (
    ("CONSENT_POLICY_VERSION", "consent_policy_version"),
    ("ONBOARDING_PRIMARY_GOAL_CODES", "onboarding_primary_goal_codes"),
    ("ONBOARDING_EXPERIENCE_LEVEL_CODES", "onboarding_experience_level_codes"),
)
_KMS_BIRTHDATE_ENVIRONMENTS = frozenset({"staging", "production"})


def _service(
    request: Request,
    repository: ProfileRepositoryPort,
    birthdate_cipher: BirthdateCipher | None,
    stale_routines: StaleRoutinePort | None = None,
) -> ProfileService:
    settings = request.app.state.settings
    return ProfileService(
        repository,
        birthdate_cipher,
        primary_goal_codes=settings.onboarding_primary_goal_codes,
        experience_level_codes=settings.onboarding_experience_level_codes,
        consent_policy_version=settings.consent_policy_version,
        stale_routines=stale_routines,
        profile_image_url_provider=getattr(request.app.state, "profile_image_storage", None),
    )


def _missing_birthdate_configuration_key(settings: Settings) -> str:
    # 판단 기준은 설정값이 아니라 cipher 조립 결과다. cipher가 있으면 어떤
    # 경로로 주입됐든 생년월일 설정은 부족하지 않다. cipher가 없을 때에만,
    # 그 환경에서 실제로 채워야 하는 키를 지목한다. 배포 환경은 KMS 키를,
    # 로컬·테스트는 base64 키를 쓴다.
    if settings.app_env in _KMS_BIRTHDATE_ENVIRONMENTS:
        return "BIRTHDATE_KMS_KEY_ID"
    return "BIRTHDATE_ENCRYPTION_KEY_BASE64"


def _missing_profile_configuration_keys(request: Request) -> list[str]:
    settings = request.app.state.settings
    missing_keys: list[str] = []
    for environment_key, setting_name in _PROFILE_CONFIGURATION_SETTINGS:
        value = getattr(settings, setting_name)
        if value is None or (isinstance(value, str) and not value.strip()) or value == ():
            missing_keys.append(environment_key)
    if getattr(request.app.state, "birthdate_cipher", None) is None:
        missing_keys.append(_missing_birthdate_configuration_key(settings))
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
    if isinstance(exc, ApprovedCatalogUnavailableError):
        return AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="APPROVED_CATALOG_UNAVAILABLE",
            message="운영 승인된 운동 카탈로그를 현재 사용할 수 없습니다.",
        )
    if isinstance(exc, RoutineContentUnavailableError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="ROUTINE_CONTENT_UNAVAILABLE",
            message="승인된 운동 콘텐츠로 기본 루틴을 구성할 수 없습니다.",
        )
    if isinstance(exc, RoutineDurationUnavailableError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="ROUTINE_DURATION_UNAVAILABLE",
            message="요청한 시간에 맞는 기본 루틴을 구성할 수 없습니다.",
        )
    if isinstance(exc, AgeRequirementNotMetError):
        return AppError(
            status_code=HTTPStatus.FORBIDDEN,
            code="OUT_OF_SCOPE_AGE",
            message="현재 서비스는 만 18–64세 성인을 대상으로 제공됩니다.",
        )
    if isinstance(exc, MedicalExerciseRestrictionError):
        return AppError(
            status_code=HTTPStatus.FORBIDDEN,
            code="OUT_OF_SCOPE_MEDICAL_MANAGEMENT",
            message="개별 운동 관리는 의료진 또는 전문가와 상의해주세요.",
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


def _translate_profile_image_error(exc: Exception, *, request: Request) -> AppError:
    if isinstance(exc, InvalidProfileImageError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="INVALID_PROFILE_IMAGE",
            message="JPEG, PNG, WEBP 형식의 5MB 이하 이미지만 업로드할 수 있습니다.",
        )
    if isinstance(exc, ProfileImageStorageUnavailableError):
        return AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="PROFILE_IMAGE_STORAGE_UNAVAILABLE",
            message="프로필 이미지 저장소를 일시적으로 사용할 수 없습니다.",
        )
    return _translate_profile_update_error(exc, request=request)


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
    routine_repository: Annotated[RoutineRepositoryPort, Depends(get_routine_repository)],
    birthdate_cipher: Annotated[BirthdateCipher | None, Depends(get_birthdate_cipher)],
) -> OnboardingResponse:
    try:
        return OnboardingCompletionService(
            _service(request, repository, birthdate_cipher), RoutineService(routine_repository)
        ).complete(session, current_user.user_id, payload, idempotency_key)
    except (
        AgeRequirementNotMetError,
        InvalidBirthdateError,
        InvalidTimezoneError,
        InvalidOnboardingCodeError,
        MedicalExerciseRestrictionError,
        RequiredConsentMissingError,
        IdempotencyKeyReusedError,
        ProfileConfigurationError,
        ApprovedCatalogUnavailableError,
        RoutineContentUnavailableError,
        RoutineDurationUnavailableError,
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
    routine_repository: Annotated[StaleRoutinePort, Depends(get_routine_repository)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProfileSettingsUpdateResponse:
    try:
        return _service(
            request, repository, birthdate_cipher, routine_repository
        ).update_profile_settings(
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


@router.post("/profile-image", response_model=ProfileImageMutationResponse)
async def upload_profile_image(
    file: Annotated[UploadFile, File()],
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[ProfileRepositoryPort, Depends(get_profile_repository)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProfileImageMutationResponse:
    try:
        result = ProfileImageService(
            repository, getattr(request.app.state, "profile_image_storage", None)
        ).upload(
            session,
            current_user.user_id,
            idempotency_key,
            _expected_profile_version(if_match),
            file.content_type,
            await file.read(MAX_PROFILE_IMAGE_BYTES + 1),
        )
        return ProfileImageMutationResponse(**result.__dict__)
    except (
        InvalidProfileImageError,
        ProfileImageStorageUnavailableError,
        ProfileNotFoundError,
        StaleProfileError,
        IdempotencyKeyReusedError,
        SQLAlchemyError,
    ) as exc:
        raise _translate_profile_image_error(exc, request=request) from None
    finally:
        await file.close()


@router.delete("/profile-image", response_model=ProfileImageMutationResponse)
def delete_profile_image(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[ProfileRepositoryPort, Depends(get_profile_repository)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProfileImageMutationResponse:
    try:
        result = ProfileImageService(
            repository, getattr(request.app.state, "profile_image_storage", None)
        ).delete(
            session,
            current_user.user_id,
            idempotency_key,
            _expected_profile_version(if_match),
        )
        return ProfileImageMutationResponse(**result.__dict__)
    except (
        ProfileImageStorageUnavailableError,
        ProfileNotFoundError,
        StaleProfileError,
        IdempotencyKeyReusedError,
        SQLAlchemyError,
    ) as exc:
        raise _translate_profile_image_error(exc, request=request) from None


__all__ = ["router"]
