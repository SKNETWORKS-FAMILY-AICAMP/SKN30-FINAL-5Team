from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class ScheduledWorkout(Base):
    __tablename__ = "scheduled_workouts"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "scheduled_local_date",
            "routine_day_id",
            name="uq_scheduled_workouts_user_date_day",
        ),
        CheckConstraint(
            "status_code IN ('SCHEDULED','STARTED','COMPLETED','PARTIAL',"
            "'NOT_COMPLETED','REST_SELECTED')",
            name="ck_scheduled_workouts_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    routine_day_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("routine_days.id", ondelete="RESTRICT"), nullable=False
    )
    scheduled_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    status_code: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DecisionSelection(Base):
    __tablename__ = "decision_selections"
    __table_args__ = (
        CheckConstraint(
            "selected_action_code IN ('KEEP','DOWNSHIFT','CHANGE','RECOVERY','REST')",
            name="ck_decision_selections_action",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("decision_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    decision_option_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_options.id", ondelete="RESTRICT"), nullable=False
    )
    selected_action_code: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"
    __table_args__ = (
        CheckConstraint(
            "status_code IN ('PLANNED','IN_PROGRESS','COMPLETED','PARTIAL',"
            "'NOT_COMPLETED','STOPPED_FOR_SAFETY')",
            name="ck_workout_sessions_status",
        ),
        CheckConstraint(
            "actual_elapsed_seconds IS NULL OR actual_elapsed_seconds >= 0",
            name="ck_workout_sessions_elapsed_nonnegative",
        ),
        CheckConstraint(
            "estimated_calories_burned IS NULL OR estimated_calories_burned >= 0",
            name="ck_workout_sessions_calories_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision_selection_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("decision_selections.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    plan_candidate_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("plan_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    scheduled_workout_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("scheduled_workouts.id", ondelete="SET NULL"), nullable=True
    )
    status_code: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_elapsed_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_calories_burned: Mapped[float | None] = mapped_column(Float, nullable=True)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    items: Mapped[list["WorkoutSessionItem"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    safety_events: Mapped[list["WorkoutSafetyEvent"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class WorkoutSessionItem(Base):
    __tablename__ = "workout_session_items"
    __table_args__ = (
        UniqueConstraint(
            "workout_session_id", "plan_item_id", name="uq_workout_session_items_session_plan"
        ),
        CheckConstraint(
            "status_code IN ('PENDING','COMPLETED')",
            name="ck_workout_session_items_status",
        ),
        CheckConstraint(
            "(status_code = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status_code = 'PENDING' AND completed_at IS NULL)",
            name="ck_workout_session_items_completed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workout_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False
    )
    plan_item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("plan_items.id", ondelete="RESTRICT"), nullable=False
    )
    status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkoutTimerEvent(Base):
    __tablename__ = "workout_timer_events"
    __table_args__ = (
        CheckConstraint(
            "event_code IN ('START','PAUSE','RESUME','END')",
            name="ck_workout_timer_events_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workout_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_code: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    client_recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkoutAdditionalActivity(Base):
    __tablename__ = "workout_additional_activities"
    __table_args__ = (
        CheckConstraint("duration_seconds > 0", name="ck_workout_additional_duration_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workout_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    intensity_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkoutSafetyEvent(Base):
    __tablename__ = "workout_safety_events"
    __table_args__ = (
        CheckConstraint(
            "instruction_code IN ('SHOW_CAUTION','STOP_SESSION','STOP_AND_SEEK_HELP')",
            name="ck_workout_safety_events_instruction",
        ),
        CheckConstraint(
            "resulting_action_code IS NULL OR "
            "resulting_action_code IN ('REST','STOP_AND_SEEK_HELP')",
            name="ck_workout_safety_events_action",
        ),
        CheckConstraint(
            "guidance_code IN ('MILD_DISCOMFORT_CAUTION','MODERATE_DISCOMFORT_CAUTION',"
            "'SEVERE_OR_ACUTE_STOP','SERIOUS_ADVERSE_REACTION_STOP')",
            name="ck_workout_safety_events_guidance",
        ),
        CheckConstraint(
            "reason_code IN ('MILD_DISCOMFORT','MODERATE_DISCOMFORT','SEVERE_DISCOMFORT',"
            "'ACUTE_MUSCULOSKELETAL_REACTION','EMERGENCY_ADVERSE_REACTION')",
            name="ck_workout_safety_events_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workout_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instruction_code: Mapped[str] = mapped_column(String(32), nullable=False)
    resulting_action_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    guidance_code: Mapped[str] = mapped_column(String(48), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(48), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    discomforts: Mapped[list["WorkoutSafetyEventDiscomfort"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    adverse_reactions: Mapped[list["WorkoutSafetyEventAdverseReaction"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class WorkoutSafetyEventDiscomfort(Base):
    __tablename__ = "workout_safety_event_discomforts"
    __table_args__ = (
        UniqueConstraint(
            "workout_safety_event_id",
            "body_area_code",
            name="uq_workout_safety_event_discomfort_body",
        ),
        CheckConstraint(
            "severity_code IN ('MILD','MODERATE','SEVERE')",
            name="ck_workout_safety_event_discomfort_severity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workout_safety_event_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workout_safety_events.id", ondelete="CASCADE"), nullable=False
    )
    body_area_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("body_areas.code", ondelete="RESTRICT"), nullable=False
    )
    severity_code: Mapped[str] = mapped_column(String(16), nullable=False)


class WorkoutSafetyEventAdverseReaction(Base):
    __tablename__ = "workout_safety_event_adverse_reactions"

    workout_safety_event_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workout_safety_events.id", ondelete="CASCADE"), primary_key=True
    )
    reaction_code: Mapped[str] = mapped_column(String(80), primary_key=True)


class WorkoutFeedback(Base):
    __tablename__ = "workout_feedback"
    __table_args__ = (
        CheckConstraint(
            "difficulty_code IN ('EASY','APPROPRIATE','HARD')",
            name="ck_workout_feedback_difficulty",
        ),
    )

    workout_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workout_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    difficulty_code: Mapped[str] = mapped_column(String(16), nullable=False)
    fatigue_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    satisfaction_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pain_occurred: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    discomforts: Mapped[list["WorkoutFeedbackDiscomfort"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    adverse_reactions: Mapped[list["WorkoutFeedbackAdverseReaction"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    difficulty_reasons: Mapped[list["WorkoutFeedbackDifficultyReason"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class WorkoutFeedbackDifficultyReason(Base):
    """Why a `HARD` session felt hard; drives the next routine's adjustment axis.

    Typed rows rather than JSONB because the decision path reads and replays these
    (`DATA_MODEL.md` 10.4.1), and `AGENTS.md` 10 reserves JSONB for flexible proposal and
    metadata fields rather than queried decision inputs.
    """

    __tablename__ = "workout_feedback_difficulty_reasons"
    __table_args__ = (
        UniqueConstraint(
            "workout_session_id",
            "reason_code",
            name="uq_workout_feedback_difficulty_reason",
        ),
        CheckConstraint(
            "reason_code IN ('VOLUME_HIGH','MOVEMENT_DIFFICULT')",
            name="ck_workout_feedback_difficulty_reason_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workout_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workout_feedback.workout_session_id", ondelete="CASCADE"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkoutFeedbackDiscomfort(Base):
    __tablename__ = "workout_feedback_discomforts"
    __table_args__ = (
        UniqueConstraint(
            "workout_session_id", "body_area_code", name="uq_workout_feedback_discomfort_body"
        ),
        CheckConstraint(
            "severity_code IN ('MILD','MODERATE','SEVERE')",
            name="ck_workout_feedback_discomfort_severity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workout_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workout_feedback.workout_session_id", ondelete="CASCADE"), nullable=False
    )
    body_area_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("body_areas.code", ondelete="RESTRICT"), nullable=False
    )
    severity_code: Mapped[str] = mapped_column(String(16), nullable=False)


class WorkoutFeedbackAdverseReaction(Base):
    __tablename__ = "workout_feedback_adverse_reactions"

    workout_session_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workout_feedback.workout_session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    reaction_code: Mapped[str] = mapped_column(String(80), primary_key=True)


class WorkoutSkipFeedback(Base):
    __tablename__ = "workout_skip_feedback"
    __table_args__ = (
        CheckConstraint(
            "reason_code IN ('TIME_SHORTAGE','FATIGUE','MUSCLE_SORENESS','PAIN',"
            "'SCHEDULE_CHANGE','LOCATION_EQUIPMENT','WEATHER','DIFFICULTY',"
            "'LOW_INTEREST','LOW_MOTIVATION')",
            name="ck_workout_skip_feedback_reason",
        ),
    )

    workout_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workout_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    reason_code: Mapped[str] = mapped_column(String(48), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "DecisionSelection",
    "ScheduledWorkout",
    "WorkoutAdditionalActivity",
    "WorkoutFeedback",
    "WorkoutFeedbackAdverseReaction",
    "WorkoutFeedbackDiscomfort",
    "WorkoutSafetyEvent",
    "WorkoutSafetyEventAdverseReaction",
    "WorkoutSafetyEventDiscomfort",
    "WorkoutSession",
    "WorkoutSessionItem",
    "WorkoutSkipFeedback",
    "WorkoutTimerEvent",
]
