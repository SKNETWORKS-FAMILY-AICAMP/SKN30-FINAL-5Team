import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, delete, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.account_deletion import AccountDeletionAudit, AccountDeletionJob
from backend.app.db.models.catalog import (
    BodyFocus,
    CatalogVersion,
    Exercise,
    Location,
    MovementPattern,
    TrainingType,
)
from backend.app.db.models.checkin import DailyContext
from backend.app.db.models.decision import (
    AgentProposalRecord,
    DecisionOption,
    DecisionPolicyVersion,
    DecisionRun,
    PlanCandidate,
    PlanItem,
    SafetyReview,
)
from backend.app.db.models.identity import User, UserIdentity
from backend.app.db.models.profile import UserProfile
from backend.app.db.models.routine import Routine, RoutineDay
from backend.app.db.models.weekly_report import UserWeek, WeeklyReport
from backend.app.db.models.workout import (
    DecisionSelection,
    WorkoutFeedback,
    WorkoutSession,
    WorkoutSessionItem,
)
from backend.app.db.repositories.account_deletion import AccountDeletionRepository
from backend.app.modules.account_deletion.codes import DeletionJobStatusCode
from backend.app.modules.account_deletion.ports import BackupExpiryEvidence
from backend.app.modules.account_deletion.service import (
    AccountDeletionJobService,
    AccountDeletionService,
)
from backend.app.modules.identity.codes import (
    IDENTITY_CODE_SET_VERSION,
    IdentityProviderCode,
    PremiumStatusCode,
    UserStatusCode,
)

ALEMBIC_CONFIG = Path("backend/alembic.ini")
NOW = datetime(2026, 8, 14, 5, 0, tzinfo=UTC)


class SuccessfulRevoker:
    def __init__(self) -> None:
        self.subjects: list[str] = []

    def revoke(self, provider_code: str, provider_subject: str) -> None:
        assert provider_code == IdentityProviderCode.FIREBASE
        self.subjects.append(provider_subject)


class NoBackupEvidence:
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
        pytest.fail("Account deletion tests require a dedicated *_test database")
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


