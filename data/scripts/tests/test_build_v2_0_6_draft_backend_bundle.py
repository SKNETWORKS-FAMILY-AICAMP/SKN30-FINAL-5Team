from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from backend.app.modules.catalog.schemas import AlternativeManifest
from backend.app.modules.catalog.service import load_alternative_artifact

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_6_draft_backend_bundle.py"
spec = importlib.util.spec_from_file_location("build_v2_0_6_draft_backend_bundle", SCRIPT)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = builder
spec.loader.exec_module(builder)

VALIDATOR_SCRIPT = Path(__file__).resolve().parents[1] / "validate_v2_backend_bundle.py"
validator_spec = importlib.util.spec_from_file_location(
    "validate_v2_backend_bundle", VALIDATOR_SCRIPT
)
assert validator_spec and validator_spec.loader
validator = importlib.util.module_from_spec(validator_spec)
sys.modules[validator_spec.name] = validator
validator_spec.loader.exec_module(validator)


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_build_is_media_gated_and_has_no_alternatives(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    summary = builder.build(target=output)

    assert summary["catalog_records"] == 70
    assert summary["media_asset_records"] == 70
    assert summary["alternative_records"] == 0
    assert summary["withheld_no_alternative_fallback"] == 3

    catalog = _jsonl(output / "catalog/exercises.jsonl")
    media = _jsonl(output / "media/media_assets.jsonl")
    source_catalog = _jsonl(
        Path("data/generated/exercise-catalog-v2.0.5-final/backend_bundle/catalog/exercises.jsonl")
    )
    source_by_code = {row["stable_code"]: row for row in source_catalog}
    assert len({row["stable_code"] for row in catalog}) == 70
    assert "cardio_jump_plyometric_bodyweight" not in {row["stable_code"] for row in catalog}
    assert all(set(row) == set(source_catalog[0]) for row in catalog)
    assert all(
        all(
            row[field] == source_by_code[row["stable_code"]][field]
            for field in (
                "source_track",
                "source_identity",
                "review_status_code",
                "primary_body_area_codes",
                "secondary_body_area_codes",
            )
        )
        for row in catalog
    )
    assert all(
        row["form_cues_review_status"] == builder.BACKEND_APPROVED_FORM_CUES_REVIEW_STATUS
        and row["instruction_content_version"]
        in {builder.INSTRUCTION_CONTENT_VERSION, "gif-reviewed-natural-language-ko-v2.0.6"}
        for row in catalog
    )
    assert all(
        row["instruction_summary_ko"]
        == source_by_code[row["stable_code"]]["instruction_summary_ko"]
        or row["form_cues_source"].startswith("data/videos/")
        or row["instruction_summary_ko"].startswith("1. ")
        for row in catalog
    )
    assert all(row["instruction_summary_ko"].startswith("1. ") for row in catalog)
    assert len(media) == len(catalog)
    assert all(row["media_status"] == "AVAILABLE" for row in media)
    assert all(row["rights_review_status"] == "APPROVED" for row in media)
    assert (output / "alternatives/alternatives.jsonl").read_bytes() == b""
    assert json.loads(
        (output / "alternatives/input/alternative_projection_conflicts.json").read_text(
            encoding="utf-8"
        )
    ) == {
        "conflict_count": 0,
        "conflicts": [],
        "importer_record_count": 0,
        "production_eligible": False,
        "projection_status": "DIRECT",
        "runtime_record_count": 0,
        "status": "DRAFT",
    }

    for relative in (
        "catalog/seed_manifest.json",
        "catalog/exercises.jsonl",
        "alternatives/alternatives.jsonl",
        "alternatives/alternatives_manifest.json",
        "alternatives/input/alternative_projection_conflicts.json",
        "media/media_assets.jsonl",
        "media/media_manifest.json",
        "safety/safety_rules.jsonl",
        "safety/rules_manifest.json",
        "prescriptions/goal_tag_links.jsonl",
        "prescriptions/prescription_profiles.jsonl",
        "prescriptions/prescription_manifest.json",
        "bundle_manifest.json",
    ):
        assert (output / relative).is_file()

    audit = _jsonl(output / builder.CONTENT_AUDIT_PATH)
    # GIF-reviewed rows overlay the naturalized source cues after this audit is
    # emitted, so it can contain more source sentences than final form cues.
    assert len(audit) >= sum(len(row["form_cues_ko"]) for row in catalog)
    assert all(
        set(row)
        == {
            "stable_code",
            "source_track",
            "source_identity",
            "existing_instruction_content_version",
            "new_instruction_content_version",
            "existing_form_cues_source",
            "original_sentence",
            "changed_sentence",
            "reason_code",
            "review_required",
        }
        and row["review_required"] is True
        and row["reason_code"] == "SOURCE_INSTRUCTION_STEPS_NATURAL_LANGUAGE_REWRITE"
        for row in audit
    )


def test_empty_alternative_manifest_and_loader_are_importable(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    builder.build(target=output)

    manifest = AlternativeManifest.model_validate_json(
        (output / "alternatives/alternatives_manifest.json").read_bytes()
    )
    assert manifest.summary.alternative_records == 0
    assert manifest.files[0].records == 0
    artifact = load_alternative_artifact(output / "alternatives", v2_import=True)
    assert artifact.records == ()


def test_v2_bundle_validator_accepts_empty_alternatives_and_zero_conflicts(
    tmp_path: Path,
) -> None:
    output = tmp_path / "bundle"
    builder.build(target=output)

    report = validator.validate(output)

    assert report["status"] == "valid"
    assert report["alternative_records"] == 0
    bundle_manifest = json.loads((output / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert bundle_manifest["projection"]["runtime_alternative_records"] == 0
    assert bundle_manifest["projection"]["importer_alternative_records"] == 0
    assert bundle_manifest["projection"]["alternative_conflict_count"] == 0


def test_existing_alternative_input_rows_are_not_projected(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    source = Path("data/generated/exercise-catalog-v2.0.5-final/backend_bundle")
    assert _jsonl(source / "alternatives/alternatives.jsonl")

    builder.build(target=output)

    assert (output / "alternatives/alternatives.jsonl").read_bytes() == b""


def test_empty_safety_pool_does_not_use_an_alternative_fallback() -> None:
    allowed, withheld = builder._allowed_media_codes_without_alternative_fallback(
        [{"stable_code": "strap_only", "equipment_codes": ["STRETCH_STRAP"]}],
        {"strap_only": {"media_status": "AVAILABLE"}},
    )

    assert allowed == set()
    assert withheld == {"strap_only"}


def test_build_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_summary = builder.build(target=first)
    second_summary = builder.build(target=second)
    assert first_summary == second_summary
    assert (first / "bundle_manifest.json").read_bytes() == (
        second / "bundle_manifest.json"
    ).read_bytes()
    assert (first / "alternatives/alternatives.jsonl").read_bytes() == b""
    assert (first / "alternatives/alternatives_manifest.json").read_bytes() == (
        second / "alternatives/alternatives_manifest.json"
    ).read_bytes()
    assert (first / "alternatives/input/alternative_projection_conflicts.json").read_bytes() == (
        second / "alternatives/input/alternative_projection_conflicts.json"
    ).read_bytes()


def test_derived_rows_reference_only_the_v2_0_6_catalog(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    builder.build(target=output)
    catalog_codes = {row["stable_code"] for row in _jsonl(output / "catalog/exercises.jsonl")}

    for relative in (
        "safety/safety_rules.jsonl",
        "prescriptions/goal_tag_links.jsonl",
        "prescriptions/prescription_profiles.jsonl",
    ):
        for row in _jsonl(output / relative):
            assert row.get("exercise_stable_code") in catalog_codes
            assert "alternative_exercise_stable_code" not in row


def test_unknown_form_cue_development_token_fails_closed() -> None:
    with pytest.raises(builder.BundleBuildError):
        builder._naturalize_form_cue("UNKNOWN_INTERNAL_TOKEN 자세")


def test_representative_development_cue_is_rewritten_as_actionable_korean() -> None:
    cue = builder._naturalize_form_cue(
        "SUPPORTED_SEATED_KNEES_NEUTRAL_UNWEIGHTED 자세를 먼저 잡고 "
        "BACKREST_AND_LOWER_LEG_SUPPORT 지지를 끝날 때까지 유지한다."
    )

    assert cue == (
        "등받이가 있는 안정적인 의자에 앉아 두 발을 바닥에 편하게 둡니다. "
        "운동이 끝날 때까지 등을 등받이에 기대어 몸을 안정적으로 유지합니다."
    )
    assert not builder.UPPER_SNAKE_CASE_RE.search(cue)
    assert not builder.BODY_AREA_CODE_RE.search(cue)


def test_user_facing_upper_snake_case_and_body_area_codes_fail_closed() -> None:
    base = {
        "stable_code": "exercise_code",
        "instruction_summary_ko": "운동",
        "name_ko": "운동",
        "form_cues_ko": ["준비 자세를 잡고 천천히 움직입니다."],
    }

    bad_token = {**base, "form_cues_ko": ["SUPPORTED_SEATED_TOKEN 자세를 잡습니다."]}
    with pytest.raises(builder.BundleBuildError):
        builder._validate_user_exposed_fields([bad_token])

    bad_body_area = {**base, "form_cues_ko": ["KNEE 부위에 체중이 실리지 않도록 합니다."]}
    with pytest.raises(builder.BundleBuildError):
        builder._validate_user_exposed_fields([bad_body_area])


def test_source_provenance_and_machine_fields_are_preserved(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    builder.build(target=output)
    source_rows = _jsonl(
        Path("data/generated/exercise-catalog-v2.0.5-final/backend_bundle/catalog/exercises.jsonl")
    )
    source_by_code = {row["stable_code"]: row for row in source_rows}
    normalized_by_code = builder._normalized_content_by_stable_code(builder.NORMALIZED_CATALOG)
    target_rows = _jsonl(output / "catalog/exercises.jsonl")
    machine_fields = (
        "stable_code",
        "training_type_code",
        "difficulty_code",
        "source_track",
        "source_identity",
    )
    for row in target_rows:
        source = source_by_code[row["stable_code"]]
        normalized = normalized_by_code[row["stable_code"]]
        assert all(row[field] == source[field] for field in machine_fields)
        assert row["name_en"] == normalized["name_en"]
        assert row["equipment_codes"] == normalized["equipment_codes"]
        assert row["location_codes"] == normalized["location_codes"]
        assert row["body_focus_code"] == normalized["body_focus_code"]
        assert row["primary_movement_pattern_code"] == normalized["primary_movement_pattern_code"]
        assert row["form_cues_ko"] == normalized["form_cues_ko"]
        expected_form_cues_status = (
            builder.BACKEND_APPROVED_FORM_CUES_REVIEW_STATUS
            if normalized["form_cues_review_status"] == builder.APPROVED_FORM_CUES_REVIEW_STATUS
            else normalized["form_cues_review_status"]
        )
        assert row["form_cues_review_status"] == expected_form_cues_status
        assert row["form_cues_source"] == normalized["form_cues_source"]
        assert "GYM" in row["location_codes"]


def test_quality_validator_rejects_duplicate_and_vague_cues() -> None:
    base = {
        "stable_code": "exercise_code",
        "instruction_summary_ko": "운동",
        "name_ko": "운동",
        "form_cues_ko": ["준비합니다.", "준비합니다."],
    }
    with pytest.raises(builder.BundleBuildError):
        builder._validate_user_exposed_fields([base])

    vague = {**base, "form_cues_ko": ["안내된 부위를 중심으로 움직입니다."]}
    with pytest.raises(builder.BundleBuildError):
        builder._validate_user_exposed_fields([vague])
