from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db import models as db_models
from backend.app.db.base import Base
from backend.app.db.models.decision import DecisionRun
from backend.app.db.models.profile import MutationIdempotencyRecord, UserProfile
from backend.app.db.models.weekly_report import UserWeek, WeeklyReport
from backend.app.db.models.workout import (
    DecisionSelection,
    WorkoutFeedback,
    WorkoutSafetyEvent,
    WorkoutSession,
    WorkoutSessionItem,
    WorkoutSkipFeedback,
)
from backend.app.db.repositories.weekly_report import WeeklyReportRepository
from backend.app.modules.profiles.codes import PROFILE_CODE_SET_VERSION
from backend.app.modules.weekly_reports.ports import ReportValues
from backend.app.modules.weekly_reports.schemas import WeeklyReportResponse

_ = db_models
NOW = datetime(2026, 8, 10, 0, 0, tzinfo=UTC)
WEEK_START = date(2026, 8, 3)
WEEK_END = date(2026, 8, 9)


def _decision(user_id, local_date: date) -> DecisionRun:
    return DecisionRun(
        id=uuid4(),
        user_id=user_id,
        local_date=local_date,
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


def test_repository_round_trip_preserves_week_snapshot_and_block_evidence() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            UserProfile.__table__,
            MutationIdempotencyRecord.__table__,
            DecisionRun.__table__,
            DecisionSelection.__table__,
            WorkoutSession.__table__,
            WorkoutSessionItem.__table__,
            WorkoutSafetyEvent.__table__,
            WorkoutFeedback.__table__,
            WorkoutSkipFeedback.__table__,
            UserWeek.__table__,
            WeeklyReport.__table__,
        ],
    )
    user_id = uuid4()
    completed_run = _decision(user_id, WEEK_START)
    missed_run = _decision(user_id, WEEK_START.replace(day=5))
    completed_selection_id = uuid4()
    missed_selection_id = uuid4()
    completed_session_id = uuid4()
    missed_session_id = uuid4()
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(
            UserProfile(
                user_id=user_id,
                protected_birthdate="encrypted",
                nickname="tester",
                primary_goal_code="GENERAL_FITNESS",
                experience_level_code="BEGINNER",
                timezone="Asia/Seoul",
                preferred_location_code="HOME",
                default_requested_duration_minutes=30,
                desired_weekly_workout_count=3,
                coaching_style_code="SUPPORTIVE",
                height_cm=None,
                weight_kg=None,
                sex_code=None,
                code_set_version=PROFILE_CODE_SET_VERSION,
                profile_version=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add_all([completed_run, missed_run])
        session.add_all(
            [
                DecisionSelection(
                    id=completed_selection_id,
                    decision_run_id=completed_run.id,
                    decision_option_id=uuid4(),
                    selected_action_code="KEEP",
                    idempotency_key=uuid4(),
                    selected_at=NOW,
                ),
                DecisionSelection(
                    id=missed_selection_id,
                    decision_run_id=missed_run.id,
                    decision_option_id=uuid4(),
                    selected_action_code="DOWNSHIFT",
                    idempotency_key=uuid4(),
                    selected_at=NOW,
                ),
            ]
        )
        session.add_all(
            [
                WorkoutSession(
                    id=completed_session_id,
                    user_id=user_id,
                    decision_selection_id=completed_selection_id,
                    plan_candidate_id=uuid4(),
                    scheduled_workout_id=None,
                    status_code="COMPLETED",
                    started_at=NOW,
                    ended_at=NOW,
                    actual_elapsed_seconds=9999,
                    estimated_calories_burned=None,
                    idempotency_key=uuid4(),
                    created_at=NOW,
                ),
                WorkoutSession(
                    id=missed_session_id,
                    user_id=user_id,
                    decision_selection_id=missed_selection_id,
                    plan_candidate_id=uuid4(),
                    scheduled_workout_id=None,
                    status_code="NOT_COMPLETED",
                    started_at=None,
                    ended_at=NOW,
                    actual_elapsed_seconds=None,
                    estimated_calories_burned=None,
                    idempotency_key=uuid4(),
                    created_at=NOW,
                ),
            ]
        )
        session.add_all(
            [
                WorkoutSessionItem(
                    id=uuid4(),
                    workout_session_id=completed_session_id,
                    plan_item_id=uuid4(),
                    status_code="COMPLETED",
                    completed_at=NOW,
                    updated_at=NOW,
                ),
                WorkoutSessionItem(
                    id=uuid4(),
                    workout_session_id=missed_session_id,
                    plan_item_id=uuid4(),
                    status_code="PENDING",
                    completed_at=None,
                    updated_at=NOW,
                ),
                WorkoutSkipFeedback(
                    workout_session_id=missed_session_id,
                    reason_code="TIME_SHORTAGE",
                    created_at=NOW,
                ),
            ]
        )
        session.flush()

        repository = WeeklyReportRepository()
        profile = repository.get_week_profile(session, user_id, WEEK_START)
        assert profile is not None
        assert profile.timezone == "Asia/Seoul"
        assert profile.target_workout_count == 3

        week = repository.create_week(
            session,
            week_id=uuid4(),
            user_id=user_id,
            week_start=WEEK_START,
            week_end=WEEK_END,
            timezone=profile.timezone,
            target_workout_count=profile.target_workout_count,
            plan_origin_code="COLD_START",
            cold_start_applied=True,
            status_code="CLOSED",
            closed_at=NOW,
            now=NOW,
        )
        evidence = repository.get_week_evidence(session, user_id, WEEK_START, WEEK_END)
        assert [row.stored_status_code for row in evidence] == ["COMPLETED", "NOT_COMPLETED"]
        assert evidence[0].block_status_codes == ("COMPLETED",)
        assert evidence[1].not_completed_reason_code == "TIME_SHORTAGE"

        report_id = uuid4()
        stored = repository.create_report(
            session,
            week=week,
            values=ReportValues(
                report_id=report_id,
                input_schema_version="weekly-report-input-v1",
                input_snapshot={"counts": {"completed": 1, "not_completed": 1}},
                input_hash="a" * 64,
                completed_count=1,
                partial_count=0,
                not_completed_count=1,
                stopped_for_safety=0,
                primary_miss_reason_code="TIME_SHORTAGE",
                completion_rate=1 / 3,
                persistence_rate=1 / 3,
                negotiation_success_rate=0.0,
                weekday_failure_summary={"WEDNESDAY": {"not_completed": 1}},
                high_completion_windows=[],
                pattern_summary={
                    "high_completion_windows": [],
                    "high_completion_exercise_types": [],
                    "high_completion_intensity_codes": [],
                    "blocker_reason_codes": ["TIME_SHORTAGE"],
                },
                decision_summary="block-based",
                adjustment_direction_code="MIXED",
                next_action="next",
                agent_summaries=None,
                summary="summary",
                report_policy_version="weekly-report-policy-v1",
                generated_at=NOW,
            ),
        )
        assert stored.input_hash == "a" * 64
        assert stored.response_payload["counts"]["completed"] == 1
        fetched = repository.get_report_by_id(session, user_id, report_id)
        assert fetched is not None
        assert fetched.input_hash == stored.input_hash
        assert fetched.response_payload["report_id"] == report_id
        assert fetched.response_payload["status_code"] == "GENERATED"

        acknowledged = repository.acknowledge_report(
            session,
            user_id=user_id,
            report_id=report_id,
            acknowledged_at=NOW,
        )
        assert acknowledged is not None
        assert acknowledged.response_payload["status_code"] == "ACKNOWLEDGED"

        key = uuid4()
        repository.save_idempotency_record(
            session,
            user_id=user_id,
            endpoint_code="POST_WEEKLY_REPORT",
            key=key,
            request_hash="b" * 64,
            response_payload=WeeklyReportResponse.model_validate(
                stored.response_payload
            ).model_dump(mode="json"),
            now=NOW,
        )
        replay = repository.get_idempotency_record(session, user_id, "POST_WEEKLY_REPORT", key)
        assert replay is not None
        assert replay.request_hash == "b" * 64
