from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "merge_v2_0_6_catalog_additions.py"
spec = importlib.util.spec_from_file_location("merge_v2_0_6_catalog_additions", SCRIPT)
assert spec and spec.loader
merge_script = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = merge_script
spec.loader.exec_module(merge_script)

SCHEMA = [
    "stable_code",
    "name_ko",
    "name_en",
    "training_type_code",
    "body_focus_code",
    "primary_movement_pattern_code",
    "difficulty_code",
    "timing_mode_code",
    "default_seconds_per_rep",
    "default_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "recovery_eligible",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "safety_relevant_body_area_codes",
    "equipment_codes",
    "location_codes",
    "instruction_summary_ko",
    "form_cues_ko",
    "instruction_content_version",
    "review_status_code",
    "source_track",
    "source_identity",
    "record_type",
    "family_code",
    "representative_stable_code",
    "general_pool_included",
    "form_cues_source",
    "form_cues_review_status",
]


def existing_record(
    *,
    identity: str = "9000",
    name: str = "Existing exercise",
    stable_code: str = "existing_exercise",
    cues: list[str] | None = None,
    source_track: str = "gymvisual",
) -> dict[str, object]:
    values: dict[str, object] = {
        "stable_code": stable_code,
        "name_ko": "기존 운동",
        "name_en": name,
        "training_type_code": "STRENGTH",
        "body_focus_code": "CORE",
        "primary_movement_pattern_code": "CORE_BRACE",
        "difficulty_code": "BEGINNER",
        "timing_mode_code": "REPS",
        "default_seconds_per_rep": 4,
        "default_work_seconds": None,
        "default_rest_seconds": 60,
        "default_transition_seconds": 15,
        "recovery_eligible": False,
        "primary_body_area_codes": ["ABDOMEN"],
        "secondary_body_area_codes": [],
        "safety_relevant_body_area_codes": [],
        "equipment_codes": ["BODYWEIGHT"],
        "location_codes": ["HOME"],
        "instruction_summary_ko": "기존 운동",
        "form_cues_ko": cues if cues is not None else ["기존 안내"],
        "instruction_content_version": "v1",
        "review_status_code": "DOMAIN_APPROVED",
        "source_track": source_track,
        "source_identity": identity,
        "record_type": "REPRESENTATIVE",
        "family_code": "EXISTING",
        "representative_stable_code": None,
        "general_pool_included": True,
        "form_cues_source": "reviewed",
        "form_cues_review_status": "DOMAIN_APPROVED",
    }
    return {field: values[field] for field in SCHEMA}


def addition(identity: str = "1000", name: str = "New exercise") -> dict[str, object]:
    return {
        "id": identity,
        "name": name,
        "category": "chest",
        "muscle_group": "pectorals",
        "secondary_muscles": ["triceps"],
        "target": "pectorals",
        "equipment": "body weight",
        "instructions_ko": "원문 안내입니다.",
        "instructions_steps_ko": ["첫 단계입니다. ", "두 번째 단계입니다."],
        "exercise_contraindicated_pain_regions": ["SHOULDER"],
    }


def gymvisual_source(
    *items: tuple[str, str], steps: list[str] | None = None
) -> list[dict[str, object]]:
    return [
        {
            "id": identity,
            "name": name,
            "equipment": "body weight",
            "instruction_steps": {"ko": steps or ["첫 단계입니다.", "두 번째 단계입니다."]},
        }
        for identity, name in items
    ]


def test_direct_mapping_leaves_unknown_fields_unresolved() -> None:
    result = merge_script.merge_records(
        [existing_record()],
        [addition()],
        gymvisual_source(("1000", "New exercise")),
    )
    record = next(row for row in result["records"] if row["source_identity"] == "1000")

    assert list(record) == SCHEMA
    assert record["source_identity"] == "1000"
    assert record["name_en"] == "New exercise"
    assert record["form_cues_ko"] == ["첫 단계입니다.", "두 번째 단계입니다."]
    assert record["source_track"] == "gymvisual"
    assert record["stable_code"] is None
    assert record["name_ko"] is None
    assert record["primary_body_area_codes"] == []
    assert record["safety_relevant_body_area_codes"] == []
    assert record["equipment_codes"] == ["BODYWEIGHT"]
    assert record["recovery_eligible"] is None
    assert "category" not in record
    assert result["report"]["counts"]["new_draft_record_count"] == 1


