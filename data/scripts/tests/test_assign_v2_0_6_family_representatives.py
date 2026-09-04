from collections import defaultdict
from pathlib import Path

from data.scripts.assign_v2_0_6_family_representatives import (
    FAMILY_GROUPS,
    apply_family_assignments,
    normalized_equipment,
    read_catalog,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "normalized/v2_0_6_exercise_catalog.csv"


def test_normalized_catalog_has_complete_family_relationships():
    rows, _ = read_catalog(CATALOG)
    report = apply_family_assignments(rows)

    assert report["counts"]["catalog_records"] == 237
    assert all(row["family_code"] for row in rows)
    assert all(row["record_type"] in {"REPRESENTATIVE", "VARIANT"} for row in rows)

    by_family = defaultdict(list)
    for row in rows:
        by_family[row["family_code"]].append(row)
    assert all(
        sum(row["record_type"] == "REPRESENTATIVE" for row in members) == 1
        for members in by_family.values()
    )


def test_variant_parent_is_only_populated_for_variants_and_matches_family():
    rows, _ = read_catalog(CATALOG)
    apply_family_assignments(rows)
    by_code = {row["stable_code"]: row for row in rows}

    for row in rows:
        if row["record_type"] == "REPRESENTATIVE":
            assert row["representative_stable_code"] == ""
        else:
            parent = by_code[row["representative_stable_code"]]
            assert parent["record_type"] == "REPRESENTATIVE"
            assert parent["family_code"] == row["family_code"]


def test_representative_uses_requested_equipment_priority():
    rows, _ = read_catalog(CATALOG)
    apply_family_assignments(rows)
    by_family = defaultdict(list)
    for row in rows:
        by_family[row["family_code"]].append(row)

    priority = {"MACHINE": 0, "BODYWEIGHT": 1, "DUMBBELL": 2, "BARBELL": 3}
    for members in by_family.values():
        representative = next(row for row in members if row["record_type"] == "REPRESENTATIVE")
        representative_rank = priority.get(
            normalized_equipment(representative["equipment_codes"]), 4
        )
        assert representative_rank == min(
            priority.get(normalized_equipment(row["equipment_codes"]), 4) for row in members
        )


def test_explicit_groups_are_materialized_without_unknown_stable_codes():
    rows, _ = read_catalog(CATALOG)
    by_code = {row["stable_code"]: row for row in rows}
    for family, members in FAMILY_GROUPS.items():
        assert all(code in by_code for code in members), family


def test_squat_family_uses_0514_as_bodyweight_representative():
    rows, _ = read_catalog(CATALOG)
    apply_family_assignments(rows)
    squat = [row for row in rows if row["family_code"] == "SQUAT"]
    representative = next(row for row in squat if row["record_type"] == "REPRESENTATIVE")

    assert representative["stable_code"] == "bodyweight_squat"
    assert all(
        row["representative_stable_code"] == representative["stable_code"]
        for row in squat
        if row["record_type"] == "VARIANT"
    )
