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
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class DecisionPolicyVersion(Base):
    __tablename__ = "decision_policy_versions"
    __table_args__ = (
        CheckConstraint("status_code IN ('ACTIVE','DEPRECATED')", name="ck_decision_policy_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    version_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DecisionRun(Base):
    __tablename__ = "decision_runs"
    __table_args__ = (
        CheckConstraint(
            "status_code IN ('RUNNING','COMPLETED','FAILED','NEEDS_INPUT')",
            name="ck_decision_runs_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    daily_context_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("daily_contexts.id", ondelete="RESTRICT"), nullable=False
    )
    daily_context_version: Mapped[int] = mapped_column(Integer, nullable=False)
    base_routine_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("routines.id", ondelete="RESTRICT"), nullable=False
    )
    input_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_versions.id", ondelete="RESTRICT"), nullable=False
    )
    policy_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_policy_versions.id", ondelete="RESTRICT"), nullable=False
    )
    safety_rule_version: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_rule_version: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(128), nullable=False)
    coordinator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    safety_status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    recommended_action_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    coordinator_result: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proposals: Mapped[list["AgentProposalRecord"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    candidates: Mapped[list["PlanCandidate"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    safety_reviews: Mapped[list["SafetyReview"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    options: Mapped[list["DecisionOption"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class AgentProposalRecord(Base):
    __tablename__ = "agent_proposals"
    __table_args__ = (
        UniqueConstraint("decision_run_id", "agent_type_code", name="uq_agent_proposals_run_type"),
        CheckConstraint(
            "agent_type_code IN ('TRAINING','RECOVERY','SAFETY','FEASIBILITY')",
            name="ck_agent_proposals_type",
        ),
        CheckConstraint(
            "proposal_status_code IN ('READY','NEEDS_INPUT','FAILED')",
            name="ck_agent_proposals_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_runs.id", ondelete="CASCADE"), nullable=False
    )
    agent_type_code: Mapped[str] = mapped_column(String(32), nullable=False)
    proposal_status_code: Mapped[str] = mapped_column(String(24), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    proposal_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PlanCandidate(Base):
    __tablename__ = "plan_candidates"
    __table_args__ = (
        UniqueConstraint("decision_run_id", "candidate_code", name="uq_plan_candidates_run_code"),
        CheckConstraint(
            "action_code IN ('KEEP','DOWNSHIFT','CHANGE','RECOVERY')",
            name="ck_plan_candidates_action",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_runs.id", ondelete="CASCADE"), nullable=False
    )
    candidate_code: Mapped[str] = mapped_column(String(128), nullable=False)
    action_code: Mapped[str] = mapped_column(String(32), nullable=False)
    training_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    body_focus_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_adjustment_source_code: Mapped[str] = mapped_column(String(32), nullable=False)
    estimated_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_calories_burned: Mapped[float | None] = mapped_column(Float, nullable=True)
    setup_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    warmup_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    goal_tags: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    duration_rule_version: Mapped[str] = mapped_column(String(128), nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    items: Mapped[list["PlanItem"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="PlanItem.sequence"
    )


class PlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        UniqueConstraint("plan_candidate_id", "sequence", name="uq_plan_items_candidate_sequence"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    plan_candidate_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("plan_candidates.id", ondelete="CASCADE"), nullable=False
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
    work_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    rest_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    transition_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    intensity_code: Mapped[str] = mapped_column(String(32), nullable=False)
    instruction_content_version: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)


class SafetyReview(Base):
    __tablename__ = "safety_reviews"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    plan_candidate_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("plan_candidates.id", ondelete="CASCADE"), nullable=False
    )
    safety_status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    vetoed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    excluded_exercise_ids: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    public_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)


class DecisionOption(Base):
    __tablename__ = "decision_options"
    __table_args__ = (
        UniqueConstraint("decision_run_id", "option_code", name="uq_decision_options_run_code"),
        CheckConstraint("option_code IN ('FINAL_ROUTINE','REST')", name="ck_decision_options_code"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_runs.id", ondelete="CASCADE"), nullable=False
    )
    option_code: Mapped[str] = mapped_column(String(32), nullable=False)
    action_code: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_candidate_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("plan_candidates.id", ondelete="CASCADE"), nullable=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    selectable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    blocked_reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)


__all__ = [
    "AgentProposalRecord",
    "DecisionOption",
    "DecisionPolicyVersion",
    "DecisionRun",
    "PlanCandidate",
    "PlanItem",
    "SafetyReview",
]
