"""Approve the reviewed safety rules and exercise alternatives.

Revision ID: 0016_approve_safety_data
Revises: 0015_graded_safety_policy
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_approve_safety_data"
down_revision: str | None = "0015_graded_safety_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SAFETY_VERSION = "mvp-v0.3.0"
_SAFETY_HASH = "d3281fb7bcf85d614ace027b1a50587430a6578733aab765f0d0b805dd85f51b"
_SAFETY_COUNT = 354
_ALTERNATIVE_VERSION = "mvp-v0.2.0"
_ALTERNATIVE_HASH = "9875cecc075ff1e3f827243f1ebe4db475dfe9a86985a122febaf2558b81ec7f"
_ALTERNATIVE_COUNT = 238


def upgrade() -> None:
    op.drop_constraint(
        "ck_exercise_safety_rules_production_ineligible",
        "exercise_safety_rules",
        type_="check",
    )
    op.drop_constraint(
        "ck_exercise_alternatives_production_ineligible",
        "exercise_alternatives",
        type_="check",
    )
    op.create_check_constraint(
        "ck_exercise_safety_rules_production_approval",
        "exercise_safety_rules",
        "production_eligible = false OR review_status_code = 'DOMAIN_APPROVED'",
    )
    op.create_check_constraint(
        "ck_exercise_alternatives_production_approval",
        "exercise_alternatives",
        "production_eligible = false OR review_status_code = 'DOMAIN_APPROVED'",
    )
    op.execute(
        f"""
        DO $$
        DECLARE matched_count integer;
        BEGIN
          SELECT count(*) INTO matched_count
          FROM exercise_safety_rules
          WHERE rule_set_version_code = '{_SAFETY_VERSION}';
          IF matched_count <> 0 AND matched_count <> {_SAFETY_COUNT} THEN
            RAISE EXCEPTION
              'approved safety rule count mismatch: expected {_SAFETY_COUNT}, got %',
              matched_count;
          END IF;
          IF matched_count = {_SAFETY_COUNT} AND EXISTS (
            SELECT 1 FROM exercise_safety_rules
            WHERE rule_set_version_code = '{_SAFETY_VERSION}'
              AND (source_manifest_hash <> '{_SAFETY_HASH}'
                   OR review_status_code <> 'DOMAIN_APPROVED')
          ) THEN
            RAISE EXCEPTION 'approved safety rule hash or review status mismatch';
          END IF;
        END $$;
        """
    )
    op.execute(
        f"""
        DO $$
        DECLARE matched_count integer;
        BEGIN
          SELECT count(*) INTO matched_count
          FROM exercise_alternatives
          WHERE alternative_set_version_code = '{_ALTERNATIVE_VERSION}';
          IF matched_count <> 0 AND matched_count <> {_ALTERNATIVE_COUNT} THEN
            RAISE EXCEPTION
              'approved alternative count mismatch: expected {_ALTERNATIVE_COUNT}, got %',
              matched_count;
          END IF;
          IF matched_count = {_ALTERNATIVE_COUNT} AND EXISTS (
            SELECT 1 FROM exercise_alternatives
            WHERE alternative_set_version_code = '{_ALTERNATIVE_VERSION}'
              AND (source_manifest_hash <> '{_ALTERNATIVE_HASH}'
                   OR review_status_code <> 'DOMAIN_APPROVED')
          ) THEN
            RAISE EXCEPTION 'approved alternative hash or review status mismatch';
          END IF;
        END $$;
        """
    )
    approval_metadata_prefix = (
        '\'{"approval_record_code": "ISSUE-53-PM-DOMAIN-APPROVAL", '
        '"approved_on": "2026-08-18", '
        '"approver_role_codes": ["DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"], '
        '"scope": "ALL_RECORDS", '
    )
    safety_approval_metadata = (
        approval_metadata_prefix
        + f'"manifest_sha256": "{_SAFETY_HASH}", "record_count": {_SAFETY_COUNT}}}'
        + "'::jsonb"
    )
    alternative_approval_metadata = (
        approval_metadata_prefix
        + f'"manifest_sha256": "{_ALTERNATIVE_HASH}", '
        + f'"record_count": {_ALTERNATIVE_COUNT}}}'
        + "'::jsonb"
    )
    op.execute(
        f"UPDATE exercise_safety_rules SET production_eligible = true, "
        "source_metadata = source_metadata || "
        f"jsonb_build_object('production_approval', {safety_approval_metadata}) "
        f"WHERE rule_set_version_code = '{_SAFETY_VERSION}' "
        f"AND source_manifest_hash = '{_SAFETY_HASH}'"
    )
    op.execute(
        f"UPDATE exercise_alternatives SET production_eligible = true, "
        "source_metadata = source_metadata || "
        f"jsonb_build_object('production_approval', {alternative_approval_metadata}) "
        f"WHERE alternative_set_version_code = '{_ALTERNATIVE_VERSION}' "
        f"AND source_manifest_hash = '{_ALTERNATIVE_HASH}'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE exercise_safety_rules SET production_eligible = false, "
        "source_metadata = source_metadata - 'production_approval' "
        f"WHERE rule_set_version_code = '{_SAFETY_VERSION}' "
        f"AND source_manifest_hash = '{_SAFETY_HASH}'"
    )
    op.execute(
        f"UPDATE exercise_alternatives SET production_eligible = false, "
        "source_metadata = source_metadata - 'production_approval' "
        f"WHERE alternative_set_version_code = '{_ALTERNATIVE_VERSION}' "
        f"AND source_manifest_hash = '{_ALTERNATIVE_HASH}'"
    )
    op.drop_constraint(
        "ck_exercise_safety_rules_production_approval",
        "exercise_safety_rules",
        type_="check",
    )
    op.drop_constraint(
        "ck_exercise_alternatives_production_approval",
        "exercise_alternatives",
        type_="check",
    )
    op.create_check_constraint(
        "ck_exercise_safety_rules_production_ineligible",
        "exercise_safety_rules",
        "production_eligible = false",
    )
    op.create_check_constraint(
        "ck_exercise_alternatives_production_ineligible",
        "exercise_alternatives",
        "production_eligible = false",
    )
