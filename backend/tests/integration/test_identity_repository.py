import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.identity import User, UserIdentity
from backend.app.db.repositories.identity import IdentityRepository
from backend.app.modules.identity.codes import (
    IDENTITY_CODE_SET_VERSION,
    IdentityProviderCode,
    UserStatusCode,
)
from backend.app.modules.identity.ports import VerifiedFirebaseIdentity
from backend.app.modules.identity.service import AccountAccessBlockedError, CurrentUserService

ALEMBIC_CONFIG = Path("backend/alembic.ini")


class StaticVerifier:
    def __init__(self, subject: str) -> None:
        self.subject = subject

    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        assert token == "id-token"
        return VerifiedFirebaseIdentity(firebase_subject=self.subject)


class BarrierVerifier(StaticVerifier):
    def __init__(self, subject: str, barrier: Barrier) -> None:
        super().__init__(subject)
        self.barrier = barrier

    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        result = super().verify_id_token(token)
        self.barrier.wait(timeout=5)
        return result


@pytest.fixture
def postgres_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(test_database_url).database.endswith("_test"):
        pytest.fail("Identity repository tests require a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")

    engine: Engine = create_engine(test_database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()
        get_settings.cache_clear()


@pytest.mark.integration
def test_authentication_creates_identity_once_and_updates_last_active(
    postgres_session: Session,
) -> None:
    first_seen = datetime(2026, 8, 13, 1, 0, tzinfo=UTC)
    second_seen = first_seen + timedelta(hours=1)
    clock_values = iter((first_seen, second_seen))
    service = CurrentUserService(
        StaticVerifier("firebase-subject-one"),
        IdentityRepository(),
        clock=lambda: next(clock_values),
    )

    first = service.authenticate(postgres_session, "id-token")
    second = service.authenticate(postgres_session, "id-token")

    assert second.user_id == first.user_id
    assert postgres_session.scalar(select(func.count()).select_from(User)) == 1
    assert postgres_session.scalar(select(func.count()).select_from(UserIdentity)) == 1
    user = postgres_session.get(User, first.user_id)
    assert user is not None
    assert user.status_code == UserStatusCode.ACTIVE
    assert user.code_set_version == IDENTITY_CODE_SET_VERSION
    assert user.last_active_at == second_seen
    assert user.ai_trial_ends_at - user.ai_trial_started_at == timedelta(days=14)
    identity = postgres_session.scalar(select(UserIdentity))
    assert identity is not None
    assert identity.provider_code == IdentityProviderCode.FIREBASE
    assert identity.provider_subject == "firebase-subject-one"
    assert identity.firebase_subject == "firebase-subject-one"


@pytest.mark.integration
def test_active_firebase_subject_unique_index_blocks_duplicate_link(
    postgres_session: Session,
) -> None:
    service = CurrentUserService(StaticVerifier("duplicate-subject"), IdentityRepository())
    current_user = service.authenticate(postgres_session, "id-token")

    with pytest.raises(IntegrityError), postgres_session.begin():
        postgres_session.add(
            UserIdentity(
                user_id=current_user.user_id,
                provider_code=IdentityProviderCode.FIREBASE,
                provider_subject="another-provider-subject",
                firebase_subject="duplicate-subject",
                code_set_version=IDENTITY_CODE_SET_VERSION,
            )
        )
        postgres_session.flush()


@pytest.mark.integration
def test_inactive_linked_user_is_rejected(postgres_session: Session) -> None:
    service = CurrentUserService(StaticVerifier("disabled-subject"), IdentityRepository())
    current_user = service.authenticate(postgres_session, "id-token")
    with postgres_session.begin():
        user = postgres_session.get(User, current_user.user_id)
        assert user is not None
        user.status_code = UserStatusCode.DISABLED

    with pytest.raises(AccountAccessBlockedError):
        service.authenticate(postgres_session, "id-token")


@pytest.mark.integration
def test_concurrent_first_authentication_resolves_to_one_user(
    postgres_session: Session,
) -> None:
    del postgres_session
    test_database_url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(test_database_url)
    barrier = Barrier(2)

    def authenticate() -> UUID:
        service = CurrentUserService(
            BarrierVerifier("concurrent-firebase-subject", barrier),
            IdentityRepository(),
        )
        with Session(engine) as session:
            return service.authenticate(session, "id-token").user_id

    user_ids: list[UUID] = []
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            user_ids = list(executor.map(lambda _: authenticate(), range(2)))

        assert user_ids[0] == user_ids[1]
        with Session(engine) as verification_session:
            assert (
                verification_session.scalar(
                    select(func.count())
                    .select_from(UserIdentity)
                    .where(UserIdentity.firebase_subject == "concurrent-firebase-subject")
                )
                == 1
            )
    finally:
        if user_ids:
            with engine.begin() as connection:
                connection.execute(delete(User).where(User.id.in_(set(user_ids))))
        engine.dispose()
