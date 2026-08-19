from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.modules.account_deletion.codes import ACCOUNT_DELETION_POLICY_VERSION

_COMPLETION_CODE_CHECK = (
    "completion_code IS NULL OR completion_code IN "
    "('COMPLETED','COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE')"
)


class AccountDeletionJob(Base):
    """Temporary user-linked state removed during audit de-identification."""

    __tablename__ = "account_deletion_jobs"
    __table_args__ = (
        CheckConstraint(
            "status_code IN ('PENDING','RUNNING','RETRY_PENDING','FAILED_REQUIRES_REVIEW')",
            name="ck_account_deletion_jobs_status",
        ),
        CheckConstraint(
            "current_stage_code IN ('ACCESS_BLOCK','EXTERNAL_REVOCATION',"
            "'OPERATIONAL_DATA_DELETE','CACHE_AND_WORK_DELETE','AUDIT_DEIDENTIFICATION')",
            name="ck_account_deletion_jobs_stage",
        ),
        CheckConstraint(
            "external_revocation_status_code IN "
            "('NOT_REQUIRED','PENDING','SUCCEEDED','RETRY_PENDING','FAILED_FINAL')",
            name="ck_account_deletion_jobs_external_status",
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code IN "
            "('EXTERNAL_REVOCATION_RETRYABLE','EXTERNAL_REVOCATION_FINAL',"
            "'OPERATIONAL_DATA_DELETE_FAILED')",
            name="ck_account_deletion_jobs_failure_code",
        ),
        CheckConstraint(_COMPLETION_CODE_CHECK, name="ck_account_deletion_jobs_completion_code"),
        CheckConstraint("attempt_count >= 0", name="ck_account_deletion_jobs_attempt_count"),
        CheckConstraint(
            "operational_data_delete_by = requested_at + INTERVAL '7 days'",
            name="ck_account_deletion_jobs_operational_deadline",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "backup_expiry_due_at = requested_at + INTERVAL '30 days'",
            name="ck_account_deletion_jobs_backup_deadline",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "operational_deleted_at IS NULL AND backup_expiry_verified_at IS NULL "
            "AND completed_at IS NULL AND completion_code IS NULL AND audit_expires_at IS NULL",
            name="ck_account_deletion_jobs_pre_deidentification",
        ),
        CheckConstraint(
            f"policy_version = '{ACCOUNT_DELETION_POLICY_VERSION}'",
            name="ck_account_deletion_jobs_policy_version",
        ),
        Index("ix_account_deletion_jobs_runnable", "status_code", "requested_at"),
        Index(
            "ix_account_deletion_jobs_operational_deadline",
            "operational_data_delete_by",
        ),
    )

    deletion_request_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    deletion_job_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, unique=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status_code: Mapped[str] = mapped_column(String(64), nullable=False)
    current_stage_code: Mapped[str] = mapped_column(String(48), nullable=False)
    external_revocation_status_code: Mapped[str] = mapped_column(String(32), nullable=False)
    completion_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operational_data_delete_by: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    operational_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    backup_expiry_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    backup_expiry_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AccountDeletionAudit(Base):
    """Opaque post-deletion audit state with no user or provider linkage."""

    __tablename__ = "account_deletion_audits"
    __table_args__ = (
        CheckConstraint(
            "status_code IN ('BACKUP_EXPIRY_PENDING','COMPLETED',"
            "'COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE')",
            name="ck_account_deletion_audits_status",
        ),
        CheckConstraint(
            "current_stage_code = 'BACKUP_EXPIRY_VERIFICATION'",
            name="ck_account_deletion_audits_stage",
        ),
        CheckConstraint(
            "external_revocation_status_code IN ('NOT_REQUIRED','SUCCEEDED','FAILED_FINAL')",
            name="ck_account_deletion_audits_external_status",
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code = 'EXTERNAL_REVOCATION_FINAL'",
            name="ck_account_deletion_audits_failure_code",
        ),
        CheckConstraint(_COMPLETION_CODE_CHECK, name="ck_account_deletion_audits_completion_code"),
        CheckConstraint("attempt_count >= 0", name="ck_account_deletion_audits_attempt_count"),
        CheckConstraint(
            "operational_data_delete_by = requested_at + INTERVAL '7 days'",
            name="ck_account_deletion_audits_operational_deadline",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "backup_expiry_due_at = requested_at + INTERVAL '30 days'",
            name="ck_account_deletion_audits_backup_deadline",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "operational_deleted_at IS NOT NULL",
            name="ck_account_deletion_audits_operational_deleted",
        ),
        CheckConstraint(
            "(status_code IN ('COMPLETED','COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE') "
            "AND completed_at IS NOT NULL AND backup_expiry_verified_at IS NOT NULL "
            "AND completion_code = status_code) OR "
            "(status_code = 'BACKUP_EXPIRY_PENDING' AND completed_at IS NULL "
            "AND completion_code IS NULL)",
            name="ck_account_deletion_audits_completion",
        ),
        CheckConstraint(
            f"policy_version = '{ACCOUNT_DELETION_POLICY_VERSION}'",
            name="ck_account_deletion_audits_policy_version",
        ),
        Index("ix_account_deletion_audits_backup_deadline", "backup_expiry_due_at"),
    )

    deletion_request_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    deletion_job_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, unique=True)
    status_code: Mapped[str] = mapped_column(String(64), nullable=False)
    current_stage_code: Mapped[str] = mapped_column(String(48), nullable=False)
    external_revocation_status_code: Mapped[str] = mapped_column(String(32), nullable=False)
    completion_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operational_data_delete_by: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    operational_deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    backup_expiry_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    backup_expiry_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["AccountDeletionAudit", "AccountDeletionJob"]