def test_new_identity_fields_use_exact_review_csv_mapping_only() -> None:
    result = merge_script.merge_records(
        [existing_record()],
        [addition()],
        gymvisual_source(("1000", "New exercise")),
        {"1000": {"stable_code": "reviewed_code", "name_ko": "검수 운동"}},
    )
    record = next(row for row in result["records"] if row["source_identity"] == "1000")

    assert record["stable_code"] == "reviewed_code"
    assert record["name_ko"] == "검수 운동"
    assert record["primary_body_area_codes"] == []
    assert record["secondary_body_area_codes"] == []
    assert record["safety_relevant_body_area_codes"] == []
    assert result["report"]["counts"]["identity_field_fill_count"] == 2


def test_safety_body_areas_are_never_copied_from_primary_or_secondary() -> None:
    result = merge_script.merge_records(
        [existing_record()],
        [addition()],
        gymvisual_source(("1000", "New exercise")),
    )
    record = next(row for row in result["records"] if row["source_identity"] == "1000")

    assert record["primary_body_area_codes"] == []
    assert record["secondary_body_area_codes"] == []
    assert record["safety_relevant_body_area_codes"] == []


def test_stable_code_is_not_generated_without_a_raw_stable_code() -> None:
    result = merge_script.merge_records([existing_record(stable_code=None)], [], None)
    assert result["records"][0]["stable_code"] is None


def test_blank_stable_codes_remain_blank() -> None:
    first = existing_record(identity="0513", stable_code=None, name="jump squat v. 2")
    second = existing_record(identity="0514", stable_code=None, name="jump squat")
    result = merge_script.merge_records([first, second], [], None)
    assert [row["stable_code"] for row in result["records"]] == [None, None]


def test_existing_values_are_preserved_and_empty_cues_are_filled() -> None:
    existing = existing_record(identity="1000", name="Legacy name", cues=["기존 안내"])
    result = merge_script.merge_records(
        [existing],
        [addition(identity="1000", name="New exercise")],
        gymvisual_source(("1000", "New exercise")),
    )
    merged = result["records"][0]
    assert merged["name_en"] == "Legacy name"
    assert merged["form_cues_ko"] == ["기존 안내"]
    assert result["report"]["counts"]["exact_duplicate_merge_count"] == 1
    assert {row["field"] for row in result["report"]["conflicts"]} == {
        "name_en",
        "form_cues_ko",
    }
    assert all(
        row["action"] == "KEEP_EXISTING_NON_EMPTY_VALUE" for row in result["report"]["conflicts"]
    )
    assert result["report"]["counts"]["direct_field_overwrite_count"] == 0

    empty_cues = existing_record(identity="1001", cues=[])
    filled = merge_script.merge_records(
        [empty_cues],
        [addition(identity="1001", name="New exercise")],
        gymvisual_source(("1001", "New exercise")),
    )
    assert filled["records"][0]["form_cues_ko"] == ["첫 단계입니다.", "두 번째 단계입니다."]
    assert filled["report"]["counts"]["direct_field_fill_count"] == 1


def test_exact_identity_does_not_leave_a_new_record() -> None:
    result = merge_script.merge_records(
        [existing_record(identity="1000", name="New exercise")],
        [addition()],
        gymvisual_source(("1000", "New exercise")),
    )
    assert len(result["records"]) == 1
    assert result["report"]["merged_addition_ids"] == ["1000"]
    assert result["report"]["new_draft_source_identities"] == []


def test_stable_code_duplicates_are_removed_without_replacing_first_row() -> None:
    first = existing_record(identity="1000", stable_code="same_code")
    second = existing_record(identity="1001", stable_code="same_code", name="Other")
    result = merge_script.merge_records([first, second], [], None)
    assert len(result["records"]) == 1
    assert result["records"][0]["source_identity"] == "1000"
    assert result["report"]["validation"]["stable_code_duplicate_count"] == 0
    assert result["report"]["counts"]["existing_duplicate_rows_removed"] == 1


def test_name_only_match_stays_review_required_and_is_not_deleted() -> None:
    result = merge_script.merge_records(
        [existing_record(identity="9000", name="New exercise", source_track="wger")],
        [addition()],
        gymvisual_source(("1000", "New exercise")),
    )
    assert len(result["records"]) == 2
    review = result["duplicate_review"]["records"]
    assert len(review) == 1
    assert review[0]["duplicate_reason_code"] == "NAME_EXACT_MATCH_ONLY"
    assert review[0]["review_status"] == "REVIEW_REQUIRED"
    assert result["report"]["validation"]["name_only_items_automatically_deleted"] is False


