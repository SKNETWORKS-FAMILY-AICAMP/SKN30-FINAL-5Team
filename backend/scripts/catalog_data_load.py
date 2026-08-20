"""Load the complete DRAFT MVP catalog bundle into a local/test database.

Usage:
    uv run python -m backend.scripts.catalog_data_load load

The fixed bundle contains one merged catalog, its reviewed safety rules,
directional alternatives, goal tags, and prescriptions. The command is
idempotent and fails closed if an existing version has different content.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.modules.catalog.service import CatalogDataBundleImporter

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GENERATED_ROOT = REPOSITORY_ROOT / "data" / "generated"
CATALOG_DIRECTORIES = (GENERATED_ROOT / "exercise-catalog-seed-merged-mvp-v0.4.0",)
SAFETY_RULE_DIRECTORY = GENERATED_ROOT / "exercise-safety-rules-merged-mvp-v0.5.0"
ALTERNATIVE_DIRECTORY = GENERATED_ROOT / "exercise-alternatives-merged-mvp-v0.4.0"
PRESCRIPTION_DIRECTORY = GENERATED_ROOT / "exercise-prescriptions-merged-mvp-v0.1.0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("load",))
    parser.parse_args(argv)

    settings = get_settings()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as session:
            result = CatalogDataBundleImporter(CatalogRepository(), settings.app_env).import_bundle(
                session,
                CATALOG_DIRECTORIES,
                SAFETY_RULE_DIRECTORY,
                ALTERNATIVE_DIRECTORY,
                PRESCRIPTION_DIRECTORY,
            )
    finally:
        engine.dispose()

    imported_catalogs = sum(item.imported for item in result.catalogs)
    print(
        "catalog bundle ready: "
        f"catalogs={len(result.catalogs)} (new={imported_catalogs}), "
        f"safety_rules={result.safety_rules.record_count} "
        f"(new={result.safety_rules.imported}), "
        f"alternatives={result.alternatives.record_count} "
        f"(new={result.alternatives.imported}), "
        f"prescription_rows={result.prescriptions.record_count} "
        f"(new={result.prescriptions.imported})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
