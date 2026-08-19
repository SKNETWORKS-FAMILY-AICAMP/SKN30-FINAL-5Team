"""Add account deletion request, job, and de-identified audit lifecycle.

Revision ID: 0012_account_deletion_retention
Revises: 0011_weekly_plan_revisions
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_account_deletion_retention"
down_revision: str | None = "0011_weekly_plan_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING','PUT_ME_CONSENTS','POST_ROUTINES',"
        "'PUT_DAILY_CONTEXT','POST_DECISIONS','POST_DECISION_SELECTION',"
        "'PATCH_WORKOUT_SESSION_START','PATCH_WORKOUT_SESSION_ITEM',"
        "'POST_WORKOUT_TIMER_EVENT','POST_WORKOUT_ADDITIONAL_ACTIVITY',"
        "'POST_WORKOUT_SAFETY_EVENT','PATCH_WORKOUT_SESSION_FINISH',"
        "'PATCH_WORKOUT_SESSION_NOT_COMPLETED','POST_WORKOUT_FEEDBACK',"
        "'POST_WEEKLY_REPORT','POST_WEEKLY_REPORT_ACKNOWLEDGEMENT',"
        "'POST_WEEKLY_PLAN','POST_WEEKLY_PLAN_REVISION','DELETE_ME')",
    )
    op.create_table(
        "account_deletion_jobs",
        sa.Column("deletion_request_id", sa.Uuid(), nullable=False),
        sa.Column("deletion_job_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status_code", sa.String(64), nullable=False),
        sa.Column("current_stage_code", sa.String(48), nullable=False),
        sa.Column("external_revocation_status_code", sa.String(32), nullable=False),
        sa.Column("completion_code", sa.String(64), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operational_data_delete_by", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operational_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backup_expiry_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("backup_expiry_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("audit_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status_code IN ('PENDING','RUNNING','RETRY_PENDING','FAILED_REQUIRES_REVIEW')",
            name="ck_account_deletion_jobs_status",
        ),
        sa.CheckConstraint(
            "current_stage_code IN ('ACCESS_BLOCK','EXTERNAL_REVOCATION',"
            "'OPERATIONAL_DATA_DELETE','CACHE_AND_WORK_DELETE','AUDIT_DEIDENTIFICATION')",
            name="ck_account_deletion_jobs_stage",
        ),
        sa.CheckConstraint(
            "external_revocation_status_code IN "
            "('NOT_REQUIRED','PENDING','SUCCEEDED','RETRY_PENDING','FAILED_FINAL')",
            name="ck_account_deletion_jobs_external_status",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code IN "
            "('EXTERNAL_REVOCATION_RETRYABLE','EXTERNAL_REVOCATION_FINAL',"
            "'OPERATIONAL_DATA_DELETE_FAILED')",
            name="ck_account_deletion_jobs_failure_code",
        ),
        sa.CheckConstraint(
            "completion_code IS NULL OR completion_code IN "
            "('COMPLETED','COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE')",
            name="ck_account_deletion_jobs_completion_code",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_account_deletion_jobs_attempt_count",
        ),
        sa.CheckConstraint(
            "operational_data_delete_by = requested_at + INTERVAL '7 days'",
            name="ck_account_deletion_jobs_operational_deadline",
        ),
        sa.CheckConstraint(
            "backup_expiry_due_at = requested_at + INTERVAL '30 days'",
            name="ck_account_deletion_jobs_backup_deadline",
        ),
        sa.CheckConstraint(
            "operational_deleted_at IS NULL AND backup_expiry_verified_at IS NULL "
            "AND completed_at IS NULL AND completion_code IS NULL AND audit_expires_at IS NULL",
            name="ck_account_deletion_jobs_pre_deidentification",
        ),
        sa.CheckConstraint(
            "policy_version = 'account-deletion-retention-v1'",
            name="ck_account_deletion_jobs_policy_version",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("deletion_request_id"),
        sa.UniqueConstraint("deletion_job_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_account_deletion_jobs_runnable",
        "account_deletion_jobs",
        ["status_code", "requested_at"],
    )
    op.create_index(
        "ix_account_deletion_jobs_operational_deadline",
        "account_deletion_jobs",
        ["operational_data_delete_by"],
    )
    op.create_table(
        "account_deletion_audits",
        sa.Column("deletion_request_id", sa.Uuid(), nullable=False),
        sa.Column("deletion_job_id", sa.Uuid(), nullable=False),
        sa.Column("status_code", sa.String(64), nullable=False),
        sa.Column("current_stage_code", sa.String(48), nullable=False),
        sa.Column("external_revocation_status_code", sa.String(32), nullable=False),
        sa.Column("completion_code", sa.String(64), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operational_data_delete_by", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operational_deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("backup_expiry_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("backup_expiry_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("audit_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status_code IN ('BACKUP_EXPIRY_PENDING','COMPLETED',"
            "'COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE')",
            name="ck_account_deletion_audits_status",
        ),
        sa.CheckConstraint(
            "current_stage_code = 'BACKUP_EXPIRY_VERIFICATION'",
            name="ck_account_deletion_audits_stage",
        ),
        sa.CheckConstraint(
            "external_revocation_status_code IN ('NOT_REQUIRED','SUCCEEDED','FAILED_FINAL')",
            name="ck_account_deletion_audits_external_status",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code = 'EXTERNAL_REVOCATION_FINAL'",
            name="ck_account_deletion_audits_failure_code",
        ),
        sa.CheckConstraint(
            "completion_code IS NULL OR completion_code IN "
            "('COMPLETED','COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE')",
            name="ck_account_deletion_audits_completion_code",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_account_deletion_audits_attempt_count"),
        sa.CheckConstraint(
            "operational_data_delete_by = requested_at + INTERVAL '7 days'",
            name="ck_account_deletion_audits_operational_deadline",
        ),
        sa.CheckConstraint(
            "backup_expiry_due_at = requested_at + INTERVAL '30 days'",
            name="ck_account_deletion_audits_backup_deadline",
        ),
        sa.CheckConstraint(
            "operational_deleted_at IS NOT NULL",
            name="ck_account_deletion_audits_operational_deleted",
        ),
        sa.CheckConstraint(
            "(status_code IN ('COMPLETED','COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE') "
            "AND completed_at IS NOT NULL AND backup_expiry_verified_at IS NOT NULL "
            "AND completion_code = status_code) OR "
            "(status_code = 'BACKUP_EXPIRY_PENDING' AND completed_at IS NULL "
            "AND completion_code IS NULL)",
            name="ck_account_deletion_audits_completion",
        ),
        sa.CheckConstraint(
            "policy_version = 'account-deletion-retention-v1'",
            name="ck_account_deletion_audits_policy_version",
        ),
        sa.PrimaryKeyConstraint("deletion_request_id"),
        sa.UniqueConstraint("deletion_job_id"),
    )
    op.create_index(
        "ix_account_deletion_audits_backup_deadline",
        "account_deletion_audits",
        ["backup_expiry_due_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_deletion_audits_backup_deadline",
        table_name="account_deletion_audits",
    )
    op.drop_table("account_deletion_audits")
    op.drop_index(
        "ix_account_deletion_jobs_operational_deadline",
        table_name="account_deletion_jobs",
    )
    op.drop_index(
        "ix_account_deletion_jobs_runnable",
        table_name="account_deletion_jobs",
    )
    op.drop_table("account_deletion_jobs")
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        type_="check",
    )
    op.execute("DELETE FROM mutation_idempotency_records WHERE endpoint_code = 'DELETE_ME'")
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING','PUT_ME_CONSENTS','POST_ROUTINES',"
        "'PUT_DAILY_CONTEXT','POST_DECISIONS','POST_DECISION_SELECTION',"
        "'PATCH_WORKOUT_SESSION_START','PATCH_WORKOUT_SESSION_ITEM',"
        "'POST_WORKOUT_TIMER_EVENT','POST_WORKOUT_ADDITIONAL_ACTIVITY',"
        "'POST_WORKOUT_SAFETY_EVENT','PATCH_WORKOUT_SESSION_FINISH',"
        "'PATCH_WORKOUT_SESSION_NOT_COMPLETED','POST_WORKOUT_FEEDBACK',"
        "'POST_WEEKLY_REPORT','POST_WEEKLY_REPORT_ACKNOWLEDGEMENT',"
        "'POST_WEEKLY_PLAN','POST_WEEKLY_PLAN_REVISION')",
    )
