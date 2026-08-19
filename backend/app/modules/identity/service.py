from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.ports import FirebaseTokenVerifier, IdentityRepositoryPort


class AccountAccessBlockedError(Exception):
    """The linked internal account may not access ordinary APIs."""


class AccountAuthenticationRequiredError(Exception):
    """No existing account is linked to the verified provider identity."""


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    status_code: UserStatusCode


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CurrentUserService:
    def __init__(
        self,
        verifier: FirebaseTokenVerifier,
        repository: IdentityRepositoryPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._verifier = verifier
        self._repository = repository
        self._clock = clock

    def authenticate(self, session: Session, token: str) -> CurrentUser:
        verified = self._verifier.verify_id_token(token)
        now = self._clock()

        with session.begin():
            self._repository.acquire_subject_lock(session, verified.firebase_subject)
            record = self._repository.get_active_by_firebase_subject(
                session,
                verified.firebase_subject,
            )
            if record is None:
                record = self._repository.create_firebase_user(
                    session,
                    verified.firebase_subject,
                    now,
                )

            if record.status_code is not UserStatusCode.ACTIVE:
                raise AccountAccessBlockedError

            self._repository.touch_last_active(session, record.user_id, now)

        return CurrentUser(user_id=record.user_id, status_code=record.status_code)


class DeletionLifecycleUserService:
    """Authenticate only an existing account that may request or replay deletion."""

    def __init__(
        self,
        verifier: FirebaseTokenVerifier,
        repository: IdentityRepositoryPort,
    ) -> None:
        self._verifier = verifier
        self._repository = repository

    def authenticate(self, session: Session, token: str) -> CurrentUser:
        verified = self._verifier.verify_id_token(token)
        with session.begin():
            self._repository.acquire_subject_lock(session, verified.firebase_subject)
            record = self._repository.get_active_by_firebase_subject(
                session,
                verified.firebase_subject,
            )
            if record is None:
                raise AccountAuthenticationRequiredError
            if record.status_code not in {
                UserStatusCode.ACTIVE,
                UserStatusCode.DELETION_PENDING,
            }:
                raise AccountAccessBlockedError
        return CurrentUser(user_id=record.user_id, status_code=record.status_code)


__all__ = [
    "AccountAccessBlockedError",
    "AccountAuthenticationRequiredError",
    "CurrentUser",
    "CurrentUserService",
    "DeletionLifecycleUserService",
]
