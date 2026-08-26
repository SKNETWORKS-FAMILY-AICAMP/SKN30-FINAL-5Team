"""Activate a catalog version so the decision engine can read it.

Usage:
    uv run python -m backend.scripts.catalog_activate activate <version_code>
    uv run python -m backend.scripts.catalog_activate activate <version_code> --demo-unreviewed

`DecisionRepository.get_creation_context` only reads a catalog that is ACTIVE,
DOMAIN_APPROVED, production eligible and activated, and
`uq_catalog_versions_single_active` allows exactly one ACTIVE row, so activating
a version always deprecates the one it replaces.

A catalog is refused unless a domain reviewer already approved it, which the
`ck_catalog_versions_production_approval` constraint expresses as
`review_method_code = 'DOMAIN_REVIEWER'` and
`status_interpretation_code = 'PRODUCTION_APPROVED'`. The imported bundle ships
as `AGENT_ONLY` / `PIPELINE_COMPATIBILITY_ONLY`, so it is refused until that
review is recorded.

`--demo-unreviewed` overrides those two fields so the local demo can exercise
the loaded bundle before the review lands. It runs only against a *_demo or
*_test database in local/test, and it records the missing review under
`manifest_metadata["demo_activation"]` the same way the synthetic demo catalog
records its own. It must never be used to promote data outside the demo.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import (
    CatalogVersion,
    Exercise,
    ExerciseAlternative,
    ExerciseGoalTagLink,
    ExerciseMediaAsset,
    ExercisePrescriptionProfile,
    ExerciseSafetyRule,
)
from backend.scripts.demo_seed import _require_demo_database, _require_demo_environment

REVIEWED_METHOD_CODE = "DOMAIN_REVIEWER"
REVIEWED_INTERPRETATION_CODE = "PRODUCTION_APPROVED"
V2_CATALOG_VERSION_CODE = "exercise-catalog-v2.0.0-final"
V2_RULE_SET_VERSION = "safety-rule-set-v2.0.0"
V2_ALTERNATIVE_SET_VERSION = "alternative-set-v2.0.0"
V2_PRESCRIPTION_SET_VERSION = "prescription-set-v2.0.0"


def missing_review_fields(catalog: CatalogVersion) -> tuple[str, ...]:
    """Name the review fields that keep a catalog from being production eligible."""
    missing: list[str] = []
    if catalog.review_method_code != REVIEWED_METHOD_CODE:
        missing.append(
            f"review_method_code={catalog.review_method_code!r} (needs {REVIEWED_METHOD_CODE!r})"
        )
    if catalog.status_interpretation_code != REVIEWED_INTERPRETATION_CODE:
        missing.append(
            f"status_interpretation_code={catalog.status_interpretation_code!r} "
            f"(needs {REVIEWED_INTERPRETATION_CODE!r})"
        )
    return tuple(missing)


def _routine_input_counts(session: Session, catalog: CatalogVersion) -> tuple[int, int]:
    """Count the two tables `RoutineRepository.get_creation_context` inner joins."""
    exercise_ids = select(Exercise.id).where(Exercise.catalog_version_id == catalog.id)
    prescriptions = session.scalar(
        select(func.count())
        .select_from(ExercisePrescriptionProfile)
        .where(ExercisePrescriptionProfile.exercise_id.in_(exercise_ids))
    )
    goal_links = session.scalar(
        select(func.count())
        .select_from(ExerciseGoalTagLink)
        .where(ExerciseGoalTagLink.exercise_id.in_(exercise_ids))
    )
    return int(prescriptions or 0), int(goal_links or 0)


def validate_v2_activation(session: Session, catalog: CatalogVersion) -> None:
    """Fail closed unless every approved V2 component is exact and exposable."""
    if catalog.version_code != V2_CATALOG_VERSION_CODE:
        return
    if catalog.exercise_record_count != 102 or not isinstance(
        catalog.manifest_metadata.get("production_approval"), dict
    ):
        raise SystemExit("refusing to activate V2: catalog approval hash/count is not recorded")
    safety_count = session.scalar(
        select(func.count())
        .select_from(ExerciseSafetyRule)
        .where(
            ExerciseSafetyRule.catalog_version_id == catalog.id,
            ExerciseSafetyRule.rule_set_version_code == V2_RULE_SET_VERSION,
            ExerciseSafetyRule.production_eligible.is_(True),
        )
    )
    alternative_count = session.scalar(
        select(func.count())
        .select_from(ExerciseAlternative)
        .join(Exercise, Exercise.id == ExerciseAlternative.source_exercise_id)
        .where(
            Exercise.catalog_version_id == catalog.id,
            ExerciseAlternative.alternative_set_version_code == V2_ALTERNATIVE_SET_VERSION,
            ExerciseAlternative.production_eligible.is_(True),
        )
    )
    prescription = catalog.manifest_metadata.get("prescription_artifact")
    prescription_valid = (
        isinstance(prescription, dict)
        and prescription.get("version_code") == V2_PRESCRIPTION_SET_VERSION
        and prescription.get("goal_tag_records") == 102
        and prescription.get("prescription_records") == 137
        and isinstance(prescription.get("production_approval"), dict)
    )
    if int(safety_count or 0) != 394 or int(alternative_count or 0) != 285:
        raise SystemExit(
            "refusing to activate V2: approved safety/alternative version or count mismatch"
        )
    if not prescription_valid:
        raise SystemExit("refusing to activate V2: prescription version/hash/count mismatch")
    unapproved_exposable_media = session.scalar(
        select(func.count())
        .select_from(ExerciseMediaAsset)
        .where(
            ExerciseMediaAsset.catalog_version_id == catalog.id,
            ExerciseMediaAsset.media_status == "AVAILABLE",
            ExerciseMediaAsset.rights_review_status == "APPROVED",
            ExerciseMediaAsset.approval_metadata.is_(None),
        )
    )
    if unapproved_exposable_media:
        raise SystemExit(
            "refusing to activate V2: an exposable media asset lacks registry approval"
        )


def activate(
    session: Session,
    version_code: str,
    *,
    now: datetime,
    allow_unreviewed: bool = False,
) -> CatalogVersion:
    """Make `version_code` the single active catalog, or fail closed."""
    catalog = session.scalar(
        select(CatalogVersion).where(CatalogVersion.version_code == version_code)
    )
    if catalog is None:
        raise SystemExit(f"catalog version {version_code!r} not found")

    validate_v2_activation(session, catalog)

    # `get_creation_context` inner joins prescription profiles and goal tag
    # links, and `CatalogImporter` writes neither, so an imported catalog
    # activates into a state where no routine can be built at all. Refused
    # regardless of review: this is missing content, not a missing signature.
    prescriptions, goal_links = _routine_input_counts(session, catalog)
    if not prescriptions or not goal_links:
        raise SystemExit(
            f"refusing to activate {version_code!r}: no routine could be built from it - "
            f"exercise_prescription_profiles={prescriptions}, "
            f"exercise_goal_tag_links={goal_links}. "
            "Both are required by RoutineRepository.get_creation_context and the "
            "catalog importer does not create them."
        )

    missing = missing_review_fields(catalog)
    if missing and not allow_unreviewed:
        raise SystemExit(
            f"refusing to activate {version_code!r}: domain review is not recorded - "
            + "; ".join(missing)
            + ". Record the review first, or pass --demo-unreviewed on a demo database."
        )

    # The single-active index rejects two ACTIVE rows, so the version being
    # replaced steps down in the same transaction before this one comes up.
    session.execute(
        update(CatalogVersion)
        .where(
            CatalogVersion.status_code == "ACTIVE",
            CatalogVersion.version_code != version_code,
        )
        .values(status_code="DEPRECATED", production_eligible=False, activated_at=None)
    )
    session.flush()

    if missing:
        catalog.review_method_code = REVIEWED_METHOD_CODE
        catalog.status_interpretation_code = REVIEWED_INTERPRETATION_CODE
        # Reassigned rather than mutated so the JSONB change is detected.
        catalog.manifest_metadata = {
            **catalog.manifest_metadata,
            "demo_activation": {
                "domain_review": "none - local demo only, not for production",
                "activated_at": now.isoformat(),
                "overridden_fields": list(missing),
            },
        }

    catalog.status_code = "ACTIVE"
    catalog.activated_at = catalog.activated_at or now
    catalog.production_eligible = True
    session.flush()
    return catalog


def _content_counts(session: Session, catalog: CatalogVersion) -> tuple[int, int]:
    exercises = session.scalar(
        select(func.count()).select_from(Exercise).where(Exercise.catalog_version_id == catalog.id)
    )
    rules = session.scalar(
        select(func.count())
        .select_from(ExerciseSafetyRule)
        .where(ExerciseSafetyRule.catalog_version_id == catalog.id)
    )
    return int(exercises or 0), int(rules or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("activate",))
    parser.add_argument("version_code", help="catalog_versions.version_code to activate")
    parser.add_argument(
        "--demo-unreviewed",
        action="store_true",
        help=(
            "local demo only: activate a catalog whose domain review is not recorded, "
            "and store the missing review in manifest_metadata"
        ),
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    database_url = settings.database_url.get_secret_value()
    if args.demo_unreviewed:
        _require_demo_environment()
        database_name = _require_demo_database(database_url)
    else:
        database_name = make_url(database_url).database or ""

    engine = create_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            catalog = activate(
                session,
                args.version_code,
                now=datetime.now(UTC),
                allow_unreviewed=args.demo_unreviewed,
            )
            exercises, rules = _content_counts(session, catalog)
            review_pending = "demo_activation" in catalog.manifest_metadata
    finally:
        engine.dispose()

    print(
        f"activated {args.version_code} in {database_name}: "
        f"exercises={exercises}, safety_rules={rules}"
    )
    if review_pending:
        print(
            "WARNING: domain review is NOT recorded for this catalog. "
            "Local demo only - do not promote this database."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
