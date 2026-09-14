from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "approve_v2_0_6_catalog.py"
spec = importlib.util.spec_from_file_location("approve_v2_0_6_catalog", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_approve_sets_all_catalog_rows_and_writes_evidence(tmp_path: Path) -> None:
    input_path = tmp_path / "catalog.csv"
    fields = ["stable_code", "review_status_code"]
    with input_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for index in range(237):
            writer.writerow(
                {
                    "stable_code": f"exercise_{index:03d}",
                    "review_status_code": "DOMAIN_APPROVED" if index < 72 else "",
                }
            )

    manifest_path = tmp_path / "approval.json"
    result = module.approve(input_path, manifest_path)

    rows = list(csv.DictReader(input_path.open(encoding="utf-8-sig")))
    assert len(rows) == 237
    assert {row["review_status_code"] for row in rows} == {"DOMAIN_APPROVED"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result["records"] == 237
    assert manifest["reviewer_code"] == "PM_DIRECT_REVIEW"
    assert manifest["after_review_status_counts"] == {"DOMAIN_APPROVED": 237}
