import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.db import models as db_models
from backend.app.db.base import Base
from backend.app.db.models.decision import (
    DecisionOption,
    DecisionRun,
    PlanCandidate,
    PlanItem,
    SafetyReview,
)
from backend.app.db.models.identity import User
from backend.app.db.models.profile import (
    UserAvailableLocation,
    UserEquipment,
    UserProfile,
)
from backend.app.db.models.workout import (
    DecisionSelection,
    WorkoutAdditionalActivity,
    WorkoutFeedback,
    WorkoutFeedbackAdverseReaction,
    WorkoutFeedbackDiscomfort,
    WorkoutSafetyEvent,
    WorkoutSafetyEventAdverseReaction,
    WorkoutSafetyEventDiscomfort,
    WorkoutSession,
    WorkoutSessionItem,
    WorkoutSkipFeedback,
    WorkoutTimerEvent,
)
from backend.app.db.repositories.checkin import DailyContextRepository
from backend.app.db.repositories.decision import DecisionRepository
from backend.app.db.repositories.routine import RoutineRepository
from backend.app.db.repositories.workout import WorkoutRepository
from backend.app.modules.checkins.schemas import DailyContextUpsertRequest
from backend.app.modules.checkins.service import DailyContextService
from backend.app.modules.decisions.schemas import DecisionCreateRequest
from backend.app.modules.decisions.service import DecisionService
from backend.app.modules.routines.schemas import RoutineCreateRequest
from backend.app.modules.routines.service import RoutineService
from backend.app.modules.workouts.ports import WorkoutLogCursor
from backend.app.modules.workouts.schemas import DecisionSelectionRequest
from backend.app.modules.workouts.service import WorkoutService
from backend.scripts.demo_seed import seed_catalog

_ = db_models
NOW = datetime(2026, 8, 14, 1, 0, tzinfo=UTC)
ALEMBIC_CONFIG = Path("backend/alembic.ini")


