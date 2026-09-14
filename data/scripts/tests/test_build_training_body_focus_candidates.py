from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_training_body_focus_candidates.py"
spec = importlib.util.spec_from_file_location("build_training_body_focus_candidates", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def catalog_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "stable_code": None,
        "source_track": "gymvisual",
        "source_identity": "0001",
        "name_ko": None,
        "name_en": "barbell bench press",
        "training_type_code": None,
        "body_focus_code": None,
        "instruction_summary_ko": None,
    }
    row.update(overrides)
    return row


def addition(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "0001",
        "name": "barbell bench press",
        "category": "chest",
        "target": "pectorals",
        "muscle_group": "chest",
        "secondary_muscles": ["triceps"],
        "equipment": "barbell",
        "instructions_ko": "바벨을 가슴 앞에서 밀어 올립니다.",
    }
    row.update(overrides)
    return row


def test_exact_identity_source_generates_strength_candidate() -> None:
    rows = module.build_candidates([catalog_row()], [addition()], [])
    row = rows[0]
    assert row["training_type_code_candidate"] == "STRENGTH"
    assert row["training_type_review_status"] == "CANDIDATE_READY"
    assert row["body_focus_code_candidate"] == "CHEST"
    assert row["body_focus_review_status"] == "CANDIDATE_READY"
    assert row["source_target"] == "pectorals"


def test_cardio_and_mobility_are_review_required() -> None:
    cardio = addition(
        id="0002",
        name="treadmill walking",
        category="cardio",
        target="cardiovascular system",
        equipment="treadmill",
    )
    mobility = addition(
        id="0003",
        name="chest stretch",
        category="chest",
        target="pectorals",
        equipment="body weight",
        instructions_ko="가슴을 천천히 늘립니다.",
    )
    rows = module.build_candidates(
        [
            catalog_row(source_identity="0002", name_en="treadmill walking"),
            catalog_row(source_identity="0003", name_en="chest stretch"),
        ],
        [cardio, mobility],
        [],
    )
    assert rows[0]["training_type_code_candidate"] == "CARDIO"
    assert rows[0]["training_type_review_status"] == "REVIEW_REQUIRED"
    assert rows[0]["body_focus_code_candidate"] == "CARDIO"
    assert rows[1]["training_type_code_candidate"] == "MOBILITY"
    assert rows[1]["training_type_review_status"] == "REVIEW_REQUIRED"
    assert rows[1]["body_focus_code_candidate"] == "MOBILITY"


def test_existing_value_is_preserved_and_conflict_is_review_required() -> None:
    row = catalog_row(training_type_code="STRENGTH", body_focus_code="BACK")
    rows = module.build_candidates([row], [addition()], [])
    result = rows[0]
    assert result["current_training_type_code"] == "STRENGTH"
    assert result["training_type_code_candidate"] == "STRENGTH"
    assert result["training_type_review_status"] == "CONSISTENT"
    assert result["current_body_focus_code"] == "BACK"
    assert result["body_focus_code_candidate"] == "CHEST"
    assert result["body_focus_review_status"] == "REVIEW_REQUIRED"
    assert "CURRENT_VALUE_CONFLICT" in result["conflict_codes"]


def test_body_source_conflict_does_not_change_training_status() -> None:
    result = module.build_candidates(
        [catalog_row()],
        [addition(muscle_group="hamstrings")],
        [],
    )[0]
    assert result["training_type_code_candidate"] == "STRENGTH"
    assert result["training_type_review_status"] == "CANDIDATE_READY"
    assert result["body_focus_code_candidate"] == "CHEST"
    assert result["body_focus_review_status"] == "REVIEW_REQUIRED"
    assert "TARGET_MUSCLE_GROUP_CONFLICT" in result["conflict_codes"]


def test_additions_are_resolved_by_id_not_name() -> None:
    row = catalog_row(name_en="barbell bench press")
    source = addition(id="9999", name="barbell bench press")
    result = module.build_candidates(
        [row],
        [source],
        [
            {
                "id": "0001",
                "name": "different name",
                "category": "cardio",
                "target": "cardiovascular system",
                "instructions": {"ko": "걷습니다."},
            },
        ],
    )[0]
    assert result["source_identity"] == "0001"
    assert result["source_category"] == "cardio"
    assert result["training_type_code_candidate"] == "CARDIO"
