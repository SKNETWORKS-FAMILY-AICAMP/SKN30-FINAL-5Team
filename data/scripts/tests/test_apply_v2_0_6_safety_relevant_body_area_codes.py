from __future__ import annotations

import csv
import json
from pathlib import Path

from data.scripts import apply_v2_0_6_safety_relevant_body_area_codes as target


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "normalized/v2_0_6_exercise_catalog.csv"
SOURCE = Path(
    "/Users/bini/Desktop/Bini/projects/HK_data/exercises-dataset/data/exercise_catalog.json"
)


def test_real_catalog_is_fully_covered_by_direct_or_manual_decisions(tmp_path: Path) -> None:
    output = tmp_path / "catalog.csv"
    report = tmp_path / "report.json"
    output.write_bytes(CATALOG.read_bytes())

    result = target.apply(output, SOURCE, report)

    assert result["catalog_records"] == 237
    assert result["direct_source_records"] == 202
    assert result["manual_instruction_review_records"] == 35
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert all(row["safety_relevant_body_area_codes"] for row in rows)
    allowed = set(target.SAFETY_BODY_AREA_CODES)
    assert all(
        set(row["safety_relevant_body_area_codes"].split("|")) <= allowed
        for row in rows
    )

    saved_report = json.loads(report.read_text(encoding="utf-8"))
    assert saved_report["counts"] == {
        "catalog_records": 237,
        "direct_source_records": 202,
        "manual_instruction_review_records": 35,
    }


def test_direct_source_values_are_preserved(tmp_path: Path) -> None:
    output = tmp_path / "catalog.csv"
    report = tmp_path / "report.json"
    output.write_bytes(CATALOG.read_bytes())

    target.apply(output, SOURCE, report)
    source_by_id = {
        row["id"]: row
        for row in json.loads(SOURCE.read_text(encoding="utf-8"))
    }
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["source_identity"] in source_by_id:
            expected = source_by_id[row["source_identity"]][
                "exercise_contraindicated_pain_regions"
            ]
            assert row["safety_relevant_body_area_codes"].split("|") == expected