def _user(user_id: UUID, subject: str | None = None) -> tuple[User, UserIdentity | None]:
    user = User(
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
    identity = None
    if subject is not None:
        identity = UserIdentity(
            id=uuid4(),
            user_id=user_id,
            provider_code=IdentityProviderCode.FIREBASE,
            provider_subject=subject,
            firebase_subject=subject,
            code_set_version=IDENTITY_CODE_SET_VERSION,
            created_at=NOW,
            revoked_at=None,
        )
    return user, identity


def _seed_linked_graph(session: Session, user_id: UUID, suffix: str) -> dict[str, UUID]:
    catalog_id = uuid4()
    exercise_id = uuid4()
    location_code = f"LOCATION_{suffix}"
    training_code = f"TRAINING_{suffix}"
    focus_code = f"FOCUS_{suffix}"
    movement_code = f"MOVEMENT_{suffix}"
    session.add_all(
        (
            Location(code=location_code, code_set_version="mvp-v1", display_name_ko=None),
            TrainingType(code=training_code, code_set_version="mvp-v1", display_name_ko=None),
            BodyFocus(code=focus_code, code_set_version="mvp-v1", display_name_ko=None),
            MovementPattern(code=movement_code, code_set_version="mvp-v1", display_name_ko=None),
            CatalogVersion(
                id=catalog_id,
                version_code=f"delete-test-{suffix}",
                status_code="DRAFT",
                manifest_schema_version="1.0",
                generator_version="test",
                code_set_version="mvp-v1",
                source_manifest_hash="a" * 64,
                source_track_code="wger",
                review_status_code="DOMAIN_APPROVED",
                review_method_code="AGENT_ONLY",
                status_interpretation_code="PIPELINE_COMPATIBILITY_ONLY",
                production_eligible=False,
                exercise_record_count=1,
                manifest_metadata={},
                activated_at=None,
                created_at=NOW,
            ),
        )
    )
    session.flush()
    session.add(
        Exercise(
            id=exercise_id,
            catalog_version_id=catalog_id,
            stable_code=f"exercise-{suffix}",
            name_ko="테스트 운동",
            name_en=None,
            training_type_code=training_code,
            body_focus_code=focus_code,
            primary_movement_pattern_code=movement_code,
            difficulty_code="BEGINNER",
            beginner_suitable=True,
            timing_mode_code="REPS",
            default_seconds_per_rep=3,
            default_work_seconds=None,
            default_rest_seconds=10,
            default_transition_seconds=10,
            recovery_eligible=False,
            instruction_summary_ko="테스트",
            form_cues_ko=[],
            instruction_content_version="test-v1",
            review_status_code="DOMAIN_APPROVED",
            source_track_code="wger",
            source_identity=f"source-{suffix}",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.add(
        UserProfile(
            user_id=user_id,
            protected_birthdate="encrypted-sensitive-birthdate",
            nickname="private-nickname",
            primary_goal_code="GENERAL_FITNESS",
            experience_level_code="BEGINNER",
            timezone="Asia/Seoul",
            preferred_location_code=location_code,
            default_requested_duration_minutes=30,
            desired_weekly_workout_count=3,
            coaching_style_code="SUPPORTIVE",
            height_cm=None,
            weight_kg=None,
            sex_code=None,
            code_set_version="profile-mvp-v1",
            profile_version=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    daily_context_id = uuid4()
    routine_id = uuid4()
    routine_day_id = uuid4()
    policy_id = uuid4()
    session.add_all(
        (
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
            Routine(
                id=routine_id,
                user_id=user_id,
                version=1,
                goal_code="GENERAL_FITNESS",
                status_code="ACTIVE",
                effective_from=NOW.date(),
                effective_to=None,
                catalog_version_id=catalog_id,
                created_at=NOW,
            ),
            DecisionPolicyVersion(
                id=policy_id,
                version_code=f"delete-policy-{suffix}",
                status_code="ACTIVE",
                created_at=NOW,
            ),
        )
    )
    session.flush()
    session.add(
        RoutineDay(
            id=routine_day_id,
            routine_id=routine_id,
            sequence=1,
            schedule_rule="ROTATION",
            title="테스트",
            training_type_code=training_code,
            body_focus_code=focus_code,
            requested_duration_minutes=30,
            estimated_duration_seconds=1800,
            setup_seconds=30,
            estimated_calories_burned=None,
        )
    )
    decision_id = uuid4()
    candidate_id = uuid4()
    plan_item_id = uuid4()
    option_id = uuid4()
    proposal_id = uuid4()
    session.add(
        DecisionRun(
            id=decision_id,
            user_id=user_id,
            local_date=NOW.date(),
            daily_context_id=daily_context_id,
            daily_context_version=1,
            base_routine_id=routine_id,
            input_schema_version="test-v1",
            input_snapshot={"private_health": "must-delete"},
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
    session.add_all(
        (
            AgentProposalRecord(
                id=proposal_id,
                decision_run_id=decision_id,
                agent_type_code="TRAINING",
                proposal_status_code="READY",
                schema_version="test-v1",
                proposal_payload={"private_health": "must-delete"},
                created_at=NOW,
            ),
            PlanCandidate(
                id=candidate_id,
                decision_run_id=decision_id,
                candidate_code="candidate",
                action_code="KEEP",
                training_type_code=training_code,
                body_focus_code=focus_code,
                requested_duration_minutes=30,
                duration_adjustment_source_code="PROFILE",
                estimated_duration_seconds=1800,
                estimated_calories_burned=None,
                setup_seconds=30,
                warmup_seconds=300,
                cooldown_seconds=300,
                goal_tags=[],
                duration_rule_version="test-v1",
                selected=True,
                created_at=NOW,
            ),
        )
    )
    session.flush()
    session.add(
        PlanItem(
            id=plan_item_id,
            plan_candidate_id=candidate_id,
            exercise_id=exercise_id,
            sequence=1,
            phase_code="MAIN",
            tier_code="CORE",
            sets=1,
            reps=10,
            work_seconds_per_set=None,
            rest_seconds_per_set=10,
            work_seconds=30,
            rest_seconds=10,
            transition_seconds=10,
            intensity_code="LOW",
            instruction_content_version="test-v1",
            display_name="테스트 운동",
        )
    )
    session.add_all(
        (
            SafetyReview(
                id=uuid4(),
                decision_run_id=decision_id,
                plan_candidate_id=candidate_id,
                safety_status_code="PASS",
                vetoed=False,
                ruleset_version="test-v1",
                reason_codes=[],
                excluded_exercise_ids=[],
                public_guidance=None,
            ),
            DecisionOption(
                id=option_id,
                decision_run_id=decision_id,
                option_code="FINAL_ROUTINE",
                action_code="KEEP",
                plan_candidate_id=candidate_id,
                display_order=1,
                selectable=True,
                blocked_reason_code=None,
            ),
        )
    )
    session.flush()
    selection_id = uuid4()
    workout_id = uuid4()
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
            id=workout_id,
            user_id=user_id,
            decision_selection_id=selection_id,
            plan_candidate_id=candidate_id,
            scheduled_workout_id=None,
            status_code="COMPLETED",
            started_at=NOW,
            ended_at=NOW,
            actual_elapsed_seconds=30,
            estimated_calories_burned=None,
            idempotency_key=uuid4(),
            created_at=NOW,
        )
    )
    session.flush()
    session.add_all(
        (
            WorkoutSessionItem(
                id=uuid4(),
                workout_session_id=workout_id,
                plan_item_id=plan_item_id,
                status_code="COMPLETED",
                completed_at=NOW,
                updated_at=NOW,
            ),
            WorkoutFeedback(
                workout_session_id=workout_id,
                difficulty_code="APPROPRIATE",
                fatigue_code=None,
                satisfaction_code=None,
                pain_occurred=False,
                created_at=NOW,
            ),
        )
    )
    user_week_id = uuid4()
    report_id = uuid4()
    session.add(
        UserWeek(
            id=user_week_id,
            user_id=user_id,
            week_start_local_date=date(2026, 8, 10),
            week_end_local_date=date(2026, 8, 16),
            timezone="Asia/Seoul",
            target_workout_count=3,
            plan_origin_code="COLD_START",
            cold_start_applied=True,
            status_code="CLOSED",
            closed_at=NOW,
            created_at=NOW,
        )
    )
    session.flush()
    session.add(
        WeeklyReport(
            id=report_id,
            user_week_id=user_week_id,
            status_code="GENERATED",
            input_schema_version="test-v1",
            input_snapshot={"private": "must-delete"},
            input_hash="c" * 64,
            completed_count=1,
            partial_count=0,
            not_completed_count=0,
            stopped_for_safety=0,
            primary_miss_reason_code=None,
            completion_rate=1.0,
            persistence_rate=1.0,
            negotiation_success_rate=None,
            weekday_failure_summary={},
            high_completion_windows=[],
            pattern_summary={},
            decision_summary="summary",
            adjustment_direction_code="MAINTAIN",
            next_action="continue",
            agent_summaries=None,
            summary="summary",
            report_policy_version="test-v1",
            generated_at=NOW,
            acknowledged_at=None,
        )
    )
    return {
        "catalog_id": catalog_id,
        "policy_id": policy_id,
        "decision_id": decision_id,
        "proposal_id": proposal_id,
        "workout_id": workout_id,
        "report_id": report_id,
    }


@pytest.mark.integration
def test_hard_delete_removes_linked_graph_and_leaves_only_opaque_audit(
    postgres_engine: Engine,
) -> None:
    user_id = uuid4()
    suffix = uuid4().hex[:10]
    subject = f"private-provider-{suffix}"
    user, identity = _user(user_id, subject)
    assert identity is not None
    with Session(postgres_engine) as session, session.begin():
        session.add_all((user, identity))
        ids = _seed_linked_graph(session, user_id, suffix)

    repository = AccountDeletionRepository()
    with Session(postgres_engine) as session:
        response = AccountDeletionService(repository, clock=lambda: NOW).request_deletion(
            session, user_id, uuid4()
        )
        job = session.scalar(
            select(AccountDeletionJob).where(
                AccountDeletionJob.deletion_request_id == response.deletion_request_id
            )
        )
        assert job is not None
        job_id = job.deletion_job_id
        session.rollback()
        revoker = SuccessfulRevoker()
        result = AccountDeletionJobService(
            repository,
            revoker,
            NoBackupEvidence(),
            clock=lambda: NOW,
        ).run_job(session, job_id)

        assert result is not None
        assert result.status_code is DeletionJobStatusCode.BACKUP_EXPIRY_PENDING
        assert result.user_id is None
        assert revoker.subjects == [subject]
        assert session.get(User, user_id) is None
        assert session.get(UserProfile, user_id) is None
        assert session.get(DecisionRun, ids["decision_id"]) is None
        assert session.get(AgentProposalRecord, ids["proposal_id"]) is None
        assert session.get(WorkoutSession, ids["workout_id"]) is None
        assert session.get(WorkoutFeedback, ids["workout_id"]) is None
        assert session.get(WeeklyReport, ids["report_id"]) is None
        assert (
            session.scalar(
                select(AccountDeletionJob).where(AccountDeletionJob.deletion_job_id == job_id)
            )
            is None
        )
        audit = session.scalar(
            select(AccountDeletionAudit).where(AccountDeletionAudit.deletion_job_id == job_id)
        )
        assert audit is not None
        assert audit.audit_expires_at is None
        session.rollback()

    audit_columns = {
        column["name"] for column in inspect(postgres_engine).get_columns("account_deletion_audits")
    }
    assert audit_columns == {
        "deletion_request_id",
        "deletion_job_id",
        "status_code",
        "current_stage_code",
        "external_revocation_status_code",
        "completion_code",
        "policy_version",
        "attempt_count",
        "requested_at",
        "operational_data_delete_by",
        "operational_deleted_at",
        "backup_expiry_due_at",
        "backup_expiry_verified_at",
        "completed_at",
        "failure_code",
        "audit_expires_at",
    }
    assert inspect(postgres_engine).get_foreign_keys("account_deletion_audits") == []

    with postgres_engine.begin() as connection:
        connection.execute(
            delete(AccountDeletionAudit).where(AccountDeletionAudit.deletion_job_id == job_id)
        )
        connection.execute(delete(CatalogVersion).where(CatalogVersion.id == ids["catalog_id"]))
        connection.execute(
            delete(DecisionPolicyVersion).where(DecisionPolicyVersion.id == ids["policy_id"])
        )
        connection.execute(delete(Location).where(Location.code == f"LOCATION_{suffix}"))
        connection.execute(delete(TrainingType).where(TrainingType.code == f"TRAINING_{suffix}"))
        connection.execute(delete(BodyFocus).where(BodyFocus.code == f"FOCUS_{suffix}"))
        connection.execute(
            delete(MovementPattern).where(MovementPattern.code == f"MOVEMENT_{suffix}")
        )


class FailingDeleteRepository(AccountDeletionRepository):
    def hard_delete_user_data_and_deidentify(
        self, session: Session, deletion_job_id: UUID, now: datetime
    ):
        super().hard_delete_user_data_and_deidentify(session, deletion_job_id, now)
        raise OperationalError("DELETE private", {}, RuntimeError("forced rollback"))


@pytest.mark.integration
def test_hard_delete_failure_rolls_back_and_marks_review(postgres_engine: Engine) -> None:
    user_id = uuid4()
    user, _ = _user(user_id)
    with Session(postgres_engine) as session, session.begin():
        session.add(user)

    repository = FailingDeleteRepository()
    with Session(postgres_engine) as session:
        response = AccountDeletionService(repository, clock=lambda: NOW).request_deletion(
            session, user_id, uuid4()
        )
        job_id = session.scalar(
            select(AccountDeletionJob.deletion_job_id).where(
                AccountDeletionJob.deletion_request_id == response.deletion_request_id
            )
        )
        assert job_id is not None
        session.rollback()
        result = AccountDeletionJobService(
            repository,
            SuccessfulRevoker(),
            NoBackupEvidence(),
            clock=lambda: NOW,
        ).run_job(session, job_id)

        assert result is not None
        assert result.status_code is DeletionJobStatusCode.FAILED_REQUIRES_REVIEW
        assert session.get(User, user_id) is not None
        assert (
            session.scalar(
                select(AccountDeletionAudit).where(AccountDeletionAudit.deletion_job_id == job_id)
            )
            is None
        )
        session.rollback()

    with postgres_engine.begin() as connection:
        connection.execute(delete(AccountDeletionJob).where(AccountDeletionJob.user_id == user_id))
        connection.execute(delete(User).where(User.id == user_id))


@pytest.mark.integration
def test_concurrent_requests_converge_to_one_job(postgres_engine: Engine) -> None:
    user_id = uuid4()
    user, _ = _user(user_id)
    with Session(postgres_engine) as session, session.begin():
        session.add(user)

    barrier = Barrier(2)

    def request() -> UUID:
        def clock() -> datetime:
            barrier.wait(timeout=5)
            return NOW

        with Session(postgres_engine) as session:
            return (
                AccountDeletionService(
                    AccountDeletionRepository(),
                    clock=clock,
                )
                .request_deletion(session, user_id, uuid4())
                .deletion_request_id
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            request_ids = list(executor.map(lambda _: request(), range(2)))
        assert request_ids[0] == request_ids[1]
        with Session(postgres_engine) as session:
            jobs = tuple(
                session.scalars(
                    select(AccountDeletionJob).where(AccountDeletionJob.user_id == user_id)
                )
            )
            assert len(jobs) == 1
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(
                delete(AccountDeletionJob).where(AccountDeletionJob.user_id == user_id)
            )
            connection.execute(delete(User).where(User.id == user_id))
