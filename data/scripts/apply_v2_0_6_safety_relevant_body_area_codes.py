"""Fill v2.0.6 safety-relevant body areas from the reviewed source catalog.

The external HK exercise catalog is authoritative when its ``id`` matches a
normalized GymVisual row. Rows without a matching source record use the
explicit, instruction-based decisions below. The field is intentionally not
derived by copying primary or secondary muscle fields.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_SOURCE = Path(
    "/Users/bini/Desktop/Bini/projects/HK_data/exercises-dataset/data/exercise_catalog.json"
)
DEFAULT_REPORT = PROJECT_ROOT / ("data/normalized/v2_0_6_safety_relevant_body_area_source_map.json")

# The safety policy engine's 11 selectable physical body areas. GENERALIZED
# and OTHER are input/control codes, not exercise-specific safety targets.
SAFETY_BODY_AREA_CODES = (
    "NECK",
    "SHOULDER",
    "ELBOW",
    "WRIST_HAND",
    "UPPER_BACK",
    "LOWER_BACK",
    "HIP",
    "KNEE",
    "ANKLE_FOOT",
    "CHEST",
    "ABDOMEN",
)

# The 35 catalog rows not present in the referenced HK source. Values are
# instruction-based decisions, with analogous reviewed movements used only as
# a consistency check. They are keyed by source_identity so row order is not
# part of the decision.
MANUAL_SAFETY_CODES: dict[str, tuple[str, ...]] = {
    "1369": ("HIP", "KNEE", "ANKLE_FOOT"),
    "0041": ("SHOULDER", "ELBOW", "WRIST_HAND", "UPPER_BACK"),
    "0116": ("WRIST_HAND", "UPPER_BACK", "LOWER_BACK", "HIP", "KNEE"),
    "0140": (
        "SHOULDER",
        "ELBOW",
        "WRIST_HAND",
        "UPPER_BACK",
        "ABDOMEN",
    ),
    "1373": ("HIP", "KNEE", "ANKLE_FOOT"),
    "0201": ("SHOULDER", "ELBOW", "WRIST_HAND"),
    "1271": ("SHOULDER", "ELBOW", "CHEST"),
    "1760": (
        "SHOULDER",
        "WRIST_HAND",
        "UPPER_BACK",
        "LOWER_BACK",
        "HIP",
        "KNEE",
        "ANKLE_FOOT",
        "CHEST",
        "ABDOMEN",
    ),
    "0334": ("SHOULDER", "ELBOW", "WRIST_HAND", "UPPER_BACK"),
    "0335": ("SHOULDER", "ELBOW", "WRIST_HAND", "UPPER_BACK"),
    "0372": ("SHOULDER", "ELBOW", "WRIST_HAND", "CHEST"),
    "0378": (
        "SHOULDER",
        "ELBOW",
        "WRIST_HAND",
        "UPPER_BACK",
        "LOWER_BACK",
        "HIP",
        "KNEE",
    ),
    "0406": ("SHOULDER", "WRIST_HAND", "UPPER_BACK", "LOWER_BACK"),
    "0416": ("SHOULDER", "ELBOW", "WRIST_HAND"),
    "2796": (
        "SHOULDER",
        "WRIST_HAND",
        "UPPER_BACK",
        "LOWER_BACK",
        "HIP",
        "KNEE",
        "ANKLE_FOOT",
    ),
    "1559": ("LOWER_BACK", "HIP", "KNEE", "ANKLE_FOOT"),
    "0854": ("SHOULDER", "ELBOW", "WRIST_HAND"),
    "0499": (
        "SHOULDER",
        "ELBOW",
        "WRIST_HAND",
        "UPPER_BACK",
        "LOWER_BACK",
        "HIP",
        "KNEE",
        "ABDOMEN",
    ),
    "1386": ("HIP", "KNEE", "ANKLE_FOOT"),
    "0109": ("SHOULDER", "ELBOW", "WRIST_HAND", "UPPER_BACK"),
    "0662": ("SHOULDER", "ELBOW", "WRIST_HAND", "CHEST", "ABDOMEN"),
    "1000": ("HIP", "KNEE", "ANKLE_FOOT"),
    "0082": ("ELBOW", "WRIST_HAND"),
    "0688": ("SHOULDER", "ELBOW", "WRIST_HAND", "UPPER_BACK", "ABDOMEN"),
    "0861": (
        "SHOULDER",
        "ELBOW",
        "WRIST_HAND",
        "UPPER_BACK",
        "LOWER_BACK",
        "HIP",
        "KNEE",
        "ABDOMEN",
    ),
    "1390": (
        "UPPER_BACK",
        "LOWER_BACK",
        "HIP",
        "KNEE",
        "ANKLE_FOOT",
    ),
    "0599": ("HIP", "KNEE", "ANKLE_FOOT"),
    "2567": (
        "ELBOW",
        "UPPER_BACK",
        "LOWER_BACK",
        "HIP",
        "KNEE",
        "ANKLE_FOOT",
    ),
    "0721": ("SHOULDER", "ELBOW", "WRIST_HAND"),
    "0763": ("HIP", "KNEE", "ANKLE_FOOT"),
    "0794": ("UPPER_BACK", "LOWER_BACK", "HIP", "KNEE", "ABDOMEN"),
    "0817": ("SHOULDER", "ELBOW"),
    "1604": (
        "SHOULDER",
        "WRIST_HAND",
        "UPPER_BACK",
        "LOWER_BACK",
        "HIP",
        "KNEE",
        "ANKLE_FOOT",
        "ABDOMEN",
    ),
    "1428": ("SHOULDER", "ELBOW", "WRIST_HAND"),
    "0126": ("ELBOW", "WRIST_HAND"),
}


class SafetyBodyAreaError(ValueError):
    """Raised when safety body-area input or output is invalid."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SafetyBodyAreaError(f"cannot read source JSON: {path}") from exc
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise SafetyBodyAreaError("source JSON must be an array of objects")
    return value


