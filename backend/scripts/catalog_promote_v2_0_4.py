"""Import the approved v2.0.4 backend bundle, and optionally activate it.

Separate from ``catalog_promote_v2_0_3`` on purpose, for the same reason that
command is separate from the v2.0.2 one: each release pins its own bundle hash
so both can be imported and compared side by side before either is activated.

v2.0.4 is v2.0.3 plus seven compound movements that passed domain review for
v2.0.2 and were then dropped before packaging, because a prune filter kept only
records the upstream payload had marked as general-pool candidates. Without
them the approved pool held almost no multi-joint work, so the composer filled
the main block with isolation and stretching. Their safety rules are carried
from v2.0.1 where they were approved; alternatives and media are unchanged.
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

APPROVED_BUNDLE_MANIFEST_SHA256 = "c223bdbf9f439ff1cdb0b404de2267d1e79bd8607c9fc3fd1f25b9d357d3afa7"
V2_0_4_CATALOG_VERSION_CODE = "exercise-catalog-v2.0.4-final"
DEFAULT_BUNDLE_DIRECTORY = Path("data/generated/exercise-catalog-v2.0.4-final/backend_bundle")


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
        help="activate the validated v2.0.4 catalog after the atomic import commits",
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
                    V2_0_4_CATALOG_VERSION_CODE,
                    now=datetime.now(UTC),
                )
                session.commit()
    finally:
        engine.dispose()

    print(
        "validated v2.0.4 bundle: "
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
