from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class UserWeek(Base):
    __tablename__ = "user_weeks"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start_local_date", name="uq_user_weeks_user_start"),
        CheckConstraint("target_workout_count BETWEEN 1 AND 7", name="ck_user_weeks_target_count"),
        CheckConstraint(
            "plan_origin_code IN ('COLD_START','WEEKLY_REPORT')",
            name="ck_user_weeks_plan_origin",
        ),
        CheckConstraint("status_code IN ('OPEN','CLOSED')", name="ck_user_weeks_status"),
        CheckConstraint(
            "(status_code = 'OPEN' AND closed_at IS NULL) OR "
            "(status_code = 'CLOSED' AND closed_at IS NOT NULL)",
            name="ck_user_weeks_closed_at",
        ),
        CheckConstraint(
            "(plan_origin_code = 'COLD_START' AND cold_start_applied) OR "
            "(plan_origin_code = 'WEEKLY_REPORT' AND NOT cold_start_applied)",
            name="ck_user_weeks_cold_start",
        ),
        Index("ix_user_weeks_user_status_start", "user_id", "status_code", "week_start_local_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    week_start_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    week_end_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    target_workout_count: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_origin_code: Mapped[str] = mapped_column(String(24), nullable=False)
    cold_start_applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    report: Mapped["WeeklyReport | None"] = relationship(
        back_populates="user_week", uselist=False, cascade="all, delete-orphan"
    )
    plan_revisions: Mapped[list["WeeklyPlanRevision"]] = relationship(
        back_populates="target_user_week", cascade="all, delete-orphan"
    )


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"
    __table_args__ = (
        CheckConstraint(
            "status_code IN ('GENERATED','ACKNOWLEDGED','FAILED')",
            name="ck_weekly_reports_status",
        ),
        CheckConstraint(
            "adjustment_direction_code IN ('MAINTAIN','REDUCE','INCREASE','MIXED')",
            name="ck_weekly_reports_adjustment_direction",
        ),
        CheckConstraint(
            "completed_count >= 0 AND partial_count >= 0 AND not_completed_count >= 0 "
            "AND stopped_for_safety >= 0",
            name="ck_weekly_reports_counts_nonnegative",
        ),
        CheckConstraint(
            "completion_rate BETWEEN 0 AND 1", name="ck_weekly_reports_completion_rate"
        ),
        CheckConstraint(
            "persistence_rate BETWEEN 0 AND 1", name="ck_weekly_reports_persistence_rate"
        ),
        CheckConstraint(
            "negotiation_success_rate IS NULL OR negotiation_success_rate BETWEEN 0 AND 1",
            name="ck_weekly_reports_negotiation_rate",
        ),
        CheckConstraint(
            "(status_code = 'ACKNOWLEDGED' AND acknowledged_at IS NOT NULL) OR "
            "(status_code IN ('GENERATED','FAILED') AND acknowledged_at IS NULL)",
            name="ck_weekly_reports_acknowledged_at",
        ),
        UniqueConstraint("user_week_id", "input_hash", name="uq_weekly_reports_week_hash"),
        Index("ix_weekly_reports_user_week_status", "user_week_id", "status_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_week_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user_weeks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status_code: Mapped[str] = mapped_column(String(24), nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(48), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_TYPE, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    partial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    not_completed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # Legacy count from the single-status era, still written for read compatibility.
    stopped_for_safety: Mapped[int] = mapped_column(Integer, nullable=False)
    # Sessions whose execution state ended at STOPPED_SAFETY, under the split axes P1-C
    # introduced. Separate from the official completion counts above.
    safety_stopped_session_count: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_miss_reason_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    completion_rate: Mapped[float] = mapped_column(Float, nullable=False)
    persistence_rate: Mapped[float] = mapped_column(Float, nullable=False)
    negotiation_success_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    weekday_failure_summary: Mapped[dict[str, Any]] = mapped_column(_JSON_TYPE, nullable=False)
    high_completion_windows: Mapped[list[Any]] = mapped_column(_JSON_TYPE, nullable=False)
    pattern_summary: Mapped[dict[str, Any]] = mapped_column(_JSON_TYPE, nullable=False)
    decision_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    adjustment_direction_code: Mapped[str] = mapped_column(String(16), nullable=False)
    next_action: Mapped[str] = mapped_column(String(500), nullable=False)
    agent_summaries: Mapped[dict[str, Any] | None] = mapped_column(_JSON_TYPE, nullable=True)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    report_policy_version: Mapped[str] = mapped_column(String(48), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user_week: Mapped[UserWeek] = relationship(back_populates="report")
    sourced_plan_revisions: Mapped[list["WeeklyPlanRevision"]] = relationship(
        back_populates="source_weekly_report"
    )


class WeeklyPlanRevision(Base):
    __tablename__ = "weekly_plan_revisions"
    __table_args__ = (
        UniqueConstraint(
            "target_user_week_id",
            "revision_sequence",
            name="uq_weekly_plan_revisions_week_sequence",
        ),
        UniqueConstraint(
            "target_user_week_id",
            "ai_revision_number",
            name="uq_weekly_plan_revisions_week_ai_number",
        ),
        CheckConstraint("revision_sequence > 0", name="ck_weekly_plan_revisions_sequence"),
        CheckConstraint(
            "(revision_source_code = 'AI' AND "
            "((safety_status_code IN ('PASS','REVISE') AND ai_revision_number IN (1, 2)) OR "
            "(safety_status_code IN ('NEEDS_INPUT','BLOCKED','FAILED') "
            "AND ai_revision_number IS NULL))) OR "
            "(revision_source_code IN ('INITIAL', 'USER') AND ai_revision_number IS NULL)",
            name="ck_weekly_plan_revisions_source_ai_number",
        ),
        CheckConstraint(
            "safety_status_code IN ('PASS','NEEDS_INPUT','REVISE','BLOCKED','FAILED')",
            name="ck_weekly_plan_revisions_safety_status",
        ),
        CheckConstraint(
            "(safety_status_code IN ('PASS','REVISE') AND routine_id IS NOT NULL "
            "AND selected_location_code IS NOT NULL) OR "
            "(safety_status_code IN ('NEEDS_INPUT','BLOCKED','FAILED') AND routine_id IS NULL "
            "AND selected_location_code IS NULL)",
            name="ck_weekly_plan_revisions_routine_status",
        ),
        CheckConstraint(
            "finalized_at IS NULL OR "
            "(routine_id IS NOT NULL AND safety_status_code IN ('PASS','REVISE'))",
            name="ck_weekly_plan_revisions_finalize",
        ),
        CheckConstraint("length(input_hash) = 64", name="ck_weekly_plan_revisions_input_hash"),
        Index(
            "uq_weekly_plan_revisions_initial",
            "target_user_week_id",
            unique=True,
            postgresql_where=text("revision_source_code = 'INITIAL'"),
            sqlite_where=text("revision_source_code = 'INITIAL'"),
        ),
        Index(
            "ix_weekly_plan_revisions_week_created",
            "target_user_week_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    target_user_week_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user_weeks.id", ondelete="CASCADE"), nullable=False
    )
    source_weekly_report_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("weekly_reports.id", ondelete="CASCADE"), nullable=True
    )
    revision_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_revision_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision_source_code: Mapped[str] = mapped_column(String(16), nullable=False)
    routine_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("routines.id", ondelete="RESTRICT"), nullable=True
    )
    selected_location_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safety_status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(48), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_TYPE, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    weekly_plan_policy_version: Mapped[str] = mapped_column(String(48), nullable=False)
    revision_reason_codes: Mapped[list[str]] = mapped_column(_JSON_TYPE, nullable=False)
    finalization_reason_codes: Mapped[list[str]] = mapped_column(_JSON_TYPE, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    target_user_week: Mapped[UserWeek] = relationship(back_populates="plan_revisions")
    source_weekly_report: Mapped[WeeklyReport | None] = relationship(
        back_populates="sourced_plan_revisions"
    )


__all__ = ["UserWeek", "WeeklyPlanRevision", "WeeklyReport"]
