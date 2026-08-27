"""Import the approved V2 backend bundle and optionally activate its catalog.

The V1/merged importer remains unchanged. This command accepts only the exact
approved bundle and taxonomy hashes and leaves the catalog DRAFT unless the
operator explicitly passes ``--activate``.
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

APPROVED_BUNDLE_MANIFEST_SHA256 = "5974ed95fdc9598000d9ac4e84c600ddac3d1caec245f04a29ad46e592be4206"
APPROVED_TAXONOMY_REGISTRY_SHA256 = (
    "79e487cc1a41ea39db9b4afb0799b3297840de878a2ae4ed621ef3e4403a0985"
)
V2_CATALOG_VERSION_CODE = "exercise-catalog-v2.0.1-final"
DEFAULT_BUNDLE_DIRECTORY = Path("data/generated/exercise-catalog-v2.0.1-final/backend_bundle")


def promote_v2(
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
    parser.add_argument(
        "--bundle-directory",
        type=Path,
        default=DEFAULT_BUNDLE_DIRECTORY,
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="activate the validated V2 catalog after the atomic import commits",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as session:
            result = promote_v2(session, args.bundle_directory, app_env=settings.app_env)
        if args.activate:
            with Session(engine) as session, session.begin():
                activate(session, V2_CATALOG_VERSION_CODE, now=datetime.now(UTC))
    finally:
        engine.dispose()
    print(
        "validated V2 bundle: "
        f"catalogs={sum(item.exercise_record_count for item in result.catalogs)}, "
        f"safety={result.safety_rules.record_count}, "
        f"alternatives={result.alternatives.record_count}, "
        f"prescriptions={result.prescriptions.record_count}, "
        f"media={result.media_assets.record_count if result.media_assets else 0}, "
        f"activated={args.activate}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
