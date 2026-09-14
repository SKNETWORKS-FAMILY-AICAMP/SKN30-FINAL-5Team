from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[1] / ("merge_v2_0_6_recent_into_normalized.py")
    spec = importlib.util.spec_from_file_location("recent_merge", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


merge_module = load_module()


def catalog_row(stable_code: str, identity: str, name: str) -> dict[str, object]:
    return {
        "stable_code": stable_code,
        "source_identity": identity,
        "name_en": name,
        "primary_body_area_codes": ["CHEST"],
        "secondary_body_area_codes": [],
        "met_value": None,
        "met_source_code": None,
        "met_source_activity_code": None,
        "met_mapping_method_code": "OLD",
        "met_review_status_code": "REVIEW_REQUIRED",
        "met_policy_version": "old",
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: merge_module._text(row.get(field)) for field in fields})


def test_latest_duplicate_and_met_provenance_replace_existing(tmp_path: Path) -> None:
    existing = tmp_path / "canonical.csv"
    write_csv(existing, [catalog_row("a", "1", "old name")])
    latest = tmp_path / "latest.json"
    latest.write_text(
        json.dumps(
            [
                catalog_row("a", "1", "first new name"),
                catalog_row("b", "2", "added name"),
                catalog_row("a", "1", "last new name"),
            ]
        ),
        encoding="utf-8",
    )
    met = tmp_path / "met.csv"
    met_rows = [
        {
            "stable_code": "a",
            "source_identity": "1",
            "met_value": "7.5",
            "met_source_code": "SOURCE",
            "met_source_activity_code": "A1",
            "met_mapping_method_code": "DIRECT",
            "met_review_status_code": "REVIEW_REQUIRED",
            "met_policy_version": "policy",
        },
        {
            "stable_code": "b",
            "source_identity": "2",
            "met_value": "",
            "met_source_code": "",
            "met_source_activity_code": "",
            "met_mapping_method_code": "",
            "met_review_status_code": "REVIEW_REQUIRED",
            "met_policy_version": "policy",
        },
    ]
    write_csv(met, met_rows)
    compendium = tmp_path / "compendium.jsonl"
    compendium.write_text(
        json.dumps(
            {
                "activity_code": "A1",
                "activity_description": "exact",
                "met_value": 7.5,
                "source_id": "SOURCE",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = merge_module.merge(
        existing,
        latest,
        met,
        compendium,
        tmp_path / "reports",
        expected_record_count=2,
    )

    with existing.open(encoding="utf-8-sig", newline="") as handle:
        output = list(csv.DictReader(handle))
    assert [row["stable_code"] for row in output] == ["b", "a"]
    assert output[1]["name_en"] == "last new name"
    assert output[1]["met_value"] == "7.5"
    assert report["counts"]["added"] == 1
    assert report["counts"]["replaced"] == 1
    assert report["inputs"]["latest_catalog_snapshot"]["duplicate_stable_codes_last_wins"] == ["a"]


def test_met_value_not_in_designated_source_fails_closed(tmp_path: Path) -> None:
    existing = tmp_path / "canonical.csv"
    write_csv(existing, [catalog_row("a", "1", "name")])
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps([catalog_row("a", "1", "name")]), encoding="utf-8")
    met = tmp_path / "met.csv"
    write_csv(
        met,
        [
            {
                "stable_code": "a",
                "source_identity": "1",
                "met_value": "8.0",
                "met_source_code": "SOURCE",
                "met_source_activity_code": "A1",
                "met_mapping_method_code": "DIRECT",
                "met_review_status_code": "REVIEW_REQUIRED",
                "met_policy_version": "policy",
            }
        ],
    )
    compendium = tmp_path / "compendium.jsonl"
    compendium.write_text(
        json.dumps(
            {
                "activity_code": "A1",
                "activity_description": "exact",
                "met_value": 7.5,
                "source_id": "SOURCE",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        merge_module.merge(
            existing,
            latest,
            met,
            compendium,
            tmp_path / "reports",
            expected_record_count=1,
        )
    except merge_module.CatalogMergeError as exc:
        assert "does not match designated source" in str(exc)
    else:
        raise AssertionError("unsupported MET value must fail closed")
