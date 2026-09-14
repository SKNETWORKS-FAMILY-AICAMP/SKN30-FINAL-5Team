"""Import and optionally activate the PM-approved integrated v2.0.8 catalog."""

from __future__ import annotations

import argparse
import hashlib
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
    CatalogImportError,
    load_integrated_catalog_bundle,
)
from backend.scripts.catalog_activate import activate

APPROVED_INTEGRATED_BUNDLE_MANIFEST_SHA256 = (
    "2380df3067f03ea6360b47592db68e3ce531fbda3e300db8188f53714658f401"
)
APPROVED_CATALOG_BUNDLE_MANIFEST_SHA256 = (
    "b1e2bc0da5253722218615d80af7f9fe85b46e0ed08db61dcccb0c5b5f31ecae"
)
APPROVED_TAXONOMY_REGISTRY_SHA256 = (
    "79e487cc1a41ea39db9b4afb0799b3297840de878a2ae4ed621ef3e4403a0985"
)
V2_0_8_CATALOG_VERSION_CODE = "exercise-catalog-v2.0.8-final"
DEFAULT_BUNDLE_DIRECTORY = Path("data/generated/integrated-catalog-v2.0.8-final")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def promote_v2_0_8(
    session: Session,
    bundle_directory: Path,
    *,
    app_env: str,
) -> CatalogDataBundleImportResult:
    manifest_path = bundle_directory / "bundle_manifest.json"
    if _sha256(manifest_path) != APPROVED_INTEGRATED_BUNDLE_MANIFEST_SHA256:
        raise CatalogImportError(
            "APPROVAL_REGISTRY_MISMATCH",
            "integrated v2.0.8 bundle does not match its approved root hash",
        )
    load_integrated_catalog_bundle(
        bundle_directory,
        expected_catalog_version=V2_0_8_CATALOG_VERSION_CODE,
    )
    importer = CatalogDataBundleImporter(
        CatalogRepository(),
        app_env,
        v2_import=True,
        v2_taxonomy_registry_sha256=APPROVED_TAXONOMY_REGISTRY_SHA256,
    )
    return importer.import_v2_bundle(
        session,
        bundle_directory / "catalog",
        expected_bundle_manifest_sha256=APPROVED_CATALOG_BUNDLE_MANIFEST_SHA256,
        allow_production=app_env == "production",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-directory", type=Path, default=DEFAULT_BUNDLE_DIRECTORY)
    parser.add_argument(
        "--activate",
        action="store_true",
        help="activate the imported v2.0.8 catalog after the atomic import commits",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as session:
            result = promote_v2_0_8(
                session,
                args.bundle_directory,
                app_env=settings.app_env,
            )
            session.commit()
            if args.activate:
                activate(session, V2_0_8_CATALOG_VERSION_CODE, now=datetime.now(UTC))
                session.commit()
    finally:
        engine.dispose()
    print(
        "validated v2.0.8 bundle: "
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
