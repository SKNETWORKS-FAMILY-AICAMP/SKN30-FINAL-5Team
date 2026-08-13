from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Routine(Base):
    __tablename__ = "routines"
    __table_args__ = (
        UniqueConstraint("user_id", "version", name="uq_routines_user_version"),
        CheckConstraint("version > 0", name="ck_routines_version_positive"),
        CheckConstraint(
            "status_code IN ('DRAFT', 'ACTIVE', 'ARCHIVED')",
            name="ck_routines_status_code",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_routines_effective_period",
        ),
        Index("ix_routines_user_status_effective", "user_id", "status_code", "effective_from"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    goal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    catalog_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_versions.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    days: Mapped[list["RoutineDay"]] = relationship(
        back_populates="routine",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RoutineDay.sequence",
    )


class RoutineDay(Base):
    __tablename__ = "routine_days"
    __table_args__ = (
        UniqueConstraint("routine_id", "sequence", name="uq_routine_days_sequence"),
        CheckConstraint("sequence > 0", name="ck_routine_days_sequence_positive"),
        CheckConstraint("schedule_rule = 'ROTATION'", name="ck_routine_days_schedule_rule"),
        CheckConstraint(
            "requested_duration_minutes > 0",
            name="ck_routine_days_requested_duration_positive",
        ),
        CheckConstraint(
            "estimated_duration_seconds = requested_duration_minutes * 60",
            name="ck_routine_days_exact_duration",
        ),
        CheckConstraint("setup_seconds BETWEEN 0 AND 60", name="ck_routine_days_setup"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    routine_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("routines.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    schedule_rule: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    training_type_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("training_types.code"), nullable=False
    )
    body_focus_code: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("body_focuses.code"), nullable=True
    )
    requested_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    setup_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_calories_burned: Mapped[float | None] = mapped_column(Float, nullable=True)

    routine: Mapped[Routine] = relationship(back_populates="days")
    items: Mapped[list["RoutineItem"]] = relationship(
        back_populates="routine_day",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RoutineItem.sequence",
    )


class RoutineItem(Base):
    __tablename__ = "routine_items"
    __table_args__ = (
        UniqueConstraint("routine_day_id", "sequence", name="uq_routine_items_sequence"),
        CheckConstraint("sequence > 0", name="ck_routine_items_sequence_positive"),
        CheckConstraint(
            "phase_code IN ('WARMUP', 'MAIN', 'COOLDOWN')",
            name="ck_routine_items_phase_code",
        ),
        CheckConstraint(
            "tier_code IN ('CORE', 'SUPPORT', 'OPTIONAL')",
            name="ck_routine_items_tier_code",
        ),
        CheckConstraint("sets > 0", name="ck_routine_items_sets_positive"),
        CheckConstraint(
            "(reps > 0 AND work_seconds_per_set IS NULL) OR "
            "(reps IS NULL AND work_seconds_per_set > 0)",
            name="ck_routine_items_timing",
        ),
        CheckConstraint("rest_seconds_per_set >= 0", name="ck_routine_items_rest"),
        Index("ix_routine_items_day_phase_sequence", "routine_day_id", "phase_code", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    routine_day_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("routine_days.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    phase_code: Mapped[str] = mapped_column(String(16), nullable=False)
    tier_code: Mapped[str] = mapped_column(String(16), nullable=False)
    sets: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_seconds_per_set: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds_per_set: Mapped[int] = mapped_column(Integer, nullable=False)
    intensity_code: Mapped[str] = mapped_column(String(32), nullable=False)

    routine_day: Mapped[RoutineDay] = relationship(back_populates="items")


__all__ = ["Routine", "RoutineDay", "RoutineItem"]
