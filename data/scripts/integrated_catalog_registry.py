"""Permanent identifiers for the integrated exercise catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = DATA_ROOT / "normalized" / "integrated_catalog_id_registry.json"
REGISTRY_VERSION = "integrated-catalog-id-registry-v1"

# These are explicit duplicate candidates, not confirmed merges.
DUPLICATE_CANDIDATE_GROUPS = {
    ("gymvisual", "0300"): "DUP-CANDIDATE-001",
    ("wger", "1370"): "DUP-CANDIDATE-001",
    ("gymvisual", "1760"): "DUP-CANDIDATE-002",
    ("wger", "203"): "DUP-CANDIDATE-002",
}


class RegistryError(ValueError):
    """Raised when the permanent ID registry is incomplete or inconsistent."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError(f"invalid registry JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RegistryError("registry root must be an object")
    return value


def load_registry(path: Path = REGISTRY_PATH) -> dict[tuple[str, str], dict[str, str]]:
    document = _read_json(path)
    if document.get("registry_version") != REGISTRY_VERSION:
        raise RegistryError("unsupported registry version")
    records = document.get("records")
    if not isinstance(records, list):
        raise RegistryError("registry records must be a list")
    result: dict[tuple[str, str], dict[str, str]] = {}
    catalog_ids: set[str] = set()
    normalized_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise RegistryError("registry record must be an object")
        required = ("source_system", "source_id", "catalog_id", "normalized_exercise_id")
        if any(not str(record.get(key, "")).strip() for key in required):
            raise RegistryError(f"registry record is incomplete: {record}")
        key = (str(record["source_system"]), str(record["source_id"]))
        if key in result:
            raise RegistryError(f"duplicate source key in registry: {key}")
        if str(record["catalog_id"]) in catalog_ids:
            raise RegistryError(f"duplicate catalog_id in registry: {record['catalog_id']}")
        catalog_ids.add(str(record["catalog_id"]))
        normalized_ids.add(str(record["normalized_exercise_id"]))
        result[key] = {str(k): str(v) for k, v in record.items()}
    return result


def lookup(
    source_system: str, source_id: str, registry: dict[tuple[str, str], dict[str, str]]
) -> dict[str, str]:
    key = (source_system, source_id)
    try:
        return registry[key]
    except KeyError as exc:
        raise RegistryError(f"source key is missing from permanent registry: {key}") from exc


def _next_number(values: list[str], prefix: str) -> int:
    numbers = [int(value.removeprefix(prefix)) for value in values if value.startswith(prefix)]
    return max(numbers, default=0) + 1


def bootstrap_registry(
    rows: list[dict[str, str]],
    *,
    existing_path: Path | None = None,
    output_path: Path = REGISTRY_PATH,
) -> None:
    """Create or extend a registry while preserving every existing assignment."""

    existing: dict[tuple[str, str], dict[str, str]] = {}
    if existing_path is not None and existing_path.exists():
        existing = load_registry(existing_path)
    elif output_path.exists():
        existing = load_registry(output_path)

    catalog_next = _next_number([r["catalog_id"] for r in existing.values()], "CAT-")
    normalized_next = _next_number([r["normalized_exercise_id"] for r in existing.values()], "NEX-")
    normalized_by_key = {
        r.get("normalized_key", ""): r["normalized_exercise_id"]
        for r in existing.values()
        if r.get("normalized_key")
    }

    for row in sorted(rows, key=lambda item: (item["source_track"], item["source_identity"])):
        source_system = row["source_track"]
        source_id = row["source_identity"]
        key = (source_system, source_id)
        if key in existing:
            continue
        legacy = row.get("review_normalized_exercise_id", "").strip()
        normalized_key = f"legacy:{legacy}" if legacy else f"source:{source_system}:{source_id}"
        normalized_id = normalized_by_key.get(normalized_key)
        if normalized_id is None:
            normalized_id = f"NEX-{normalized_next:06d}"
            normalized_next += 1
            normalized_by_key[normalized_key] = normalized_id
        existing[key] = {
            "source_system": source_system,
            "source_id": source_id,
            "catalog_id": f"CAT-{catalog_next:06d}",
            "normalized_exercise_id": normalized_id,
            "normalized_key": normalized_key,
            "legacy_review_normalized_exercise_id": legacy,
            "registry_assignment": "BOOTSTRAPPED" if not existing else "APPENDED",
        }
        catalog_next += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": "1.0.0",
        "registry_version": REGISTRY_VERSION,
        "purpose": "Permanent catalog and normalized exercise identifiers.",
        "key": ["source_system", "source_id"],
        "name_or_classification_changes_reissue_ids": False,
        "records": sorted(
            existing.values(), key=lambda record: (record["source_system"], record["source_id"])
        ),
    }
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