def _validate_codes(identity: str, codes: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = tuple(str(code).strip() for code in codes if str(code).strip())
    if not normalized:
        raise SafetyBodyAreaError(f"safety codes are empty for {identity}")
    if len(set(normalized)) != len(normalized):
        raise SafetyBodyAreaError(f"safety codes are duplicated for {identity}")
    invalid = sorted(set(normalized) - set(SAFETY_BODY_AREA_CODES))
    if invalid:
        raise SafetyBodyAreaError(f"invalid safety codes for {identity}: {invalid}")
    return normalized


def _read_catalog(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            field_order = list(reader.fieldnames or [])
            rows = list(reader)
    except OSError as exc:
        raise SafetyBodyAreaError(f"cannot read catalog: {path}") from exc
    if "source_identity" not in field_order or "safety_relevant_body_area_codes" not in field_order:
        raise SafetyBodyAreaError("catalog is missing source_identity or safety field")
    if any(None in row for row in rows):
        raise SafetyBodyAreaError("catalog contains a row wider than its header")
    identities = [row["source_identity"].strip() for row in rows]
    if any(not identity for identity in identities) or len(set(identities)) != len(identities):
        raise SafetyBodyAreaError("source_identity must be non-empty and unique")
    return rows, field_order


def apply(
    catalog_path: Path = DEFAULT_CATALOG,
    source_path: Path = DEFAULT_SOURCE,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, int | str]:
    rows, field_order = _read_catalog(catalog_path)
    source_rows = _read_json(source_path)
    source_by_id: dict[str, dict[str, Any]] = {}
    for source_row in source_rows:
        identity = str(source_row.get("id") or "").strip()
        if not identity or identity in source_by_id:
            raise SafetyBodyAreaError(f"source id is blank or duplicated: {identity}")
        source_by_id[identity] = source_row

    catalog_ids = {row["source_identity"].strip() for row in rows}
    missing_manual = sorted(catalog_ids - set(source_by_id) - set(MANUAL_SAFETY_CODES))
    if missing_manual:
        raise SafetyBodyAreaError(
            "catalog rows are missing both source and manual decisions: "
            + ", ".join(missing_manual)
        )

    direct_count = 0
    manual_count = 0
    provenance: list[dict[str, Any]] = []
    for row in rows:
        identity = row["source_identity"].strip()
        if identity in source_by_id:
            raw_codes = source_by_id[identity].get("exercise_contraindicated_pain_regions")
            if not isinstance(raw_codes, list):
                raise SafetyBodyAreaError(f"source safety regions are not a list for {identity}")
            codes = _validate_codes(identity, raw_codes)
            source_type = "HK_EXERCISE_CATALOG_DIRECT"
            direct_count += 1
        else:
            codes = _validate_codes(identity, MANUAL_SAFETY_CODES[identity])
            source_type = "INSTRUCTION_REVIEW_MANUAL"
            manual_count += 1
        row["safety_relevant_body_area_codes"] = "|".join(codes)
        provenance.append(
            {
                "source_identity": identity,
                "name_en": row.get("name_en", ""),
                "name_ko": row.get("name_ko", ""),
                "source_type": source_type,
                "safety_relevant_body_area_codes": list(codes),
                "instruction_summary_ko": row.get("instruction_summary_ko", "")
                if source_type == "INSTRUCTION_REVIEW_MANUAL"
                else None,
            }
        )

    with catalog_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_order, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "status": "DRAFT",
        "policy": {
            "field": "safety_relevant_body_area_codes",
            "selectable_body_area_codes": list(SAFETY_BODY_AREA_CODES),
            "primary_secondary_copy": False,
            "manual_basis": "instruction_summary_ko and analogous reviewed movement checks",
        },
        "catalog_source": {"path": str(catalog_path), "sha256": _sha256(catalog_path)},
        "hk_source": {"path": str(source_path), "sha256": _sha256(source_path)},
        "counts": {
            "catalog_records": len(rows),
            "direct_source_records": direct_count,
            "manual_instruction_review_records": manual_count,
        },
        "records": provenance,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "catalog_records": len(rows),
        "direct_source_records": direct_count,
        "manual_instruction_review_records": manual_count,
        "report": str(report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = apply(args.catalog, args.source, args.report)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
