"""Record the exact merged-catalog data approval.

The migration promotes only already-loaded rows whose versions, manifest hashes, and
record counts exactly match the approval record. Catalog activation remains an explicit
`catalog_activate` operation after this migration.

Revision ID: 0022_promote_merged_data
Revises: 0021_merged_catalog_source
Create Date: 2026-08-20
"""

# ruff: noqa: E501 -- keeping approval SQL and immutable hashes visually auditable

from collections.abc import Sequence

from alembic import op

revision: str = "0022_promote_merged_data"
down_revision: str | None = "0021_merged_catalog_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATALOG_VERSION = "merged-mvp-v0.4.0"
CATALOG_HASH = "5686be3d379c8e3742e7e891b9fb5265215aaebd4c3b3c0ec76a000b3175a9a1"
CATALOG_COUNT = 56
SAFETY_VERSION = "merged-mvp-v0.5.0"
SAFETY_HASH = "e42133f2550b6bd4d82063668200f6c08fe57be1445fe8e462cba92487961172"
SAFETY_COUNT = 282
ALTERNATIVE_VERSION = "merged-mvp-v0.4.0"
ALTERNATIVE_HASH = "8acc955f5ce24b145b9e0041ff7c70df89274d4cefa0b9a69c9429e3ecf4bb24"
ALTERNATIVE_COUNT = 238
PRESCRIPTION_VERSION = "merged-mvp-v0.1.0"
PRESCRIPTION_HASH = "0ff5bf451345a57b6152cacc6d90e4aeb3cc9da5283093b2863ffbcd8af87273"
GOAL_COUNT = 32
PRESCRIPTION_COUNT = 36
APPROVAL_CODE = "MERGED-MVP-20260820-PM-DOMAIN-APPROVAL"


