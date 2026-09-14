from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_7_fitt_stable_code_mapping.py"
spec = importlib.util.spec_from_file_location("fitt_mapping", SCRIPT)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_builds_only_exact_identity_mappings(tmp_path: Path) -> None:
    target = tmp_path / "mapping.csv"
    report_path = tmp_path / "approval.json"

    report = builder.build(target, report_path)

    with target.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == report["mapped_record_count"] == 89
    assert report["unmatched_fitt_record_count"] == 119
    assert len({row["exercise_id"] for row in rows}) == len(rows)
    assert len({row["exercise_stable_code"] for row in rows}) == len(rows)
    assert {row["review_status_code"] for row in rows} == {"DOMAIN_APPROVED"}
    assert {row["review_method_code"] for row in rows} == {"IDENTITY_REGISTRY_EXACT_JOIN"}
    deadlift = next(row for row in rows if row["exercise_id"] == "NEX-000001")
    assert deadlift["exercise_stable_code"] == "barbell_deadlift_hip_dominant_barbell"
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_rejects_unapproved_fitt_input() -> None:
    catalog = [{"source_track": "gymvisual", "source_identity": "0032", "stable_code": "deadlift"}]
    registry = {
        "records": [
            {
                "source_system": "gymvisual",
                "source_id": "0032",
                "normalized_exercise_id": "NEX-000001",
            }
        ]
    }
    fitt = [
        {
            "exercise_id": "NEX-000001",
            "fitt_status": "REVIEW_REQUIRED",
            "fitt_template_id": "FITT-COMPOUND-HINGE-V1",
        }
    ]

    try:
        builder.build_rows(catalog, registry, fitt)
    except ValueError as exc:
        assert "not approved" in str(exc)
    else:
        raise AssertionError("unapproved FITT must be rejected")
