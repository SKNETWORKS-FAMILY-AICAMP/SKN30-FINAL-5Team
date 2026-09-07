#!/usr/bin/env python3
"""Build concise strength guides for dumbbells, barbells and assisted pull-ups.

Preserve existing body-area/movement weight ranges; difficulty is not a weight mapping.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_OUTPUT = ROOT / "data/normalized/gym_equipment_starting_guides_v1.jsonl"

REQUIRED_FIELDS = {
    "exercise_stable_code",
    "equipment_code",
    "proposal_ko",
    "examples_ko",
    "cautions_ko",
    "review_status_code",
    "content_version",
}
GUIDE_EQUIPMENT = frozenset({"DUMBBELL", "BARBELL", "MACHINE"})
LOWER_BODY_AREAS = frozenset({"GLUTES", "QUADRICEPS", "HAMSTRINGS", "ADDUCTORS", "CALVES"})
ASSISTED_MACHINE_CODES = frozenset({"assisted_pull_up", "assisted_standing_pull_up"})
CONTENT_VERSION = "gym-equipment-starting-guide-v1"
REVIEW_STATUS = "DOMAIN_APPROVED"

SERVICE_POLICY_LINES = (
    "추천 무게는 초보자가 운동을 안전하게 시작하기 위한 초기 기준입니다",
    "개인의 근력과 운동 경험 기구 특성에 따라 실제 적정 무게는 달라질 수 있습니다",
    "목표 반복수를 올바른 자세로 수행할 수 있는 범위에서 조절합니다",
)


class GymGuideError(ValueError):
    """Raised when the gym guide source or output violates the policy contract."""


def _codes(value: str) -> set[str]:
    return {item for item in value.split("|") if item}


def _field(row: dict[str, str], name: str) -> str:
    return row.get(name, row.get(f"\ufeff{name}", ""))


def _is_lower_body(row: dict[str, str]) -> bool:
    return _field(row, "body_focus_code") in LOWER_BODY_AREAS


def _dumbbell_start_weight(row: dict[str, str]) -> str:
    if _is_lower_body(row):
        return "처음 시작할 때(권장): 5~10kg"
    if _field(row, "primary_movement_pattern_code") == "ISOLATION":
        return "처음 시작할 때(권장): 1~2kg"
    return "처음 시작할 때(권장): 2~4kg"


def _barbell_start_weight(row: dict[str, str]) -> str:
    if _is_lower_body(row):
        return "처음 시작할 때(권장): 10~20kg"
    return "처음 시작할 때(권장): 5~10kg"


def _proposal(row: dict[str, str], equipment: str) -> str:
    stable_code = _field(row, "stable_code")
    if equipment == "MACHINE" and stable_code in ASSISTED_MACHINE_CODES:
        lines = (
            *SERVICE_POLICY_LINES,
            "설정 무게가 높을수록 보조가 커져 수행이 쉬워집니다",
            "처음 시작할 때(권장): 체중의 60~70% 보조",
        )
    elif equipment == "DUMBBELL":
        lines = (*SERVICE_POLICY_LINES, _dumbbell_start_weight(row))
    elif equipment == "BARBELL":
        lines = (*SERVICE_POLICY_LINES, _barbell_start_weight(row))
    else:
        raise GymGuideError(f"unsupported equipment: {equipment}")
    return "\n".join(lines)


def _cautions(equipment: str, stable_code: str) -> list[str]:
    if equipment == "MACHINE" and stable_code in ASSISTED_MACHINE_CODES:
        return ["보조 무게가 높을수록 쉬워지는 장비인지 먼저 확인합니다"]
    return []


def _guide_equipment(row: dict[str, str]) -> set[str]:
    if _field(row, "training_type_code") != "STRENGTH":
        return set()
    equipment = _codes(_field(row, "equipment_codes")) & GUIDE_EQUIPMENT
    if _field(row, "stable_code") not in ASSISTED_MACHINE_CODES:
        equipment.discard("MACHINE")
    return equipment


def build_rows(catalog_path: Path) -> list[dict[str, Any]]:
    with catalog_path.open(newline="", encoding="utf-8-sig") as handle:
        catalog = list(csv.DictReader(handle))
    if not catalog:
        raise GymGuideError("catalog is empty")
    rows: list[dict[str, Any]] = []
    for catalog_row in catalog:
        stable_code = _field(catalog_row, "stable_code")
        if not stable_code:
            raise GymGuideError("catalog row missing stable_code")
        for equipment in sorted(_guide_equipment(catalog_row)):
            rows.append(
                {
                    "exercise_stable_code": stable_code,
                    "equipment_code": equipment,
                    "proposal_ko": _proposal(catalog_row, equipment),
                    "examples_ko": [],
                    "cautions_ko": _cautions(equipment, stable_code),
                    "review_status_code": REVIEW_STATUS,
                    "content_version": CONTENT_VERSION,
                }
            )
    return sorted(rows, key=lambda row: (row["equipment_code"], row["exercise_stable_code"]))


def validate_rows(catalog_path: Path, rows: list[dict[str, Any]]) -> None:
    with catalog_path.open(newline="", encoding="utf-8-sig") as handle:
        catalog = {_field(row, "stable_code"): row for row in csv.DictReader(handle)}
    expected = {
        (stable_code, equipment)
        for stable_code, row in catalog.items()
        for equipment in _guide_equipment(row)
    }
    actual: set[tuple[str, str]] = set()
    for number, row in enumerate(rows, 1):
        if set(row) != REQUIRED_FIELDS:
            raise GymGuideError(f"row {number}: guide fields do not match the reused contract")
        key = (str(row["exercise_stable_code"]), str(row["equipment_code"]))
        if key in actual:
            raise GymGuideError(f"row {number}: duplicate guide combination: {key}")
        actual.add(key)
        if key[0] not in catalog or key[1] not in _codes(
            _field(catalog[key[0]], "equipment_codes")
        ):
            raise GymGuideError(f"row {number}: guide does not match catalog equipment: {key}")
        if key[1] not in GUIDE_EQUIPMENT:
            raise GymGuideError(f"row {number}: unsupported gym equipment: {key[1]}")
        if row["review_status_code"] != REVIEW_STATUS or row["content_version"] != CONTENT_VERSION:
            raise GymGuideError(f"row {number}: approval/version mismatch")
        if not isinstance(row["proposal_ko"], str) or not row["proposal_ko"].strip():
            raise GymGuideError(f"row {number}: proposal_ko is required")
        if not isinstance(row["examples_ko"], list) or not isinstance(row["cautions_ko"], list):
            raise GymGuideError(f"row {number}: examples_ko and cautions_ko must be arrays")
    if actual != expected:
        raise GymGuideError("guide rows do not cover exactly the gym equipment combinations")


def render(rows: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rows = build_rows(args.catalog)
    validate_rows(args.catalog, rows)
    expected = render(rows)
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != expected:
            raise GymGuideError("output is missing or not generated from the approved policy")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