def test_repository_round_trip_keeps_timer_and_additional_activity_informational() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            DecisionRun.__table__,
            PlanCandidate.__table__,
            PlanItem.__table__,
            SafetyReview.__table__,
            DecisionOption.__table__,
            DecisionSelection.__table__,
            WorkoutSession.__table__,
            WorkoutSessionItem.__table__,
            WorkoutTimerEvent.__table__,
            WorkoutAdditionalActivity.__table__,
            WorkoutSafetyEvent.__table__,
            WorkoutSafetyEventDiscomfort.__table__,
            WorkoutSafetyEventAdverseReaction.__table__,
            WorkoutFeedback.__table__,
            WorkoutFeedbackDiscomfort.__table__,
            WorkoutFeedbackAdverseReaction.__table__,
            WorkoutSkipFeedback.__table__,
        ],
    )
    user_id = uuid4()
    decision_id = uuid4()
    candidate_id = uuid4()
    plan_item_id = uuid4()
    option_id = uuid4()
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(
            DecisionRun(
                id=decision_id,
                user_id=user_id,
                local_date=date(2026, 8, 14),
                daily_context_id=uuid4(),
                daily_context_version=1,
                base_routine_id=uuid4(),
                input_schema_version="decision-input-v1",
                input_snapshot={},
                input_hash="0" * 64,
                catalog_version_id=uuid4(),
                policy_version_id=uuid4(),
                safety_rule_version="safety-v1",
                duration_rule_version="duration-v1",
                graph_version="graph-v1",
                coordinator_version="coordinator-v1",
                status_code="COMPLETED",
                safety_status_code="PASS",
                recommended_action_code="KEEP",
                coordinator_result={},
                failure_code=None,
                created_at=NOW,
                completed_at=NOW,
            )
        )
        session.add(
            PlanCandidate(
                id=candidate_id,
                decision_run_id=decision_id,
                candidate_code="final",
                action_code="KEEP",
                training_type_code="STRENGTH",
                body_focus_code=None,
                requested_duration_minutes=10,
                duration_adjustment_source_code="PROFILE",
                estimated_duration_seconds=600,
                estimated_calories_burned=None,
                setup_seconds=0,
                warmup_seconds=60,
                cooldown_seconds=60,
                goal_tags=[],
                duration_rule_version="duration-v1",
                selected=True,
                created_at=NOW,
            )
        )
        session.add(
            PlanItem(
                id=plan_item_id,
                plan_candidate_id=candidate_id,
                exercise_id=uuid4(),
                sequence=1,
                phase_code="MAIN",
                tier_code="CORE",
                sets=1,
                reps=10,
                work_seconds_per_set=None,
                rest_seconds_per_set=0,
                work_seconds=480,
                rest_seconds=0,
                transition_seconds=0,
                intensity_code="LOW",
                instruction_content_version="instruction-v1",
                display_name="테스트 운동",
            )
        )
        session.add(
            SafetyReview(
                id=uuid4(),
                decision_run_id=decision_id,
                plan_candidate_id=candidate_id,
                safety_status_code="PASS",
                vetoed=False,
                ruleset_version="safety-v1",
                reason_codes=[],
                excluded_exercise_ids=[],
                public_guidance=None,
            )
        )
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

        repository = WorkoutRepository()
        source = repository.get_selection_source(session, user_id, decision_id, option_id)
        assert source is not None
        selection_id = uuid4()
        workout_session_id = uuid4()
        repository.create_selection(
            session,
            source=source,
            user_id=user_id,
            selection_id=selection_id,
            workout_session_id=workout_session_id,
            idempotency_key=uuid4(),
            now=NOW,
        )
        assert not repository.is_pressure_notification_suppressed(
            session, user_id, date(2026, 8, 14)
        )
        selection = session.get(DecisionSelection, selection_id)
        assert selection is not None
        selection.selected_action_code = "REST"
        session.flush()
        assert repository.is_pressure_notification_suppressed(session, user_id, date(2026, 8, 14))
        selection.selected_action_code = "KEEP"
        session.flush()
        state = repository.start_session(session, workout_session_id, NOW)
        assert state.status_code == "IN_PROGRESS"
        assert state.items == ((plan_item_id, "PENDING", None),)

        repository.create_timer_event(
            session,
            event_id=uuid4(),
            session_id=workout_session_id,
            event_code="END",
            occurred_at=NOW,
            client_recorded_at=NOW,
            now=NOW,
        )
        repository.create_additional_activity(
            session,
            activity_id=uuid4(),
            session_id=workout_session_id,
            activity_type_code="WALKING",
            duration_seconds=600,
            intensity_code="LOW",
            note=None,
            now=NOW,
        )
        unchanged = repository.get_session_state(session, user_id, workout_session_id)
        assert unchanged is not None
        assert unchanged.status_code == state.status_code
        assert unchanged.items == state.items

        updated = repository.update_session_item(
            session, workout_session_id, plan_item_id, "COMPLETED", NOW
        )
        assert updated is not None
        assert updated.status_code == "IN_PROGRESS"
        assert updated.items[0][1] == "COMPLETED"

        repository.finish_session(
            session,
            session_id=workout_session_id,
            status_code="COMPLETED",
            ended_at=NOW,
            actual_elapsed_seconds=0,
        )
        completed_history = repository.get_return_history(session, user_id, date(2026, 8, 15))
        assert completed_history.last_completed_local_date == date(2026, 8, 14)
        assert completed_history.not_completed_history_count == 0

        repository.create_feedback(
            session,
            session_id=workout_session_id,
            difficulty_code="APPROPRIATE",
            fatigue_code="MODERATE",
            satisfaction_code="SATISFIED",
            pain_occurred=False,
            discomforts=(),
            adverse_reaction_codes=(),
            difficulty_reason_codes=(),
            now=NOW,
        )
        assert repository.feedback_exists(session, workout_session_id)

        repository.finish_session(
            session,
            session_id=workout_session_id,
            status_code="NOT_COMPLETED",
            ended_at=NOW,
            actual_elapsed_seconds=None,
        )
        repository.create_skip_feedback(
            session,
            session_id=workout_session_id,
            reason_code="TIME_SHORTAGE",
            now=NOW,
        )
        missed_history = repository.get_return_history(session, user_id, date(2026, 8, 15))
        assert missed_history.last_completed_local_date is None
        assert missed_history.not_completed_history_count == 1

        repository.create_safety_event(
            session,
            event_id=uuid4(),
            session_id=workout_session_id,
            occurred_at=NOW,
            instruction_code="STOP_AND_SEEK_HELP",
            resulting_action_code="STOP_AND_SEEK_HELP",
            session_status_code="STOPPED_FOR_SAFETY",
            guidance_code="SERIOUS_ADVERSE_REACTION_STOP",
            reason_code="EMERGENCY_ADVERSE_REACTION",
            rule_version="1.0.0",
            discomforts=(),
            adverse_reaction_codes=("CHEST_DISCOMFORT",),
            now=NOW,
        )
        assert repository.is_pressure_notification_suppressed(session, user_id, date(2026, 8, 14))


