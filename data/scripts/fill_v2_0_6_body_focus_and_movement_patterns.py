#!/usr/bin/env python3
"""Fill approved body-focus and movement-pattern values from exercise instructions."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_MAPPING = PROJECT_ROOT / "data/normalized/v2_0_6_catalog_source_mapping.json"
DEFAULT_REPORT = (
    PROJECT_ROOT / "data/reports/v2_0_6_catalog_merge/body_focus_movement_pattern_apply_report.json"
)
BODY_FOCUS_FIELD = "body_focus_code"
MOVEMENT_FIELD = "primary_movement_pattern_code"
REQUIRED_FIELDS = {
    "source_identity",
    "stable_code",
    "name_ko",
    "name_en",
    "instruction_summary_ko",
    "training_type_code",
    BODY_FOCUS_FIELD,
    MOVEMENT_FIELD,
}
ADDUCTOR_IDENTITIES = frozenset({"0168", "0597", "3667"})
MOVEMENT_PATTERN_OVERRIDES = {"0514": "KNEE_DOMINANT"}
ALLOWED_MOVEMENT_PATTERNS = frozenset(
    {
        "BALANCE",
        "CYCLING",
        "ELLIPTICAL",
        "VERTICAL_PULL",
        "HORIZONTAL_PULL",
        "HORIZONTAL_PUSH",
        "VERTICAL_PUSH",
        "KNEE_DOMINANT",
        "HIP_DOMINANT",
        "KNEE_FLEXION",
        "ISOLATION",
        "GAIT",
        "CORE_BRACE",
        "MOBILITY_STRETCH",
        "JUMP_PLYOMETRIC",
    }
)


class PatternFillError(ValueError):
    """Raised when approved body-focus or movement values cannot be filled."""


def read_catalog(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [
                {key: (value or "").strip() for key, value in row.items() if key is not None}
                for row in reader
            ]
    except OSError as exc:
        raise PatternFillError(f"cannot read catalog: {path}") from exc
    missing = sorted(REQUIRED_FIELDS - set(fields))
    if missing:
        raise PatternFillError(f"catalog is missing columns: {', '.join(missing)}")
    identities = [row["source_identity"] for row in rows]
    if not rows or not all(identities) or len(identities) != len(set(identities)):
        raise PatternFillError("source_identity values must be unique and non-empty")
    return rows, fields


def _text(row: dict[str, str]) -> str:
    return " ".join(
        (row["name_ko"], row["name_en"], row["stable_code"], row["instruction_summary_ko"])
    ).lower()


def classify_movement_pattern(row: dict[str, str]) -> str:
    """Classify only from the displayed exercise action and its instruction."""
    text = _text(row)
    training_type = row["training_type_code"]

    if "balance" in text or "밸런스" in text or "중심을 잡" in text:
        return "BALANCE"
    if "cycle" in text or "bike" in text or "사이클" in text or "페달" in text:
        return "CYCLING"
    if "elliptical" in text or "일립티컬" in text:
        return "ELLIPTICAL"
    if training_type == "MOBILITY":
        return "MOBILITY_STRETCH"
    if "jump" in text or "점프" in text or "착지" in text:
        return "JUMP_PLYOMETRIC"
    if any(token in text for token in ("달리", "달립", "걷", "walk", "run", "스텝")):
        return "GAIT"
    if any(
        token in text
        for token in (
            "크런치",
            "싯업",
            "sit up",
            "sit-up",
            "컬업",
            "curl up",
            "플랭크",
            "plank",
            "복근",
            "복부",
            "골반 기울",
            "twist",
            "트위스트",
            "side bend",
            "사이드 벤드",
        )
    ):
        return "CORE_BRACE"
    if any(
        token in text
        for token in ("pull up", "pull-up", "풀업", "pulldown", "풀다운", "랫풀", "lat pulldown")
    ):
        return "VERTICAL_PULL"
    if any(token in text for token in ("row", "로우", "몸 쪽으로 당기", "가슴 쪽으로 당기")):
        return "HORIZONTAL_PULL"
    if any(token in text for token in ("overhead", "오버헤드", "머리 위로 밀", "위로 밀어")):
        return "VERTICAL_PUSH"
    if any(
        token in text for token in ("leg curl", "레그 컬", "무릎을 굽혀 다리", "무릎을 구부려 다리")
    ):
        return "KNEE_FLEXION"
    if any(
        token in text
        for token in (
            "deadlift",
            "데드리프트",
            "good morning",
            "굿모닝",
            "bridge",
            "브릿지",
            "hip extension",
            "힙 익스텐션",
            "힙 리프팅",
            "덩키킥",
            "엉덩이를 들어",
        )
    ):
        return "HIP_DOMINANT"
    if any(
        token in text
        for token in (
            "squat",
            "스쿼트",
            "lunge",
            "런지",
            "leg press",
            "레그 프레스",
            "step up",
            "스텝업",
            "무릎을 굽혀 몸",
            "의자에 앉듯",
        )
    ):
        return "KNEE_DOMINANT"
    if any(
        token in text
        for token in (
            "bench press",
            "벤치 프레스",
            "push up",
            "push-up",
            "푸시업",
            "dip",
            "딥",
            "fly",
            "플라이",
            "가슴 앞까지",
            "가슴 앞에서",
        )
    ):
        return "HORIZONTAL_PUSH"
    return "ISOLATION"


def apply_fill(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    body_focus_updates: list[dict[str, str]] = []
    pattern_updates: list[dict[str, str]] = []
    pattern_counts: Counter[str] = Counter()
    present = {row["source_identity"] for row in rows}
    missing = ADDUCTOR_IDENTITIES - present
    if missing:
        raise PatternFillError(f"missing required adductor rows: {sorted(missing)}")

    for row in rows:
        identity = row["source_identity"]
        if identity in ADDUCTOR_IDENTITIES and row[BODY_FOCUS_FIELD] != "ADDUCTORS":
            body_focus_updates.append(
                {"source_identity": identity, "before": row[BODY_FOCUS_FIELD], "after": "ADDUCTORS"}
            )
            row[BODY_FOCUS_FIELD] = "ADDUCTORS"
        override = MOVEMENT_PATTERN_OVERRIDES.get(identity)
        if override and row[MOVEMENT_FIELD] != override:
            pattern = override
            pattern_updates.append(
                {
                    "source_identity": identity,
                    "stable_code": row["stable_code"],
                    "before": row[MOVEMENT_FIELD],
                    "after": pattern,
                }
            )
            row[MOVEMENT_FIELD] = pattern
            pattern_counts[pattern] += 1
        elif not row[MOVEMENT_FIELD]:
            pattern = classify_movement_pattern(row)
            if pattern not in ALLOWED_MOVEMENT_PATTERNS:
                raise PatternFillError(f"unsupported movement pattern: {identity}: {pattern}")
            row[MOVEMENT_FIELD] = pattern
            pattern_updates.append(
                {"source_identity": identity, "stable_code": row["stable_code"], "after": pattern}
            )
            pattern_counts[pattern] += 1
    if any(not row[MOVEMENT_FIELD] for row in rows):
        raise PatternFillError("primary movement patterns remain blank")
    return rows, {
        "status": "DRAFT",
        "production_eligible": False,
        "input_record_count": len(rows),
        "body_focus_updates": body_focus_updates,
        "movement_pattern_updates": pattern_updates,
        "movement_pattern_fill_counts": dict(sorted(pattern_counts.items())),
    }


def update_source_mapping(path: Path, rows: list[dict[str, str]], report: dict[str, Any]) -> None:
    try:
        mapping = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PatternFillError(f"cannot read source mapping: {path}") from exc
    records = mapping.get("records")
    if not isinstance(records, list):
        raise PatternFillError("source mapping records are invalid")
    by_identity = {row["source_identity"]: row for row in rows}
    changed_focus = {item["source_identity"] for item in report["body_focus_updates"]}
    changed_patterns = {item["source_identity"] for item in report["movement_pattern_updates"]}
    for record in records:
        identity = str(record.get("source_identity", ""))
        fields = record.get("fields")
        row = by_identity.get(identity)
        if row is None or not isinstance(fields, dict):
            continue
        if identity in changed_focus:
            fields[BODY_FOCUS_FIELD] = {
                "source": "USER_CONFIRMED_ADDUCTOR_ASSIGNMENT",
                "value": "ADDUCTORS",
            }
        if identity in changed_patterns:
            fields[MOVEMENT_FIELD] = {
                "source": "instruction_summary_ko:PRIMARY_ACTION_CLASSIFICATION",
                "value": row[MOVEMENT_FIELD],
            }
    policy = mapping.setdefault("policy", {})
    policy["primary_movement_pattern_code"] = "FILL_BLANKS_FROM_INSTRUCTION_SUMMARY_KO"
    path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_catalog(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows, fields = read_catalog(args.catalog)
    rows, report = apply_fill(rows)
    if not args.dry_run:
        write_catalog(args.catalog, rows, fields)
        update_source_mapping(args.mapping, rows, report)
        write_report(args.report, report)
    print(
        json.dumps(
            {
                "body_focus_updates": len(report["body_focus_updates"]),
                "movement_pattern_updates": len(report["movement_pattern_updates"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
