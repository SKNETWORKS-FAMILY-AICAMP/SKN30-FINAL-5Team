"""Backfill form-cue provenance onto a catalog that is already imported.

Migration 0032 adds ``form_cues_source`` and ``form_cues_review_status``, but a
catalog imported before it exists carries neither, and re-importing is not an
option: ``import_v2_bundle`` refuses a version whose manifest hash has moved, and
the v2.0.2 catalog is live. This reads the values out of the packaged bundle and
writes them onto the matching rows.

Matching is by ``(catalog_version_code, stable_code)`` and the script only ever
sets the two provenance columns, so it cannot alter an exercise's content. Rows
the bundle does not mention are left alone, and a row whose values already match
is not rewritten.

    uv run python -m backend.scripts.backfill_form_cue_provenance --dry-run
    uv run python -m backend.scripts.backfill_form_cue_provenance
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import CatalogVersion, Exercise

DEFAULT_BUNDLE_CATALOG = Path(
    "data/generated/exercise-catalog-v2.0.2-final/backend_bundle/catalog/exercises.jsonl"
)
DEFAULT_CATALOG_VERSION_CODE = "exercise-catalog-v2.0.2-final"


def read_provenance(path: Path) -> dict[str, tuple[str | None, str | None]]:
    """Return {stable_code: (form_cues_source, form_cues_review_status)}."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"bundle catalog is unreadable: {path}") from exc
    provenance: dict[str, tuple[str | None, str | None]] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        record: dict[str, Any] = json.loads(line)
        provenance[str(record["stable_code"])] = (
            record.get("form_cues_source"),
            record.get("form_cues_review_status"),
        )
    return provenance


def backfill(
    session: Session,
    provenance: dict[str, tuple[str | None, str | None]],
    *,
    version_code: str,
    dry_run: bool,
) -> dict[str, Any]:
    catalog = session.scalar(
        select(CatalogVersion).where(CatalogVersion.version_code == version_code)
    )
    if catalog is None:
        raise SystemExit(f"catalog version {version_code!r} is not loaded")

    rows = session.execute(
        select(
            Exercise.id,
            Exercise.stable_code,
            Exercise.form_cues_source,
            Exercise.form_cues_review_status,
        ).where(Exercise.catalog_version_id == catalog.id)
    ).all()

    updated = 0
    unchanged = 0
    unknown: list[str] = []
    for row in rows:
        expected = provenance.get(row.stable_code)
        if expected is None:
            unknown.append(row.stable_code)
            continue
        if (row.form_cues_source, row.form_cues_review_status) == expected:
            unchanged += 1
            continue
        if not dry_run:
            session.execute(
                update(Exercise)
                .where(Exercise.id == row.id)
                .values(form_cues_source=expected[0], form_cues_review_status=expected[1])
            )
        updated += 1

    return {
        "catalog_version_code": version_code,
        "database_rows": len(rows),
        "updated": updated,
        "already_correct": unchanged,
        "not_in_bundle": sorted(unknown),
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-catalog", type=Path, default=DEFAULT_BUNDLE_CATALOG)
    parser.add_argument("--version-code", default=DEFAULT_CATALOG_VERSION_CODE)
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change and write nothing"
    )
    args = parser.parse_args(argv)

    provenance = read_provenance(args.bundle_catalog)
    settings = get_settings()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as session:
            report = backfill(
                session,
                provenance,
                version_code=args.version_code,
                dry_run=args.dry_run,
            )
            if not args.dry_run:
                session.commit()
    finally:
        engine.dispose()

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
