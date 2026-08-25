#!/usr/bin/env python3
"""Build a conservative MET mapping and human-review log for the exercise catalog.

Only an exact, condition-complete Compendium match is auto-approved.  Similar
exercise names, generic resistance-training rows, and condition-dependent
activities remain REVIEW_REQUIRED.

Source: 2024 Adult Compendium of Physical Activities
https://pacompendium.com/adult-compendium/
https://pacompendium.com/conditioning-exercise/
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


MET_SOURCE = "ADULT_COMPENDIUM_PDF_2024"
MET_SOURCE_URL = "https://pacompendium.com/adult-compendium/"
OUTPUT_FIELDS = [
    "exercise_id",
    "exercise_name",
    "representative_id",
    "met_value",
    "intensity_level",
    "met_source",
    "source_activity_name",
    "mapping_basis",
    "review_status",
    "production_eligible",
]
REVIEW_FIELDS = [
    "exercise_id",
    "exercise_name",
    "issue_type",
    "reason",
    "suggested_mapping",
    "required_decision",
]

# These are candidate options only; they are never written as mapped values
# unless the catalog activity is an exact match. Values are transcribed from
# the official 2024 Compendium conditioning-exercise table.
OFFICIAL_CANDIDATES = {
    "jump_rope": [
        ("02068", 11.0, "Rope skipping exercise, general"),
        ("02069", 9.0, "Jumping rope, Digi-Jump Machine, 120 jumps/minute"),
    ],
    "elliptical": [
        ("02048", 5.0, "Elliptical trainer, moderate effort"),
        ("02049", 9.0, "Elliptical trainer, vigorous effort"),
    ],
    "stepmill": [("02065", 9.3, "Stair treadmill ergometer, general")],
    "resistance": [
        ("02050", 6.0, "Resistance (weight lifting - free weight, nautilus or universal-type), power lifting or body building, vigorous effort"),
        ("02052", 5.0, "Resistance (weight) training, squats, deadlift, slow or explosive effort"),
        ("02054", 3.5, "Resistance (weight) training, multiple exercises, 8-15 reps at varied resistance"),
    ],
    "bodyweight": [
        ("02020", 7.5, "Calisthenics, vigorous effort"),
        ("02022", 3.8, "Calisthenics, moderate effort"),
        ("02024", 2.8, "Calisthenics, light effort"),
        ("02056", 3.0, "Body weight resistance exercises, general"),
        ("02057", 6.5, "Body weight resistance exercises, high intensity"),
    ],
    "stretching": [("02101", 2.3, "Stretching, mild")],
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def display_name(row: dict[str, str]) -> str:
    return (
        row.get("name_en", "").strip()
        or row.get("source_name", "").strip()
        or row.get("source_display_name_ko", "").strip()
        or f"UNNAMED ({row['normalized_exercise_id']})"
    )


def candidate_rows(name: str, row: dict[str, str]) -> list[tuple[str, float, str]]:
    normalized = normalize(name)
    if "jump rope" in normalized:
        return OFFICIAL_CANDIDATES["jump_rope"]
    if "elliptical" in normalized:
        return OFFICIAL_CANDIDATES["elliptical"]
    if "stepmill" in normalized:
        return OFFICIAL_CANDIDATES["stepmill"]
    if any(token in normalized for token in ("deadlift", "squat", "press", "curl", "raise", "row", "fly", "pulldown", "push up")):
        return OFFICIAL_CANDIDATES["resistance"]
    if any(token in normalized for token in ("crunch", "plank", "lunge", "push up", "pull up", "jump", "high knee", "step")):
        return OFFICIAL_CANDIDATES["bodyweight"]
    if any(token in normalized for token in ("stretch", "pose", "circles")):
        return OFFICIAL_CANDIDATES["stretching"]
    if any(token in normalized for token in ("run", "walk")):
        return []
    if row.get("source_category") == "training_video":
        return []
    return []


def issue_type(name: str, row: dict[str, str]) -> str:
    normalized = normalize(name)
    if name.startswith("UNNAMED") or row.get("source_category") == "training_video":
        return "AMBIGUOUS_EXERCISE_NAME"
    if "jump rope" in normalized or "elliptical" in normalized or "run" in normalized or "walk" in normalized or "stepmill" in normalized:
        return "MET_RANGE_POSSIBLE"
    if any(token in normalized for token in ("with", "pass through", "on stability ball", "one arm", "alternating", "contralateral")):
        return "COMPOUND_EXERCISE"
    if row.get("equipment_code_candidate", "") not in {"", "BODYWEIGHT"}:
        return "EQUIPMENT_CONDITION_VARIANCE"
    return "COMPENDIUM_ACTIVITY_UNCLEAR"


def candidate_text(candidates: list[tuple[str, float, str]]) -> str:
    if not candidates:
        return "NO_DIRECT_MATCH_IDENTIFIED"
    return " | ".join(f"{code}: {value:g} MET — {activity}" for code, value, activity in candidates)


def source_text(candidates: list[tuple[str, float, str]], activity_code: str = "") -> str:
    if activity_code:
        return f"{MET_SOURCE};activity_code={activity_code};source_locator=PDF page 2;url={MET_SOURCE_URL}"
    codes = ",".join(code for code, _, _ in candidates)
    suffix = f";candidate_activity_codes={codes}" if codes else ";no_direct_activity_code"
    return f"{MET_SOURCE}{suffix};url={MET_SOURCE_URL}"


def load_compendium(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(activity["activity_code"]): activity for activity in data["activities"]}


def build_mapping(rows: list[dict[str, str]], compendium: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mapping_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for row in rows:
        exercise_id = row["normalized_exercise_id"]
        name = display_name(row)
        normalized = normalize(name)
        exact_kettlebell_swing = "kettlebell" in normalized and "swing" in normalized
        if exact_kettlebell_swing and "lunge" not in normalized and "deadlift" not in normalized:
            activity = compendium["02058"]
            mapping_rows.append(
                {
                    "exercise_id": exercise_id,
                    "exercise_name": name,
                    "representative_id": row.get("representative_id", ""),
                    "met_value": activity["met_value"],
                    "intensity_level": "vigorous",
                    "met_source": source_text([], "02058"),
                    "source_activity_name": activity["activity_description"],
                    "mapping_basis": "COMPENDIUM_EXACT_MATCH_EXERCISE_AND_EQUIPMENT",
                    "review_status": "APPROVED",
                    # The input catalog and normalized reference are still DRAFT;
                    # production eligibility is intentionally fail-closed.
                    "production_eligible": "false",
                }
            )
            continue

        candidates = candidate_rows(name, row)
        kind = issue_type(name, row)
        mapping_rows.append(
            {
                "exercise_id": exercise_id,
                "exercise_name": name,
                "representative_id": row.get("representative_id", ""),
                "met_value": "",
                "intensity_level": "REVIEW_REQUIRED",
                "met_source": source_text(candidates),
                "source_activity_name": candidate_text(candidates),
                "mapping_basis": f"REVIEW_REQUIRED__{kind}",
                "review_status": "REVIEW_REQUIRED",
                "production_eligible": "false",
            }
        )
        reason = (
            "정확한 운동·강도·장비 조건이 Compendium 항목과 완전히 대응하지 않아 자동 확정할 수 없음. "
            "후보 MET는 참고 선택지이며 현재 매핑값으로 사용하지 않음."
        )
        if not candidates:
            reason += " 직접 대응 항목이 없거나 속도·반복수·강도 조건이 누락됨."
        elif len(candidates) > 1:
            reason += " 동일 유형에 강도별 MET가 여러 개라 강도 확인이 필요함."
        else:
            reason += " 운동명은 유사하나 장비·강도·수행 조건의 일치 여부를 사람 검수해야 함."
        review_rows.append(
            {
                "exercise_id": exercise_id,
                "exercise_name": name,
                "issue_type": kind,
                "reason": reason,
                "suggested_mapping": candidate_text(candidates),
                "required_decision": "수행 강도·속도·반복수·장비 조건을 확인한 후 하나의 Compendium 활동을 선택하고 APPROVED 처리하거나 REVIEW_REQUIRED 유지",
            }
        )
    return mapping_rows, review_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--compendium", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mapping_rows, review_rows = build_mapping(read_csv(args.catalog), load_compendium(args.compendium))
    write_csv(args.output_dir / "exercise_met_mapping.csv", OUTPUT_FIELDS, mapping_rows)
    write_csv(args.output_dir / "met_mapping_review_log.csv", REVIEW_FIELDS, review_rows)


if __name__ == "__main__":
    main()
