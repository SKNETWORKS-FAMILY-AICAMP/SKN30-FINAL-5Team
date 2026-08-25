"""Additive PostgreSQL records for V3 decision replay and audit."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class DecisionConstraintEnvelopeRecord(Base):
    __tablename__ = "decision_constraint_envelopes"
    __table_args__ = (
        UniqueConstraint("root_decision_run_id", name="uq_v3_envelope_root"),
        CheckConstraint("char_length(input_hash) = 64", name="ck_v3_envelope_input_hash"),
        CheckConstraint("char_length(envelope_hash) = 64", name="ck_v3_envelope_hash"),
        CheckConstraint(
            "required_action_code IS NULL OR required_action_code IN ('REST','STOP_AND_SEEK_HELP')",
            name="ck_v3_envelope_required_action",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    root_decision_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_runs.id", ondelete="CASCADE"), nullable=False
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    envelope_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    safety_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_policy_versions.id", ondelete="RESTRICT"), nullable=False
    )
    safety_rule_version: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_rule_version: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_generation_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    required_action_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    veto: Mapped[bool] = mapped_column(Boolean, nullable=False)
    envelope_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    envelope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DecisionExercisePoolRecord(Base):
    __tablename__ = "decision_exercise_pools"
    __table_args__ = (
        UniqueConstraint("constraint_envelope_id", name="uq_v3_pool_envelope"),
        CheckConstraint("exercise_count >= 0", name="ck_v3_pool_exercise_count"),
        CheckConstraint(
            "char_length(constraint_envelope_hash) = 64", name="ck_v3_pool_envelope_hash"
        ),
        CheckConstraint("char_length(pool_hash) = 64", name="ck_v3_pool_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    constraint_envelope_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("decision_constraint_envelopes.id", ondelete="CASCADE"),
        nullable=False,
    )
    catalog_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_versions.id", ondelete="RESTRICT"), nullable=False
    )
    pool_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    filter_codes: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    constraint_envelope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    exercise_payload: Mapped[list[dict[str, Any]]] = mapped_column(_JSON, nullable=False)
    mandatory_exercise_ids: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    vector_ranked_exercise_ids: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    retrieval_metadata: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    exercise_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pool_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DecisionExerciseRetrievalRecord(Base):
    __tablename__ = "decision_exercise_retrievals"
    __table_args__ = (
        UniqueConstraint("constraint_envelope_id", name="uq_v3_retrieval_envelope"),
        UniqueConstraint("exercise_pool_id", name="uq_v3_retrieval_pool"),
        CheckConstraint("requested_limit > 0", name="ck_v3_retrieval_limit"),
        CheckConstraint(
            "retrieval_latency_ms IS NULL OR retrieval_latency_ms >= 0",
            name="ck_v3_retrieval_latency",
        ),
        CheckConstraint(
            "retrieval_mode_code IN ('VECTOR_RANKED','DETERMINISTIC_ONLY')",
            name="ck_v3_retrieval_mode",
        ),
        CheckConstraint(
            "retrieval_status_code IN ('VECTOR_RETRIEVAL_SUCCEEDED',"
            "'VECTOR_INDEX_UNAVAILABLE','VECTOR_INDEX_NOT_READY',"
            "'VECTOR_INDEX_VERSION_MISMATCH','VECTOR_SEARCH_TIMEOUT',"
            "'VECTOR_RESULT_STALE','VECTOR_RESULT_NOT_CANONICAL',"
            "'VECTOR_RESULT_INSUFFICIENT')",
            name="ck_v3_retrieval_status",
        ),
        CheckConstraint(
            "(retrieval_status_code = 'VECTOR_RETRIEVAL_SUCCEEDED' "
            "AND fallback_used = false AND collection_name IS NOT NULL "
            "AND vector_index_version IS NOT NULL AND embedding_model_version IS NOT NULL) OR "
            "(retrieval_status_code <> 'VECTOR_RETRIEVAL_SUCCEEDED' "
            "AND fallback_used = true AND fallback_policy_version IS NOT NULL)",
            name="ck_v3_retrieval_outcome",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    constraint_envelope_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("decision_constraint_envelopes.id", ondelete="CASCADE"),
        nullable=False,
    )
    exercise_pool_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_exercise_pools.id", ondelete="CASCADE"), nullable=False
    )
    vector_index_registry_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("vector_index_registry.id", ondelete="RESTRICT"), nullable=True
    )
    request_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    eligible_exercise_ids_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mandatory_exercise_ids_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_query_codes_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_mode_code: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    result_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    collection_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vector_index_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_status_code: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_failure_codes: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    returned_ranked_ids_and_scores: Mapped[list[dict[str, Any]]] = mapped_column(
        _JSON, nullable=False
    )
    revalidated_ranked_exercise_ids: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fallback_policy_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retrieval_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DecisionCoordinationAttemptRecord(Base):
    __tablename__ = "decision_coordination_attempts"
    __table_args__ = (
        UniqueConstraint(
            "decision_run_id", "attempt_number", name="uq_v3_coordination_run_attempt"
        ),
        UniqueConstraint(
            "id", "decision_run_id", "attempt_number", name="uq_v3_coordination_identity"
        ),
        CheckConstraint("attempt_number IN (0,1)", name="ck_v3_coordination_attempt"),
        CheckConstraint("status_code IN ('READY','FAILED')", name="ck_v3_coordination_status"),
        CheckConstraint("char_length(input_hash) = 64", name="ck_v3_coordination_input_hash"),
        CheckConstraint(
            "output_hash IS NULL OR char_length(output_hash) = 64",
            name="ck_v3_coordination_output_hash",
        ),
        CheckConstraint(
            "(status_code = 'READY' AND plan_spec IS NOT NULL AND output_hash IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status_code = 'FAILED' AND plan_spec IS NULL AND output_hash IS NULL "
            "AND failure_code IS NOT NULL)",
            name="ck_v3_coordination_outcome",
        ),
        CheckConstraint(
            "(attempt_number = 0 AND repair_violation_codes IS NULL) OR "
            "(attempt_number = 1 AND repair_violation_codes IS NOT NULL)",
            name="ck_v3_coordination_repair_codes",
        ),
        Index("ix_v3_coordination_run", "decision_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_runs.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    coordinator_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    model_code: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_spec: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    repair_violation_codes: Mapped[list[str] | None] = mapped_column(_JSON, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PlanIntegrityValidationRecord(Base):
    __tablename__ = "plan_integrity_validations"
    __table_args__ = (
        UniqueConstraint("coordination_attempt_id", name="uq_v3_validation_coordination"),
        UniqueConstraint(
            "decision_run_id",
            "coordination_attempt_number",
            name="uq_v3_validation_run_attempt",
        ),
        ForeignKeyConstraint(
            ["coordination_attempt_id", "decision_run_id", "coordination_attempt_number"],
            [
                "decision_coordination_attempts.id",
                "decision_coordination_attempts.decision_run_id",
                "decision_coordination_attempts.attempt_number",
            ],
            name="fk_v3_validation_coordination_identity",
            ondelete="CASCADE",
        ),
        CheckConstraint("coordination_attempt_number IN (0,1)", name="ck_v3_validation_attempt"),
        CheckConstraint(
            "status_code IN ('PASS','REPAIRABLE','FAILED')", name="ck_v3_validation_status"
        ),
        CheckConstraint("char_length(validation_hash) = 64", name="ck_v3_validation_hash"),
        CheckConstraint(
            "status_code <> 'PASS' OR plan_candidate_id IS NOT NULL",
            name="ck_v3_validation_pass_candidate",
        ),
        Index("ix_v3_validation_run", "decision_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decision_runs.id", ondelete="CASCADE"), nullable=False
    )
    coordination_attempt_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    coordination_attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_candidate_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("plan_candidates.id", ondelete="SET NULL"), nullable=True
    )
    compiler_version: Mapped[str] = mapped_column(String(128), nullable=False)
    validator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    violation_codes: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    meaningful_difference_codes: Mapped[list[str] | None] = mapped_column(_JSON, nullable=True)
    validation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "DecisionConstraintEnvelopeRecord",
    "DecisionCoordinationAttemptRecord",
    "DecisionExercisePoolRecord",
    "DecisionExerciseRetrievalRecord",
    "PlanIntegrityValidationRecord",
]