def test_unmapped_fields_are_preserved_outside_output_schema() -> None:
    source_addition = addition()
    result = merge_script.merge_records(
        [existing_record()],
        [source_addition],
        gymvisual_source(("1000", "New exercise")),
    )
    unmapped = result["unmapped"]["records"][0]
    assert unmapped["source_identity"] == "1000"
    assert unmapped["unmapped_fields"]["instructions_ko"] == source_addition["instructions_ko"]
    assert unmapped["unmapped_fields"]["exercise_contraindicated_pain_regions"] == ["SHOULDER"]
    assert all(set(row) == set(SCHEMA) for row in result["records"])


def test_raw_steps_are_cleaned_and_unverified_source_values_stay_empty() -> None:
    source_addition = addition(identity="1002")
    source_addition["instructions_steps_ko"] = [
        " 첫 단계입니다. ",
        "",
        "첫 단계입니다.",
        "마지막 단계입니다.",
    ]
    result = merge_script.merge_records(
        [existing_record()],
        [source_addition],
        gymvisual_source(
            ("1002", "New exercise"),
            steps=source_addition["instructions_steps_ko"],
        ),
    )
    record = next(row for row in result["records"] if row["source_identity"] == "1002")
    assert record["form_cues_ko"] == ["첫 단계입니다.", "마지막 단계입니다."]
    assert record["source_track"] == "gymvisual"
    audit = result["report"]["content_audits"][0]
    assert audit["issues"] == ["DUPLICATE_STEP_REMOVED", "EMPTY_STEP_REMOVED"]

    unverified = merge_script.merge_records([existing_record()], [source_addition], [])["records"][
        -1
    ]
    assert unverified["source_identity"] is None
    assert unverified["name_en"] is None
    assert unverified["form_cues_ko"] == []


def test_real_inputs_have_expected_provenance_and_counts() -> None:
    root = Path("data/generated/exercise-catalog-v2.0.6-draft/backend_bundle/catalog")
    catalog = [json.loads(line) for line in (root / "exercises.jsonl").read_text().splitlines()]
    additions = json.loads((root / "exercise_catalog_additions.json").read_text())
    source = json.loads(Path("data/raw/gym_visual/exercises.json").read_text())
    result = merge_script.merge_records(catalog, additions, source)
    counts = result["report"]["counts"]
    assert counts["existing_catalog_records"] == len(catalog)
    assert counts["additions_records"] == len(additions)
    assert counts["exact_duplicate_merge_count"] == 37
    assert counts["new_draft_record_count"] == len(additions) - 37
    assert counts["name_exact_match_only_review_required_count"] == 0
    assert counts["verified_gymvisual_source_records"] == len(additions)


def test_run_is_byte_reproducible_and_does_not_write_final_jsonl(tmp_path: Path) -> None:
    catalog_path = tmp_path / "exercises.jsonl"
    additions_path = tmp_path / "additions.json"
    source_path = tmp_path / "gymvisual.json"
    catalog_path.write_text(json.dumps(existing_record()) + "\n", encoding="utf-8")
    additions_path.write_text(json.dumps([addition()], ensure_ascii=False), encoding="utf-8")
    source_path.write_text(
        json.dumps(gymvisual_source(("1000", "New exercise")), ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "exercise_catalog_merged_draft.json"
    report_dir = tmp_path / "reports"
    mapping_path = tmp_path / "normalized-source-mapping.json"
    merge_script.run(catalog_path, additions_path, output, report_dir, source_path, mapping_path)
    csv_output = output.with_suffix(".csv")
    assert csv_output.read_bytes().startswith(b"\xef\xbb\xbf")
    with csv_output.open(encoding="utf-8-sig", newline="") as handle:
        parsed = list(csv.DictReader(handle))
    new_csv_row = next(row for row in parsed if row["source_identity"] == "1000")
    assert new_csv_row["stable_code"] == ""
    csv_first = csv_output.read_bytes()
    first = {path.name: path.read_bytes() for path in report_dir.iterdir()}
    output_first = output.read_bytes()
    merge_script.run(catalog_path, additions_path, output, report_dir, source_path, mapping_path)
    second = {path.name: path.read_bytes() for path in report_dir.iterdir()}
    assert output.read_bytes() == output_first
    assert csv_output.read_bytes() == csv_first
    assert second == first
    assert len(catalog_path.read_text(encoding="utf-8").splitlines()) == 1
