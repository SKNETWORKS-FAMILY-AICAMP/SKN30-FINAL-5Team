"""Build review-only directional exercise alternative relationships.

The generator is intentionally conservative: it uses only IDs present in the
integrated catalog, excludes same-representative/same-family variants, requires
an approved MET mapping for both endpoints, and never promotes a relation to
production eligibility without a separate domain approval step.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_INTEGRATED = Path(__file__).resolve().parents[1] / "reports" / "integrated_exercise_review_updated.csv"
DEFAULT_TAXONOMY = Path(__file__).resolve().parents[1] / "reports" / "representative_exercise_taxonomy_reviewed.csv"
DEFAULT_MET = (
    Path(__file__).resolve().parents[1]
    / "generated"
    / "exercise-met-mapping-v0.1.0"
    / "exercise_met_mapping_reviewed.csv"
)
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "generated"
    / "exercise-alternatives-v0.3.0"
)

RELATION_COLUMNS = [
    "source_exercise_id",
    "source_exercise_name",
    "alternative_exercise_id",
    "alternative_exercise_name",
    "alternative_type",
    "goal_code",
    "goal_match",
    "movement_pattern_match",
    "source_met_value",
    "alternative_met_value",
    "met_difference",
    "difficulty_difference",
    "reason",
    "trigger_condition",
    "direction",
    "confidence",
    "evidence_basis",
    "review_status",
    "production_eligible",
]

LOG_COLUMNS = [
    "source_exercise_id",
    "source_exercise_name",
    "alternative_exercise_id",
    "alternative_exercise_name",
    "alternative_type",
    "issue_type",
    "reason",
    "suggested_action",
    "required_decision",
    "review_status",
    "production_eligible",
]

REPORT_COLUMNS = ["check_code", "check_name", "expected", "actual", "status", "details"]

DIFFICULTY_RANK = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}
VALID_TYPES = {"CONSTRAINT", "INTENSITY", "RECOVERY", "SAFETY"}

# Equipment burden is used only to detect a clear constraint downshift. It is
# not a claim that two different devices have the same physiological load.
EQUIPMENT_BURDEN = {
    "BODYWEIGHT": 0,
    "MAT": 0,
    "CHAIR": 1,
    "RESISTANCE_BAND": 1,
    "HOUSEHOLD_WEIGHT": 1,
    "DUMBBELL": 2,
    "KETTLEBELL": 2,
    "ROPE": 2,
    "FOAM_ROLLER": 2,
    "STEP_BOX": 2,
    "BENCH": 3,
    "PULL_UP_BAR": 3,
    "EZ_BAR": 3,
    "BARBELL": 4,
    "CABLE_MACHINE": 4,
    "MACHINE": 4,
    "STABILITY_BALL": 2,
    "SUSPENSION_STRAPS": 3,
}


def read_csv(path: Path, label: str) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{label} is empty: {path}")
    return rows


def clean_name(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+v\.?\s*\d+\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+\(male\)$", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip()


def tokens(value: str) -> set[str]:
    return {item.strip().upper() for item in value.split("|") if item.strip()}


def equipment_burden(value: str) -> int | None:
    values = tokens(value)
    if not values:
        return None
    scores = [EQUIPMENT_BURDEN.get(item) for item in values]
    if any(score is None for score in scores):
        return None
    return max(scores)  # type: ignore[arg-type]


def canonical_target(value: str) -> str:
    text = value.lower().strip()
    if not text or text == "review_required":
        return "UNKNOWN"
    aliases = (
        ("pector", "CHEST"),
        ("chest", "CHEST"),
        ("deltoid", "SHOULDER"),
        ("delt", "SHOULDER"),
        ("shoulder", "SHOULDER"),
        ("lat", "BACK"),
        ("back", "BACK"),
        ("trapez", "TRAP"),
        ("trap", "TRAP"),
        ("glute", "GLUTE"),
        ("hamstring", "HAMSTRING"),
        ("biceps femoris", "HAMSTRING"),
        ("quad", "QUAD"),
        ("quadriceps", "QUAD"),
        ("calf", "CALF"),
        ("calves", "CALF"),
        ("gastrocnemius", "CALF"),
        ("soleus", "CALF"),
        ("triceps", "TRICEPS"),
        ("biceps", "BICEPS"),
        ("forearm", "FOREARM"),
        ("wrist", "FOREARM"),
        ("abs", "CORE"),
        ("abdom", "CORE"),
        ("spine", "SPINE"),
        ("adductor", "ADDUCTOR"),
        ("골반", "HIP_FLEXOR"),
        ("엉덩", "GLUTE"),
        ("허벅지", "QUAD"),
        ("종아리", "CALF"),
        ("뒤쪽 넓적다리", "HAMSTRING"),
        ("복부", "CORE"),
    )
    found = {alias for needle, alias in aliases if needle in text}
    return "+".join(sorted(found)) if found else "UNKNOWN"


def taxonomy_for(rep_id: str, taxonomy: dict[str, dict[str, str]]) -> dict[str, str]:
    return taxonomy.get(rep_id, {})


def pattern_for(row: dict[str, str], taxonomy: dict[str, dict[str, str]]) -> str:
    rep = taxonomy_for(row.get("representative_id", ""), taxonomy)
    value = rep.get("reviewed_movement_pattern") or rep.get("movement_pattern") or row.get(
        "movement_pattern_code_candidate", ""
    )
    return value.strip().upper()


def goal_for(row: dict[str, str], pattern: str) -> str:
    if pattern == "CORE_BRACE":
        return "CORE_STABILITY"
    if pattern == "GAIT":
        return "CARDIO_ENDURANCE"
    pattern_goals = {
        "HIP_DOMINANT": "POSTERIOR_CHAIN_STRENGTH",
        "KNEE_DOMINANT": "KNEE_DOMINANT_STRENGTH",
        "KNEE_FLEXION": "KNEE_FLEXION_STRENGTH",
        "HORIZONTAL_PULL": "HORIZONTAL_PULL_STRENGTH",
        "HORIZONTAL_PUSH": "HORIZONTAL_PUSH_STRENGTH",
        "VERTICAL_PULL": "VERTICAL_PULL_STRENGTH",
        "VERTICAL_PUSH": "VERTICAL_PUSH_STRENGTH",
    }
    if pattern in pattern_goals:
        return pattern_goals[pattern]
    if pattern == "MOBILITY_STRETCH":
        target = canonical_target(row.get("source_target") or row.get("target", ""))
        return f"MOBILITY_{target}" if target != "UNKNOWN" else "UNKNOWN"
    if pattern == "ISOLATION":
        family = row.get("exercise_family", "").upper()
        isolation_goals = (
            (("PULLOVER", "ONE_ARM_WALL_LATS"), "ISOLATION_LAT_PULL"),
            (("TRICEPS",), "ISOLATION_ELBOW_EXTENSION"),
            (("BICEPS", "CURL"), "ISOLATION_ELBOW_FLEXION"),
            (("SEATED_CALF", "CALF_RAISE", "CALF_PRESS"), "ISOLATION_CALF_RAISE"),
            (("REVERSE_WRIST",), "ISOLATION_WRIST_EXTENSION"),
            (("WRIST_CURL",), "ISOLATION_WRIST_FLEXION"),
            (("HAND_GRIP",), "ISOLATION_GRIP"),
            (("SHRUG",), "ISOLATION_SHRUG"),
            (("FRONT_RAISE",), "ISOLATION_FRONT_RAISE"),
            (("LATERAL_RAISE",), "ISOLATION_LATERAL_RAISE"),
            (("REAR_FLY", "REAR_LATERAL"), "ISOLATION_REAR_DELTOID"),
            (("Y_RAISE",), "ISOLATION_Y_RAISE"),
            (("FLY",), "ISOLATION_CHEST_FLY"),
            (("LEG_EXTENSION",), "ISOLATION_KNEE_EXTENSION"),
        )
        for needles, goal in isolation_goals:
            if any(needle in family for needle in needles):
                return goal
        return "UNKNOWN"
    return "UNKNOWN"


def difficulty_delta(source: dict[str, str], alternative: dict[str, str]) -> str:
    source_rank = DIFFICULTY_RANK.get(source.get("difficulty_code_candidate", ""))
    alternative_rank = DIFFICULTY_RANK.get(alternative.get("difficulty_code_candidate", ""))
    if source_rank is None or alternative_rank is None:
        return ""
    return str(alternative_rank - source_rank)


def met_value(met: dict[str, str], exercise_id: str) -> float:
    try:
        return float(met[exercise_id]["met_value"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"approved MET value is missing: {exercise_id}") from exc


def eligible_rows(
    integrated: list[dict[str, str]],
    taxonomy: dict[str, dict[str, str]],
    met: dict[str, dict[str, str]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in integrated:
        exercise_id = row.get("normalized_exercise_id", "").strip()
        if not exercise_id or exercise_id in result:
            raise ValueError(f"integrated exercise ID is blank or duplicated: {exercise_id}")
        if exercise_id not in met or met[exercise_id].get("review_status") != "APPROVED":
            continue
        if not met[exercise_id].get("met_value", "").strip():
            continue
        pattern = pattern_for(row, taxonomy)
        name = clean_name(row.get("name_en", "") or met[exercise_id].get("exercise_name", ""))
        result[exercise_id] = {
            "row": row,
            "name": name,
            "pattern": pattern,
            "goal": goal_for(row, pattern),
            "met": met_value(met, exercise_id),
            "equipment_burden": equipment_burden(row.get("equipment_code_candidate", "")),
            "difficulty": row.get("difficulty_code_candidate", "").strip(),
        }
    return result


def candidate_pool(source: dict[str, Any], exercises: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for alternative in exercises.values():
        if alternative["name"] == "" or alternative["pattern"] in {"", "REVIEW_REQUIRED"}:
            continue
        if source["name"] == "" or source["pattern"] in {"", "REVIEW_REQUIRED"}:
            continue
        if source["goal"] == "UNKNOWN":
            continue
        if alternative["row"]["normalized_exercise_id"] == source["row"]["normalized_exercise_id"]:
            continue
        # Same representative or family is a variant candidate, not an Alternative.
        if alternative["row"].get("representative_id") == source["row"].get("representative_id"):
            continue
        if alternative["row"].get("exercise_family") == source["row"].get("exercise_family"):
            continue
        if alternative["goal"] != source["goal"] or alternative["pattern"] != source["pattern"]:
            continue
        if alternative["met"] > source["met"]:
            continue
        result.append(alternative)
    return result


def explicit_safety_pairs(exercises: dict[str, dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    # Both source records are explicitly marked HIGH impact in the catalog; the
    # destination is a lower-impact, bodyweight stepping activity.
    pairs = [("NEX-000158", "NEX-000171"), ("NEX-000164", "NEX-000171")]
    return [(exercises[source], exercises[alternative]) for source, alternative in pairs if source in exercises and alternative in exercises]


def relation(
    source: dict[str, Any],
    alternative: dict[str, Any],
    alternative_type: str,
    movement_match: bool,
    reason: str,
    trigger: str,
    confidence: str,
    goal_override: str | None = None,
) -> dict[str, str]:
    source_id = source["row"]["normalized_exercise_id"]
    alternative_id = alternative["row"]["normalized_exercise_id"]
    met_diff = round(alternative["met"] - source["met"], 1)
    taxonomy_status = taxonomy_status_text(source["row"], alternative["row"])
    return {
        "source_exercise_id": source_id,
        "source_exercise_name": source["name"],
        "alternative_exercise_id": alternative_id,
        "alternative_exercise_name": alternative["name"],
        "alternative_type": alternative_type,
        "goal_code": goal_override or source["goal"],
        "goal_match": "true",
        "movement_pattern_match": str(movement_match).lower(),
        "source_met_value": f"{source['met']:.1f}",
        "alternative_met_value": f"{alternative['met']:.1f}",
        "met_difference": f"{met_diff:.1f}",
        "difficulty_difference": difficulty_delta(source["row"], alternative["row"]),
        "reason": reason,
        "trigger_condition": trigger,
        "direction": "A_TO_B",
        "confidence": confidence,
        "evidence_basis": (
            f"integrated_catalog(source_pattern={source['pattern']}, source_equipment={source['row'].get('equipment_code_candidate', '')}, "
            f"source_difficulty={source['difficulty']}; alternative_pattern={alternative['pattern']}, "
            f"alternative_equipment={alternative['row'].get('equipment_code_candidate', '')}, "
            f"alternative_difficulty={alternative['difficulty']}); representative_taxonomy={taxonomy_status}; "
            f"MET_mapping=APPROVED({source['met']:.1f}->{alternative['met']:.1f})"
        ),
        "review_status": "REVIEW_REQUIRED",
        "production_eligible": "false",
    }


def taxonomy_status_text(source: dict[str, str], alternative: dict[str, str]) -> str:
    return f"{source.get('representative_id', '')}->{alternative.get('representative_id', '')}"


def build_relations(exercises: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pair_keys: set[tuple[str, str]] = set()

    def add(row: dict[str, str]) -> None:
        key = (row["source_exercise_id"], row["alternative_exercise_id"])
        if key in pair_keys:
            return
        # A relation is directional. Once one direction is selected, the
        # reverse direction is suppressed even when the reverse candidate
        # would have a different alternative_type.
        if (key[1], key[0]) in pair_keys:
            return
        if float(row["met_difference"]) > 0:
            return
        pair_keys.add(key)
        rows.append(row)

    for source, alternative in explicit_safety_pairs(exercises):
        add(
            relation(
                source,
                alternative,
                "SAFETY",
                False,
                "고충격 유산소를 저충격 스테핑으로 전환하여 cardio 목표를 유지하고 충격 부담을 낮춘다.",
                "통증·관절 부담·고충격 동작 회피 필요",
                "LOW",
                "CARDIO_ENDURANCE",
            )
        )

    for source in exercises.values():
        pool = candidate_pool(source, exercises)
        if not pool:
            continue
        constraint_candidates = [
            candidate
            for candidate in pool
            if source["equipment_burden"] is not None
            and candidate["equipment_burden"] is not None
            and candidate["equipment_burden"] < source["equipment_burden"]
        ]
        intensity_candidates = [
            candidate
            for candidate in pool
            if DIFFICULTY_RANK.get(candidate["difficulty"], -1) >= 0
            and DIFFICULTY_RANK.get(source["difficulty"], -1) >= 0
            and DIFFICULTY_RANK[candidate["difficulty"]] < DIFFICULTY_RANK[source["difficulty"]]
        ]
        recovery_candidates = [
            candidate
            for candidate in pool
            if source["met"] - candidate["met"] >= 1.0
            and candidate not in intensity_candidates
        ]

        def ordered(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return sorted(
                candidates,
                key=lambda candidate: (
                    source["met"] - candidate["met"],
                    candidate["equipment_burden"] if candidate["equipment_burden"] is not None else 99,
                    candidate["row"]["normalized_exercise_id"],
                ),
                reverse=True,
            )[:2]

        for candidate in ordered(constraint_candidates):
            add(
                relation(
                    source,
                    candidate,
                    "CONSTRAINT",
                    True,
                    "장비 또는 장소 제약 시 동일 목표와 movement pattern을 유지하면서 장비 부담이 낮은 운동으로 전환한다.",
                    "사용 가능한 장비가 없거나 현재 장소에서 원 장비를 사용할 수 없음",
                    "HIGH",
                )
            )
        for candidate in ordered(intensity_candidates):
            add(
                relation(
                    source,
                    candidate,
                    "INTENSITY",
                    True,
                    "운동 목적과 movement pattern을 유지하되 난이도와 MET가 낮은 운동으로 조절한다.",
                    "초보자·수행 실패 가능성·현재 체력 부족",
                    "MEDIUM",
                )
            )
        for candidate in ordered(recovery_candidates):
            add(
                relation(
                    source,
                    candidate,
                    "RECOVERY",
                    True,
                    "회복 상태가 낮을 때 동일 목표를 유지하면서 MET 부담이 낮은 운동으로 조절한다.",
                    "피로도 높음·근육통·수면 부족·이전 고강도 운동 수행",
                    "MEDIUM",
                )
            )

    rows.sort(key=lambda row: (row["source_exercise_id"], row["alternative_type"], row["alternative_exercise_id"]))
    return rows


def build_review_log(relations: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "source_exercise_id": row["source_exercise_id"],
            "source_exercise_name": row["source_exercise_name"],
            "alternative_exercise_id": row["alternative_exercise_id"],
            "alternative_exercise_name": row["alternative_exercise_name"],
            "alternative_type": row["alternative_type"],
            "issue_type": "RELATION_DOMAIN_REVIEW_REQUIRED",
            "reason": (
                f"{row['reason']} 현재 catalog가 DRAFT 또는 관계 승인이 없으므로 자동 승인하지 않으며, "
                "목표 보존·장비/강도 조건·안전 적합성을 사람이 확인해야 한다."
            ),
            "suggested_action": "원천 운동과 대체 운동의 실제 수행 조건을 확인한 뒤 관계를 승인하거나 반려",
            "required_decision": "대체 관계 승인 여부 및 trigger_condition 확정",
            "review_status": "REVIEW_REQUIRED",
            "production_eligible": "false",
        }
        for row in relations
    ]


def validate(
    relations: list[dict[str, str]],
    review_log: list[dict[str, str]],
    integrated: list[dict[str, str]],
    met: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    catalog_ids = {row["normalized_exercise_id"] for row in integrated}
    met_approved_ids = {key for key, row in met.items() if row.get("review_status") == "APPROVED" and row.get("met_value", "").strip()}
    report: list[dict[str, str]] = []

    def check(code: str, name: str, expected: str, actual: str, status: str, details: str) -> None:
        report.append({"check_code": code, "check_name": name, "expected": expected, "actual": actual, "status": status, "details": details})

    endpoint_ok = all(row["source_exercise_id"] in catalog_ids and row["alternative_exercise_id"] in catalog_ids for row in relations)
    check("EXERCISE_ID_EXISTENCE", "source/alternative exercise_id 존재", "all endpoints exist", str(endpoint_ok).lower(), "PASS" if endpoint_ok else "FAIL", "통합 카탈로그 ID 집합과 비교")

    keys = [(row["source_exercise_id"], row["alternative_exercise_id"], row["alternative_type"]) for row in relations]
    duplicate_count = len(keys) - len(set(keys))
    check("DUPLICATE_RELATION", "동일 방향·유형 중복", "0", str(duplicate_count), "PASS" if duplicate_count == 0 else "FAIL", "natural key=(source, alternative, type)")

    pairs = {(row["source_exercise_id"], row["alternative_exercise_id"]) for row in relations}
    reverse_count = sum((alternative, source) in pairs for source, alternative in pairs)
    check("REVERSE_DIRECTION", "역방향 자동 생성 없음", "0", str(reverse_count), "PASS" if reverse_count == 0 else "FAIL", "direction은 A_TO_B만 허용")

    by_id = {row["normalized_exercise_id"]: row for row in integrated}
    variant_count = sum(
        by_id[row["source_exercise_id"]].get("representative_id") == by_id[row["alternative_exercise_id"]].get("representative_id")
        or by_id[row["source_exercise_id"]].get("exercise_family") == by_id[row["alternative_exercise_id"]].get("exercise_family")
        for row in relations
    )
    check("VARIANT_EXCLUSION", "Variant 관계 제외", "0", str(variant_count), "PASS" if variant_count == 0 else "FAIL", "동일 representative_id 또는 exercise_family 관계를 차단")

    invalid_type = sum(row["alternative_type"] not in VALID_TYPES for row in relations)
    check("ALTERNATIVE_TYPE", "alternative_type 허용값", "0 invalid", str(invalid_type), "PASS" if invalid_type == 0 else "FAIL", "CONSTRAINT/INTENSITY/RECOVERY/SAFETY")

    missing_trigger = sum(not row["trigger_condition"].strip() for row in relations)
    check("TRIGGER_CONDITION", "trigger_condition 기록", "0 missing", str(missing_trigger), "PASS" if missing_trigger == 0 else "FAIL", "대체 발생 조건 필수")

    missing_goal = sum(row["goal_match"] != "true" or not row["goal_code"].strip() for row in relations)
    check("GOAL_MATCH", "goal_match 근거 필드", "0 missing", str(missing_goal), "PASS" if missing_goal == 0 else "FAIL", "동일 목표 코드와 보존 여부 기록")

    missing_met = sum(row["source_exercise_id"] not in met_approved_ids or row["alternative_exercise_id"] not in met_approved_ids for row in relations)
    check("MET_DATA", "양 끝점 approved MET", "0 missing", str(missing_met), "PASS" if missing_met == 0 else "FAIL", "exercise_met_mapping_reviewed.csv의 APPROVED만 사용")

    met_increase = sum(float(row["met_difference"]) > 0 for row in relations)
    check("MET_INCREASE", "대체 운동 MET 증가 차단", "0", str(met_increase), "PASS" if met_increase == 0 else "FAIL", "강도 증가 방향은 생성하지 않음")

    log_keys = {(row["source_exercise_id"], row["alternative_exercise_id"], row["alternative_type"]) for row in review_log}
    missing_log = sum((row["source_exercise_id"], row["alternative_exercise_id"], row["alternative_type"]) not in log_keys for row in relations)
    check("REVIEW_REASON", "review_required 사유 기록", "0 missing", str(missing_log), "PASS" if missing_log == 0 else "FAIL", "관계별 review log 존재")

    production_true = sum(row["production_eligible"] != "false" or row["review_status"] != "REVIEW_REQUIRED" for row in relations)
    check("PRODUCTION_GATE", "검수 전 production eligibility", "0 eligible", str(production_true), "PASS" if production_true == 0 else "FAIL", "승인 전 관계는 모두 REVIEW_REQUIRED/false")

    source_count = len({row["source_exercise_id"] for row in relations})
    check("SOURCE_COVERAGE", "관계가 생성된 source 수", "informational", str(source_count), "PASS", "근거 부족/variant-only source는 자동 관계를 생성하지 않음")
    check("CATALOG_EXERCISE_COUNT", "통합 카탈로그 exercise 수", "208", str(len(catalog_ids)), "PASS" if len(catalog_ids) == 208 else "FAIL", "입력 통합 카탈로그 기준")
    check("MET_APPROVED_COUNT", "Alternative endpoint로 사용 가능한 approved MET 수", "207", str(len(met_approved_ids)), "PASS" if len(met_approved_ids) == 207 else "FAIL", "REVIEW_REQUIRED MET는 endpoint에서 제외")
    check("MET_REVIEW_REQUIRED_COUNT", "MET REVIEW_REQUIRED 수", "1", str(len(catalog_ids - met_approved_ids)), "PASS" if len(catalog_ids - met_approved_ids) == 1 else "FAIL", "NEX-000173은 MET 미확정으로 관계 생성에서 제외")
    check("SOURCES_WITHOUT_RELATIONS", "자동 관계 미생성 source 수", "informational", str(len(catalog_ids - {row['source_exercise_id'] for row in relations})), "PASS", "근거 부족/variant-only/패턴 불명확 source")
    check("REVIEW_LOG_COUNT", "관계별 review log 수", str(len(relations)), str(len(review_log)), "PASS" if len(relations) == len(review_log) else "FAIL", "모든 생성 관계는 사람이 승인해야 함")
    check("RELATION_COUNT", "생성 관계 수", "informational", str(len(relations)), "PASS", "새 관계는 domain review 대기 상태")
    check("TYPE_COUNTS", "유형별 관계 수", "informational", str(dict(sorted(Counter(row["alternative_type"] for row in relations).items()))), "PASS", "검수 우선순위 산정용")
    return report


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build(integrated_path: Path, taxonomy_path: Path, met_path: Path, output_dir: Path) -> Path:
    integrated = read_csv(integrated_path, "integrated catalog")
    taxonomy_rows = read_csv(taxonomy_path, "representative taxonomy")
    met_rows = read_csv(met_path, "reviewed MET mapping")
    taxonomy = {row["representative_id"]: row for row in taxonomy_rows}
    if len(taxonomy) != len(taxonomy_rows):
        raise ValueError("representative taxonomy contains duplicate representative_id")
    met = {row["exercise_id"]: row for row in met_rows}
    if len(met) != len(met_rows):
        raise ValueError("reviewed MET mapping contains duplicate exercise_id")
    exercises = eligible_rows(integrated, taxonomy, met)
    relations = build_relations(exercises)
    review_log = build_review_log(relations)
    validation = validate(relations, review_log, integrated, met)
    if any(row["status"] == "FAIL" for row in validation):
        failures = "; ".join(row["check_code"] for row in validation if row["status"] == "FAIL")
        raise ValueError(f"alternative validation failed: {failures}")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "alternative_relationships.csv", RELATION_COLUMNS, relations)
    write_csv(output_dir / "alternative_review_log.csv", LOG_COLUMNS, review_log)
    write_csv(output_dir / "alternative_validation_report.csv", REPORT_COLUMNS, validation)
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integrated", type=Path, default=DEFAULT_INTEGRATED)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--met", type=Path, default=DEFAULT_MET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        output = build(args.integrated, args.taxonomy, args.met, args.output)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
