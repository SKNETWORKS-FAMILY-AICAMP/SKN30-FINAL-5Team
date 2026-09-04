from collections.abc import Iterator
from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.db.repositories.account_deletion import AccountDeletionRepository
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.db.repositories.checkin import DailyContextRepository
from backend.app.db.repositories.decision import DecisionRepository
from backend.app.db.repositories.identity import IdentityRepository
from backend.app.db.repositories.notification import NotificationRepository
from backend.app.db.repositories.profile import ProfileRepository
from backend.app.db.repositories.routine import RoutineRepository
from backend.app.db.repositories.weekly_plan import WeeklyPlanRepository
from backend.app.db.repositories.weekly_report import WeeklyReportRepository
from backend.app.db.repositories.workout import WorkoutRepository
from backend.app.modules.account_deletion.ports import AccountDeletionRepositoryPort
from backend.app.modules.catalog.service import ExerciseMediaUrlPort, ExerciseReadRepositoryPort
from backend.app.modules.checkins.ports import DailyContextRepositoryPort
from backend.app.modules.decisions.execution_profile import DecisionCreationServicePort
from backend.app.modules.decisions.ports import DecisionRepositoryPort, NarrationProviderPort
from backend.app.modules.decisions.v3_regeneration import (
    V3EngineDisabledError,
    V3RegenerationCommand,
    V3RegenerationCompositionUnavailableError,
    V3RegenerationResult,
    V3RegenerationServicePort,
)
from backend.app.modules.identity.ports import (
    FirebaseTokenVerifier,
    FirebaseVerifierUnavailableError,
    IdentityRepositoryPort,
    InvalidFirebaseTokenError,
)
from backend.app.modules.identity.service import (
    AccountAccessBlockedError,
    AccountAuthenticationRequiredError,
    CurrentUser,
    CurrentUserService,
    DeletionLifecycleUserService,
)
from backend.app.modules.notifications.ports import NotificationRepositoryPort
from backend.app.modules.notifications.service import NotificationService
from backend.app.modules.profiles.ports import BirthdateCipher, ProfileRepositoryPort
from backend.app.modules.routines.ports import RoutineRepositoryPort
from backend.app.modules.weekly_plans.ports import WeeklyPlanRepositoryPort
from backend.app.modules.weekly_reports.ports import (
    WeeklyReportNarrationAgentPort,
    WeeklyReportRepositoryPort,
)
from backend.app.modules.workouts.ports import WorkoutRepositoryPort

_bearer_scheme = HTTPBearer(auto_error=False)
_catalog_repository = CatalogRepository()
_identity_repository = IdentityRepository()
_notification_repository = NotificationRepository()
_profile_repository = ProfileRepository()
_routine_repository = RoutineRepository()
_daily_context_repository = DailyContextRepository()
_decision_repository = DecisionRepository()
_workout_repository = WorkoutRepository()
_weekly_report_repository = WeeklyReportRepository()
_weekly_plan_repository = WeeklyPlanRepository()
_account_deletion_repository = AccountDeletionRepository()


class _DisabledV3RegenerationService:
    async def regenerate(self, command: V3RegenerationCommand) -> V3RegenerationResult:
        del command
        raise V3EngineDisabledError


class _UnavailableV3RegenerationService:
    async def regenerate(self, command: V3RegenerationCommand) -> V3RegenerationResult:
        del command
        raise V3RegenerationCompositionUnavailableError


_disabled_v3_regeneration_service = _DisabledV3RegenerationService()
_unavailable_v3_regeneration_service = _UnavailableV3RegenerationService()


def get_db_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database_manager.session()


def get_firebase_token_verifier(request: Request) -> FirebaseTokenVerifier:
    return request.app.state.firebase_token_verifier


def get_identity_repository() -> IdentityRepositoryPort:
    return _identity_repository


def get_notification_repository() -> NotificationRepositoryPort:
    return _notification_repository


def get_catalog_repository() -> ExerciseReadRepositoryPort:
    return _catalog_repository


def get_exercise_media_url_provider(request: Request) -> ExerciseMediaUrlPort:
    return request.app.state.exercise_media_url_provider


def get_account_deletion_repository() -> AccountDeletionRepositoryPort:
    return _account_deletion_repository


def get_profile_repository() -> ProfileRepositoryPort:
    return _profile_repository


def get_routine_repository() -> RoutineRepositoryPort:
    return _routine_repository


def get_daily_context_repository() -> DailyContextRepositoryPort:
    return _daily_context_repository


def get_decision_repository() -> DecisionRepositoryPort:
    return _decision_repository


def get_workout_repository() -> WorkoutRepositoryPort:
    return _workout_repository


def get_weekly_report_repository() -> WeeklyReportRepositoryPort:
    return _weekly_report_repository


def get_weekly_report_narration_agent(request: Request) -> WeeklyReportNarrationAgentPort:
    return request.app.state.weekly_report_narration_agent


