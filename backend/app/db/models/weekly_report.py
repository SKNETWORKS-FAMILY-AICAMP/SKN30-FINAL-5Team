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
    stopped_for_safety: Mapped[int] = mapped_column(Integer, nullable=False)
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


__all__ = ["UserWeek", "WeeklyReport"]
