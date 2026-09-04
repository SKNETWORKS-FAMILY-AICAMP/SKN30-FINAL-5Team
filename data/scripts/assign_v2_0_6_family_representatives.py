#!/usr/bin/env python3
"""Assign v2.0.6 movement families and representative/variant links.

The normalized catalog remains the only editable source.  This script applies
the reviewed movement-family decisions and derives the representative from
the equipment priority requested for v2.0.6.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_REPORT = ROOT / "data/normalized/v2_0_6_family_representative_source_map.json"

EQUIPMENT_PRIORITY = {
    "MACHINE": 0,
    "BODYWEIGHT": 1,
    "DUMBBELL": 2,
    "BARBELL": 3,
}
DIFFICULTY_PRIORITY = {"BEGINNER": 0, "INTERMEDIATE": 1}
VALID_RECORD_TYPES = {"REPRESENTATIVE", "VARIANT"}

# When equipment and difficulty tie, prefer the plain/base movement over a
# unilateral, grip, stance, or range-of-motion variation.
REPRESENTATIVE_PREFERENCES = {
    "CALF_RAISE_STANDING": "bodyweight_standing_calf_raise_isolation_bodyweight",
    "BENT_OVER_ROW": "dumbbell_bent_over_row",
    "SEATED_CABLE_ROW": "seated_cable_row_horizontal_pull_cable_machine",
    "REVERSE_FLY": "lever_seated_reverse_fly",
    "BICEPS_CURL": "dumbbell_standing_curl_isolation_dumbbell",
    "PUSH_UP": "push_up_horizontal_push_bodyweight",
    "CRUNCH": "bodyweight_crunch_core_brace_bodyweight",
    "SIT_UP": "curl_up",
    "SQUAT": "bodyweight_squat",
}

# Only high-confidence same-movement relationships are grouped here.  The
# remaining rows receive a stable singleton family and stay representatives.
FAMILY_GROUPS: dict[str, tuple[str, ...]] = {
    "CALF_RAISE_STANDING": (
        "band_two_legs_calf_raise_band_under_both_legs_v_2_isolation_resistance_band",
        "bodyweight_standing_calf_raise_isolation_bodyweight",
        "one_leg_donkey_calf_raise_isolation_bodyweight",
        "barbell_standing_leg_calf_raise",
        "barbell_standing_rocking_leg_calf_raise",
    ),
    "CALF_RAISE_REVERSE": (
        "reverse_calf_raise_isolation_resistance_band",
        "smith_reverse_calf_raises_isolation_machine",
    ),
    "FRONT_RAISE": (
        "barbell_front_raise_isolation_barbell",
        "dumbbell_lateral_to_front_raise_isolation_dumbbell",
    ),
    "PULL_UP": (
        "assisted_pull_up",
        "assisted_standing_pull_up",
        "bodyweight_pull_up_biceps_vertical_pull_bodyweight_pull_up_bar",
    ),
    "LAT_PULLDOWN": (
        "alternate_lateral_pulldown",
        "lat_pulldown_vertical_pull_cable_machine",
    ),
    "BENT_OVER_ROW": (
        "barbell_bent_over_row",
        "dumbbell_one_arm_bent_over_row",
        "dumbbell_bent_over_row",
    ),
    "INCLINE_ROW": (
        "barbell_incline_row",
        "dumbbell_incline_row",
    ),
    "SEATED_CABLE_ROW": (
        "seated_cable_row_horizontal_pull_cable_machine",
        "cable_decline_seated_wide_grip_row",
        "cable_low_seated_row",
        "cable_seated_one_arm_alternate_row",
        "cable_seated_wide_grip_row",
        "cable_straight_back_seated_row",
    ),
    "REAR_DELTOID_ROW": (
        "barbell_rear_delt_row",
        "cable_standing_rear_delt_row_with_rope",
    ),
    "REVERSE_FLY": (
        "dumbbell_rear_fly_isolation_dumbbell",
        "dumbbell_incline_rear_lateral_raise",
        "dumbbell_rear_lateral_raise_support_head",
        "lever_seated_reverse_fly_parallel_grip",
        "lever_seated_reverse_fly",
    ),
    "LATERAL_RAISE": (
        "dumbbell_lateral_raise_isolation_dumbbell",
        "lever_lateral_raise",
    ),
    "BICEPS_CURL": (
        "barbell_curl",
        "barbell_lying_preacher_curl",
        "barbell_preacher_curl",
        "dumbbell_alternate_biceps_curl",
        "dumbbell_incline_curl",
        "dumbbell_preacher_curl_isolation_dumbbell",
        "dumbbell_standing_curl_isolation_dumbbell",
    ),
    "SEATED_SHOULDER_PRESS": (
        "barbell_seated_overhead_press",
        "seated_shoulder_press_vertical_push_dumbbell",
    ),
    "DEADLIFT": (
        "barbell_deadlift_hip_dominant_barbell",
        "dumbbell_deadlift",
    ),
    "SPLIT_SQUAT": (
        "bodyweight_split_squat_knee_dominant_bodyweight",
        "dumbbell_single_leg_split_squat",
        "band_single_leg_split_squat",
        "smith_single_leg_split_squat",
    ),
    "SQUAT": (
        "bodyweight_squat",
        "dumbbell_goblet_squat_knee_dominant_dumbbell",
        "barbell_bench_squat",
        "dumbbell_bench_squat",
        "barbell_full_squat",
        "barbell_narrow_stance_squat",
        "barbell_overhead_squat",
    ),
    "LUNGE": (
        "bodyweight_forward_lunge_knee_dominant_bodyweight",
        "barbell_lunge",
        "walking_lunge",
        "smith_sprint_lunge",
    ),
    "LEG_EXTENSION": (
        "lever_leg_extension",
        "resistance_band_leg_extension",
    ),
    "LEG_CURL": (
        "seated_leg_curl_knee_flexion_machine",
        "lever_lying_leg_curl",
        "lever_lying_two_one_leg_curl",
    ),
    "HIP_ABDUCTION": (
        "lever_seated_hip_abduction",
        "side_hip_abduction",
        "resistance_band_seated_hip_abduction",
    ),
    "HIP_ADDUCTION": (
        "cable_hip_adduction",
        "lever_seated_hip_adduction",
        "side_lying_hip_adduction_male",
    ),
    "GLUTE_BRIDGE": (
        "bodyweight_glute_bridge_hip_dominant_bodyweight",
        "rear_decline_bridge",
        "single_leg_bridge_with_outstretched_leg",
    ),
    "GOOD_MORNING": (
        "barbell_good_morning",
        "barbell_seated_good_morning",
        "smith_bent_knee_good_morning",
    ),
    "CHEST_PRESS": (
        "smith_bench_press",
        "barbell_incline_bench_press",
        "cable_incline_bench_press",
        "dumbbell_incline_bench_press",
        "dumbbell_decline_hammer_press",
        "dumbbell_incline_hammer_press",
    ),
    "CHEST_FLY": (
        "lever_seated_fly",
        "cable_decline_fly",
    ),
    "PUSH_UP": (
        "push_up_horizontal_push_bodyweight",
        "push_up_wall",
        "close_grip_push_up_horizontal_push_bodyweight",
        "close_grip_push_up_on_knees",
    ),
    "DIP": (
        "assisted_triceps_dip_kneeling",
        "bench_dip_knees_bent",
        "chest_dip_on_dip_pull_up_cage",
    ),
    "TRICEPS_EXTENSION": (
        "overhead_triceps_extension_isolation_barbell",
        "dumbbell_seated_bench_extension",
        "bodyweight_kneeling_triceps_extension",
    ),
    "SHRUG": (
        "dumbbell_shrug_isolation_dumbbell",
        "barbell_shrug",
    ),
    "JUMP_SQUAT": (
        "jump_squat",
        "barbell_jump_squat",
        "dumbbell_plyo_squat",
    ),
    "CRUNCH": (
        "bodyweight_crunch_core_brace_bodyweight",
        "crunch_on_stability_ball",
        "crunch_on_stability_ball_arms_straight",
    ),
    "SIDE_PLANK": (
        "bodyweight_incline_side_plank",
        "side_bridge",
    ),
    "SIT_UP": (
        "curl_up",
        "flexion_leg_sit_up_bent_knee",
        "quarter_sit_up",
    ),
}


def read_catalog(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if not rows:
        raise ValueError("normalized catalog is empty")
    if "family_code" not in fields or "record_type" not in fields:
        raise ValueError("family_code and record_type columns are required")
    return rows, fields


def normalized_equipment(value: str) -> str:
    tokens = {part.strip() for part in value.split("|") if part.strip()}
    if "MACHINE" in tokens or "CABLE_MACHINE" in tokens:
        return "MACHINE"
    if "BODYWEIGHT" in tokens:
        return "BODYWEIGHT"
    if "DUMBBELL" in tokens:
        return "DUMBBELL"
    if "BARBELL" in tokens:
        return "BARBELL"
    return "OTHER"


def singleton_family(stable_code: str) -> str:
    code = re.sub(r"[^A-Za-z0-9]+", "_", stable_code).strip("_")
    return code.upper()


def representative_sort_key(
    family: str, row: dict[str, str]
) -> tuple[int, int, int, str]:
    equipment = normalized_equipment(row.get("equipment_codes", ""))
    return (
        EQUIPMENT_PRIORITY.get(equipment, 4),
        DIFFICULTY_PRIORITY.get(row.get("difficulty_code", ""), 2),
        0 if row.get("stable_code") == REPRESENTATIVE_PREFERENCES.get(family) else 1,
        row.get("stable_code", ""),
    )


def validate_groups(rows_by_code: dict[str, dict[str, str]]) -> None:
    seen: dict[str, str] = {}
    for family, members in FAMILY_GROUPS.items():
        if len(members) < 2:
            raise ValueError(f"family group must contain at least two records: {family}")
        for stable_code in members:
            if stable_code not in rows_by_code:
                raise ValueError(f"family member not found: {family}/{stable_code}")
            previous = seen.get(stable_code)
            if previous and previous != family:
                raise ValueError(f"record appears in multiple groups: {stable_code}")
            seen[stable_code] = family


def apply_family_assignments(rows: list[dict[str, str]]) -> dict[str, Any]:
    rows_by_code = {row.get("stable_code", ""): row for row in rows}
    if len(rows_by_code) != len(rows) or "" in rows_by_code:
        raise ValueError("stable_code values must be unique and non-empty")
    validate_groups(rows_by_code)

    group_by_code = {
        stable_code: family
        for family, members in FAMILY_GROUPS.items()
        for stable_code in members
    }
    grouped_codes = set(group_by_code)
    family_members: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        stable_code = row["stable_code"]
        if stable_code in group_by_code:
            family = group_by_code[stable_code]
        else:
            # Existing single-record family codes are retained.  Invalid
            # multi-record legacy families are split into stable singletons.
            family = row.get("family_code", "").strip() or singleton_family(stable_code)
        family_members[family].append(row)

    legacy_counts = Counter(
        row.get("family_code", "").strip()
        for row in rows
        if row.get("family_code", "").strip()
    )
    for family, members in list(family_members.items()):
        if family not in FAMILY_GROUPS and len(members) > 1:
            # A legacy family with several representatives is not a stable
            # family decision.  Split it unless it was explicitly reviewed.
            family_members.pop(family)
            for row in members:
                row_family = singleton_family(row["stable_code"])
                family_members[row_family].append(row)

    decisions: list[dict[str, Any]] = []
    for family in sorted(family_members):
        members = family_members[family]
        representative = sorted(members, key=lambda row: representative_sort_key(family, row))[0]
        for row in members:
            row["family_code"] = family
            if row is representative:
                row["record_type"] = "REPRESENTATIVE"
                row["representative_stable_code"] = ""
            else:
                row["record_type"] = "VARIANT"
                row["representative_stable_code"] = representative["stable_code"]
            decisions.append(
                {
                    "stable_code": row["stable_code"],
                    "family_code": family,
                    "record_type": row["record_type"],
                    "representative_stable_code": row["representative_stable_code"],
                    "equipment_class": normalized_equipment(row.get("equipment_codes", "")),
                    "difficulty_code": row.get("difficulty_code", ""),
                    "decision_source": (
                        "EXPLICIT_SAME_MOVEMENT_GROUP"
                        if family in FAMILY_GROUPS
                        else "SINGLETON_OR_LEGACY_SINGLE_FAMILY"
                    ),
                }
            )

    return {
        "schema_version": "exercise-catalog-v2.0.6-family-representative-v1",
        "status": "DRAFT",
        "policy": {
            "family_code": "shared_stable_movement_family_code",
            "representative_priority": ["MACHINE", "BODYWEIGHT", "DUMBBELL", "BARBELL"],
            "difficulty_priority_reference": ["BODYWEIGHT", "DUMBBELL", "MACHINE", "BARBELL"],
            "difficulty_values_changed": False,
            "unreviewed_ambiguous_rows": "kept_as_singleton_representatives",
        },
        "counts": {
            "catalog_records": len(rows),
            "family_count": len(family_members),
            "representative_count": sum(row["record_type"] == "REPRESENTATIVE" for row in rows),
            "variant_count": sum(row["record_type"] == "VARIANT" for row in rows),
            "explicit_family_count": len(FAMILY_GROUPS),
            "explicit_group_member_count": len(grouped_codes),
            "legacy_family_value_count": len(legacy_counts),
        },
        "explicit_family_groups": {
            family: list(members) for family, members in sorted(FAMILY_GROUPS.items())
        },
        "records": sorted(decisions, key=lambda item: item["stable_code"]),
    }


def write_catalog(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    rows, fields = read_catalog(args.input)
    report = apply_family_assignments(rows)
    write_catalog(args.input, rows, fields)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
