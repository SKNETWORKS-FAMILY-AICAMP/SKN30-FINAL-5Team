"""Import and optionally activate the approved v2.0.6 backend bundle.

This release pins the root bundle hash and all five derived-data approval
records in ``backend.app.modules.catalog.approvals``. Production import is an
explicit opt-in and is available only through this exact approved path.
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

APPROVED_BUNDLE_MANIFEST_SHA256 = "ab0e3d9f9aaa53c5e4572d854830341fb610cdc24040dcc0f2c6c62a6fec9a36"
APPROVED_TAXONOMY_REGISTRY_SHA256 = (
    "79e487cc1a41ea39db9b4afb0799b3297840de878a2ae4ed621ef3e4403a0985"
)
V2_0_6_CATALOG_VERSION_CODE = "exercise-catalog-v2.0.6-final"
DEFAULT_BUNDLE_DIRECTORY = Path("data/generated/exercise-catalog-v2.0.6-final/backend_bundle")


def promote_v2_0_6(
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
        allow_production=app_env == "production",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-directory", type=Path, default=DEFAULT_BUNDLE_DIRECTORY)
    parser.add_argument(
        "--activate",
        action="store_true",
        help="activate the imported v2.0.6 catalog after the atomic import commits",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as session:
            result = promote_v2_0_6(
                session,
                args.bundle_directory,
                app_env=settings.app_env,
            )
            session.commit()
            if args.activate:
                activate(
                    session,
                    V2_0_6_CATALOG_VERSION_CODE,
                    now=datetime.now(UTC),
                )
                session.commit()
    finally:
        engine.dispose()

    print(
        "validated v2.0.6 bundle: "
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
