from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.db.models.identity import User, UserIdentity
from backend.app.modules.identity.codes import (
    IDENTITY_CODE_SET_VERSION,
    IdentityProviderCode,
    PremiumStatusCode,
    UserStatusCode,
)
from backend.app.modules.identity.ports import IdentityUserRecord

AI_TRIAL_DURATION = timedelta(days=14)


def _subject_lock_key(firebase_subject: str) -> int:
    digest = sha256(firebase_subject.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class IdentityRepository:
    def acquire_subject_lock(self, session: Session, firebase_subject: str) -> None:
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _subject_lock_key(firebase_subject)},
        )

    def get_active_by_firebase_subject(
        self,
        session: Session,
        firebase_subject: str,
    ) -> IdentityUserRecord | None:
        user = session.scalar(
            select(User)
            .join(UserIdentity)
            .where(
                UserIdentity.firebase_subject == firebase_subject,
                UserIdentity.revoked_at.is_(None),
            )
        )
        if user is None:
            return None
        return IdentityUserRecord(
            user_id=user.id,
            status_code=UserStatusCode(user.status_code),
        )

    def create_firebase_user(
        self,
        session: Session,
        firebase_subject: str,
        now: datetime,
    ) -> IdentityUserRecord:
        user_id = uuid4()
        user = User(
            id=user_id,
            status_code=UserStatusCode.ACTIVE,
            code_set_version=IDENTITY_CODE_SET_VERSION,
            last_active_at=now,
            ai_trial_started_at=now,
            ai_trial_ends_at=now + AI_TRIAL_DURATION,
            premium_status_code=PremiumStatusCode.NOT_AVAILABLE,
        )
        identity = UserIdentity(
            id=uuid4(),
            user=user,
            provider_code=IdentityProviderCode.FIREBASE,
            provider_subject=firebase_subject,
            firebase_subject=firebase_subject,
            code_set_version=IDENTITY_CODE_SET_VERSION,
        )
        session.add_all((user, identity))
        session.flush()
        return IdentityUserRecord(user_id=user_id, status_code=UserStatusCode.ACTIVE)

    def touch_last_active(self, session: Session, user_id: UUID, now: datetime) -> None:
        user = session.get(User, user_id)
        if user is None:
            raise RuntimeError("linked identity user does not exist")
        user.last_active_at = now
        user.updated_at = now


__all__ = ["AI_TRIAL_DURATION", "IdentityRepository"]
