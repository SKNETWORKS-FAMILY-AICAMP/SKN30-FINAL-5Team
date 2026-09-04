from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_6_training_body_focus_review_csv.py"
spec = importlib.util.spec_from_file_location("build_v2_0_6_training_body_focus_review_csv", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_build_rows_sorts_and_leaves_review_inputs_blank() -> None:
    catalog = [
        {
            "source_identity": "0002",
            "name_en": "두 번째",
            "name_ko": "둘",
            "stable_code": None,
            "training_type_code": None,
            "body_focus_code": "CORE",
            "primary_body_area_codes": ["ABDOMEN", "LOWER_BACK"],
            "secondary_body_area_codes": [],
            "form_cues_ko": ["첫 단계", "두 번째 단계"],
            "training_type_review_status": "REVIEW_REQUIRED",
            "body_focus_review_status": "CANDIDATE_READY",
        },
        {
            "source_identity": "0001",
            "name_en": "첫 번째",
            "name_ko": "하나",
            "stable_code": "first",
            "training_type_code": "STRENGTH",
            "body_focus_code": "CHEST",
            "primary_body_area_codes": ["CHEST"],
            "secondary_body_area_codes": ["SHOULDER"],
            "form_cues_ko": ["안내"],
        },
    ]
    rows = module.build_rows(catalog)
    assert [row["source_identity"] for row in rows] == ["0001", "0002"]
    assert rows[0]["stable_code"] == "first"
    assert rows[1]["stable_code"] == ""
    assert rows[0]["training_type_code"] == "STRENGTH"
    assert rows[1]["training_type_code"] == "STRENGTH"
    assert rows[1]["primary_body_area_codes"] == "ABDOMEN|LOWER_BACK"
    assert rows[1]["form_cues_ko"] == "첫 단계|두 번째 단계"
    assert rows[0]["training_type_review_status"] == ""
    assert rows[0]["body_focus_review_status"] == ""
    assert rows[0]["review_note"] == ""


def test_write_csv_uses_utf8_bom_and_preserves_korean(tmp_path: Path) -> None:
    catalog = [
        {
            "source_identity": "0001",
            "name_en": "first",
            "name_ko": "한글 운동",
            "stable_code": "first",
            "training_type_code": "STRENGTH",
            "body_focus_code": "CHEST",
            "primary_body_area_codes": [],
            "secondary_body_area_codes": [],
            "form_cues_ko": ["가슴을 편안히 유지합니다."],
        }
    ]
    output = tmp_path / "review.csv"
    rows = module.build_rows(catalog)
    module.validate_rows(rows, catalog)
    module.write_csv(output, rows)
    raw = output.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    with output.open(encoding="utf-8-sig", newline="") as handle:
        parsed = list(csv.DictReader(handle))
    assert parsed[0]["name_ko"] == "한글 운동"
    assert parsed[0]["form_cues_ko"] == "가슴을 편안히 유지합니다."


def test_candidate_body_focus_overrides_current_value_by_exact_identity() -> None:
    catalog = [
        {
            "source_identity": "0001",
            "name_en": "first",
            "body_focus_code": None,
        },
        {
            "source_identity": "0002",
            "name_en": "second",
            "body_focus_code": "BACK",
        },
    ]
    candidates = [
        {"source_identity": "0001", "body_focus_code_candidate": "CHEST"},
        {"source_identity": "0002", "body_focus_code_candidate": "CHEST"},
    ]
    rows = module.build_rows(catalog, candidates)
    assert rows[0]["body_focus_code"] == "CHEST"
    assert rows[1]["body_focus_code"] == "BACK"
    module.validate_rows(rows, catalog, candidates)


def test_reviewed_override_is_applied_to_the_csv_only() -> None:
    catalog = [{"source_identity": "0168", "name_en": "cable hip adduction"}]
    candidates = [{"source_identity": "0168", "body_focus_code_candidate": None}]
    rows = module.build_rows(catalog, candidates)
    assert rows[0]["body_focus_code"] == "ADDUCTORS"
    assert rows[0]["training_type_code"] == "STRENGTH"
    module.validate_rows(rows, catalog, candidates)


def test_training_type_mapping_preserves_cardio_mobility_and_blank() -> None:
    assert module.training_type_from_body_focus("CARDIO") == "CARDIO"
    assert module.training_type_from_body_focus("MOBILITY") == "MOBILITY"
    assert module.training_type_from_body_focus("GLUTES") == "STRENGTH"
    assert module.training_type_from_body_focus("") == ""


def test_late_reviewed_glute_overrides_are_applied() -> None:
    identities = ("0710", "3006", "3667")
    catalog = [{"source_identity": identity, "name_en": identity} for identity in identities]
    candidates = [
        {"source_identity": identity, "body_focus_code_candidate": None} for identity in identities
    ]
    rows = module.build_rows(catalog, candidates)
    assert {row["source_identity"]: row["body_focus_code"] for row in rows} == {
        "0710": "GLUTES",
        "3006": "GLUTES",
        "3667": "ADDUCTORS",
    }