def _approval_json(hash_value: str, record_count: int) -> str:
    return (
        "jsonb_build_object("
        f"'approval_record_code', '{APPROVAL_CODE}', "
        "'approved_on', '2026-08-20', "
        "'approver_role_codes', jsonb_build_array('DEVELOPMENT_LEAD', 'PM', 'DOMAIN_REVIEWER'), "
        "'scope', 'ALL_RECORDS', "
        f"'manifest_sha256', '{hash_value}', 'record_count', {record_count})"
    )


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        DECLARE catalog_id uuid;
        DECLARE matched integer;
        BEGIN
          SELECT id INTO catalog_id FROM catalog_versions
          WHERE version_code = '{CATALOG_VERSION}';
          IF catalog_id IS NULL THEN RETURN; END IF;
          IF EXISTS (
            SELECT 1 FROM catalog_versions WHERE id = catalog_id
              AND (source_manifest_hash <> '{CATALOG_HASH}' OR exercise_record_count <> {CATALOG_COUNT})
          ) THEN RAISE EXCEPTION 'approved merged catalog hash or count mismatch'; END IF;

          SELECT count(*) INTO matched FROM exercise_safety_rules
          WHERE rule_set_version_code = '{SAFETY_VERSION}';
          IF matched <> {SAFETY_COUNT} OR EXISTS (
            SELECT 1 FROM exercise_safety_rules
            WHERE rule_set_version_code = '{SAFETY_VERSION}'
              AND (source_manifest_hash <> '{SAFETY_HASH}' OR catalog_version_id <> catalog_id)
          ) THEN RAISE EXCEPTION 'approved merged safety rules mismatch'; END IF;

          SELECT count(*) INTO matched FROM exercise_alternatives ea
          JOIN exercises source ON source.id = ea.source_exercise_id
          WHERE ea.alternative_set_version_code = '{ALTERNATIVE_VERSION}';
          IF matched <> {ALTERNATIVE_COUNT} OR EXISTS (
            SELECT 1 FROM exercise_alternatives ea
            JOIN exercises source ON source.id = ea.source_exercise_id
            JOIN exercises alternative ON alternative.id = ea.alternative_exercise_id
            WHERE ea.alternative_set_version_code = '{ALTERNATIVE_VERSION}'
              AND (ea.source_manifest_hash <> '{ALTERNATIVE_HASH}'
                   OR source.catalog_version_id <> catalog_id
                   OR alternative.catalog_version_id <> catalog_id)
          ) THEN RAISE EXCEPTION 'approved merged alternatives mismatch'; END IF;

          SELECT count(*) INTO matched FROM exercise_goal_tag_links link
          JOIN exercises exercise ON exercise.id = link.exercise_id
          WHERE exercise.catalog_version_id = catalog_id;
          IF matched <> {GOAL_COUNT} THEN RAISE EXCEPTION 'approved goal tag count mismatch'; END IF;
          SELECT count(*) INTO matched FROM exercise_prescription_profiles profile
          JOIN exercises exercise ON exercise.id = profile.exercise_id
          WHERE exercise.catalog_version_id = catalog_id;
          IF matched <> {PRESCRIPTION_COUNT} THEN
            RAISE EXCEPTION 'approved prescription count mismatch';
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM catalog_versions
            WHERE id = catalog_id
              AND manifest_metadata #>> '{{prescription_artifact,version_code}}' = '{PRESCRIPTION_VERSION}'
              AND manifest_metadata #>> '{{prescription_artifact,manifest_sha256}}' = '{PRESCRIPTION_HASH}'
          ) THEN RAISE EXCEPTION 'approved prescription manifest mismatch'; END IF;
        END $$;
        """
    )
    catalog_approval = _approval_json(CATALOG_HASH, CATALOG_COUNT)
    safety_approval = _approval_json(SAFETY_HASH, SAFETY_COUNT)
    alternative_approval = _approval_json(ALTERNATIVE_HASH, ALTERNATIVE_COUNT)
    prescription_approval = _approval_json(PRESCRIPTION_HASH, GOAL_COUNT + PRESCRIPTION_COUNT)
    op.execute(
        f"UPDATE catalog_versions SET review_method_code = 'DOMAIN_REVIEWER', "
        "status_interpretation_code = 'PRODUCTION_APPROVED', "
        f"manifest_metadata = jsonb_set(manifest_metadata || jsonb_build_object('production_approval', {catalog_approval}), "
        f"'{{prescription_artifact,production_approval}}', {prescription_approval}, true) "
        f"WHERE version_code = '{CATALOG_VERSION}' AND source_manifest_hash = '{CATALOG_HASH}'"
    )
    op.execute(
        f"UPDATE exercise_safety_rules SET production_eligible = true, "
        f"source_metadata = source_metadata || jsonb_build_object('production_approval', {safety_approval}) "
        f"WHERE rule_set_version_code = '{SAFETY_VERSION}' AND source_manifest_hash = '{SAFETY_HASH}'"
    )
    op.execute(
        f"UPDATE exercise_alternatives SET production_eligible = true, "
        f"source_metadata = source_metadata || jsonb_build_object('production_approval', {alternative_approval}) "
        f"WHERE alternative_set_version_code = '{ALTERNATIVE_VERSION}' "
        f"AND source_manifest_hash = '{ALTERNATIVE_HASH}'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE exercise_safety_rules SET production_eligible = false, "
        "source_metadata = source_metadata - 'production_approval' "
        f"WHERE rule_set_version_code = '{SAFETY_VERSION}' AND source_manifest_hash = '{SAFETY_HASH}'"
    )
    op.execute(
        f"UPDATE exercise_alternatives SET production_eligible = false, "
        "source_metadata = source_metadata - 'production_approval' "
        f"WHERE alternative_set_version_code = '{ALTERNATIVE_VERSION}' "
        f"AND source_manifest_hash = '{ALTERNATIVE_HASH}'"
    )
    op.execute(
        f"UPDATE catalog_versions SET production_eligible = false, status_code = 'DRAFT', "
        "activated_at = NULL, review_method_code = 'AGENT_ONLY', "
        "status_interpretation_code = 'PIPELINE_COMPATIBILITY_ONLY', "
        "manifest_metadata = (manifest_metadata - 'production_approval') "
        "#- '{prescription_artifact,production_approval}' "
        f"WHERE version_code = '{CATALOG_VERSION}' AND source_manifest_hash = '{CATALOG_HASH}'"
    )
