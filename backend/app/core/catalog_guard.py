import json
from pathlib import Path
from typing import Any


class CatalogManifestError(RuntimeError):
    """Raised when catalog approval metadata is unsafe or malformed."""


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogManifestError(f"Catalog manifest is unreadable: {path}") from exc

    if not isinstance(payload, dict):
        raise CatalogManifestError(f"Catalog manifest must be an object: {path}")
    review = payload.get("review")
    if not isinstance(review, dict) or not isinstance(review.get("production_eligible"), bool):
        raise CatalogManifestError(f"Catalog manifest lacks approval metadata: {path}")
    return payload


def validate_catalog_manifests(app_env: str, manifest_paths: tuple[Path, ...]) -> None:
    if app_env == "production" and not manifest_paths:
        raise CatalogManifestError("Production requires approved catalog manifests")

    for path in manifest_paths:
        manifest = _load_manifest(path)
        review = manifest["review"]
        if app_env == "production" and review["production_eligible"] is not True:
            raise CatalogManifestError(f"Catalog manifest is not production eligible: {path}")
