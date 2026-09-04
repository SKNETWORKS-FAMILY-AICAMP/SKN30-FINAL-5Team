from __future__ import annotations

import csv
import json
from pathlib import Path

from data.scripts import fill_v2_0_6_fitt_defaults as target


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "normalized/v2_0_6_exercise_catalog.csv"


def test_real_catalog_has_complete_description_based_fitt_values(tmp_path: Path) -> None:
    output = tmp_path / "catalog.csv"
    report = tmp_path / "report.json"
    output.write_bytes(CATALOG.read_bytes())

    result = target.apply(output, report)

    assert result["catalog_records"] == 237
    assert result["timing_mode_counts"] == {"DURATION": 63, "REPS": 174}
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert all(row["timing_mode_code"] in target.TIMING_MODES for row in rows)
    assert all(row["default_rest_seconds"] in {"30", "60", "90"} for row in rows)
    assert all(row["default_transition_seconds"] == "15" for row in rows)
    assert all(
        row["default_seconds_per_rep"] == "4"
        and not row["default_work_seconds"]
        for row in rows
        if row["timing_mode_code"] == "REPS"
    )
    assert all(
        not row["default_seconds_per_rep"] and row["default_work_seconds"]
        for row in rows
        if row["timing_mode_code"] == "DURATION"
    )
    by_id = {row["source_identity"]: row for row in rows}
    assert by_id["1352"]["timing_mode_code"] == "REPS"
    assert by_id["2133"]["timing_mode_code"] == "DURATION"
    assert by_id["3147"]["timing_mode_code"] == "DURATION"
    assert by_id["3552"]["timing_mode_code"] == "DURATION"
    json.loads(report.read_text(encoding="utf-8"))
