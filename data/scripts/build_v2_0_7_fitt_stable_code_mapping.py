#!/usr/bin/env python3
"""Build the reviewed NEX-to-v2.0.7 stable-code FITT mapping.

The join is deliberately limited to immutable source identity. Names and other
descriptive fields are never used, so unmatched rows remain review gaps.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
ID_REGISTRY = ROOT / "data/normalized/integrated_catalog_id_registry.json"
FITT_REFERENCE = ROOT / "data/normalized/catalog_enrichment_v3_fitt.csv"
TARGET = ROOT / "data/normalized/v2_0_7_fitt_stable_code_mapping.csv"
REPORT = ROOT / "data/reports/integrated_catalog_v2_0_7/fitt_stable_code_mapping_approval.json"

FIELDNAMES = (
    "exercise_id",
    "exercise_stable_code",
    "source_system",
    "source_id",
    "fitt_template_id",
    "review_status_code",
    "review_method_code",
    "approval_record_code",
    "reviewed_at",
)
APPROVAL_RECORD_CODE = "V2-0-7-FITT-IDENTITY-MAPPING-APPROVAL-2026-09-08-R01"
REVIEWED_AT = "2026-09-08T00:00:00+09:00"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        value = resolved.relative_to(ROOT.resolve())
    except ValueError:
        value = resolved
    return value.as_posix()


def build_rows(
    catalog_rows: list[dict[str, str]],
    registry: dict[str, Any],
    fitt_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[str]]:
    catalog_by_identity: dict[tuple[str, str], dict[str, str]] = {}
    for row in catalog_rows:
        key = (row["source_track"], row["source_identity"])
        if not all(key) or key in catalog_by_identity:
            raise ValueError(f"catalog source identity is blank or duplicated: {key}")
        catalog_by_identity[key] = row

    registry_by_nex: dict[str, dict[str, str]] = {}
    for raw in registry.get("records", []):
        row = {key: str(value) for key, value in raw.items()}
        nex = row.get("normalized_exercise_id", "")
        if not nex or nex in registry_by_nex:
            raise ValueError(f"registry normalized ID is blank or duplicated: {nex!r}")
        registry_by_nex[nex] = row

    result: list[dict[str, str]] = []
    gaps: list[str] = []
    for fitt in fitt_rows:
        nex = fitt.get("exercise_id", "")
        if fitt.get("fitt_status") != "APPROVED":
            raise ValueError(f"FITT row is not approved: {nex}")
        registry_row = registry_by_nex.get(nex)
        if registry_row is None:
            raise ValueError(f"FITT row is absent from the permanent ID registry: {nex}")
        key = (registry_row["source_system"], registry_row["source_id"])
        catalog = catalog_by_identity.get(key)
        if catalog is None:
            gaps.append(nex)
            continue
        result.append(
            {
                "exercise_id": nex,
                "exercise_stable_code": catalog["stable_code"],
                "source_system": key[0],
                "source_id": key[1],
                "fitt_template_id": fitt["fitt_template_id"],
                "review_status_code": "DOMAIN_APPROVED",
                "review_method_code": "IDENTITY_REGISTRY_EXACT_JOIN",
                "approval_record_code": APPROVAL_RECORD_CODE,
                "reviewed_at": REVIEWED_AT,
            }
        )
    result.sort(key=lambda row: row["exercise_stable_code"])
    gaps.sort()
    if len({row["exercise_id"] for row in result}) != len(result):
        raise ValueError("mapping contains duplicate NEX identifiers")
    if len({row["exercise_stable_code"] for row in result}) != len(result):
        raise ValueError("mapping contains duplicate stable codes")
    return result, gaps


def build(target: Path = TARGET, report_path: Path = REPORT) -> dict[str, Any]:
    catalog_rows = _read_csv(CATALOG)
    fitt_rows = _read_csv(FITT_REFERENCE)
    registry = json.loads(ID_REGISTRY.read_text(encoding="utf-8"))
    rows, gaps = build_rows(catalog_rows, registry, fitt_rows)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    report: dict[str, Any] = {
        "schema_version": "fitt-stable-code-mapping-approval-v1",
        "approval_record_code": APPROVAL_RECORD_CODE,
        "review_status_code": "DOMAIN_APPROVED",
        "review_method_code": "IDENTITY_REGISTRY_EXACT_JOIN",
        "reviewed_at": REVIEWED_AT,
        "approver_role_codes": ["BACKEND_DEVELOPMENT_LEAD", "DATA_LEAD", "AI_LEAD"],
        "mapping_path": _display_path(target),
        "mapping_sha256": _sha256(target),
        "mapped_record_count": len(rows),
        "unmatched_fitt_record_count": len(gaps),
        "unmatched_exercise_ids": gaps,
        "source_hashes": {
            "catalog": _sha256(CATALOG),
            "id_registry": _sha256(ID_REGISTRY),
            "fitt_reference": _sha256(FITT_REFERENCE),
        },
        "policy": (
            "Map only exact (source_system, source_id) identities; never infer a mapping "
            "from exercise names, movement patterns, or difficulty."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    print(json.dumps(build(args.target, args.report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
