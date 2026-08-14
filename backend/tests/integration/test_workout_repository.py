from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import create_engine
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
from backend.app.db.repositories.workout import WorkoutRepository

_ = db_models
NOW = datetime(2026, 8, 14, 1, 0, tzinfo=UTC)


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
