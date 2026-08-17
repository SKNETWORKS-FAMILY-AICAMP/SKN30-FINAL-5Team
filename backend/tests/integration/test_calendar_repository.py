import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.account_deletion import AccountDeletionAudit, AccountDeletionJob
from backend.app.db.models.calendar import (
    CalendarConnection,
    CalendarEventLink,
    CalendarOAuthRequest,
    CalendarRateLimitCounter,
)
from backend.app.db.models.catalog import CatalogVersion, Location
from backend.app.db.models.checkin import DailyContext
from backend.app.db.models.decision import (
    DecisionOption,
    DecisionPolicyVersion,
    DecisionRun,
    PlanCandidate,
)
from backend.app.db.models.identity import User
from backend.app.db.models.routine import Routine
from backend.app.db.models.workout import DecisionSelection, WorkoutSession
from backend.app.db.repositories.account_deletion import AccountDeletionRepository
from backend.app.db.repositories.calendar import CalendarRepository
from backend.app.modules.account_deletion.ports import BackupExpiryEvidence
from backend.app.modules.account_deletion.service import (
    AccountDeletionJobService,
    AccountDeletionService,
)
from backend.app.modules.external_context.ports import (
    CalendarPersistenceConflictError,
    CalendarRateLimitBucketCode,
    CalendarSecretCleanupPendingError,
    OAuthConsumeStatusCode,
)
from backend.app.modules.identity.codes import (
    IDENTITY_CODE_SET_VERSION,
    PremiumStatusCode,
    UserStatusCode,
)

ALEMBIC_CONFIG = Path("backend/alembic.ini")
NOW = datetime(2026, 8, 17, 5, 23, 45, tzinfo=UTC)


class _NoOpIdentityRevoker:
    def revoke(self, provider_code: str, provider_subject: str) -> None:
        raise AssertionError(f"unexpected identity revocation: {provider_code}:{provider_subject}")


class _NoBackupEvidence:
    def verify_expiry(
        self, deletion_job_id: UUID, backup_expiry_due_at: datetime
    ) -> BackupExpiryEvidence | None:
        del deletion_job_id, backup_expiry_due_at
        return None


@pytest.fixture
def postgres_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(test_database_url).database.endswith("_test"):
        pytest.fail("Calendar repository tests require a dedicated *_test database")
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")
    engine = create_engine(test_database_url)
    try:
        yield engine
    finally:
        engine.dispose()
        get_settings.cache_clear()


def _user(user_id: UUID) -> User:
    return User(
        id=user_id,
        status_code=UserStatusCode.ACTIVE,
        code_set_version=IDENTITY_CODE_SET_VERSION,
        last_active_at=NOW,
        created_at=NOW,
        updated_at=NOW,
        deletion_requested_at=None,
        ai_trial_started_at=NOW,
        ai_trial_ends_at=NOW + timedelta(days=14),
        premium_status_code=PremiumStatusCode.NOT_AVAILABLE,
    )


