from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class DailyContext(Base):
    __tablename__ = "daily_contexts"
    __table_args__ = (
        UniqueConstraint("user_id", "local_date", name="uq_daily_contexts_user_local_date"),
        CheckConstraint(
            "fatigue_level_code IN ('LOW', 'MODERATE', 'HIGH')",
            name="ck_daily_contexts_fatigue",
        ),
        CheckConstraint(
            "duration_adjustment_source_code IN ('PROFILE', 'USER_OVERRIDE')",
            name="ck_daily_contexts_duration_source",
        ),
        CheckConstraint(
            "requested_duration_minutes BETWEEN 1 AND 240",
            name="ck_daily_contexts_duration",
        ),
        CheckConstraint(
            "sleep_minutes IS NULL OR sleep_minutes BETWEEN 0 AND 1440",
            name="ck_daily_contexts_sleep_minutes",
        ),
        CheckConstraint("context_version > 0", name="ck_daily_contexts_version"),
        CheckConstraint(
            "availability_source_code IN ('MANUAL', 'ROUTINE_DEFAULT')",
            name="ck_daily_contexts_availability_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    fatigue_level_code: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_adjustment_source_code: Mapped[str] = mapped_column(String(32), nullable=False)
    location_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("locations.code", ondelete="RESTRICT"), nullable=False
    )
    sleep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fasting_state_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hydration_state_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    availability_source_code: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ROUTINE_DEFAULT", server_default="ROUTINE_DEFAULT"
    )
    context_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    discomforts: Mapped[list["DailyContextDiscomfort"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    adverse_reactions: Mapped[list["DailyContextAdverseReaction"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    availability_slots: Mapped[list["DailyContextAvailabilitySlot"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class DailyContextDiscomfort(Base):
    __tablename__ = "daily_context_discomforts"
    __table_args__ = (
        UniqueConstraint(
            "daily_context_id", "body_area_code", name="uq_daily_context_discomfort_body"
        ),
        CheckConstraint(
            "severity_code IN ('MILD', 'MODERATE', 'SEVERE')",
            name="ck_daily_context_discomfort_severity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    daily_context_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("daily_contexts.id", ondelete="CASCADE"), nullable=False
    )
    body_area_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("body_areas.code", ondelete="RESTRICT"), nullable=False
    )
    severity_code: Mapped[str] = mapped_column(String(16), nullable=False)


class DailyContextAdverseReaction(Base):
    __tablename__ = "daily_context_adverse_reactions"

    daily_context_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("daily_contexts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    reaction_code: Mapped[str] = mapped_column(String(80), primary_key=True)


class DailyContextAvailabilitySlot(Base):
    """A workout window the user entered by hand; no calendar body text is stored."""

    __tablename__ = "daily_context_availability_slots"
    __table_args__ = (
        UniqueConstraint("daily_context_id", "slot_order", name="uq_daily_context_slot_order"),
        CheckConstraint("end_at > start_at", name="ck_daily_context_slot_range"),
        CheckConstraint("slot_order >= 0 AND slot_order < 8", name="ck_daily_context_slot_order"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    daily_context_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("daily_contexts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_order: Mapped[int] = mapped_column(Integer, nullable=False)


__all__ = [
    "DailyContext",
    "DailyContextAdverseReaction",
    "DailyContextAvailabilitySlot",
    "DailyContextDiscomfort",
]
