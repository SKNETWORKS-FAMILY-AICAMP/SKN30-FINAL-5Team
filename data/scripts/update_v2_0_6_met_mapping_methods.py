#!/usr/bin/env python3
"""Create a targeted MET mapping-method correction copy of the v2.0.6 catalog."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog_updated.csv"
)

# Only rows with an explicit Compendium core-exercise match are included.
# Ambiguous intensity or activity correspondence remains unchanged.
METHOD_CORRECTIONS = {
    "0032": "DIRECT_VARIANT",
    "0116": "DIRECT_VARIANT",
    "0274": "DIRECT_VARIANT",
    "3470": "DIRECT_VARIANT",
    "0872": "DIRECT_VARIANT",
    "2368": "DIRECT_VARIANT",
    "0259": "DIRECT_VARIANT",
    "1760": "DIRECT_VARIANT",
    "2796": "DIRECT_VARIANT",
    "0662": "DIRECT",
    "0026": "DIRECT_VARIANT",
    "0043": "DIRECT_VARIANT",
    "0054": "DIRECT_VARIANT",
    "0063": "DIRECT_VARIANT",
    "0069": "DIRECT_VARIANT",
    "0085": "DIRECT_VARIANT",
    "0117": "DIRECT_VARIANT",
    "0262": "DIRECT_VARIANT",
    "0291": "DIRECT_VARIANT",
    "0300": "DIRECT_VARIANT",
    "0410": "DIRECT_VARIANT",
    "0469": "DIRECT_VARIANT",
    "0514": "DIRECT_VARIANT",
    "0635": "DIRECT_VARIANT",
    "0659": "DIRECT_VARIANT",
    "0691": "DIRECT_VARIANT",
    "0768": "DIRECT_VARIANT",
    "0769": "DIRECT_VARIANT",
    "1001": "DIRECT_VARIANT",
    "1460": "DIRECT_VARIANT",
    "1476": "DIRECT_VARIANT",
    "1689": "DIRECT_VARIANT",
    "2398": "DIRECT_VARIANT",
    "3011": "DIRECT_VARIANT",
    "3016": "DIRECT",
    "3220": "DIRECT_VARIANT",
    "3640": "DIRECT_VARIANT",
    "3662": "DIRECT_VARIANT",
    "3769": "DIRECT_VARIANT",
}

# These rows were previously attached to an activity that did not name the
# exercise's core movement. Update only the MET pair when the direct activity
# is explicit in the Compendium table.
MET_CORRECTIONS = {
    "0054": ("02056", "3.0"),
    "0769": ("02056", "3.0"),
    "1001": ("02056", "3.0"),
    "1689": ("02056", "3.0"),
    "2796": ("02056", "3.0"),
}


def update(input_path: Path, output_path: Path) -> list[dict[str, str]]:
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        if "met_mapping_method_code" not in fields:
            raise ValueError("met_mapping_method_code column is missing")
        rows = list(reader)

    by_identity = {row.get("source_identity", ""): row for row in rows}
    missing = sorted(set(METHOD_CORRECTIONS) - set(by_identity))
    if missing:
        raise ValueError("correction source_identity values are missing: " + ", ".join(missing))

    changed = []
    for row in rows:
        identity = row.get("source_identity", "")
        recommended = METHOD_CORRECTIONS.get(identity)
        met_correction = MET_CORRECTIONS.get(identity)
        changed_fields = []
        if recommended and row["met_mapping_method_code"] != recommended:
            changed_fields.append("met_mapping_method_code")
        if met_correction:
            activity_code, met_value = met_correction
            if row.get("met_source_activity_code") != activity_code:
                changed_fields.append("met_source_activity_code")
            if row.get("met_value") != met_value:
                changed_fields.append("met_value")
        if changed_fields:
            old_method = row["met_mapping_method_code"]
            old_activity_code = row.get("met_source_activity_code", "")
            old_met_value = row.get("met_value", "")
            if met_correction:
                row["met_source_activity_code"] = met_correction[0]
                row["met_value"] = met_correction[1]
            if recommended:
                row["met_mapping_method_code"] = recommended
            changed.append(
                {
                    "source_identity": identity,
                    "name_ko": row.get("name_ko", ""),
                    "old_method": old_method,
                    "new_method": recommended,
                    "old_met_value": old_met_value,
                    "new_met_value": row.get("met_value", ""),
                    "old_met_source_activity_code": old_activity_code,
                    "new_met_source_activity_code": row.get(
                        "met_source_activity_code", ""
                    ),
                    "changed_fields": changed_fields,
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(row for row in rows)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    changed = update(args.input, args.output)
    print({"input": str(args.input), "output": str(args.output), "changed_rows": len(changed)})
    for row in changed:
        print(row)


if __name__ == "__main__":
    main()
