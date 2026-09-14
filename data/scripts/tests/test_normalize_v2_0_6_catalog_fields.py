from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "normalize_v2_0_6_catalog_fields.py"
spec = importlib.util.spec_from_file_location("normalize_v2_0_6_catalog_fields", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def catalog_row(
    identity: str, *, name_en: str, equipment: str, location: str = ""
) -> dict[str, str]:
    return {
        "source_identity": identity,
        "stable_code": f"exercise_{identity}",
        "name_en": name_en,
        "equipment_codes": equipment,
        "location_codes": location,
    }


def test_applies_requested_equipment_name_and_location_rules() -> None:
    rows = [
        catalog_row("1259", name_en="behind head chest stretch", equipment=""),
        catalog_row("0001", name_en="jump squat v. 2", equipment="BODYWEIGHT"),
        catalog_row("0002", name_en="barbell upright row v. 3", equipment="BARBELL"),
        catalog_row("0003", name_en="step dumbbell lunge", equipment="DUMBBELL|STEP_BOX"),
        catalog_row("0004", name_en="no equipment", equipment=""),
    ]

    normalized, report = module.apply_normalization(rows)
    by_identity = {row["source_identity"]: row for row in normalized}

    assert by_identity["1259"]["equipment_codes"] == "BODYWEIGHT"
    assert by_identity["1259"]["location_codes"] == "GYM|HOME"
    assert by_identity["0001"]["name_en"] == "jump squat"
    assert by_identity["0001"]["location_codes"] == "GYM|HOME"
    assert by_identity["0002"]["name_en"] == "barbell upright row"
    assert by_identity["0002"]["location_codes"] == "GYM"
    assert by_identity["0003"]["location_codes"] == "GYM"
    assert by_identity["0004"]["location_codes"] == "GYM"
    assert report["equipment_updates"] == [
        {"source_identity": "1259", "before": "", "after": "BODYWEIGHT"}
    ]


def test_forces_reviewed_fixture_exercises_to_gym_only() -> None:
    rows = [
        catalog_row(
            "0001",
            name_en="hyperextension",
            equipment="BODYWEIGHT",
            location="GYM|HOME",
        ),
        catalog_row(
            "0002",
            name_en="dumbbell incline curl",
            equipment="DUMBBELL",
            location="GYM|HOME",
        ),
        catalog_row("1259", name_en="behind head chest stretch", equipment="BODYWEIGHT"),
    ]
    rows[0]["stable_code"] = "bodyweight_back_extension_hip_dominant_bodyweight"
    rows[1]["stable_code"] = "dumbbell_incline_curl"
    normalized, _ = module.apply_normalization(rows)
    assert all(row["location_codes"] == "GYM" for row in normalized[:2])


def test_incline_and_decline_variants_are_gym_only() -> None:
    rows = [
        catalog_row(
            "0001", name_en="incline scapula push up", equipment="BODYWEIGHT", location="GYM|HOME"
        ),
        catalog_row(
            "0002",
            name_en="bodyweight incline side plank",
            equipment="BODYWEIGHT",
            location="GYM|HOME",
        ),
        catalog_row(
            "0003", name_en="rear decline bridge", equipment="BODYWEIGHT", location="GYM|HOME"
        ),
        catalog_row("1259", name_en="behind head chest stretch", equipment="BODYWEIGHT"),
    ]
    rows[0]["stable_code"] = "incline_scapula_push_up"
    rows[1]["stable_code"] = "bodyweight_incline_side_plank"
    rows[2]["stable_code"] = "rear_decline_bridge"
    normalized, _ = module.apply_normalization(rows)
    assert all(row["location_codes"] == "GYM" for row in normalized[:3])


def test_rejects_catalog_without_requested_row() -> None:
    rows = [catalog_row("0001", name_en="jump squat", equipment="BODYWEIGHT")]

    try:
        module.apply_normalization(rows)
    except module.CatalogFieldNormalizationError as exc:
        assert "requested row 187" in str(exc)
    else:
        raise AssertionError("missing requested row must fail")


def test_translates_reviewed_foam_roller_names_from_korean() -> None:
    rows = [
        catalog_row("1259", name_en="behind head chest stretch", equipment="BODYWEIGHT"),
        catalog_row(
            "2203",
            name_en="roller seated shoulder flexor depresor retractor",
            equipment="FOAM_ROLLER",
        ),
        catalog_row("2206", name_en="roller reverse crunch", equipment="FOAM_ROLLER"),
        catalog_row(
            "2209",
            name_en="roller seated single leg shoulder flexor depresor retractor",
            equipment="FOAM_ROLLER",
        ),
    ]

    normalized, _ = module.apply_normalization(rows)
    by_identity = {row["source_identity"]: row for row in normalized}

    assert by_identity["2203"]["name_en"] == "foam roller hamstring stretch"
    assert by_identity["2206"]["name_en"] == "foam roller calf stretch"
    assert by_identity["2209"]["name_en"] == "foam roller calf stretch"
    assert by_identity["2203"]["stable_code"] == "foam_roller_hamstring_stretch"
    assert by_identity["2206"]["stable_code"] == "foam_roller_calf_stretch_2206"
    assert by_identity["2209"]["stable_code"] == "foam_roller_calf_stretch_2209"


def test_renames_0514_as_bodyweight_squat() -> None:
    row = catalog_row("0514", name_en="jump squat", equipment="BODYWEIGHT")
    row["name_ko"] = "점프 스쿼트"

    normalized, report = module.apply_normalization(
        [row, catalog_row("1259", name_en="behind head chest stretch", equipment="BODYWEIGHT")]
    )

    assert normalized[0]["name_en"] == "bodyweight squat"
    assert normalized[0]["name_ko"] == "맨몸 스쿼트"
    assert normalized[0]["stable_code"] == "bodyweight_squat"
    assert report["name_ko_updates"] == [
        {"source_identity": "0514", "before": "점프 스쿼트", "after": "맨몸 스쿼트"}
    ]
