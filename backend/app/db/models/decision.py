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
    explanations: Mapped[list["DecisionExplanationRecord"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    deliberations: Mapped[list["DecisionDeliberationRecord"]] = relationship(
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


class DecisionDeliberationRecord(Base):
    """Versioned V2 conflict/review envelope kept separate from the final result."""

    __tablename__ = "decision_deliberations"
    __table_args__ = (
        CheckConstraint("round_count IN (1,2)", name="ck_decision_deliberations_round_count"),
        CheckConstraint(
            "round_two_status_code IN ('SKIPPED_NO_CONFLICT','COMPLETED','NEEDS_INPUT','FAILED')",
            name="ck_decision_deliberations_round_two_status",
        ),
        CheckConstraint(
            "char_length(conflict_hash) = 64",
            name="ck_decision_deliberations_conflict_hash",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("decision_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    policy_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("decision_policy_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    deliberation_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(128), nullable=False)
    round_count: Mapped[int] = mapped_column(Integer, nullable=False)
    round_two_status_code: Mapped[str] = mapped_column(String(32), nullable=False)
    conflict_detector_version: Mapped[str] = mapped_column(String(128), nullable=False)
    precedence_version: Mapped[str] = mapped_column(String(128), nullable=False)
    conflict_codes: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    conflict_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    proposal_revisions: Mapped[list["AgentProposalRevisionRecord"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    review_events: Mapped[list["AgentReviewEventRecord"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class AgentProposalRevisionRecord(Base):
    """Canonical Round 1 link or a validated Round 2 proposal revision."""

    __tablename__ = "agent_proposal_revisions"
    __table_args__ = (
        UniqueConstraint(
            "decision_run_id",
            "round_number",
            "agent_type_code",
            name="uq_agent_proposal_revisions_run_round_type",
        ),
        CheckConstraint("round_number IN (1,2)", name="ck_agent_proposal_revisions_round"),
        CheckConstraint(
            "agent_type_code IN ('TRAINING','RECOVERY','SAFETY','FEASIBILITY')",
            name="ck_agent_proposal_revisions_type",
        ),
        CheckConstraint(
            "proposal_status_code IN ('READY','NEEDS_INPUT','FAILED')",
            name="ck_agent_proposal_revisions_status",
        ),
        CheckConstraint(
            "(round_number = 1 AND source_proposal_id IS NOT NULL "
            "AND baseline_revision_id IS NULL) OR "
            "(round_number = 2 AND baseline_revision_id IS NOT NULL)",
            name="ck_agent_proposal_revisions_lineage",
        ),
        CheckConstraint(
            "char_length(proposal_hash) = 64",
            name="ck_agent_proposal_revisions_hash",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_runs.id", ondelete="CASCADE"), nullable=False
    )
    deliberation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_deliberations.id", ondelete="CASCADE"), nullable=False
    )
    source_proposal_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_proposals.id", ondelete="CASCADE"), nullable=True
    )
    baseline_revision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_proposal_revisions.id", ondelete="CASCADE"), nullable=True
    )
    policy_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("decision_policy_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_type_code: Mapped[str] = mapped_column(String(32), nullable=False)
    proposal_status_code: Mapped[str] = mapped_column(String(24), nullable=False)
    proposal_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    proposal_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgentReviewEventRecord(Base):
    """One Round 2 event per Agent, including explicit NOT_REQUIRED events."""

    __tablename__ = "agent_review_events"
    __table_args__ = (
        UniqueConstraint(
            "decision_run_id",
            "round_number",
            "agent_type_code",
            name="uq_agent_review_events_run_round_type",
        ),
        CheckConstraint("round_number = 2", name="ck_agent_review_events_round"),
        CheckConstraint(
            "agent_type_code IN ('TRAINING','RECOVERY','SAFETY','FEASIBILITY')",
            name="ck_agent_review_events_type",
        ),
        CheckConstraint(
            "review_status_code IN ('READY','NOT_REQUIRED','NEEDS_INPUT','FAILED')",
            name="ck_agent_review_events_status",
        ),
        CheckConstraint(
            "revision_status_code IS NULL OR revision_status_code IN "
            "('UNCHANGED','REVISED','NOT_REQUIRED')",
            name="ck_agent_review_events_revision_status",
        ),
        CheckConstraint(
            "(review_status_code = 'READY' AND revision_status_code IN "
            "('UNCHANGED','REVISED')) OR "
            "(review_status_code = 'NOT_REQUIRED' AND "
            "revision_status_code = 'NOT_REQUIRED') OR "
            "(review_status_code IN ('NEEDS_INPUT','FAILED') AND "
            "revision_status_code IS NULL)",
            name="ck_agent_review_events_status_pair",
        ),
        CheckConstraint(
            "(revision_status_code = 'REVISED') = (revised_revision_id IS NOT NULL)",
            name="ck_agent_review_events_revised_link",
        ),
        CheckConstraint(
            "char_length(baseline_proposal_hash) = 64 AND char_length(review_hash) = 64",
            name="ck_agent_review_events_hashes",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_runs.id", ondelete="CASCADE"), nullable=False
    )
    deliberation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_deliberations.id", ondelete="CASCADE"), nullable=False
    )
    baseline_revision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("agent_proposal_revisions.id", ondelete="CASCADE"), nullable=False
    )
    revised_revision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_proposal_revisions.id", ondelete="CASCADE"), nullable=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    agent_type_code: Mapped[str] = mapped_column(String(32), nullable=False)
    review_status_code: Mapped[str] = mapped_column(String(24), nullable=False)
    revision_status_code: Mapped[str | None] = mapped_column(String(24), nullable=True)
    review_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    baseline_proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_proposal_references: Mapped[list[dict[str, str]]] = mapped_column(
        _JSON, nullable=False
    )
    review_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    review_hash: Mapped[str] = mapped_column(String(64), nullable=False)
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


class DecisionExplanationRecord(Base):
    """Public narration for one decision run; internal prompts and reasoning stay out."""

    __tablename__ = "decision_explanations"
    __table_args__ = (
        CheckConstraint(
            "source_code IN ('TEMPLATE','LLM')", name="ck_decision_explanations_source"
        ),
        CheckConstraint(
            "(source_code = 'LLM') = (prompt_version IS NOT NULL AND model_code IS NOT NULL)",
            name="ck_decision_explanations_llm_versions",
        ),
        CheckConstraint(
            "(source_code = 'TEMPLATE') = (fallback_reason_code IS NOT NULL)",
            name="ck_decision_explanations_fallback_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    source_code: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    agent_summaries: Mapped[list[dict[str, Any]]] = mapped_column(_JSON, nullable=False)
    safety_summary: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    final_adjustment_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    coaching_style_code: Mapped[str] = mapped_column(String(32), nullable=False)
    template_version: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fallback_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


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
    "AgentProposalRevisionRecord",
    "AgentProposalRecord",
    "AgentReviewEventRecord",
    "DecisionDeliberationRecord",
    "DecisionExplanationRecord",
    "DecisionOption",
    "DecisionPolicyVersion",
    "DecisionRun",
    "PlanCandidate",
    "PlanItem",
    "SafetyReview",
]
