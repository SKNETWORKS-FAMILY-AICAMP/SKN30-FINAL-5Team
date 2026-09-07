from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest


def load_module():
    script = Path(__file__).resolve().parents[1] / "apply_v2_0_6_media_review_corrections.py"
    spec = importlib.util.spec_from_file_location("media_review_corrections", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = load_module()


def write_catalog(path: Path, identities: list[str]) -> list[str]:
    fields = [
        "source_identity",
        "stable_code",
        "name_ko",
        "primary_body_area_codes",
        "secondary_body_area_codes",
        "primary_movement_pattern_code",
        "instruction_summary_ko",
        "form_cues_ko",
        "instruction_content_version",
        "met_value",
        "unrelated",
    ]
    rows = [
        {field: (identity if field == "source_identity" else "old") for field in fields}
        for identity in identities
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return fields


def test_applies_only_the_approved_fields(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    fields = write_catalog(catalog, [*module.CORRECTIONS, "9999"])
    report = module.apply_corrections(catalog, tmp_path / "report.json")

    with catalog.open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["source_identity"]: row for row in csv.DictReader(handle)}
    for identity, corrections in module.CORRECTIONS.items():
        for field, expected in corrections.items():
            assert rows[identity][field] == expected
        assert rows[identity]["met_value"] == "old"
        assert rows[identity]["unrelated"] == "old"
    assert rows["9999"] == {
        field: ("9999" if field == "source_identity" else "old") for field in fields
    }
    assert report["outputs"]["changed_records"] == 7
    assert report["outputs"]["changed_fields"] == sum(
        len(correction) for correction in module.CORRECTIONS.values()
    )


def test_fails_closed_when_an_approved_identity_is_missing(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    write_catalog(catalog, list(module.CORRECTIONS)[1:])
    with pytest.raises(module.MediaReviewCorrectionError, match="absent"):
        module.apply_corrections(catalog, tmp_path / "report.json")
