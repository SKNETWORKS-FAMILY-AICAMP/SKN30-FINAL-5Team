import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.core.catalog_guard import CatalogManifestError, validate_catalog_manifests


def test_production_requires_at_least_one_manifest() -> None:
    with pytest.raises(CatalogManifestError, match="requires approved"):
        validate_catalog_manifests("production", ())


def test_production_rejects_draft_manifest() -> None:
    payload = json.dumps({"review": {"production_eligible": False}})
    with (
        patch.object(Path, "read_text", return_value=payload),
        pytest.raises(CatalogManifestError, match="not production eligible"),
    ):
        validate_catalog_manifests("production", (Path("manifest.json"),))


def test_production_accepts_eligible_manifest() -> None:
    payload = json.dumps({"review": {"production_eligible": True}})
    with patch.object(Path, "read_text", return_value=payload):
        validate_catalog_manifests("production", (Path("manifest.json"),))


def test_local_validates_manifest_shape_when_configured() -> None:
    with (
        patch.object(Path, "read_text", return_value="{}"),
        pytest.raises(CatalogManifestError, match="lacks approval metadata"),
    ):
        validate_catalog_manifests("local", (Path("manifest.json"),))
