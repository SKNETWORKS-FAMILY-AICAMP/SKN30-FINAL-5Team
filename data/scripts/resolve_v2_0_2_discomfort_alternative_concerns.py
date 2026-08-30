"""Resolve reviewed discomfort-map concerns with fail-closed safe variants.

The original reviewed map is immutable audit input. Direct-load rows and
concerns that cannot preserve the movement without pain-area load are removed.
Every retained concern is redirected to a separate, non-production safe
exercise variant with fixed posture, fixed support, no-load guards, and an
explicit stop guard.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT / "generated/exercise-catalog-v2.0.2-final/audit/alternatives/"
    "reviewed_discomfort_alternative_map_v2_0_2.jsonl"
)
DEFAULT_POLICY = ROOT / "normalized/discomfort_alternative_concern_resolution_policy_v2_0_2.json"
DEFAULT_OUTPUT = ROOT / "generated/exercise-catalog-v2.0.2-final/audit/alternatives"

RESOLVED_MAP_NAME = "resolved_discomfort_alternative_map_v2_0_2.jsonl"
REMOVED_MAP_NAME = "concern_resolution_removed_map_v2_0_2.jsonl"
PENDING_MAP_NAME = "difficulty_policy_pending_map_v2_0_2.jsonl"
SAFE_VARIANTS_NAME = "discomfort_safe_variants_v2_0_2.jsonl"
REPORT_NAME = "discomfort_alternative_concern_resolution_report_v2_0_2.json"
CSV_NAME = "discomfort_alternative_concern_resolution_summary_v2_0_2.csv"
DEFAULT_DIFFICULTY_REVIEW = (
    ROOT / "generated/exercise-catalog-v2.0.2-final/audit/integrity/"
    "alternative_difficulty_policy_review_batch_v2_0_2.jsonl"
)

EXPECTED_INPUT_COUNT = 1517
EXPECTED_PENDING_COUNT = 29
EXPECTED_DIRECT_REMOVE_COUNT = 347
EXPECTED_CONCERN_COUNT = 781
NO_LOAD_GUARDS = [
    "NO_PAIN_AREA_WEIGHT_BEARING",
    "NO_PAIN_AREA_GRIP",
    "NO_PAIN_AREA_BRACING",
]
STOP_GUARD = "STOP_IF_DISCOMFORT_INCREASES"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be an object: {path}:{line_number}")
            value["_input_line_number"] = line_number
            rows.append(value)
    return rows


def read_pending_relation_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        str(row["map_relation_id"])
        for row in read_jsonl(path)
        if row.get("change_code")
        in {"ADDED_AFTER_DIFFICULTY_POLICY", "REMOVED_AFTER_DIFFICULTY_POLICY"}
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(
                {key: value for key, value in row.items() if key != "_input_line_number"},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_reference(path: Path) -> str:
    if path.is_relative_to(ROOT.parent):
        return str(path.relative_to(ROOT.parent))
    return str(path)


def target_ids(policy: dict[str, Any], section: str, area: str, condition: str) -> set[str]:
    area_policy = policy[section].get(area, {})
    return {str(value) for value in area_policy.get(condition, [])}


def classify(row: dict[str, Any], policy: dict[str, Any]) -> str:
    area = str(row["pain_discomfort_area_code"])
    condition = str(row["condition_code"])
    target_id = str(row["target_exercise_id"])
    direct = target_ids(policy, "direct_remove_targets", area, condition)
    concerns = target_ids(policy, "concern_targets", area, condition)
    if target_id in direct:
        return "REMOVE_DIRECT_LOAD"
    if target_id not in concerns:
        return "KEEP_UNCHANGED"
    infeasible = {str(value) for value in policy["safe_variant_not_feasible_targets"].get(area, [])}
    if target_id in infeasible:
        return "REMOVE_SAFE_VARIANT_NOT_FEASIBLE"
    return "KEEP_AS_SAFE_VARIANT"


def validate_policy(
    rows: list[dict[str, Any]],
    policy: dict[str, Any],
    pending_ids: set[str] | frozenset[str] = frozenset(),
) -> Counter[str]:
    for area in policy["concern_targets"]:
        for condition in ("NRS_1_3", "NRS_4_6"):
            direct = target_ids(policy, "direct_remove_targets", area, condition)
            concerns = target_ids(policy, "concern_targets", area, condition)
            overlap = direct & concerns
            if overlap:
                raise ValueError(
                    f"direct-remove and concern targets overlap: {area}/{condition}/{overlap}"
                )
    if len(pending_ids) != EXPECTED_PENDING_COUNT:
        raise ValueError(f"unexpected pending review count: {len(pending_ids)}")
    counts = Counter(
        classify(row, policy) for row in rows if str(row["map_relation_id"]) not in pending_ids
    )
    if len(rows) != EXPECTED_INPUT_COUNT:
        raise ValueError(f"unexpected input count: {len(rows)}")
    if counts["REMOVE_DIRECT_LOAD"] != EXPECTED_DIRECT_REMOVE_COUNT:
        raise ValueError(f"unexpected direct-remove count: {counts}")
    concern_count = counts["KEEP_AS_SAFE_VARIANT"] + counts["REMOVE_SAFE_VARIANT_NOT_FEASIBLE"]
    if concern_count != EXPECTED_CONCERN_COUNT:
        raise ValueError(f"unexpected concern count: {counts}")
    return counts


def safe_variant_identity(area: str, base_stable_code: str) -> tuple[str, str]:
    identity = f"{area}|{base_stable_code}|safe-v1"
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    exercise_id = f"DVAR-{suffix.upper()}"
    stable_code = f"{base_stable_code}__{area.lower()}_no_load_safe_v1"
    return exercise_id, stable_code


def safe_variant_instruction(
    area: str,
    target_name: str,
    posture_code: str,
    support_code: str,
) -> tuple[str, list[str]]:
    summary = (
        f"{target_name}의 {area} 통증 비부하 변형입니다. "
        f"{posture_code} 자세와 {support_code} 지지를 고정하고, "
        "통증 부위로 체중을 받거나 잡거나 버티지 않습니다."
    )
    cues = [
        f"{posture_code} 자세를 먼저 잡고 {support_code} 지지를 끝날 때까지 유지한다.",
        f"{area} 부위는 체중지지·그립·브레이싱에 사용하지 않는다.",
        (
            "원본의 서기·기울이기·손으로 잡기 지시는 사용하지 않고, "
            f"{target_name} 목표 관절만 천천히 움직인다."
        ),
        "통증과 불편감이 증가하면 즉시 중단한다.",
    ]
    return summary, cues


def movement_name_without_posture(name: str) -> str:
    for prefix in (
        "스탠딩 ",
        "시티드 ",
        "앉아서 ",
        "누워서 ",
        "옆으로 누워 ",
        "무릎 꿇고 ",
        "벽 짚고 ",
        "의자 잡고 ",
    ):
        if name.startswith(prefix):
            return name.removeprefix(prefix)
    return name


def posture_label(posture_code: str) -> str:
    if "SUPINE" in posture_code:
        return "누워서 전신 지지"
    if "SEATED" in posture_code:
        return "등받이 지지 좌식"
    return "고정 지지"


def support_equipment_codes(support_code: str) -> list[str]:
    if "MAT" in support_code:
        return ["MAT", "SUPPORT_CUSHION"]
    return ["PADDED_CHAIR", "SUPPORT_CUSHION"]


def make_variant(
    row: dict[str, Any],
    policy: dict[str, Any],
    condition_codes: list[str],
) -> dict[str, Any]:
    area = str(row["pain_discomfort_area_code"])
    profile = policy["safe_posture_profiles"][area]
    base_id = str(row["target_exercise_id"])
    base_code = str(row["target_exercise_stable_code"])
    base_name = str(row["target_exercise_name_ko"])
    variant_id, stable_code = safe_variant_identity(area, base_code)
    is_mobility = row["target_training_type_code"] == "MOBILITY"
    posture_code = str(
        profile.get("mobility_posture_code", profile["posture_code"])
        if is_mobility
        else profile["posture_code"]
    )
    support_code = str(
        profile.get("mobility_support_code", profile["support_code"])
        if is_mobility
        else profile["support_code"]
    )
    movement_name = movement_name_without_posture(base_name)
    variant_name = f"{posture_label(posture_code)} {movement_name} ({area} 통증 비부하)"
    summary, cues = safe_variant_instruction(
        area,
        movement_name,
        posture_code,
        support_code,
    )
    return {
        "exercise_id": variant_id,
        "stable_code": stable_code,
        "record_type": "SEPARATE_EXERCISE",
        "name_ko": variant_name,
        "base_exercise_id": base_id,
        "base_exercise_stable_code": base_code,
        "pain_discomfort_area_code": area,
        "condition_codes": condition_codes,
        "primary_movement_pattern_code": row["target_primary_movement_pattern_code"],
        "primary_body_area_codes": row["target_primary_body_area_codes"],
        "secondary_body_area_codes": row["target_secondary_body_area_codes"],
        "difficulty_code": row["target_difficulty_code"],
        "training_type_code": row["target_training_type_code"],
        "equipment_codes": row["target_equipment_codes"],
        "location_codes": row["target_location_codes"],
        "timing_mode_code": row["target_timing_mode_code"],
        "recovery_eligible": row["target_recovery_eligible"],
        "fixed_posture_code": posture_code,
        "fixed_support_code": support_code,
        "support_equipment_codes": support_equipment_codes(support_code),
        "pain_area_load_guard_codes": NO_LOAD_GUARDS,
        "stop_guard_code": STOP_GUARD,
        "instruction_summary_ko": summary,
        "form_cues_ko": cues,
        "variant_relation_code": "PAIN_AREA_NO_LOAD_SAFE_VARIANT",
        "original_posture_instructions_replaced": True,
        "review_status_code": "REVIEW_REQUIRED",
        "production_eligible": False,
        "policy_version": policy["policy_version"],
        "reviewed_at": policy["reviewed_at"],
        "reviewer": policy["reviewer"],
    }


def resolved_variant_row(
    row: dict[str, Any], variant: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    result = dict(row)
    result.update(
        {
            "base_target_exercise_id": row["target_exercise_id"],
            "base_target_exercise_stable_code": row["target_exercise_stable_code"],
            "target_exercise_id": variant["exercise_id"],
            "target_exercise_stable_code": variant["stable_code"],
            "target_exercise_name_ko": variant["name_ko"],
            "target_record_type": "SEPARATE_EXERCISE",
            "concern_resolution_action_code": "KEEP_AS_SAFE_VARIANT",
            "fixed_posture_code": variant["fixed_posture_code"],
            "fixed_support_code": variant["fixed_support_code"],
            "pain_area_load_guard_codes": NO_LOAD_GUARDS,
            "stop_guard_code": STOP_GUARD,
            "review_stage_code": "CONCERN_RESOLUTION_SAFE_VARIANT",
            "review_reason_code": "SAFE_VARIANT_ALL_GUARDS_PRESENT",
            "review_reason_ko": (
                "고정 안전 자세·지지, 통증 부위 비부하 3종 guard, "
                "통증 증가 즉시 중단 guard를 갖춘 별도 운동 variant로 치환했다."
            ),
            # The relation was domain-reviewed in the input map.  The generated
            # safe-variant exercise remains REVIEW_REQUIRED separately, so the
            # relation approval must not be downgraded here.
            "review_status_code": row["review_status_code"],
            "production_eligible": False,
            "concern_resolution_policy_version": policy["policy_version"],
        }
    )
    return result


def removed_row(row: dict[str, Any], action: str, policy: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    direct = action == "REMOVE_DIRECT_LOAD"
    result.update(
        {
            "review_decision": "REMOVE",
            "concern_resolution_action_code": action,
            "review_stage_code": "CONCERN_RESOLUTION_REMOVE",
            "review_reason_code": (
                "DIRECT_PAIN_AREA_LOAD" if direct else "SAFE_VARIANT_NOT_FEASIBLE"
            ),
            "review_reason_ko": (
                "대체 운동이 통증 부위에 직접 체중지지·그립·브레이싱 "
                "또는 관절 부하를 발생시켜 제거한다."
                if direct
                else "원 운동을 유지하면 통증 부위 비부하 조건을 만족할 수 없어 제거한다."
            ),
            "review_status_code": "REVIEW_REQUIRED",
            "production_eligible": False,
            "concern_resolution_policy_version": policy["policy_version"],
        }
    )
    return result


def unchanged_row(row: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.update(
        {
            "base_target_exercise_id": row["target_exercise_id"],
            "base_target_exercise_stable_code": row["target_exercise_stable_code"],
            "concern_resolution_action_code": "KEEP_UNCHANGED",
            "concern_resolution_policy_version": policy["policy_version"],
        }
    )
    return result


def pending_row(row: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.update(
        {
            "review_decision": "PENDING_REVIEW",
            "concern_resolution_action_code": "PENDING_DIFFICULTY_POLICY_REVIEW",
            "review_stage_code": "DIFFICULTY_POLICY_REVIEW_REQUIRED",
            "review_reason_code": "ALTERNATIVE_SET_CHANGED_BY_DIFFICULTY_POLICY",
            "review_reason_ko": (
                "난이도 정책 변경으로 추가된 관계이므로 별도 재검수 전에는 적재·사용하지 않는다."
            ),
            "review_status_code": "REVIEW_REQUIRED",
            "production_eligible": False,
            "concern_resolution_policy_version": policy["policy_version"],
        }
    )
    return result


def build(
    input_path: Path = DEFAULT_INPUT,
    policy_path: Path = DEFAULT_POLICY,
    difficulty_review_path: Path = DEFAULT_DIFFICULTY_REVIEW,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    rows = read_jsonl(input_path)
    policy = read_json(policy_path)
    pending_ids = read_pending_relation_ids(difficulty_review_path)
    input_ids = {str(row["map_relation_id"]) for row in rows}
    if not pending_ids.issubset(input_ids):
        raise ValueError("difficulty review batch contains an unknown map relation")
    active_rows = [row for row in rows if str(row["map_relation_id"]) not in pending_ids]
    initial_counts = validate_policy(rows, policy, pending_ids)
    pair_conditions: dict[tuple[str, str], set[str]] = defaultdict(set)
    pair_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in active_rows:
        if classify(row, policy) != "KEEP_AS_SAFE_VARIANT":
            continue
        pair = (
            str(row["pain_discomfort_area_code"]),
            str(row["target_exercise_stable_code"]),
        )
        pair_conditions[pair].add(str(row["condition_code"]))
        pair_rows.setdefault(pair, row)

    variants = [
        make_variant(pair_rows[pair], policy, sorted(pair_conditions[pair]))
        for pair in sorted(pair_rows)
    ]
    variants_by_pair = {
        (variant["pain_discomfort_area_code"], variant["base_exercise_stable_code"]): variant
        for variant in variants
    }

    resolved: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    area_action_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        if str(row["map_relation_id"]) in pending_ids:
            pending.append(pending_row(row, policy))
            continue
        action = classify(row, policy)
        action_counts[action] += 1
        area_action_counts[str(row["pain_discomfort_area_code"])][action] += 1
        if action.startswith("REMOVE_"):
            removed.append(removed_row(row, action, policy))
        elif action == "KEEP_AS_SAFE_VARIANT":
            pair = (
                str(row["pain_discomfort_area_code"]),
                str(row["target_exercise_stable_code"]),
            )
            resolved.append(resolved_variant_row(row, variants_by_pair[pair], policy))
        else:
            resolved.append(unchanged_row(row, policy))

    if action_counts != initial_counts:
        raise AssertionError("classification changed during build")
    if len(resolved) + len(removed) + len(pending) != len(rows):
        raise AssertionError("resolved, removed, and pending rows do not reconcile")
    if len(pending) != len(pending_ids):
        raise AssertionError("difficulty review pending rows do not reconcile")
    if not variants:
        raise AssertionError("no safe variants generated")

    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_path = output_dir / RESOLVED_MAP_NAME
    removed_path = output_dir / REMOVED_MAP_NAME
    pending_path = output_dir / PENDING_MAP_NAME
    variants_path = output_dir / SAFE_VARIANTS_NAME
    report_path = output_dir / REPORT_NAME
    csv_path = output_dir / CSV_NAME
    write_jsonl(resolved_path, resolved)
    write_jsonl(removed_path, removed)
    write_jsonl(pending_path, pending)
    write_jsonl(variants_path, variants)

    summary_rows = []
    for area in sorted(area_action_counts):
        summary_rows.append(
            {
                "pain_discomfort_area_code": area,
                **{
                    action: area_action_counts[area].get(action, 0)
                    for action in (
                        "KEEP_UNCHANGED",
                        "KEEP_AS_SAFE_VARIANT",
                        "REMOVE_DIRECT_LOAD",
                        "REMOVE_SAFE_VARIANT_NOT_FEASIBLE",
                    )
                },
            }
        )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)

    report = {
        "schema_version": "discomfort-alternative-concern-resolution-report-v2.0.2-v1",
        "policy_version": policy["policy_version"],
        "status": "REVIEW_REQUIRED",
        "production_eligible": False,
        "counts": {
            "input_count": len(rows),
            "resolved_keep_count": len(resolved),
            "removed_count": len(removed),
            "pending_review_count": len(pending),
            "safe_variant_count": len(variants),
            **dict(sorted(action_counts.items())),
        },
        "area_action_counts": {
            area: dict(sorted(counts.items()))
            for area, counts in sorted(area_action_counts.items())
        },
        "invariants": {
            "original_input_preserved": True,
            "all_direct_load_rows_removed": all(
                row["concern_resolution_action_code"] != "REMOVE_DIRECT_LOAD" for row in resolved
            ),
            "all_concerns_resolved": (
                action_counts["KEEP_AS_SAFE_VARIANT"]
                + action_counts["REMOVE_SAFE_VARIANT_NOT_FEASIBLE"]
                == EXPECTED_CONCERN_COUNT
            ),
            "difficulty_review_pending_rows_are_excluded": {
                str(row["map_relation_id"]) for row in pending
            }
            == pending_ids,
            "safe_variants_have_fixed_posture": all(
                variant["fixed_posture_code"] for variant in variants
            ),
            "safe_variants_have_fixed_support": all(
                variant["fixed_support_code"] for variant in variants
            ),
            "safe_variants_have_all_no_load_guards": all(
                variant["pain_area_load_guard_codes"] == NO_LOAD_GUARDS for variant in variants
            ),
            "safe_variants_have_stop_guard": all(
                variant["stop_guard_code"] == STOP_GUARD for variant in variants
            ),
            "safe_variants_are_separate_exercises": all(
                variant["record_type"] == "SEPARATE_EXERCISE" for variant in variants
            ),
            "no_output_is_production_eligible": all(
                row["production_eligible"] is False for row in resolved + removed + variants
            ),
        },
        "artifacts": {
            "input": artifact_reference(input_path),
            "policy": artifact_reference(policy_path),
            "difficulty_review_batch": artifact_reference(difficulty_review_path),
            "resolved_map": artifact_reference(resolved_path),
            "removed_map": artifact_reference(removed_path),
            "pending_map": artifact_reference(pending_path),
            "safe_variants": artifact_reference(variants_path),
            "summary_csv": artifact_reference(csv_path),
        },
        "sha256": {
            "input": sha256_file(input_path),
            "policy": sha256_file(policy_path),
            "difficulty_review_batch": sha256_file(difficulty_review_path)
            if difficulty_review_path.exists()
            else None,
            "resolved_map": sha256_file(resolved_path),
            "removed_map": sha256_file(removed_path),
            "pending_map": sha256_file(pending_path),
            "safe_variants": sha256_file(variants_path),
            "summary_csv": sha256_file(csv_path),
        },
        "reviewed_at": policy["reviewed_at"],
        "reviewer": policy["reviewer"],
    }
    if not all(report["invariants"].values()):
        raise AssertionError(f"resolution invariant failed: {report['invariants']}")
    write_json(report_path, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--difficulty-review", type=Path, default=DEFAULT_DIFFICULTY_REVIEW)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build(args.input, args.policy, args.difficulty_review, args.output_dir)
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
