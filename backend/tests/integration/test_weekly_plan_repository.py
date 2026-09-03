from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db import models as db_models
from backend.app.db.base import Base
from backend.app.db.models.catalog import ExerciseEquipment, ExerciseLocation
from backend.app.db.models.decision import DecisionRun, SafetyReview
from backend.app.db.models.profile import (
    MutationIdempotencyRecord,
    UserAvailableLocation,
    UserEquipment,
    UserProfile,
)
from backend.app.db.models.routine import Routine, RoutineDay, RoutineItem
from backend.app.db.models.weekly_report import UserWeek, WeeklyPlanRevision, WeeklyReport
from backend.app.db.repositories.weekly_plan import WeeklyPlanRepository
from backend.app.modules.profiles.codes import PROFILE_CODE_SET_VERSION
from backend.app.modules.weekly_plans.ports import PlanRevisionValues

_ = db_models
NOW = datetime(2026, 8, 17, 0, 0, tzinfo=UTC)
WEEK_START = date(2026, 8, 17)


def test_repository_resolves_report_routine_constraints_and_revision_sequence() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            UserProfile.__table__,
            UserAvailableLocation.__table__,
            UserEquipment.__table__,
            MutationIdempotencyRecord.__table__,
            DecisionRun.__table__,
            SafetyReview.__table__,
            Routine.__table__,
            RoutineDay.__table__,
            RoutineItem.__table__,
            ExerciseLocation.__table__,
            ExerciseEquipment.__table__,
            UserWeek.__table__,
            WeeklyReport.__table__,
            WeeklyPlanRevision.__table__,
        ],
    )
    user_id = uuid4()
    routine_id = uuid4()
    exercise_id = uuid4()
    prior_week_id = uuid4()
    target_week_id = uuid4()
    report_id = uuid4()
    safety_excluded_id = uuid4()
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(
            UserProfile(
                user_id=user_id,
                protected_birthdate="synthetic-protected-value",
                nickname="synthetic-user",
                primary_goal_code="GENERAL_FITNESS",
                experience_level_code="BEGINNER",
                timezone="Asia/Seoul",
                preferred_location_code="HOME",
                default_requested_duration_minutes=40,
                desired_weekly_workout_count=4,
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
        session.add_all(
            [
                UserAvailableLocation(user_id=user_id, location_code="HOME"),
                UserEquipment(user_id=user_id, equipment_code="MAT"),
            ]
        )
        session.add(
            Routine(
                id=routine_id,
                user_id=user_id,
                version=3,
                goal_code="GENERAL_FITNESS",
                status_code="ACTIVE",
                effective_from=WEEK_START,
                effective_to=None,
                catalog_version_id=uuid4(),
                created_at=NOW,
                days=[
                    RoutineDay(
                        id=uuid4(),
                        sequence=1,
                        schedule_rule="ROTATION",
                        title="synthetic routine",
                        training_type_code="STRENGTH",
                        body_focus_code=None,
                        requested_duration_minutes=40,
                        estimated_duration_seconds=2400,
                        setup_seconds=0,
                        estimated_calories_burned=None,
                        items=[
                            RoutineItem(
                                id=uuid4(),
                                exercise_id=exercise_id,
                                sequence=1,
                                phase_code="MAIN",
                                tier_code="CORE",
                                sets=1,
                                reps=None,
                                work_seconds_per_set=2400,
                                rest_seconds_per_set=0,
                                intensity_code="LOW",
                            )
                        ],
                    )
                ],
            )
        )
        session.add_all(
            [
                ExerciseLocation(exercise_id=exercise_id, location_code="HOME"),
                ExerciseEquipment(
                    exercise_id=exercise_id,
                    equipment_code="MAT",
                    requirement_code="REQUIRED",
                ),
            ]
        )
        decision_id = uuid4()
        session.add(
            DecisionRun(
                id=decision_id,
                user_id=user_id,
                local_date=WEEK_START - timedelta(days=2),
                daily_context_id=uuid4(),
                daily_context_version=1,
                base_routine_id=routine_id,
                input_schema_version="decision-input-v1",
                input_snapshot={},
                input_hash="e" * 64,
                catalog_version_id=uuid4(),
                policy_version_id=uuid4(),
                safety_rule_version="safety-v1",
                duration_rule_version="duration-v1",
                graph_version="graph-v1",
                coordinator_version="coordinator-v1",
                status_code="COMPLETED",
                safety_status_code="REVISE",
                recommended_action_code="CHANGE",
                coordinator_result={},
                failure_code=None,
                created_at=NOW - timedelta(days=2),
                completed_at=NOW - timedelta(days=2),
            )
        )
        session.add(
            SafetyReview(
                id=uuid4(),
                decision_run_id=decision_id,
                plan_candidate_id=uuid4(),
                safety_status_code="REVISE",
                vetoed=False,
                ruleset_version="safety-v1",
                reason_codes=["EXCLUDE_CONFLICT"],
                excluded_exercise_ids=[str(safety_excluded_id)],
                public_guidance=None,
            )
        )
        session.add_all(
            [
                UserWeek(
                    id=prior_week_id,
                    user_id=user_id,
                    week_start_local_date=WEEK_START - timedelta(days=7),
                    week_end_local_date=WEEK_START - timedelta(days=1),
                    timezone="Asia/Seoul",
                    target_workout_count=4,
                    plan_origin_code="COLD_START",
                    cold_start_applied=True,
                    status_code="CLOSED",
                    closed_at=NOW - timedelta(days=7),
                    created_at=NOW - timedelta(days=14),
                ),
                UserWeek(
                    id=target_week_id,
                    user_id=user_id,
                    week_start_local_date=WEEK_START,
                    week_end_local_date=WEEK_START + timedelta(days=6),
                    timezone="Asia/Seoul",
                    target_workout_count=4,
                    plan_origin_code="WEEKLY_REPORT",
                    cold_start_applied=False,
                    status_code="OPEN",
                    closed_at=None,
                    created_at=NOW,
                ),
            ]
        )
        session.add(
            WeeklyReport(
                id=report_id,
                user_week_id=prior_week_id,
                status_code="ACKNOWLEDGED",
                input_schema_version="weekly-report-input-v1",
                input_snapshot={},
                input_hash="a" * 64,
                completed_count=3,
                partial_count=1,
                not_completed_count=0,
                stopped_for_safety=0,
                safety_stopped_session_count=0,
                primary_miss_reason_code=None,
                completion_rate=0.75,
                persistence_rate=1.0,
                negotiation_success_rate=None,
                weekday_failure_summary={},
                high_completion_windows=[],
                pattern_summary={},
                decision_summary="synthetic",
                adjustment_direction_code="MAINTAIN",
                next_action="synthetic",
                agent_summaries=None,
                summary="synthetic",
                report_policy_version="weekly-report-policy-v1",
                generated_at=NOW - timedelta(days=7),
                acknowledged_at=NOW - timedelta(days=6),
            )
        )
        session.flush()

        repository = WeeklyPlanRepository()
        context = repository.get_plan_context(session, user_id, target_week_id, WEEK_START)
        assert context is not None
        assert context.is_first_user_week is False
        assert context.source_weekly_report_id == report_id
        assert context.previous_report_status_code == "ACKNOWLEDGED"
        assert context.current_routine_id == routine_id
        assert context.allowed_location_codes == ("HOME",)
        assert context.available_equipment_codes == ("MAT",)
        assert context.safety_status_code == "REVISE"
        assert context.safety_opinion_codes == ("EXCLUDE_CONFLICT",)
        assert context.excluded_exercise_ids == (safety_excluded_id,)

        evidence = repository.get_routine_evidence(session, user_id, routine_id)
        assert evidence is not None
        assert evidence.routine_version == 3
        assert evidence.requested_duration_minutes == 40
        assert evidence.supported_location_codes == ("HOME",)
        assert evidence.required_equipment_codes == ("MAT",)

        revision_id = uuid4()
        values = PlanRevisionValues(
            revision_id=revision_id,
            target_user_week_id=target_week_id,
            source_weekly_report_id=report_id,
            revision_sequence=1,
            ai_revision_number=None,
            revision_source_code="INITIAL",
            routine_id=routine_id,
            selected_location_code="HOME",
            safety_status_code="PASS",
            input_schema_version="weekly-plan-input-v1",
            input_snapshot={"synthetic": True},
            input_hash="b" * 64,
            weekly_plan_policy_version="1.0.0",
            revision_reason_codes=["REVISION_ALLOWED"],
            finalization_reason_codes=["FINALIZE_ALLOWED"],
            finalized_at=NOW,
            created_at=NOW,
        )
        repository.create_revision(session, values)
        latest = repository.get_latest_revision(session, target_week_id)
        assert latest is not None
        assert latest.revision_id == revision_id
        assert latest.revision_sequence == 1
        assert latest.successful_ai_revision_count == 0

        blocked_values = PlanRevisionValues(
            revision_id=uuid4(),
            target_user_week_id=target_week_id,
            source_weekly_report_id=report_id,
            revision_sequence=2,
            ai_revision_number=None,
            revision_source_code="AI",
            routine_id=None,
            selected_location_code=None,
            safety_status_code="BLOCKED",
            input_schema_version="weekly-plan-input-v1",
            input_snapshot={"synthetic": "blocked"},
            input_hash="d" * 64,
            weekly_plan_policy_version="1.0.0",
            revision_reason_codes=["REVISION_ALLOWED"],
            finalization_reason_codes=["REVISION_STATUS_BLOCKS_FINALIZE"],
            finalized_at=None,
            created_at=NOW,
        )
        repository.create_revision(session, blocked_values)
        latest = repository.get_latest_revision(session, target_week_id)
        assert latest is not None
        assert latest.revision_sequence == 2
        assert latest.successful_ai_revision_count == 0

        key = uuid4()
        repository.save_idempotency_record(
            session,
            user_id=user_id,
            endpoint_code="POST_WEEKLY_PLAN",
            key=key,
            request_hash="c" * 64,
            response_payload={"revision_id": str(revision_id)},
            now=NOW,
        )
        replay = repository.get_idempotency_record(session, user_id, "POST_WEEKLY_PLAN", key)
        assert replay is not None
        assert replay.request_hash == "c" * 64