@pytest.fixture
def postgres_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    test_database_url = os.getenv("TEST_DATABASE_URL", "")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not (make_url(test_database_url).database or "").endswith("_test"):
        pytest.fail("Workout repository tests require a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    config = Config(str(ALEMBIC_CONFIG))
    config.set_main_option("sqlalchemy.url", test_database_url)
    command.upgrade(config, "head")

    engine = create_engine(test_database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        with session.begin():
            seed_catalog(session, NOW)
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def _add_postgres_user(session: Session) -> UUID:
    user_id = uuid4()
    with session.begin():
        session.add(
            User(
                id=user_id,
                status_code="ACTIVE",
                code_set_version="identity-mvp-v1",
                last_active_at=NOW,
                ai_trial_started_at=NOW,
                ai_trial_ends_at=datetime(2026, 8, 21, 1, 0, tzinfo=UTC),
                premium_status_code="NOT_AVAILABLE",
            )
        )
        session.add(
            UserProfile(
                user_id=user_id,
                protected_birthdate="synthetic-protected-value",
                nickname="합성 사용자",
                primary_goal_code="GENERAL_FITNESS",
                experience_level_code="BEGINNER",
                timezone="Asia/Seoul",
                preferred_location_code="HOME",
                default_requested_duration_minutes=30,
                desired_weekly_workout_count=3,
                coaching_style_code="SUPPORTIVE",
                height_cm=175.0,
                weight_kg=70.0,
                sex_code="PREFER_NOT_TO_SAY",
                code_set_version="profile-mvp-v1",
                profile_version=1,
            )
        )
        session.add(UserAvailableLocation(user_id=user_id, location_code="HOME"))
        session.add_all(
            UserEquipment(user_id=user_id, equipment_code=code)
            for code in ("BODYWEIGHT", "MAT", "RESISTANCE_BAND")
        )
    return user_id


def _prepare_context(session: Session, user_id: UUID) -> UUID:
    RoutineService(RoutineRepository(), clock=lambda: NOW).create(
        session,
        user_id,
        RoutineCreateRequest(effective_from=date(2026, 8, 14), goal_code="GENERAL_FITNESS"),
        uuid4(),
    )
    context = DailyContextService(DailyContextRepository(), clock=lambda: NOW).replace(
        session,
        user_id,
        date(2026, 8, 14),
        DailyContextUpsertRequest.model_validate(
            {
                "fatigue_level_code": "LOW",
                "requested_duration_minutes": 30,
                "duration_adjustment_source_code": "PROFILE",
                "location_code": "HOME",
                "discomforts": [],
                "adverse_reaction_codes": [],
            }
        ),
        uuid4(),
        None,
    )
    return context.id


def _create_workout_session(
    session: Session,
    user_id: UUID,
    context_id: UUID,
    context_version: int = 1,
) -> UUID:
    decision = DecisionService(DecisionRepository(), clock=lambda: NOW).create(
        session,
        user_id,
        DecisionCreateRequest(
            local_date=date(2026, 8, 14),
            daily_context_id=context_id,
            expected_context_version=context_version,
        ),
        uuid4(),
    )
    option = next(value for value in decision.options if value.option_code == "FINAL_ROUTINE")
    selection = WorkoutService(WorkoutRepository(), clock=lambda: NOW).select_decision(
        session,
        user_id,
        decision.decision_id,
        DecisionSelectionRequest(option_id=option.option_id),
        uuid4(),
    )
    assert selection.workout_session is not None
    return selection.workout_session.session_id


@pytest.mark.integration
def test_postgresql_workout_log_reads_are_owner_scoped_and_stably_paginated(
    postgres_session: Session,
) -> None:
    owner_id = _add_postgres_user(postgres_session)
    other_id = _add_postgres_user(postgres_session)
    owner_context_id = _prepare_context(postgres_session, owner_id)
    other_context_id = _prepare_context(postgres_session, other_id)
    owner_session_ids: list[UUID] = []
    owner_context_version = 1
    for _ in range(3):
        if owner_session_ids:
            updated_context = DailyContextService(
                DailyContextRepository(), clock=lambda: NOW
            ).replace(
                postgres_session,
                owner_id,
                date(2026, 8, 14),
                DailyContextUpsertRequest.model_validate(
                    {
                        "fatigue_level_code": "LOW",
                        "requested_duration_minutes": 30,
                        "duration_adjustment_source_code": "PROFILE",
                        "location_code": "HOME",
                        "discomforts": [],
                        "adverse_reaction_codes": [],
                    }
                ),
                uuid4(),
                owner_context_version,
            )
            owner_context_id = updated_context.id
            owner_context_version = updated_context.context_version
        owner_session_ids.append(
            _create_workout_session(
                postgres_session,
                owner_id,
                owner_context_id,
                owner_context_version,
            )
        )
    owner_session_ids = tuple(owner_session_ids)
    other_session_id = _create_workout_session(postgres_session, other_id, other_context_id)

    with postgres_session.begin():
        for index, session_id in enumerate(owner_session_ids):
            workout = postgres_session.get(WorkoutSession, session_id)
            assert workout is not None
            selection = postgres_session.get(DecisionSelection, workout.decision_selection_id)
            assert selection is not None
            decision = postgres_session.get(DecisionRun, selection.decision_run_id)
            assert decision is not None
            decision.local_date = date(2026, 8, 14) if index < 2 else date(2026, 8, 13)
            workout.started_at = NOW
            workout.ended_at = NOW
            workout.status_code = ("COMPLETED", "PARTIAL", "NOT_COMPLETED")[index]
            items = (
                postgres_session.query(WorkoutSessionItem)
                .filter(WorkoutSessionItem.workout_session_id == session_id)
                .all()
            )
            completed_items = len(items) if index == 0 else int(index == 1)
            for item in items[:completed_items]:
                item.status_code = "COMPLETED"
                item.completed_at = NOW
            if index == 0:
                postgres_session.add(
                    WorkoutFeedback(
                        workout_session_id=session_id,
                        difficulty_code="APPROPRIATE",
                        fatigue_code="MODERATE",
                        satisfaction_code="SATISFIED",
                        pain_occurred=True,
                        created_at=NOW,
                    )
                )
            if index == 2:
                postgres_session.add(
                    WorkoutSkipFeedback(
                        workout_session_id=session_id,
                        reason_code="TIME_SHORTAGE",
                        created_at=NOW,
                    )
                )

    repository = WorkoutRepository()
    first_page = repository.list_workout_logs(
        postgres_session,
        owner_id,
        from_local_date=None,
        to_local_date=None,
        status_code=None,
        cursor=None,
        limit=2,
    )
    assert len(first_page) == 2
    second_page = repository.list_workout_logs(
        postgres_session,
        owner_id,
        from_local_date=None,
        to_local_date=None,
        status_code=None,
        cursor=WorkoutLogCursor(first_page[-1].local_date, first_page[-1].session_id),
        limit=2,
    )
    returned_ids = {item.session_id for item in (*first_page, *second_page)}
    assert returned_ids == set(owner_session_ids)
    assert other_session_id not in returned_ids

    filtered = repository.list_workout_logs(
        postgres_session,
        owner_id,
        from_local_date=date(2026, 8, 14),
        to_local_date=date(2026, 8, 14),
        status_code="COMPLETED",
        cursor=None,
        limit=100,
    )
    assert len(filtered) == 1
    assert filtered[0].completed_item_count == filtered[0].total_item_count

    detail = repository.get_workout_log_detail(postgres_session, owner_id, filtered[0].session_id)
    assert detail is not None
    assert detail.items
    assert detail.items[0].exercise_name
    assert detail.feedback is not None
    assert detail.feedback.perceived_difficulty_code == "APPROPRIATE"
    assert detail.feedback.post_workout_discomfort_reported is True
    assert (
        repository.get_workout_log_detail(postgres_session, other_id, filtered[0].session_id)
        is None
    )
    assert repository.get_workout_log_detail(postgres_session, owner_id, uuid4()) is None
