from __future__ import annotations

import csv
import json

from data.scripts import build_gymvisual_cross_source_review as builder


def test_published_review_queue_is_fail_closed_and_reproducible() -> None:
    manifest = builder.build()
    with (builder.OUTPUT_DIR / "cross_source_media_candidates.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert manifest["output"]["candidate_rows"] == 8
    assert manifest["output"]["catalog_exercises"] == 4
    assert manifest["output"]["exact_match_candidates"] == 2
    assert manifest["production_eligible"] is False
    assert {row["review_status"] for row in rows} == {"REVIEW_REQUIRED"}
    assert {row["automatic_binding"] for row in rows} == {"false"}
    assert {row["production_eligible"] for row in rows} == {"false"}
    assert {
        (row["representative_exercise_id"], row["gymvisual_source_identity"]) for row in rows
    } >= {("REX-000061", "0549"), ("REX-000093", "0043")}

    first_csv = (builder.OUTPUT_DIR / "cross_source_media_candidates.csv").read_bytes()
    first_manifest = json.loads((builder.OUTPUT_DIR / "manifest.json").read_text(encoding="utf-8"))
    builder.build()
    assert (builder.OUTPUT_DIR / "cross_source_media_candidates.csv").read_bytes() == first_csv
    assert (
        json.loads((builder.OUTPUT_DIR / "manifest.json").read_text(encoding="utf-8"))
        == first_manifest
    )
