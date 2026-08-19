from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.modules.identity.codes import UserStatusCode


class InvalidFirebaseTokenError(Exception):
    """The credential is not an acceptable Firebase ID Token."""


class FirebaseVerifierUnavailableError(Exception):
    """The Firebase verifier cannot safely make an authentication decision."""


@dataclass(frozen=True)
class VerifiedFirebaseIdentity:
    firebase_subject: str


@dataclass(frozen=True)
class IdentityUserRecord:
    user_id: UUID
    status_code: UserStatusCode


class FirebaseTokenVerifier(Protocol):
    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity: ...


class IdentityRepositoryPort(Protocol):
    def acquire_subject_lock(self, session: Session, firebase_subject: str) -> None: ...

    def get_active_by_firebase_subject(
        self,
        session: Session,
        firebase_subject: str,
    ) -> IdentityUserRecord | None: ...

    def create_firebase_user(
        self,
        session: Session,
        firebase_subject: str,
        now: datetime,
    ) -> IdentityUserRecord: ...

    def touch_last_active(self, session: Session, user_id: UUID, now: datetime) -> None: ...


__all__ = [
    "FirebaseTokenVerifier",
    "FirebaseVerifierUnavailableError",
    "IdentityRepositoryPort",
    "IdentityUserRecord",
    "InvalidFirebaseTokenError",
    "VerifiedFirebaseIdentity",
]