def _seed_planned_workout(session: Session, user_id: UUID) -> dict[str, UUID | str]:
    suffix = uuid4().hex[:12]
    catalog_id = uuid4()
    location_code = f"CAL_LOCATION_{suffix}"
    routine_id = uuid4()
    daily_context_id = uuid4()
    policy_id = uuid4()
    decision_id = uuid4()
    candidate_id = uuid4()
    option_id = uuid4()
    selection_id = uuid4()
    workout_session_id = uuid4()
    session.add_all(
        (
            _user(user_id),
            CatalogVersion(
                id=catalog_id,
                version_code=f"calendar-test-{suffix}",
                status_code="DRAFT",
                manifest_schema_version="1.0",
                generator_version="test-v1",
                code_set_version="mvp-v1",
                source_manifest_hash="a" * 64,
                source_track_code="wger",
                review_status_code="DOMAIN_APPROVED",
                review_method_code="AGENT_ONLY",
                status_interpretation_code="PIPELINE_COMPATIBILITY_ONLY",
                production_eligible=False,
                exercise_record_count=0,
                manifest_metadata={},
                activated_at=None,
                created_at=NOW,
            ),
            Location(code=location_code, code_set_version="mvp-v1", display_name_ko=None),
            DecisionPolicyVersion(
                id=policy_id,
                version_code=f"calendar-policy-{suffix}",
                status_code="ACTIVE",
                created_at=NOW,
            ),
        )
    )
    session.flush()
    session.add_all(
        (
            Routine(
                id=routine_id,
                user_id=user_id,
                version=1,
                goal_code="GENERAL_FITNESS",
                status_code="DRAFT",
                effective_from=NOW.date(),
                effective_to=None,
                catalog_version_id=catalog_id,
                created_at=NOW,
            ),
            DailyContext(
                id=daily_context_id,
                user_id=user_id,
                local_date=NOW.date(),
                fatigue_level_code="LOW",
                requested_duration_minutes=30,
                duration_adjustment_source_code="PROFILE",
                location_code=location_code,
                sleep_minutes=None,
                fasting_state_code=None,
                hydration_state_code=None,
                context_version=1,
                created_at=NOW,
                updated_at=NOW,
            ),
        )
    )
    session.flush()
    session.add(
        DecisionRun(
            id=decision_id,
            user_id=user_id,
            local_date=NOW.date(),
            daily_context_id=daily_context_id,
            daily_context_version=1,
            base_routine_id=routine_id,
            input_schema_version="calendar-test-v1",
            input_snapshot={},
            input_hash="b" * 64,
            catalog_version_id=catalog_id,
            policy_version_id=policy_id,
            safety_rule_version="test-v1",
            duration_rule_version="test-v1",
            graph_version="test-v1",
            coordinator_version="test-v1",
            status_code="COMPLETED",
            safety_status_code="PASS",
            recommended_action_code="KEEP",
            coordinator_result={},
            failure_code=None,
            created_at=NOW,
            completed_at=NOW,
        )
    )
    session.flush()
    session.add(
        PlanCandidate(
            id=candidate_id,
            decision_run_id=decision_id,
            candidate_code="calendar-final",
            action_code="KEEP",
            training_type_code="STRENGTH",
            body_focus_code=None,
            requested_duration_minutes=30,
            duration_adjustment_source_code="PROFILE",
            estimated_duration_seconds=1800,
            estimated_calories_burned=None,
            setup_seconds=0,
            warmup_seconds=60,
            cooldown_seconds=60,
            goal_tags=[],
            duration_rule_version="test-v1",
            selected=True,
            created_at=NOW,
        )
    )
    session.flush()
    session.add(
        DecisionOption(
            id=option_id,
            decision_run_id=decision_id,
            option_code="FINAL_ROUTINE",
            action_code="KEEP",
            plan_candidate_id=candidate_id,
            display_order=1,
            selectable=True,
            blocked_reason_code=None,
        )
    )
    session.flush()
    session.add(
        DecisionSelection(
            id=selection_id,
            decision_run_id=decision_id,
            decision_option_id=option_id,
            selected_action_code="KEEP",
            idempotency_key=uuid4(),
            selected_at=NOW,
        )
    )
    session.flush()
    session.add(
        WorkoutSession(
            id=workout_session_id,
            user_id=user_id,
            decision_selection_id=selection_id,
            plan_candidate_id=candidate_id,
            scheduled_workout_id=None,
            status_code="PLANNED",
            started_at=None,
            ended_at=None,
            actual_elapsed_seconds=None,
            estimated_calories_burned=None,
            idempotency_key=uuid4(),
            created_at=NOW,
        )
    )
    session.flush()
    return {
        "catalog_id": catalog_id,
        "location_code": location_code,
        "policy_id": policy_id,
        "workout_session_id": workout_session_id,
    }


def _cleanup_seed(engine: Engine, user_id: UUID, seed: dict[str, UUID | str]) -> None:
    with engine.begin() as connection:
        connection.execute(delete(User).where(User.id == user_id))
        connection.execute(
            delete(DecisionPolicyVersion).where(DecisionPolicyVersion.id == seed["policy_id"])
        )
        connection.execute(delete(CatalogVersion).where(CatalogVersion.id == seed["catalog_id"]))
        connection.execute(delete(Location).where(Location.code == seed["location_code"]))


