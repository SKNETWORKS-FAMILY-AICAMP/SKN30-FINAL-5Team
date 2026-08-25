#!/usr/bin/env python3
"""Extract unresolved taxonomy blockers without changing the source catalog."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/reports/representative_exercise_taxonomy_reviewed.csv"
DEFAULT_OUTPUT = ROOT / "data/reports/taxonomy_blocker_review.csv"
BLOCKERS = {
    "EXERCISE_TAXONOMY_MAPPING_REQUIRED",
    "SOURCE_EQUIPMENT_UNSPECIFIED",
    "TOOL_METADATA_UNSPECIFIED",
}
OUTPUT_FIELDS = (
    "exercise_id",
    "exercise_name",
    "current_family",
    "current_pattern",
    "current_equipment",
    "blocker",
    "suggested_family",
    "suggested_pattern",
    "suggested_equipment",
    "review_note",
)


def extract(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    extracted: list[dict[str, str]] = []
    for row in rows:
        blockers = [
            code
            for code in (row.get("review_required_codes", "") or "").split("|")
            if code in BLOCKERS
        ]
        if not blockers:
            continue
        extracted.append(
            {
                "exercise_id": row["representative_id"],
                "exercise_name": row["representative_name_ko"],
                "current_family": row["exercise_family"],
                "current_pattern": row["movement_pattern"],
                "current_equipment": row["equipment"],
                "blocker": "|".join(dict.fromkeys(blockers)),
                "suggested_family": "",
                "suggested_pattern": "",
                "suggested_equipment": "",
                "review_note": (
                    "taxonomy blocker 검토 입력 항목. 근거 확인 전 수정값을 자동 입력하지 않음. "
                    f"taxonomy_review_status={row.get('taxonomy_review_status', '')}"
                ),
            }
        )
    return extracted


def run(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> dict[str, int]:
    with input_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    extracted = extract(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(extracted)
    return {
        "source_rows": len(rows),
        "blocker_rows": len(extracted),
        "blocker_occurrences": sum(row["blocker"].count("|") + 1 for row in extracted),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(run(args.input, args.output))


if __name__ == "__main__":
    main()
