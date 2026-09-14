from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "enrich_v2_0_6_met.py"
spec = importlib.util.spec_from_file_location("enrich_v2_0_6_met", SCRIPT)
assert spec and spec.loader
met = importlib.util.module_from_spec(spec)
spec.loader.exec_module(met)


def write_catalog(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_compendium(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def base_row(name_en: str, identity: str) -> dict[str, str]:
    return {
        "stable_code": f"exercise_{identity}",
        "source_identity": identity,
        "source_track": "gymvisual",
        "name_en": name_en,
        "name_ko": name_en,
        "training_type_code": "STRENGTH",
        "timing_mode_code": "REPS",
        "primary_movement_pattern_code": "ISOLATION",
        "equipment_codes": "BODYWEIGHT",
        "primary_body_area_codes": "",
        "secondary_body_area_codes": "",
        "safety_relevant_body_area_codes": "",
    }


def test_direct_and_similar_activity_mappings_use_source_values(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    compendium = tmp_path / "compendium.jsonl"
    rows = [
        base_row("kettlebell swing", "0549"),
        base_row("jack jump (male)", "3224"),
        base_row("push-up", "0662"),
        base_row("barbell deadlift", "0032") | {"equipment_codes": "BARBELL"},
        base_row("hamstring stretch", "1511"),
        base_row("rowing machine", "9999")
        | {
            "training_type_code": "CARDIO",
            "timing_mode_code": "DURATION",
            "equipment_codes": "MACHINE",
        },
    ]
    write_catalog(catalog, rows)
    write_compendium(
        compendium,
        [
            {
                "activity_code": "02020",
                "activity_description": (
                    "Calisthenics (e.g., pushups, jumping jacks), vigorous effort"
                ),
                "met_value": 7.5,
                "source_id": "ADULT_COMPENDIUM_PDF_2024",
            },
            {
                "activity_code": "02022",
                "activity_description": "Calisthenics (e.g., pushups), moderate effort",
                "met_value": 3.8,
                "source_id": "ADULT_COMPENDIUM_PDF_2024",
            },
            {
                "activity_code": "02052",
                "activity_description": (
                    "Resistance (weight) training, squats, deadlift, slow or explosive effort"
                ),
                "met_value": 5.0,
                "source_id": "ADULT_COMPENDIUM_PDF_2024",
            },
            {
                "activity_code": "02056",
                "activity_description": "Body weight resistance exercises, general",
                "met_value": 3.0,
                "source_id": "ADULT_COMPENDIUM_PDF_2024",
            },
            {
                "activity_code": "02024",
                "activity_description": "Calisthenics, light effort",
                "met_value": 2.8,
                "source_id": "ADULT_COMPENDIUM_PDF_2024",
            },
            {
                "activity_code": "02058",
                "activity_description": "Kettle bell swings",
                "met_value": 9.8,
                "source_id": "ADULT_COMPENDIUM_PDF_2024",
            },
            {
                "activity_code": "02101",
                "activity_description": "Stretching, mild",
                "met_value": 2.3,
                "source_id": "ADULT_COMPENDIUM_PDF_2024",
            },
        ],
    )

    report = met.enrich(catalog, compendium, tmp_path / "reports")
    output = list(csv.DictReader(catalog.open(encoding="utf-8-sig", newline="")))
    by_name = {row["name_en"]: row for row in output}
    assert by_name["kettlebell swing"]["met_value"] == "9.8"
    assert by_name["kettlebell swing"]["met_source_activity_code"] == "02058"
    assert by_name["kettlebell swing"]["met_mapping_method_code"] == "DIRECT"
    assert by_name["jack jump (male)"]["met_value"] == "7.5"
    assert by_name["jack jump (male)"]["met_source_activity_code"] == "02020"
    assert by_name["jack jump (male)"]["met_mapping_method_code"] == "SIMILAR_ACTIVITY"
    assert by_name["push-up"]["met_value"] == "3.0"
    assert by_name["push-up"]["met_source_activity_code"] == "02056"
    assert by_name["push-up"]["met_mapping_method_code"] == "SIMILAR_ACTIVITY"
    assert by_name["barbell deadlift"]["met_value"] == "5.0"
    assert by_name["barbell deadlift"]["met_source_activity_code"] == "02052"
    assert by_name["barbell deadlift"]["met_mapping_method_code"] == "SIMILAR_ACTIVITY"
    assert by_name["hamstring stretch"]["met_value"] == "2.3"
    assert by_name["hamstring stretch"]["met_mapping_method_code"] == "DIRECT"
    assert all(row["met_review_status_code"] == "REVIEW_REQUIRED" for row in output)
    assert report["counts"]["mapping_success"] == 5
    assert report["counts"]["direct_mappings"] == 2
    assert report["counts"]["similar_activity_mappings"] == 3
    assert report["counts"]["unmapped"] == 1
    evidence = list(
        csv.DictReader(
            (tmp_path / "reports/met_mapping_evidence.csv").open(encoding="utf-8-sig", newline="")
        )
    )
    assert {row["met_source_activity_code"] for row in evidence} == {
        "02020",
        "02052",
        "02056",
        "02058",
        "02101",
    }
    assert report["counts"]["review_needed"] == 6


def test_domain_approved_mapping_requires_explicit_manifest(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    compendium = tmp_path / "compendium.jsonl"
    write_catalog(catalog, [base_row("kettlebell swing", "0549")])
    write_compendium(
        compendium,
        [
            {
                "activity_code": "02058",
                "activity_description": "Kettle bell swings",
                "met_value": 9.8,
                "source_id": "ADULT_COMPENDIUM_PDF_2024",
            }
        ],
    )
    with pytest.raises(met.MetEnrichmentError, match="approval manifest"):
        met.enrich(
            catalog,
            compendium,
            tmp_path / "reports",
            review_status_code="DOMAIN_APPROVED",
        )

    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({"review_status_code": "DOMAIN_APPROVED"}), encoding="utf-8")
    report = met.enrich(
        catalog,
        compendium,
        tmp_path / "reports",
        review_status_code="DOMAIN_APPROVED",
        approval_manifest=approval,
    )
    output = list(csv.DictReader(catalog.open(encoding="utf-8-sig", newline="")))
    assert output[0]["met_review_status_code"] == "DOMAIN_APPROVED"
    assert report["counts"]["approved"] == 1


def test_rank_fields_are_rejected_and_never_generated(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    write_catalog(catalog, [base_row("kettlebell swing", "0549") | {"rank": "1"}])
    with pytest.raises(met.MetEnrichmentError, match="rank fields"):
        met.enrich(catalog, tmp_path / "compendium.jsonl", tmp_path / "reports")


def test_gif_review_can_select_a_similar_source_activity(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    compendium = tmp_path / "compendium.jsonl"
    write_catalog(
        catalog,
        [
            base_row("back and forth step", "3672")
            | {"training_type_code": "CARDIO", "timing_mode_code": "DURATION"},
            base_row("half knee bends (male)", "3221")
            | {"training_type_code": "CARDIO", "timing_mode_code": "DURATION"},
        ],
    )
    write_compendium(
        compendium,
        [
            {
                "activity_code": "02056",
                "activity_description": "Body weight resistance exercises, general",
                "met_value": 3.0,
                "source_id": "ADULT_COMPENDIUM_PDF_2024",
            },
            {
                "activity_code": "02064",
                "activity_description": "Home exercise, general",
                "met_value": 3.8,
                "source_id": "ADULT_COMPENDIUM_PDF_2024",
            },
        ],
    )

    report = met.enrich(catalog, compendium, tmp_path / "reports")
    output = list(csv.DictReader(catalog.open(encoding="utf-8-sig", newline="")))
    by_identity = {row["source_identity"]: row for row in output}
    assert by_identity["3672"]["met_source_activity_code"] == "02064"
    assert by_identity["3672"]["met_value"] == "3.8"
    assert by_identity["3221"]["met_source_activity_code"] == "02056"
    assert by_identity["3221"]["met_value"] == "3.0"
    assert all(row["met_mapping_method_code"] == "SIMILAR_ACTIVITY" for row in output)
    assert report["counts"]["similar_activity_mappings"] == 2


def test_gif_review_maps_machine_and_loaded_carry_variants(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    compendium = tmp_path / "compendium.jsonl"
    rows = [
        base_row("walking on stepmill", "2311") | {"training_type_code": "CARDIO"},
        base_row("stationary bike walk", "0798")
        | {"training_type_code": "CARDIO", "equipment_codes": "MACHINE"},
        base_row("walk elliptical cross trainer", "2141")
        | {"training_type_code": "CARDIO", "equipment_codes": "MACHINE"},
        base_row("left hook. boxing", "2271") | {"training_type_code": "CARDIO"},
        base_row("farmers walk", "2133") | {"equipment_codes": "DUMBBELL"},
    ]
    write_catalog(catalog, rows)
    write_compendium(
        compendium,
        [
            {
                "activity_code": "01200",
                "activity_description": "Bicycling, stationary, general",
                "met_value": 6.8,
                "source_id": "SOURCE",
            },
            {
                "activity_code": "02048",
                "activity_description": "Elliptical trainer, moderate effort",
                "met_value": 5.0,
                "source_id": "SOURCE",
            },
            {
                "activity_code": "02065",
                "activity_description": "Stair treadmill ergometer, general",
                "met_value": 9.3,
                "source_id": "SOURCE",
            },
            {
                "activity_code": "15110",
                "activity_description": "Boxing, punching bag",
                "met_value": 5.8,
                "source_id": "SOURCE",
            },
            {
                "activity_code": "17018",
                "activity_description": "Carrying 15 – 155 lb load, level ground, slow pace",
                "met_value": 4.5,
                "source_id": "SOURCE",
            },
        ],
    )

    met.enrich(catalog, compendium, tmp_path / "reports")
    output = list(csv.DictReader(catalog.open(encoding="utf-8-sig", newline="")))
    by_identity = {row["source_identity"]: row for row in output}
    assert by_identity["2311"]["met_source_activity_code"] == "02065"
    assert by_identity["2311"]["met_mapping_method_code"] == "DIRECT"
    assert by_identity["0798"]["met_source_activity_code"] == "01200"
    assert by_identity["0798"]["met_mapping_method_code"] == "DIRECT"
    assert by_identity["2141"]["met_source_activity_code"] == "02048"
    assert by_identity["2141"]["met_mapping_method_code"] == "DIRECT"
    assert by_identity["2271"]["met_source_activity_code"] == "15110"
    assert by_identity["2271"]["met_mapping_method_code"] == "SIMILAR_ACTIVITY"
    assert by_identity["2133"]["met_source_activity_code"] == "17018"
    assert by_identity["2133"]["met_mapping_method_code"] == "SIMILAR_ACTIVITY"
