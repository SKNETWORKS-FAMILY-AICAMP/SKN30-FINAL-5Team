from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.modules.profiles.codes import PROFILE_CODE_SET_VERSION

_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint(
            f"code_set_version = '{PROFILE_CODE_SET_VERSION}'",
            name="ck_user_profiles_code_set_version",
        ),
        CheckConstraint(
            "default_requested_duration_minutes > 0",
            name="ck_user_profiles_requested_duration_positive",
        ),
        CheckConstraint(
            "desired_weekly_workout_count BETWEEN 1 AND 7",
            name="ck_user_profiles_weekly_count",
        ),
        CheckConstraint(
            "coaching_style_code IN ('SUPPORTIVE', 'CONCISE', 'ENERGETIC')",
            name="ck_user_profiles_coaching_style",
        ),
        CheckConstraint("profile_version > 0", name="ck_user_profiles_version_positive"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    protected_birthdate: Mapped[str] = mapped_column(String(1024), nullable=False)
    nickname: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_goal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    experience_level_code: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    preferred_location_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("locations.code"), nullable=False
    )
    default_requested_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    desired_weekly_workout_count: Mapped[int] = mapped_column(Integer, nullable=False)
    coaching_style_code: Mapped[str] = mapped_column(String(32), nullable=False)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    sex_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    code_set_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PROFILE_CODE_SET_VERSION
    )
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserEquipment(Base):
    __tablename__ = "user_equipment"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    equipment_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("equipment.code"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserAvailableLocation(Base):
    __tablename__ = "user_available_locations"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    location_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("locations.code"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserAttentionArea(Base):
    __tablename__ = "user_attention_areas"
    __table_args__ = (UniqueConstraint("user_id", "body_area_code", name="uq_user_attention_area"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body_area_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("body_areas.code"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserPreferredExerciseType(Base):
    __tablename__ = "user_preferred_exercise_types"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    exercise_type_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("training_types.code"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserConsent(Base):
    __tablename__ = "user_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "consent_type_code", name="uq_user_consent_type"),
        CheckConstraint(
            "consent_type_code IN ('GENERAL_PERSONAL_DATA', 'SENSITIVE_DATA', "
            "'WEARABLE_INTEGRATION', 'CALENDAR_INTEGRATION', 'MARKETING')",
            name="ck_user_consents_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserConsentEvent(Base):
    __tablename__ = "user_consent_events"
    __table_args__ = (
        CheckConstraint(
            "consent_type_code IN ('GENERAL_PERSONAL_DATA', 'SENSITIVE_DATA', "
            "'WEARABLE_INTEGRATION', 'CALENDAR_INTEGRATION', 'MARKETING')",
            name="ck_user_consent_events_type",
        ),
        CheckConstraint(
            "event_code IN ('GRANTED', 'REVOKED')",
            name="ck_user_consent_events_event",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    event_code: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MutationIdempotencyRecord(Base):
    __tablename__ = "mutation_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "endpoint_code",
            "idempotency_key",
            name="uq_mutation_idempotency_scope",
        ),
        CheckConstraint(
            "endpoint_code IN ('PUT_ME_ONBOARDING', 'PUT_ME_CONSENTS', "
            "'POST_ROUTINES', 'PUT_DAILY_CONTEXT', 'POST_DECISIONS', "
            "'POST_DECISION_SELECTION', 'PATCH_WORKOUT_SESSION_START', "
            "'PATCH_WORKOUT_SESSION_ITEM', 'POST_WORKOUT_TIMER_EVENT', "
            "'POST_WORKOUT_ADDITIONAL_ACTIVITY', 'POST_WORKOUT_SAFETY_EVENT', "
            "'PATCH_WORKOUT_SESSION_FINISH', 'PATCH_WORKOUT_SESSION_NOT_COMPLETED', "
            "'POST_WORKOUT_FEEDBACK', 'POST_WEEKLY_REPORT', "
            "'POST_WEEKLY_REPORT_ACKNOWLEDGEMENT', 'POST_WEEKLY_PLAN', "
            "'POST_WEEKLY_PLAN_REVISION')",
            name="ck_mutation_idempotency_endpoint",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint_code: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(_JSON_TYPE, nullable=False)
    response_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "MutationIdempotencyRecord",
    "UserAvailableLocation",
    "UserAttentionArea",
    "UserConsent",
    "UserConsentEvent",
    "UserEquipment",
    "UserPreferredExerciseType",
    "UserProfile",
]
