"""Add immutable V3 decision persistence and audit lineage.

Revision ID: 0025_v3_decision_persistence
Revises: 0024_vector_index_registry
Create Date: 2026-08-25

Downgrade is safe only before production V3 writes begin. Once V3 audit rows
exist, preserve them and ship a forward-fix migration instead of downgrading.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_v3_decision_persistence"
down_revision: str | None = "0024_vector_index_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HASH_CHECK = "~ '^[0-9a-f]{64}$'"


def upgrade() -> None:
    op.add_column("decision_runs", sa.Column("root_decision_run_id", sa.Uuid(), nullable=True))
    op.add_column("decision_runs", sa.Column("parent_decision_run_id", sa.Uuid(), nullable=True))
    op.add_column("decision_runs", sa.Column("generation_mode_code", sa.String(16), nullable=True))
    op.add_column("decision_runs", sa.Column("regeneration_sequence", sa.Integer(), nullable=True))
    op.add_column("decision_runs", sa.Column("decision_engine_code", sa.String(32), nullable=True))
    op.add_column(
        "decision_runs", sa.Column("langchain_contract_version", sa.String(128), nullable=True)
    )
    op.add_column(
        "decision_runs", sa.Column("langgraph_contract_version", sa.String(128), nullable=True)
    )
    op.create_foreign_key(
        "fk_decision_runs_root",
        "decision_runs",
        "decision_runs",
        ["root_decision_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_decision_runs_parent",
        "decision_runs",
        "decision_runs",
        ["parent_decision_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_decision_runs_root_sequence",
        "decision_runs",
        ["root_decision_run_id", "regeneration_sequence"],
    )
    op.create_check_constraint(
        "ck_decision_runs_v3_lineage",
        "decision_runs",
        "(root_decision_run_id IS NULL AND parent_decision_run_id IS NULL "
        "AND generation_mode_code IS NULL AND regeneration_sequence IS NULL "
        "AND decision_engine_code IS NULL AND langchain_contract_version IS NULL "
        "AND langgraph_contract_version IS NULL) OR "
        "(root_decision_run_id IS NOT NULL AND generation_mode_code IS NOT NULL "
        "AND regeneration_sequence IS NOT NULL AND decision_engine_code IS NOT NULL "
        "AND langchain_contract_version IS NOT NULL AND langgraph_contract_version IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_decision_runs_generation_mode",
        "decision_runs",
        "generation_mode_code IS NULL OR generation_mode_code IN ('ORIGINAL','REGENERATED')",
    )
    op.create_check_constraint(
        "ck_decision_runs_regeneration_sequence",
        "decision_runs",
        "regeneration_sequence IS NULL OR regeneration_sequence BETWEEN 0 AND 2",
    )
    op.create_check_constraint(
        "ck_decision_runs_generation_shape",
        "decision_runs",
        "generation_mode_code IS NULL OR "
        "(generation_mode_code = 'ORIGINAL' AND regeneration_sequence = 0 "
        "AND parent_decision_run_id IS NULL AND root_decision_run_id = id) OR "
        "(generation_mode_code = 'REGENERATED' AND regeneration_sequence IN (1,2) "
        "AND parent_decision_run_id IS NOT NULL AND root_decision_run_id <> id)",
    )
    op.create_check_constraint(
        "ck_decision_runs_engine",
        "decision_runs",
        "decision_engine_code IS NULL OR decision_engine_code IN "
        "('DETERMINISTIC','LLM_MULTI_AGENT','DETERMINISTIC_FALLBACK')",
    )
    op.create_index("ix_decision_runs_root", "decision_runs", ["root_decision_run_id"])

    for name, type_, length in (
        ("invocation_metadata_schema_version", sa.String, 64),
        ("proposal_hash", sa.String, 64),
        ("prompt_version", sa.String, 128),
        ("provider_code", sa.String, 64),
        ("model_code", sa.String, 128),
        ("output_schema_version", sa.String, 128),
        ("invocation_status_code", sa.String, 24),
    ):
        op.add_column("agent_proposals", sa.Column(name, type_(length), nullable=True))
    op.add_column("agent_proposals", sa.Column("attempt_number", sa.Integer(), nullable=True))
    op.add_column("agent_proposals", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_agent_proposals_invocation_all_or_none",
        "agent_proposals",
        "(invocation_metadata_schema_version IS NULL AND proposal_hash IS NULL "
        "AND prompt_version IS NULL AND provider_code IS NULL AND model_code IS NULL "
        "AND output_schema_version IS NULL AND attempt_number IS NULL "
        "AND invocation_status_code IS NULL AND latency_ms IS NULL) OR "
        "(invocation_metadata_schema_version IS NOT NULL AND proposal_hash IS NOT NULL "
        "AND prompt_version IS NOT NULL AND provider_code IS NOT NULL AND model_code IS NOT NULL "
        "AND output_schema_version IS NOT NULL AND attempt_number IS NOT NULL "
        "AND invocation_status_code IS NOT NULL AND latency_ms IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_agent_proposals_invocation_attempt",
        "agent_proposals",
        "attempt_number IS NULL OR attempt_number IN (0,1)",
    )
    op.create_check_constraint(
        "ck_agent_proposals_invocation_status",
        "agent_proposals",
        "invocation_status_code IS NULL OR invocation_status_code IN "
        "('SUCCEEDED','FAILED','TIMEOUT','INVALID_OUTPUT')",
    )
    op.create_check_constraint(
        "ck_agent_proposals_invocation_latency",
        "agent_proposals",
        "latency_ms IS NULL OR latency_ms >= 0",
    )
    op.create_check_constraint(
        "ck_agent_proposals_proposal_hash",
        "agent_proposals",
        f"proposal_hash IS NULL OR proposal_hash {_HASH_CHECK}",
    )

    op.create_table(
        "decision_constraint_envelopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("root_decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("envelope_schema_version", sa.String(64), nullable=False),
        sa.Column("safety_policy_version", sa.String(128), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("safety_rule_version", sa.String(128), nullable=False),
        sa.Column("duration_rule_version", sa.String(128), nullable=False),
        sa.Column("plan_generation_allowed", sa.Boolean(), nullable=False),
        sa.Column("required_action_code", sa.String(32), nullable=True),
        sa.Column("veto", sa.Boolean(), nullable=False),
        sa.Column("envelope_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("envelope_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(f"input_hash {_HASH_CHECK}", name="ck_v3_envelope_input_hash"),
        sa.CheckConstraint(f"envelope_hash {_HASH_CHECK}", name="ck_v3_envelope_hash"),
        sa.CheckConstraint(
            "required_action_code IS NULL OR required_action_code IN ('REST','STOP_AND_SEEK_HELP')",
            name="ck_v3_envelope_required_action",
        ),
        sa.ForeignKeyConstraint(["root_decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["policy_version_id"], ["decision_policy_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("root_decision_run_id", name="uq_v3_envelope_root"),
    )

    op.create_table(
        "decision_exercise_pools",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("constraint_envelope_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_version_id", sa.Uuid(), nullable=False),
        sa.Column("pool_schema_version", sa.String(64), nullable=False),
        sa.Column("filter_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("constraint_envelope_hash", sa.String(64), nullable=False),
        sa.Column("exercise_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "mandatory_exercise_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "vector_ranked_exercise_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("retrieval_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exercise_count", sa.Integer(), nullable=False),
        sa.Column("pool_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("exercise_count >= 0", name="ck_v3_pool_exercise_count"),
        sa.CheckConstraint(
            f"constraint_envelope_hash {_HASH_CHECK}", name="ck_v3_pool_envelope_hash"
        ),
        sa.CheckConstraint(f"pool_hash {_HASH_CHECK}", name="ck_v3_pool_hash"),
        sa.ForeignKeyConstraint(
            ["constraint_envelope_id"], ["decision_constraint_envelopes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["catalog_version_id"], ["catalog_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("constraint_envelope_id", name="uq_v3_pool_envelope"),
    )

    op.create_table(
        "decision_exercise_retrievals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("constraint_envelope_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_pool_id", sa.Uuid(), nullable=False),
        sa.Column("vector_index_registry_id", sa.Uuid(), nullable=True),
        sa.Column("request_schema_version", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("eligible_exercise_ids_hash", sa.String(64), nullable=False),
        sa.Column("mandatory_exercise_ids_hash", sa.String(64), nullable=False),
        sa.Column("normalized_query_codes_hash", sa.String(64), nullable=False),
        sa.Column("retrieval_mode_code", sa.String(32), nullable=False),
        sa.Column("requested_limit", sa.Integer(), nullable=False),
        sa.Column("result_schema_version", sa.String(64), nullable=False),
        sa.Column("collection_name", sa.String(255), nullable=True),
        sa.Column("vector_index_version", sa.String(128), nullable=True),
        sa.Column("embedding_model_version", sa.String(128), nullable=True),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("retrieval_status_code", sa.String(64), nullable=False),
        sa.Column(
            "retrieval_failure_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "returned_ranked_ids_and_scores",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "revalidated_ranked_exercise_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("fallback_policy_version", sa.String(128), nullable=True),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("requested_limit > 0", name="ck_v3_retrieval_limit"),
        sa.CheckConstraint(
            "retrieval_latency_ms IS NULL OR retrieval_latency_ms >= 0",
            name="ck_v3_retrieval_latency",
        ),
        sa.CheckConstraint(
            "retrieval_mode_code IN ('VECTOR_RANKED','DETERMINISTIC_ONLY')",
            name="ck_v3_retrieval_mode",
        ),
        sa.CheckConstraint(
            "retrieval_status_code IN ('VECTOR_RETRIEVAL_SUCCEEDED',"
            "'VECTOR_INDEX_UNAVAILABLE','VECTOR_INDEX_NOT_READY',"
            "'VECTOR_INDEX_VERSION_MISMATCH','VECTOR_SEARCH_TIMEOUT',"
            "'VECTOR_RESULT_STALE','VECTOR_RESULT_NOT_CANONICAL',"
            "'VECTOR_RESULT_INSUFFICIENT')",
            name="ck_v3_retrieval_status",
        ),
        sa.CheckConstraint(
            "(retrieval_status_code = 'VECTOR_RETRIEVAL_SUCCEEDED' AND fallback_used = false "
            "AND collection_name IS NOT NULL AND vector_index_version IS NOT NULL "
            "AND embedding_model_version IS NOT NULL) OR "
            "(retrieval_status_code <> 'VECTOR_RETRIEVAL_SUCCEEDED' AND fallback_used = true "
            "AND fallback_policy_version IS NOT NULL)",
            name="ck_v3_retrieval_outcome",
        ),
        *(
            sa.CheckConstraint(f"{column} {_HASH_CHECK}", name=f"ck_v3_retrieval_{column}")
            for column in (
                "request_hash",
                "eligible_exercise_ids_hash",
                "mandatory_exercise_ids_hash",
                "normalized_query_codes_hash",
                "query_hash",
                "result_hash",
            )
        ),
        sa.ForeignKeyConstraint(
            ["constraint_envelope_id"], ["decision_constraint_envelopes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["exercise_pool_id"], ["decision_exercise_pools.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["vector_index_registry_id"], ["vector_index_registry.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("constraint_envelope_id", name="uq_v3_retrieval_envelope"),
        sa.UniqueConstraint("exercise_pool_id", name="uq_v3_retrieval_pool"),
    )

    op.create_table(
        "decision_coordination_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.String(16), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("coordinator_schema_version", sa.String(64), nullable=False),
        sa.Column("model_provider_code", sa.String(64), nullable=False),
        sa.Column("model_code", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(128), nullable=False),
        sa.Column("plan_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("repair_violation_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempt_number IN (0,1)", name="ck_v3_coordination_attempt"),
        sa.CheckConstraint("status_code IN ('READY','FAILED')", name="ck_v3_coordination_status"),
        sa.CheckConstraint(f"input_hash {_HASH_CHECK}", name="ck_v3_coordination_input_hash"),
        sa.CheckConstraint(
            "output_hash IS NULL OR output_hash ~ '^[0-9a-f]{64}$'",
            name="ck_v3_coordination_output_hash",
        ),
        sa.CheckConstraint(
            "(status_code = 'READY' AND plan_spec IS NOT NULL AND output_hash IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status_code = 'FAILED' AND plan_spec IS NULL AND output_hash IS NULL "
            "AND failure_code IS NOT NULL)",
            name="ck_v3_coordination_outcome",
        ),
        sa.CheckConstraint(
            "(attempt_number = 0 AND repair_violation_codes IS NULL) OR "
            "(attempt_number = 1 AND repair_violation_codes IS NOT NULL)",
            name="ck_v3_coordination_repair_codes",
        ),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "decision_run_id",
            "attempt_number",
            name="uq_v3_coordination_identity",
        ),
        sa.UniqueConstraint(
            "decision_run_id", "attempt_number", name="uq_v3_coordination_run_attempt"
        ),
    )

    op.create_table(
        "plan_integrity_validations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("coordination_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("coordination_attempt_number", sa.Integer(), nullable=False),
        sa.Column("plan_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("compiler_version", sa.String(128), nullable=False),
        sa.Column("validator_version", sa.String(128), nullable=False),
        sa.Column("status_code", sa.String(16), nullable=False),
        sa.Column("violation_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "meaningful_difference_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("validation_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("coordination_attempt_number IN (0,1)", name="ck_v3_validation_attempt"),
        sa.CheckConstraint(
            "status_code IN ('PASS','REPAIRABLE','FAILED')", name="ck_v3_validation_status"
        ),
        sa.CheckConstraint(f"validation_hash {_HASH_CHECK}", name="ck_v3_validation_hash"),
        sa.CheckConstraint(
            "status_code <> 'PASS' OR plan_candidate_id IS NOT NULL",
            name="ck_v3_validation_pass_candidate",
        ),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["coordination_attempt_id", "decision_run_id", "coordination_attempt_number"],
            [
                "decision_coordination_attempts.id",
                "decision_coordination_attempts.decision_run_id",
                "decision_coordination_attempts.attempt_number",
            ],
            name="fk_v3_validation_coordination_identity",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["plan_candidate_id"], ["plan_candidates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coordination_attempt_id", name="uq_v3_validation_coordination"),
        sa.UniqueConstraint(
            "decision_run_id",
            "coordination_attempt_number",
            name="uq_v3_validation_run_attempt",
        ),
    )
    op.create_index("ix_v3_coordination_run", "decision_coordination_attempts", ["decision_run_id"])
    op.create_index("ix_v3_validation_run", "plan_integrity_validations", ["decision_run_id"])


def downgrade() -> None:
    # Do not run after production V3 writes: audit history must be retained and
    # corrected with an additive forward-fix migration.
    op.drop_index("ix_v3_validation_run", table_name="plan_integrity_validations")
    op.drop_index("ix_v3_coordination_run", table_name="decision_coordination_attempts")
    op.drop_table("plan_integrity_validations")
    op.drop_table("decision_coordination_attempts")
    op.drop_table("decision_exercise_retrievals")
    op.drop_table("decision_exercise_pools")
    op.drop_table("decision_constraint_envelopes")

    for constraint in (
        "ck_agent_proposals_proposal_hash",
        "ck_agent_proposals_invocation_latency",
        "ck_agent_proposals_invocation_status",
        "ck_agent_proposals_invocation_attempt",
        "ck_agent_proposals_invocation_all_or_none",
    ):
        op.drop_constraint(constraint, "agent_proposals", type_="check")
    for column in (
        "latency_ms",
        "invocation_status_code",
        "attempt_number",
        "output_schema_version",
        "model_code",
        "provider_code",
        "prompt_version",
        "proposal_hash",
        "invocation_metadata_schema_version",
    ):
        op.drop_column("agent_proposals", column)

    op.drop_index("ix_decision_runs_root", table_name="decision_runs")
    for constraint, kind in (
        ("ck_decision_runs_engine", "check"),
        ("ck_decision_runs_generation_shape", "check"),
        ("ck_decision_runs_regeneration_sequence", "check"),
        ("ck_decision_runs_generation_mode", "check"),
        ("ck_decision_runs_v3_lineage", "check"),
        ("uq_decision_runs_root_sequence", "unique"),
        ("fk_decision_runs_parent", "foreignkey"),
        ("fk_decision_runs_root", "foreignkey"),
    ):
        op.drop_constraint(constraint, "decision_runs", type_=kind)
    for column in (
        "langgraph_contract_version",
        "langchain_contract_version",
        "decision_engine_code",
        "regeneration_sequence",
        "generation_mode_code",
        "parent_decision_run_id",
        "root_decision_run_id",
    ):
        op.drop_column("decision_runs", column)