def get_weekly_plan_repository() -> WeeklyPlanRepositoryPort:
    return _weekly_plan_repository


def get_birthdate_cipher(request: Request) -> BirthdateCipher | None:
    return request.app.state.birthdate_cipher


def get_narration_provider(request: Request) -> NarrationProviderPort:
    return request.app.state.narration_provider


def get_decision_creation_service(
    request: Request,
    repository: Annotated[DecisionRepositoryPort, Depends(get_decision_repository)],
) -> DecisionCreationServicePort:
    return request.app.state.decision_creation_service_factory(repository)


def get_v3_regeneration_service(request: Request) -> V3RegenerationServicePort:
    service: V3RegenerationServicePort | None = request.app.state.v3_regeneration_service
    settings = request.app.state.settings
    profile_enabled = getattr(
        request.app.state,
        "v3_authoritative_enabled",
        settings.v3_execution_profile == "DEMO"
        or (
            settings.v3_execution_profile == "PRODUCTION"
            and settings.v3_production_promotion_approved
        ),
    )
    if not (settings.v3_regeneration_enabled or profile_enabled):
        return _disabled_v3_regeneration_service
    if service is None:
        return _unavailable_v3_regeneration_service
    return service


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[Session, Depends(get_db_session)],
    verifier: Annotated[FirebaseTokenVerifier, Depends(get_firebase_token_verifier)],
    repository: Annotated[IdentityRepositoryPort, Depends(get_identity_repository)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            status_code=HTTPStatus.UNAUTHORIZED,
            code="AUTHENTICATION_REQUIRED",
            message="인증이 필요합니다.",
        )

    service = CurrentUserService(verifier, repository)
    try:
        current_user = service.authenticate(session, credentials.credentials)
        if current_user.previous_last_active_at is not None:
            NotificationService(
                _notification_repository, _workout_repository
            ).record_return_notification(
                session,
                current_user.user_id,
                previous_last_active_at=current_user.previous_last_active_at,
            )
        return current_user
    except InvalidFirebaseTokenError:
        raise AppError(
            status_code=HTTPStatus.UNAUTHORIZED,
            code="INVALID_TOKEN",
            message="유효하지 않은 인증 토큰입니다.",
        ) from None
    except FirebaseVerifierUnavailableError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="AUTH_PROVIDER_UNAVAILABLE",
            message="인증 제공자를 일시적으로 사용할 수 없습니다.",
        ) from None
    except AccountAccessBlockedError:
        raise AppError(
            status_code=HTTPStatus.FORBIDDEN,
            code="ACCOUNT_DISABLED",
            message="현재 이 계정으로 접근할 수 없습니다.",
        ) from None
    except SQLAlchemyError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="DATABASE_UNAVAILABLE",
            message="데이터베이스를 일시적으로 사용할 수 없습니다.",
        ) from None


def get_deletion_lifecycle_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[Session, Depends(get_db_session)],
    verifier: Annotated[FirebaseTokenVerifier, Depends(get_firebase_token_verifier)],
    repository: Annotated[IdentityRepositoryPort, Depends(get_identity_repository)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            status_code=HTTPStatus.UNAUTHORIZED,
            code="AUTHENTICATION_REQUIRED",
            message="인증이 필요합니다.",
        )
    service = DeletionLifecycleUserService(verifier, repository)
    try:
        return service.authenticate(session, credentials.credentials)
    except (InvalidFirebaseTokenError, AccountAuthenticationRequiredError):
        raise AppError(
            status_code=HTTPStatus.UNAUTHORIZED,
            code="AUTHENTICATION_REQUIRED",
            message="인증이 필요합니다.",
        ) from None
    except FirebaseVerifierUnavailableError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="AUTH_PROVIDER_UNAVAILABLE",
            message="인증 제공자를 일시적으로 사용할 수 없습니다.",
        ) from None
    except AccountAccessBlockedError:
        raise AppError(
            status_code=HTTPStatus.FORBIDDEN,
            code="ACCOUNT_DISABLED",
            message="현재 이 계정으로 접근할 수 없습니다.",
        ) from None
    except SQLAlchemyError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="DATABASE_UNAVAILABLE",
            message="데이터베이스를 일시적으로 사용할 수 없습니다.",
        ) from None


__all__ = [
    "get_account_deletion_repository",
    "get_catalog_repository",
    "get_current_user",
    "get_deletion_lifecycle_user",
    "get_daily_context_repository",
    "get_decision_repository",
    "get_decision_creation_service",
    "get_birthdate_cipher",
    "get_db_session",
    "get_firebase_token_verifier",
    "get_exercise_media_url_provider",
    "get_identity_repository",
    "get_narration_provider",
    "get_notification_repository",
    "get_profile_repository",
    "get_routine_repository",
    "get_workout_repository",
    "get_weekly_report_repository",
    "get_weekly_report_narration_agent",
    "get_weekly_plan_repository",
]
