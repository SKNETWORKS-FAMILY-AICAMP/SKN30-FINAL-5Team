from contextlib import nullcontext
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.ports import (
    FirebaseVerifierUnavailableError,
    IdentityUserRecord,
    InvalidFirebaseTokenError,
    VerifiedFirebaseIdentity,
)
from backend.app.modules.identity.service import AccountAccessBlockedError, CurrentUserService


class FakeSession:
    def __init__(self) -> None:
        self.begin_count = 0

    def begin(self) -> nullcontext[None]:
        self.begin_count += 1
        return nullcontext()


class StaticVerifier:
    def __init__(self, subject: str = "firebase-subject") -> None:
        self.subject = subject

    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        assert token == "id-token"
        return VerifiedFirebaseIdentity(firebase_subject=self.subject)


class FailingVerifier:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        del token
        raise self.error


class FakeIdentityRepository:
    def __init__(self, status_code: UserStatusCode = UserStatusCode.ACTIVE) -> None:
        self.record: IdentityUserRecord | None = None
        self.status_code = status_code
        self.created_count = 0
        self.locked_subjects: list[str] = []
        self.touched: list[tuple[UUID, datetime]] = []

    def acquire_subject_lock(self, session: FakeSession, firebase_subject: str) -> None:
        del session
        self.locked_subjects.append(firebase_subject)

    def get_active_by_firebase_subject(
        self,
        session: FakeSession,
        firebase_subject: str,
    ) -> IdentityUserRecord | None:
        del session, firebase_subject
        return self.record

    def create_firebase_user(
        self,
        session: FakeSession,
        firebase_subject: str,
        now: datetime,
    ) -> IdentityUserRecord:
        del session, firebase_subject, now
        self.created_count += 1
        self.record = IdentityUserRecord(user_id=uuid4(), status_code=self.status_code)
        return self.record

    def touch_last_active(self, session: FakeSession, user_id: UUID, now: datetime) -> None:
        del session
        self.touched.append((user_id, now))


def test_first_authentication_creates_and_returns_current_user() -> None:
    now = datetime(2026, 8, 13, 2, 0, tzinfo=UTC)
    repository = FakeIdentityRepository()
    session = FakeSession()
    service = CurrentUserService(StaticVerifier(), repository, clock=lambda: now)

    current_user = service.authenticate(session, "id-token")  # type: ignore[arg-type]

    assert current_user.user_id == repository.record.user_id  # type: ignore[union-attr]
    assert current_user.status_code is UserStatusCode.ACTIVE
    assert repository.created_count == 1
    assert repository.locked_subjects == ["firebase-subject"]
    assert repository.touched == [(current_user.user_id, now)]
    assert session.begin_count == 1


def test_repeated_authentication_reuses_the_same_user() -> None:
    repository = FakeIdentityRepository()
    service = CurrentUserService(StaticVerifier(), repository)
    session = FakeSession()

    first = service.authenticate(session, "id-token")  # type: ignore[arg-type]
    second = service.authenticate(session, "id-token")  # type: ignore[arg-type]

    assert second.user_id == first.user_id
    assert repository.created_count == 1


def test_authentication_preserves_previous_activity_for_return_notification_trigger() -> None:
    previous_activity = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
    now = datetime(2026, 8, 13, 2, 0, tzinfo=UTC)
    repository = FakeIdentityRepository()
    repository.record = IdentityUserRecord(
        user_id=uuid4(),
        status_code=UserStatusCode.ACTIVE,
        last_active_at=previous_activity,
    )

    current_user = CurrentUserService(StaticVerifier(), repository, clock=lambda: now).authenticate(
        FakeSession(),
        "id-token",  # type: ignore[arg-type]
    )

    assert current_user.previous_last_active_at == previous_activity
    assert repository.touched == [(current_user.user_id, now)]


@pytest.mark.parametrize(
    "status_code",
    [
        UserStatusCode.DORMANT,
        UserStatusCode.DELETION_PENDING,
        UserStatusCode.DISABLED,
    ],
)
def test_non_active_account_is_blocked(status_code: UserStatusCode) -> None:
    repository = FakeIdentityRepository(status_code)
    service = CurrentUserService(StaticVerifier(), repository)

    with pytest.raises(AccountAccessBlockedError):
        service.authenticate(FakeSession(), "id-token")  # type: ignore[arg-type]

    assert repository.touched == []


@pytest.mark.parametrize(
    "error",
    [InvalidFirebaseTokenError(), FirebaseVerifierUnavailableError()],
)
def test_verifier_failure_does_not_start_a_database_transaction(error: Exception) -> None:
    session = FakeSession()
    service = CurrentUserService(FailingVerifier(error), FakeIdentityRepository())

    with pytest.raises(type(error)):
        service.authenticate(session, "id-token")  # type: ignore[arg-type]

    assert session.begin_count == 0
