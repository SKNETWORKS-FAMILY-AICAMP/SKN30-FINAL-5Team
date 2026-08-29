"""User-reviewed v2.0.2 exercise difficulty policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

POLICY_PATH = (
    Path(__file__).resolve().parents[1] / "normalized/exercise_difficulty_policy_v2_0_2.json"
)


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_difficulty_policy(
    row: dict[str, Any], current_difficulty: str, policy: dict[str, Any] | None = None
) -> tuple[str, str]:
    """Return the reviewed difficulty and the applied rule code."""
    selected_policy = policy or load_policy()
    stable_code = str(row.get("stable_code") or "")
    equipment_codes = {str(value) for value in row.get("equipment_codes") or []}
    for rule in selected_policy["rules_in_priority_order"]:
        equipment = rule.get("when_equipment_contains")
        stable_codes = {str(value) for value in rule.get("stable_codes") or []}
        excluded = {str(value) for value in rule.get("exclude_stable_codes") or []}
        contains = str(rule.get("stable_code_contains") or "")
        if equipment and equipment not in equipment_codes:
            continue
        if stable_codes and stable_code not in stable_codes:
            continue
        if contains and (contains not in stable_code or stable_code in excluded):
            continue
        return str(rule["difficulty_code"]), str(rule["rule_code"])
    return current_difficulty, "NO_POLICY_OVERRIDE"
