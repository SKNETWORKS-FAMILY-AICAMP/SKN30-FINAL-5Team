"""Import the approved v2.0.2 backend bundle, and optionally activate it.

Separate from ``catalog_promote_v2`` on purpose. That command pins the v2.0.1
bundle hash and must keep working unchanged while v2.0.2 is staged, so the two
releases can be imported and compared side by side before either is activated.

Like the v2.0.1 command this accepts only the exact approved bundle and taxonomy
hashes, and leaves the catalog ``DRAFT`` unless ``--activate`` is passed. The
bundle carries 155 of the 170 v2.0.2 records; the 15 ``VARIANT`` rows without
authored form cues are withheld by the packager, together with every row that
referenced them.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.modules.catalog.service import (
    CatalogDataBundleImporter,
    CatalogDataBundleImportResult,
)
from backend.scripts.catalog_activate import activate
from backend.scripts.catalog_promote_v2 import APPROVED_TAXONOMY_REGISTRY_SHA256

APPROVED_BUNDLE_MANIFEST_SHA256 = "92cb6812da02f4375b5259fb7c55b0c6e1317c6e24986c594467363017050c4e"
V2_0_2_CATALOG_VERSION_CODE = "exercise-catalog-v2.0.2-final"
DEFAULT_BUNDLE_DIRECTORY = Path("data/generated/exercise-catalog-v2.0.2-final/backend_bundle")


def promote(
    session: Session,
    bundle_directory: Path,
    *,
    app_env: str,
) -> CatalogDataBundleImportResult:
    importer = CatalogDataBundleImporter(
        CatalogRepository(),
        app_env,
        v2_import=True,
        v2_taxonomy_registry_sha256=APPROVED_TAXONOMY_REGISTRY_SHA256,
    )
    return importer.import_v2_bundle(
        session,
        bundle_directory,
        expected_bundle_manifest_sha256=APPROVED_BUNDLE_MANIFEST_SHA256,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-directory", type=Path, default=DEFAULT_BUNDLE_DIRECTORY)
    parser.add_argument(
        "--activate",
        action="store_true",
        help="activate the validated v2.0.2 catalog after the atomic import commits",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as session:
            result = promote(session, args.bundle_directory, app_env=settings.app_env)
            session.commit()
            if args.activate:
                activate(
                    session,
                    V2_0_2_CATALOG_VERSION_CODE,
                    now=datetime.now(UTC),
                )
                session.commit()
    finally:
        engine.dispose()

    print(
        "validated v2.0.2 bundle: "
        f"catalogs={sum(item.imported for item in result.catalogs)}/{len(result.catalogs)}, "
        f"safety={result.safety_rules.record_count}, "
        f"alternatives={result.alternatives.record_count}, "
        f"prescriptions={result.prescriptions.record_count}, "
        f"media={result.media_assets.record_count if result.media_assets else 0}, "
        f"activated={args.activate}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