def test_connection_and_event_link_writes_are_idempotent(postgres_engine: Engine) -> None:
    user_id = uuid4()
    connection_id = uuid4()
    event_link_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        seed = _seed_planned_workout(session, user_id)
    secret_ref = f"calendar-credential://test/{connection_id}"
    repository = CalendarRepository()
    try:
        with Session(postgres_engine) as session, session.begin():
            first = repository.save_connection(
                session,
                connection_id=connection_id,
                user_id=user_id,
                provider_code="GOOGLE_CALENDAR",
                token_secret_ref=secret_ref,
                granted_at=NOW,
                now=NOW,
            )
            repeated = repository.save_connection(
                session,
                connection_id=connection_id,
                user_id=user_id,
                provider_code="GOOGLE_CALENDAR",
                token_secret_ref=secret_ref,
                granted_at=NOW,
                now=NOW,
            )
            assert repeated == first
            conflicting_connection_id = uuid4()
            with pytest.raises(CalendarPersistenceConflictError):
                repository.save_connection(
                    session,
                    connection_id=conflicting_connection_id,
                    user_id=user_id,
                    provider_code="GOOGLE_CALENDAR",
                    token_secret_ref=(f"calendar-credential://test/{conflicting_connection_id}"),
                    granted_at=NOW,
                    now=NOW,
                )

            workout_session_id = seed["workout_session_id"]
            assert isinstance(workout_session_id, UUID)
            link = repository.save_event_link(
                session,
                event_link_id=event_link_id,
                user_id=user_id,
                calendar_connection_id=connection_id,
                workout_session_id=workout_session_id,
                external_event_id="e" * 1024,
                start_at=NOW,
                end_at=NOW + timedelta(minutes=30),
                now=NOW,
            )
            repeated_link = repository.save_event_link(
                session,
                event_link_id=event_link_id,
                user_id=user_id,
                calendar_connection_id=connection_id,
                workout_session_id=workout_session_id,
                external_event_id="e" * 1024,
                start_at=NOW,
                end_at=NOW + timedelta(minutes=30),
                now=NOW,
            )
            assert repeated_link == link
            with pytest.raises(CalendarPersistenceConflictError):
                repository.save_event_link(
                    session,
                    event_link_id=uuid4(),
                    user_id=user_id,
                    calendar_connection_id=connection_id,
                    workout_session_id=workout_session_id,
                    external_event_id="different-event",
                    start_at=NOW,
                    end_at=NOW + timedelta(minutes=30),
                    now=NOW,
                )
    finally:
        _cleanup_seed(postgres_engine, user_id, seed)


