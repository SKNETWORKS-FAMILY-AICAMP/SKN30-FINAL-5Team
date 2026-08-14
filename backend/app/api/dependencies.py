from collections.abc import Iterator
from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.db.repositories.checkin import DailyContextRepository
from backend.app.db.repositories.decision import DecisionRepository
from backend.app.db.repositories.identity import IdentityRepository
from backend.app.db.repositories.profile import ProfileRepository
from backend.app.db.repositories.routine import RoutineRepository
from backend.app.modules.checkins.ports import DailyContextRepositoryPort
from backend.app.modules.decisions.ports import DecisionRepositoryPort
from backend.app.modules.identity.ports import (
    FirebaseTokenVerifier,
    FirebaseVerifierUnavailableError,
    IdentityRepositoryPort,
    InvalidFirebaseTokenError,
)
from backend.app.modules.identity.service import (
    AccountAccessBlockedError,
    CurrentUser,
    CurrentUserService,
)
from backend.app.modules.profiles.ports import BirthdateCipher, ProfileRepositoryPort
from backend.app.modules.routines.ports import RoutineRepositoryPort

_bearer_scheme = HTTPBearer(auto_error=False)
_identity_repository = IdentityRepository()
_profile_repository = ProfileRepository()
_routine_repository = RoutineRepository()
_daily_context_repository = DailyContextRepository()
_decision_repository = DecisionRepository()


def get_db_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database_manager.session()


def get_firebase_token_verifier(request: Request) -> FirebaseTokenVerifier:
    return request.app.state.firebase_token_verifier


def get_identity_repository() -> IdentityRepositoryPort:
    return _identity_repository


def get_profile_repository() -> ProfileRepositoryPort:
    return _profile_repository


def get_routine_repository() -> RoutineRepositoryPort:
    return _routine_repository


def get_daily_context_repository() -> DailyContextRepositoryPort:
    return _daily_context_repository


def get_decision_repository() -> DecisionRepositoryPort:
    return _decision_repository


def get_birthdate_cipher(request: Request) -> BirthdateCipher | None:
    return request.app.state.birthdate_cipher


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
        return service.authenticate(session, credentials.credentials)
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


__all__ = [
    "get_current_user",
    "get_daily_context_repository",
    "get_decision_repository",
    "get_birthdate_cipher",
    "get_db_session",
    "get_firebase_token_verifier",
    "get_identity_repository",
    "get_profile_repository",
    "get_routine_repository",
]
