from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "build_gym_equipment_starting_guides.py"
spec = importlib.util.spec_from_file_location("build_gym_equipment_starting_guides", SCRIPT)
assert spec and spec.loader
guide_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guide_builder)


def write_catalog(path: Path) -> None:
    fields = [
        "training_type_code",
        "stable_code",
        "equipment_codes",
        "body_focus_code",
        "primary_movement_pattern_code",
    ]
    rows = [
        {
            "stable_code": "raise",
            "equipment_codes": "DUMBBELL",
            "body_focus_code": "SHOULDERS",
            "primary_movement_pattern_code": "ISOLATION",
        },
        {
            "stable_code": "row",
            "equipment_codes": "DUMBBELL",
            "body_focus_code": "UPPER_BACK",
            "primary_movement_pattern_code": "HORIZONTAL_PULL",
        },
        {
            "stable_code": "squat",
            "equipment_codes": "DUMBBELL|BARBELL",
            "body_focus_code": "QUADRICEPS",
            "primary_movement_pattern_code": "KNEE_DOMINANT",
        },
        {
            "stable_code": "press",
            "equipment_codes": "BARBELL",
            "body_focus_code": "CHEST",
            "primary_movement_pattern_code": "HORIZONTAL_PUSH",
        },
        {
            "stable_code": "machine_row",
            "equipment_codes": "MACHINE",
            "body_focus_code": "UPPER_BACK",
            "primary_movement_pattern_code": "HORIZONTAL_PULL",
        },
        {
            "stable_code": "assisted_pull_up",
            "equipment_codes": "MACHINE",
            "body_focus_code": "UPPER_BACK",
            "primary_movement_pattern_code": "VERTICAL_PULL",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({"training_type_code": "STRENGTH", **row} for row in rows)


def test_builds_exact_reused_schema_and_policy_rows(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    write_catalog(catalog)
    rows = guide_builder.build_rows(catalog)
    guide_builder.validate_rows(catalog, rows)

    by_key = {(row["exercise_stable_code"], row["equipment_code"]): row for row in rows}
    assert len(rows) == 6
    assert "처음 시작할 때(권장): 1~2kg" in by_key[("raise", "DUMBBELL")]["proposal_ko"]
    assert "처음 시작할 때(권장): 2~4kg" in by_key[("row", "DUMBBELL")]["proposal_ko"]
    assert "처음 시작할 때(권장): 5~10kg" in by_key[("squat", "DUMBBELL")]["proposal_ko"]
    assert "처음 시작할 때(권장): 10~20kg" in by_key[("squat", "BARBELL")]["proposal_ko"]
    assert "처음 시작할 때(권장): 5~10kg" in by_key[("press", "BARBELL")]["proposal_ko"]
    assert ("machine_row", "MACHINE") not in by_key
    assisted = by_key[("assisted_pull_up", "MACHINE")]
    assert "체중의 60~70% 보조" in assisted["proposal_ko"]
    assert len(assisted["proposal_ko"].splitlines()) == 5
    assert all(
        len(row["proposal_ko"].splitlines()) == 4
        for row in rows
        if row["equipment_code"] != "MACHINE"
    )
    assert set(assisted) == guide_builder.REQUIRED_FIELDS


def test_validation_rejects_missing_required_guide(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    write_catalog(catalog)
    rows = guide_builder.build_rows(catalog)
    rows.pop()

    with pytest.raises(guide_builder.GymGuideError, match="cover exactly"):
        guide_builder.validate_rows(catalog, rows)


@pytest.mark.parametrize(
    "stable_code",
    [
        "stationary_bike_walk",
        "walk_elliptical_cross_trainer",
        "assisted_triceps_dip_kneeling",
        "machine_row",
    ],
)
def test_excludes_other_machines(stable_code: str) -> None:
    assert (
        guide_builder._guide_equipment(
            {
                "stable_code": stable_code,
                "equipment_codes": "MACHINE",
                "training_type_code": "STRENGTH",
            }
        )
        == set()
    )


@pytest.mark.parametrize("equipment", ["DUMBBELL", "BARBELL", "MACHINE"])
def test_excludes_non_strength(equipment: str) -> None:
    assert (
        guide_builder._guide_equipment(
            {
                "stable_code": "assisted_pull_up",
                "equipment_codes": equipment,
                "training_type_code": "CARDIO",
            }
        )
        == set()
    )


def test_real_catalog_output_is_reproducible() -> None:
    rows = guide_builder.build_rows(guide_builder.DEFAULT_CATALOG)
    guide_builder.validate_rows(guide_builder.DEFAULT_CATALOG, rows)
    assert guide_builder.DEFAULT_OUTPUT.read_text(encoding="utf-8") == guide_builder.render(rows)
    assert {row["exercise_stable_code"] for row in rows if row["equipment_code"] == "MACHINE"} == {
        "assisted_pull_up",
        "assisted_standing_pull_up",
    }