def test_database_rejects_invalid_secret_reference_and_missing_fk(
    postgres_engine: Engine,
) -> None:
    user_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(_user(user_id))
    try:
        with Session(postgres_engine) as session:
            session.add(
                CalendarConnection(
                    id=uuid4(),
                    user_id=user_id,
                    provider_code="GOOGLE_CALENDAR",
                    provider_subject=None,
                    token_secret_ref="not-an-opaque-reference",
                    status_code="ACTIVE",
                    granted_at=NOW,
                    revoked_at=None,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

            session.add(
                CalendarEventLink(
                    id=uuid4(),
                    calendar_connection_id=uuid4(),
                    workout_session_id=uuid4(),
                    external_event_id="valid-event",
                    start_at=NOW,
                    end_at=NOW + timedelta(minutes=30),
                    performed=None,
                    performance_checked_at=None,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(delete(User).where(User.id == user_id))


def test_oauth_request_is_600_seconds_single_use_and_transactional(
    postgres_engine: Engine,
) -> None:
    user_id = uuid4()
    request_id = uuid4()
    repository = CalendarRepository()
    with Session(postgres_engine) as session, session.begin():
        session.add(_user(user_id))
        request = repository.replace_oauth_request(
            session,
            request_id=request_id,
            user_id=user_id,
            provider_code="GOOGLE_CALENDAR",
            state_digest="a" * 64,
            redirect_uri_key="mobile_app",
            code_challenge_s256="A" * 43,
            consent_version="calendar-consent-v1",
            created_at=NOW,
        )
        assert request.expires_at == NOW + timedelta(seconds=600)
    try:
        with Session(postgres_engine) as session:
            result = repository.consume_oauth_request(
                session,
                user_id=user_id,
                provider_code="GOOGLE_CALENDAR",
                state_digest="a" * 64,
                redirect_uri_key="mobile_app",
                computed_code_challenge_s256="A" * 43,
                now=NOW + timedelta(seconds=599),
            )
            assert result.status_code is OAuthConsumeStatusCode.CONSUMED
            session.rollback()

        with Session(postgres_engine) as session, session.begin():
            committed = repository.consume_oauth_request(
                session,
                user_id=user_id,
                provider_code="GOOGLE_CALENDAR",
                state_digest="a" * 64,
                redirect_uri_key="mobile_app",
                computed_code_challenge_s256="A" * 43,
                now=NOW + timedelta(seconds=599),
            )
            assert committed.status_code is OAuthConsumeStatusCode.CONSUMED

        with Session(postgres_engine) as session, session.begin():
            replay = repository.consume_oauth_request(
                session,
                user_id=user_id,
                provider_code="GOOGLE_CALENDAR",
                state_digest="a" * 64,
                redirect_uri_key="mobile_app",
                computed_code_challenge_s256="A" * 43,
                now=NOW + timedelta(seconds=599),
            )
            assert replay.status_code is OAuthConsumeStatusCode.NOT_FOUND

            repository.replace_oauth_request(
                session,
                request_id=uuid4(),
                user_id=user_id,
                provider_code="GOOGLE_CALENDAR",
                state_digest="b" * 64,
                redirect_uri_key="mobile_app",
                code_challenge_s256="B" * 43,
                consent_version="calendar-consent-v1",
                created_at=NOW,
            )

        with Session(postgres_engine) as session, session.begin():
            expired = repository.consume_oauth_request(
                session,
                user_id=user_id,
                provider_code="GOOGLE_CALENDAR",
                state_digest="b" * 64,
                redirect_uri_key="mobile_app",
                computed_code_challenge_s256="B" * 43,
                now=NOW + timedelta(seconds=600),
            )
            assert expired.status_code is OAuthConsumeStatusCode.EXPIRED
            assert (
                session.scalar(
                    select(CalendarOAuthRequest.id).where(
                        CalendarOAuthRequest.state_digest == "b" * 64
                    )
                )
                is None
            )
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(delete(User).where(User.id == user_id))


@pytest.mark.parametrize(
    ("bucket_code", "call_count", "limit"),
    [
        (CalendarRateLimitBucketCode.AVAILABILITY, 31, 30),
        (CalendarRateLimitBucketCode.TOTAL, 61, 60),
    ],
)
def test_rate_limit_increment_is_atomic_at_boundary(
    postgres_engine: Engine,
    bucket_code: CalendarRateLimitBucketCode,
    call_count: int,
    limit: int,
) -> None:
    user_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(_user(user_id))

    def increment(_: int) -> tuple[int, bool]:
        with Session(postgres_engine) as session, session.begin():
            result = CalendarRepository().increment_rate_limit(
                session,
                user_id=user_id,
                bucket_code=bucket_code,
                now=NOW,
            )
            return result.count, result.allowed

    try:
        with ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(increment, range(call_count)))
        assert sorted(count for count, _ in results) == list(range(1, call_count + 1))
        assert sum(allowed for _, allowed in results) == limit
        assert dict(results)[call_count] is False
        with Session(postgres_engine) as session:
            counter = session.get(CalendarRateLimitCounter, (user_id, bucket_code))
            assert counter is not None
            assert counter.count == call_count
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(delete(User).where(User.id == user_id))


def test_user_delete_cascades_all_calendar_rows(postgres_engine: Engine) -> None:
    user_id = uuid4()
    connection_id = uuid4()
    repository = CalendarRepository()
    with Session(postgres_engine) as session, session.begin():
        seed = _seed_planned_workout(session, user_id)
        repository.save_connection(
            session,
            connection_id=connection_id,
            user_id=user_id,
            provider_code="GOOGLE_CALENDAR",
            token_secret_ref=f"calendar-credential://test/{connection_id}",
            granted_at=NOW,
            now=NOW,
        )
        workout_session_id = seed["workout_session_id"]
        assert isinstance(workout_session_id, UUID)
        repository.save_event_link(
            session,
            event_link_id=uuid4(),
            user_id=user_id,
            calendar_connection_id=connection_id,
            workout_session_id=workout_session_id,
            external_event_id="cascade-event",
            start_at=NOW,
            end_at=NOW + timedelta(minutes=30),
            now=NOW,
        )
        repository.replace_oauth_request(
            session,
            request_id=uuid4(),
            user_id=user_id,
            provider_code="GOOGLE_CALENDAR",
            state_digest="c" * 64,
            redirect_uri_key="mobile_app",
            code_challenge_s256="C" * 43,
            consent_version="calendar-consent-v1",
            created_at=NOW,
        )
        repository.increment_rate_limit(
            session,
            user_id=user_id,
            bucket_code=CalendarRateLimitBucketCode.TOTAL,
            now=NOW,
        )
        repository.mark_connection_revoke_pending(session, connection_id, NOW)
        repository.finalize_connection_revoked(session, connection_id, NOW)

    try:
        with postgres_engine.begin() as connection:
            connection.execute(delete(User).where(User.id == user_id))
        with Session(postgres_engine) as session:
            assert (
                session.scalar(
                    select(CalendarConnection.id).where(CalendarConnection.user_id == user_id)
                )
                is None
            )
            assert (
                session.scalar(
                    select(CalendarOAuthRequest.id).where(CalendarOAuthRequest.user_id == user_id)
                )
                is None
            )
            assert (
                session.scalar(
                    select(CalendarRateLimitCounter.user_id).where(
                        CalendarRateLimitCounter.user_id == user_id
                    )
                )
                is None
            )
            assert (
                session.scalar(
                    select(CalendarEventLink.id).where(
                        CalendarEventLink.calendar_connection_id == connection_id
                    )
                )
                is None
            )
    finally:
        _cleanup_seed(postgres_engine, user_id, seed)


def test_account_deletion_requires_calendar_secret_cleanup(postgres_engine: Engine) -> None:
    user_id = uuid4()
    connection_id = uuid4()
    deletion_repository = AccountDeletionRepository()
    calendar_repository = CalendarRepository()
    with Session(postgres_engine) as session, session.begin():
        session.add(_user(user_id))
        calendar_repository.save_connection(
            session,
            connection_id=connection_id,
            user_id=user_id,
            provider_code="GOOGLE_CALENDAR",
            token_secret_ref=f"calendar-credential://test/{connection_id}",
            granted_at=NOW,
            now=NOW,
        )
    with Session(postgres_engine) as session:
        response = AccountDeletionService(deletion_repository, clock=lambda: NOW).request_deletion(
            session, user_id, uuid4()
        )
        job_id = session.scalar(
            select(AccountDeletionJob.deletion_job_id).where(
                AccountDeletionJob.deletion_request_id == response.deletion_request_id
            )
        )
        assert job_id is not None
        session.rollback()

    with pytest.raises(CalendarSecretCleanupPendingError):
        with Session(postgres_engine) as session, session.begin():
            deletion_repository.begin_job_attempt(session, job_id, NOW)
            deletion_repository.mark_external_succeeded(session, job_id)
            deletion_repository.hard_delete_user_data_and_deidentify(session, job_id, NOW)

    with Session(postgres_engine) as session, session.begin():
        refs = calendar_repository.list_user_secret_references(session, user_id)
        assert refs[0].token_secret_ref == f"calendar-credential://test/{connection_id}"
        calendar_repository.mark_connection_revoke_pending(session, connection_id, NOW)
        calendar_repository.finalize_connection_revoked(session, connection_id, NOW)

    with Session(postgres_engine) as session:
        result = AccountDeletionJobService(
            deletion_repository,
            _NoOpIdentityRevoker(),
            _NoBackupEvidence(),
            clock=lambda: NOW,
        ).run_job(session, job_id)
        assert result is not None
        assert session.get(User, user_id) is None
        session.rollback()

    with postgres_engine.begin() as connection:
        connection.execute(
            delete(AccountDeletionAudit).where(AccountDeletionAudit.deletion_job_id == job_id)
        )
