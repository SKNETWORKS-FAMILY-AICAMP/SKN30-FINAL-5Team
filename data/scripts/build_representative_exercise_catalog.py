#!/usr/bin/env python3
"""Build a representative exercise catalog from the integrated review CSV.

This script keeps the source review rows intact and adds a service-facing
representative family link.  It deliberately does not rewrite catalog_id or
normalized_exercise_id; those IDs are source-record registry IDs.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "data/validation/review_batches/gymvisual-integrated-review-v0.1.0/integrated_exercise_review.csv"
CATALOG_OUTPUT = ROOT / "data/reports/representative_exercise_catalog.csv"
UPDATED_OUTPUT = ROOT / "data/reports/integrated_exercise_review_updated.csv"

REMOVABLE_CODES = {
    "HUMAN_REPRESENTATIVE_SELECTION_REVIEW",
    "EXERCISE_FAMILY_BOUNDARY_REVIEW",
}


FAMILY_KO = {
    "ABS_CORE_BRACE": "복부 브레이싱",
    "ALL_FOURS_SQUAT_STRETCH": "네발기기 스쿼트 스트레칭",
    "ANKLE_CIRCLES": "발목 돌리기",
    "BARBELL_DEADLIFT": "데드리프트",
    "BARBELL_FRONT_RAISE": "프론트 레이즈",
    "BARBELL_PULLOVER": "풀오버",
    "BARBELL_STRAIGHT_LEG_DEADLIFT": "루마니안 데드리프트",
    "BODYWEIGHT_BACK_EXTENSION": "백 익스텐션",
    "BODYWEIGHT_CRUNCH": "크런치",
    "BODYWEIGHT_FORWARD_LUNGE": "포워드 런지",
    "BODYWEIGHT_GLUTE_BRIDGE": "글루트 브리지",
    "BODYWEIGHT_PULL_UP_BICEPS": "풀업",
    "BODYWEIGHT_REVERSE_CRUNCH": "리버스 크런치",
    "BODYWEIGHT_RUSSIAN_TWIST": "러시안 트위스트",
    "BODYWEIGHT_SPLIT_SQUAT": "스플릿 스쿼트",
    "BODYWEIGHT_STANDING_CALF_RAISE": "스탠딩 카프 레이즈",
    "BUTTERFLY_ADDUCTOR_STRETCH": "버터플라이 스트레칭",
    "CABLE_FLY": "케이블 플라이",
    "CABLE_TRICEPS_PUSHDOWN": "케이블 트라이셉스 푸시다운",
    "CHAIR_LEG_EXTENDED_STRETCH": "의자 다리 스트레칭",
    "CHEST_FRONT_SHOULDER_STRETCH": "가슴·어깨 앞면 스트레칭",
    "CLOSE_GRIP_PUSH_UP": "클로즈 그립 푸시업",
    "CRUNCH_VARIANT": "사이드 크런치",
    "DEAD_BUG": "데드버그",
    "DUMBBELL_GOBLET_SQUAT": "고블릿 스쿼트",
    "DUMBBELL_LATERAL_RAISE": "레터럴 레이즈",
    "DUMBBELL_PREACHER_CURL": "프리처 컬",
    "DUMBBELL_REAR_FLY": "리어 델트 플라이",
    "DUMBBELL_SHRUG": "슈러그",
    "DUMBBELL_STANDING_CURL": "덤벨 바이셉스 컬",
    "DUMBBELL_STEP_UP_LUNGE": "덤벨 스텝업 런지",
    "DYNAMIC_CHEST_STRETCH": "다이내믹 가슴 스트레칭",
    "EXERCISE_BALL_HIP_FLEXOR_STRETCH": "짐볼 고관절 굴근 스트레칭",
    "HAMSTRING_STRETCH": "햄스트링 스트레칭",
    "HAND_GRIP_SQUEEZE": "손 악력 쥐기",
    "HIP_FLEXOR_QUADRICEPS_STRETCH": "고관절 굴근·대퇴사두근 스트레칭",
    "INCLINE_Y_RAISE": "인클라인 Y 레이즈",
    "INVERTED_ROW": "인버티드 로우",
    "KNEELING_LAT_STRETCH": "무릎 꿇고 광배근 스트레칭",
    "LAT_PULLDOWN": "랫풀다운",
    "LEG_UP_HAMSTRING_STRETCH": "누워서 햄스트링 스트레칭",
    "LEG_PRESS": "레그 프레스",
    "LOWER_BACK_CURL": "로어 백 컬",
    "MACHINE_LEG_EXTENSION": "레그 익스텐션",
    "NECK_LATERAL_STRETCH": "목 옆면 스트레칭",
    "ONE_ARM_WALL_LATS": "벽 짚고 한 팔 광배근 스트레칭",
    "OVERHEAD_TRICEPS_EXTENSION": "오버헤드 트라이셉스 익스텐션",
    "OVERHEAD_TRICEPS_STRETCH": "오버헤드 삼두근 스트레칭",
    "PECTORALS_HORIZONTAL_PUSH": "체스트 프레스",
    "PERONEAL_STRETCH": "종아리 바깥쪽 스트레칭",
    "PLANK_ROTATION": "플랭크 로테이션",
    "PUSH_UP": "푸시업",
    "REAR_DELTOID_STRETCH": "후면 어깨 스트레칭",
    "REVERSE_CALF_RAISE": "리버스 카프 레이즈",
    "REVERSE_WRIST_CURL": "리버스 리스트 컬",
    "ROLLER_BACK_STRETCH": "롤러 등 스트레칭",
    "ROLLER_HIP_STRETCH": "롤러 둔근 스트레칭",
    "ROTATION_VARIANT": "회전형 크런치",
    "ROW_VARIANT": "로우",
    "RUNNERS_STRETCH": "러너스 스트레칭",
    "SCAPULAR_PULL_UP": "스캐풀라 풀업",
    "SEATED_CABLE_ROW": "시티드 케이블 로우",
    "SEATED_CALF_RAISE": "시티드 카프 레이즈",
    "SEATED_CALF_STRETCH": "앉아서 종아리 스트레칭",
    "SEATED_GLUTE_STRETCH": "앉아서 둔근 스트레칭",
    "SEATED_LEG_CURL": "레그 컬",
    "SEATED_LOWER_BACK_STRETCH": "앉아서 허리 스트레칭",
    "SEATED_PIRIFORMIS_STRETCH": "앉아서 이상근 스트레칭",
    "SEATED_SHOULDER_PRESS": "숄더 프레스",
    "SEATED_WIDE_ANGLE_STRETCH": "시티드 와이드 앵글 스트레칭",
    "SIDE_LYING_QUADRICEPS_STRETCH": "옆으로 누워 대퇴사두근 스트레칭",
    "SIDE_WRIST_PULL_STRETCH": "손목 당기기 스트레칭",
    "SPINE_CORE_BRACE": "버드독",
    "SPINE_STRETCH": "척추 스트레칭",
    "SPINE_TWIST": "척추 비틀기",
    "SQUAT_VARIANT": "스쿼트",
    "STANDING_HAMSTRING_CALF_STRAP_STRETCH": "스트랩 햄스트링·종아리 스트레칭",
    "STANDING_LATERAL_STRETCH": "서서 옆구리 스트레칭",
    "TRICEPS_STRETCH": "삼두근 스트레칭",
    "UPPER_BACK_ISOLATION": "상부 등 밴드 당기기",
    "UPPER_BACK_STRETCH": "상부 등 스트레칭",
    "WALL_CALF_STRETCH": "벽 짚고 종아리 스트레칭",
    "WORLD_GREATEST_STRETCH": "월드 그레이티스트 스트레칭",
    "WRIST_CIRCLES": "손목 돌리기",
    "WRIST_CURL": "리스트 컬",
    "REVIEW_REQUIRED_RUN": "달리기",
    "REVIEW_REQUIRED_STATIONARY_BIKE_RUN_V_3": "실내 자전거",
    "REVIEW_REQUIRED_WALK_ELLIPTICAL_CROSS_TRAINER": "일립티컬",
    "REVIEW_REQUIRED_WALKING_ON_STEPMILL": "스텝밀",
    "REVIEW_REQUIRED_JUMP_ROPE": "줄넘기",
    "REVIEW_REQUIRED_JACK_JUMP_MALE": "점핑잭",
    "REVIEW_REQUIRED_HIGH_KNEE_AGAINST_WALL": "하이니",
    "REVIEW_REQUIRED_SHORT_STRIDE_RUN": "짧은 보폭 달리기",
    "REVIEW_REQUIRED_WALKING_ON_INCLINE_TREADMILL": "경사 트레드밀 걷기",
    "REVIEW_REQUIRED_BACK_AND_FORTH_STEP": "앞뒤 스텝",
    "REVIEW_REQUIRED_STEP_BOX": "스텝박스 오르내리기",
    "REVIEW_REQUIRED_SINGLE_LEG_BALANCE": "한발 서기 균형",
    "REVIEW_REQUIRED_CHAIR_FORWARD_KNEE_LIFT": "의자 잡고 무릎 들기",
    "REVIEW_REQUIRED_SEATED_BALL_SQUEEZE": "앉아서 짐볼 조이기",
    "REVIEW_REQUIRED_SUPINE_BAND_LEG_PRESS": "누워서 밴드 레그 프레스",
    "REVIEW_REQUIRED_SEATED_HIP_FLEXION": "앉아서 고관절 굴곡",
    "REVIEW_REQUIRED_KETTLEBELL_SWING": "케틀벨 스윙",
}


ANCHORS = {
    "BARBELL_DEADLIFT": ("barbell deadlift",),
    "BARBELL_FRONT_RAISE": ("barbell front raise",),
    "BARBELL_PULLOVER": ("barbell pullover",),
    "BARBELL_STRAIGHT_LEG_DEADLIFT": ("romanian deadlift", "barbell straight leg deadlift"),
    "BODYWEIGHT_CRUNCH": ("crunch floor",),
    "BODYWEIGHT_FORWARD_LUNGE": ("forward lunge",),
    "BODYWEIGHT_REVERSE_CRUNCH": ("reverse crunch",),
    "BODYWEIGHT_RUSSIAN_TWIST": ("russian twist",),
    "BODYWEIGHT_STANDING_CALF_RAISE": ("bodyweight standing calf raise",),
    "CABLE_FLY": ("cable standing fly", "cable lying fly"),
    "DUMBBELL_GOBLET_SQUAT": ("dumbbell goblet squat",),
    "DUMBBELL_LATERAL_RAISE": ("dumbbell lateral raise",),
    "DUMBBELL_PREACHER_CURL": ("dumbbell preacher curl",),
    "DUMBBELL_REAR_FLY": ("dumbbell rear fly", "dumbbell rear lateral raise"),
    "DUMBBELL_SHRUG": ("dumbbell shrug",),
    "INVERTED_ROW": ("inverted row",),
    "LAT_PULLDOWN": ("cable pulldown",),
    "MACHINE_LEG_EXTENSION": ("leg extension",),
    "PECTORALS_HORIZONTAL_PUSH": ("seated bench press", "incline bench press - dumbbell"),
    "PUSH_UP": ("push-up",),
    "ROW_VARIANT": ("seated cable row",),
    "SEATED_CABLE_ROW": ("cable seated row", "cable seated wide-grip row"),
    "SEATED_CALF_RAISE": ("barbell seated calf raise",),
    "SEATED_LEG_CURL": ("leg curl",),
    "SEATED_SHOULDER_PRESS": ("dumbbell seated shoulder press", "overhead barbell press"),
    "SQUAT_VARIANT": ("leg press", "barbell full squat"),
    "LEG_PRESS": ("leg press",),
}


EQUIPMENT_PATTERNS = (
    ("body weight", "BODYWEIGHT"),
    ("bodyweight", "BODYWEIGHT"),
    ("dumbbell", "DUMBBELL"),
    ("barbell", "BARBELL"),
    ("ez bar", "EZ_BAR"),
    ("cable", "CABLE"),
    ("band", "BAND"),
    ("resistance band", "BAND"),
    ("kettlebell", "KETTLEBELL"),
    ("machine", "MACHINE"),
    ("leverage", "MACHINE"),
    ("bench", "BENCH"),
    ("stability ball", "STABILITY_BALL"),
    ("roller", "ROLLER"),
    ("rope", "ROPE"),
    ("pull-up bar", "PULL_UP_BAR"),
    ("weighted", "WEIGHTED"),
    ("의자", "CHAIR"),
    ("짐볼", "STABILITY_BALL"),
    ("매트", "MAT"),
)


TARGET_PATTERNS = (
    (("pector", "chest"), "CHEST"),
    (("delt", "shoulder"), "SHOULDERS"),
    (("lat",), "LATS"),
    (("upper back", "trapezius", "traps", "levator"), "UPPER_BACK"),
    (("biceps", "brachialis"), "BICEPS"),
    (("triceps",), "TRICEPS"),
    (("forearm", "wrist"), "FOREARMS"),
    (("glute",), "GLUTES"),
    (("hamstring", "biceps femoris"), "HAMSTRINGS"),
    (("quad", "quadriceps"), "QUADRICEPS"),
    (("calf", "calves", "gastrocnemius", "soleus"), "CALVES"),
    (("adductor",), "ADDUCTORS"),
    (("abs", "abdom", "obliquus"), "CORE"),
    (("spine",), "SPINE"),
)


PROVISIONAL_FAMILY_BY_NAME = {
    "run": "REVIEW_REQUIRED_RUN",
    "stationary bike run v. 3": "REVIEW_REQUIRED_STATIONARY_BIKE_RUN_V_3",
    "walk elliptical cross trainer": "REVIEW_REQUIRED_WALK_ELLIPTICAL_CROSS_TRAINER",
    "walking on stepmill": "REVIEW_REQUIRED_WALKING_ON_STEPMILL",
    "jump rope": "REVIEW_REQUIRED_JUMP_ROPE",
    "jack jump (male)": "REVIEW_REQUIRED_JACK_JUMP_MALE",
    "high knee against wall": "REVIEW_REQUIRED_HIGH_KNEE_AGAINST_WALL",
    "short stride run": "REVIEW_REQUIRED_SHORT_STRIDE_RUN",
    "walking on incline treadmill": "REVIEW_REQUIRED_WALKING_ON_INCLINE_TREADMILL",
    "back and forth step": "REVIEW_REQUIRED_BACK_AND_FORTH_STEP",
    "스텝박스 오르내리기": "REVIEW_REQUIRED_STEP_BOX",
    "한발 서서 균형잡기": "REVIEW_REQUIRED_SINGLE_LEG_BALANCE",
    "의자잡고 전방으로 무릎 굽혀 들기": "REVIEW_REQUIRED_CHAIR_FORWARD_KNEE_LIFT",
    "의자에 앉아 다리로 짐볼 쥐기": "REVIEW_REQUIRED_SEATED_BALL_SQUEEZE",
    "밴드 잡고 누워서 다리 밀기": "REVIEW_REQUIRED_SUPINE_BAND_LEG_PRESS",
    "앉아서 엉덩관절 굽히기": "REVIEW_REQUIRED_SEATED_HIP_FLEXION",
    "2 handed kettlebell swing": "REVIEW_REQUIRED_KETTLEBELL_SWING",
}


VARIANT_TERMS = (
    ("decline", "DECLINE"),
    ("incline", "INCLINE"),
    ("seated", "SEATED"),
    ("standing", "STANDING"),
    ("lying", "LYING"),
    ("kneeling", "KNEELING"),
    ("half-kneeling", "HALF_KNEELING"),
    ("on bench", "BENCH_SUPPORT"),
    ("over bench", "BENCH_SUPPORT"),
    ("on stability ball", "STABILITY_BALL"),
    ("on floor", "FLOOR"),
    ("with straps", "STRAPS"),
    ("one arm", "ONE_ARM"),
    ("one leg", "SINGLE_LEG"),
    ("single leg", "SINGLE_LEG"),
    ("alternate", "ALTERNATING"),
    ("contralateral", "CONTRALATERAL"),
    ("wide-grip", "WIDE_GRIP"),
    ("wide grip", "WIDE_GRIP"),
    ("close-grip", "CLOSE_GRIP"),
    ("close grip", "CLOSE_GRIP"),
    ("reverse-grip", "REVERSE_GRIP"),
    ("reverse grip", "REVERSE_GRIP"),
    ("neutral grip", "NEUTRAL_GRIP"),
    ("sumo", "SUMO"),
    ("romanian", "ROMANIAN"),
    ("stiff leg", "STIFF_LEG"),
    ("straight leg", "STRAIGHT_LEG"),
    ("forward", "FORWARD"),
    ("rear", "REAR"),
    ("walking", "WALKING"),
    ("reverse", "REVERSE"),
    ("twist", "ROTATION"),
    ("twisting", "ROTATION"),
    ("weighted", "WEIGHTED"),
    ("v. 2", "SOURCE_VERSION_2"),
    ("v. 3", "SOURCE_VERSION_3"),
)


def clean_family(candidate: str) -> str:
    return candidate.removesuffix("_CANDIDATE")


def family_for_row(row: dict[str, str]) -> str:
    """Apply narrow human taxonomy corrections to the generated candidate."""
    candidate = row.get("exercise_family_candidate", "REVIEW_REQUIRED")
    if candidate == "REVIEW_REQUIRED":
        return PROVISIONAL_FAMILY_BY_NAME.get(normalized_name(row), "REVIEW_REQUIRED_UNMAPPED")
    family = clean_family(candidate)
    # A leg press is not merely an equipment substitution for a squat: the
    # supported posture and force path require separate service guidance.
    if family == "SQUAT_VARIANT" and normalized_name(row) == "leg press":
        return "LEG_PRESS"
    return family


def is_provisional_family(family: str) -> bool:
    return family.startswith("REVIEW_REQUIRED_")


def codes(value: str) -> list[str]:
    return [code for code in (value or "").split("|") if code]


def normalize_equipment(value: str) -> str:
    found: list[str] = []
    low = (value or "").lower()
    for needle, code in EQUIPMENT_PATTERNS:
        if needle.lower() in low and code not in found:
            found.append(code)
    return "|".join(found) if found else "UNSPECIFIED"


def normalize_target(rows: list[dict[str, str]]) -> str:
    values = [r.get("source_target", "") for r in rows if r.get("source_target")]
    if not values:
        return "UNSPECIFIED"
    joined = " ".join(values).lower()
    for needles, code in TARGET_PATTERNS:
        if any(needle in joined for needle in needles):
            return code
    return Counter(values).most_common(1)[0][0]


def normalized_name(row: dict[str, str]) -> str:
    return re.sub(r"\s+", " ", (row.get("source_name") or row.get("name_en") or "").strip().lower())


def candidate_score(row: dict[str, str], family: str) -> tuple[int, int, int, int, str]:
    name = normalized_name(row)
    score = 0
    for anchor in ANCHORS.get(family, ()):
        if name == anchor or anchor in name:
            score += 10
    if row.get("selection_recommendation") == "RECOMMENDED":
        score += 4
    if row.get("beginner_suitability_candidate") in {"SUITABLE", "CONDITIONAL"}:
        score += 2
    if row.get("difficulty_code_candidate") == "BEGINNER":
        score += 2
    if row.get("reviewed_decision") == "INCLUDE":
        score += 2
    if row.get("raw_source_instruction_en") or row.get("source_description"):
        score += 2
    if not row.get("source_equipment"):
        score -= 1
    score -= 2 * len(re.findall(r"\bv\.\s*\d+\b", name))
    score -= sum(1 for term in ("contralateral", "alternate", "one arm", "one leg") if term in name)
    rank = row.get("selection_rank")
    rank_value = -int(rank) if rank and rank.isdigit() else -99
    source_quality = 1 if row.get("source_track") == "wger" else 0
    return score, rank_value, source_quality, -len(name.split()), name


def variant_code(row: dict[str, str], representative: dict[str, str]) -> str:
    name = normalized_name(row)
    rep_name = normalized_name(representative)
    if name == rep_name:
        return "BASE"
    parts: list[str] = []
    rep_equipment = normalize_equipment(representative.get("source_equipment", ""))
    equipment = normalize_equipment(row.get("source_equipment", ""))
    if equipment != rep_equipment and equipment != "UNSPECIFIED":
        parts.extend(equipment.split("|"))
    for needle, label in VARIANT_TERMS:
        if needle in name and label not in parts:
            parts.append(label)
    if not parts:
        parts.append("SOURCE_VARIANT")
    return "|".join(parts)


def difficulty(row: dict[str, str]) -> str:
    return row.get("difficulty_code_candidate") or row.get("reviewed_difficulty_code") or "REVIEW_REQUIRED"


def beginner(row: dict[str, str]) -> str:
    value = row.get("beginner_suitability_candidate") or row.get("reviewed_beginner_suitability")
    return value or "REVIEW_REQUIRED"


def merge_basis(rows: list[dict[str, str]], family: str) -> str:
    if is_provisional_family(family):
        return (
            "원천 후보를 대표 카탈로그에 포함하되 family taxonomy가 미확정이므로 자동 병합하지 않은 "
            "provisional singleton이다. 사람 검토 후 family 통합 또는 분리를 확정해야 한다."
        )
    patterns = sorted({r.get("movement_pattern_candidate", "") for r in rows if r.get("movement_pattern_candidate")})
    if len(rows) == 1:
        return "단일 원본 레코드이며 동일 family 내 병합 대상이 없음."
    pattern_text = ", ".join(patterns) if patterns else "미확정 패턴"
    return (
        f"동일 목적과 수행 패턴({pattern_text})을 공유하는 후보를 family로 묶고, "
        "장비·자세·그립·편측성·난이도 차이는 variant로 보존했다. "
        "타겟 근육만 같은 후보는 이 family 근거로 사용하지 않았다."
    )


def selection_reason(rep: dict[str, str], rows: list[dict[str, str]], family: str) -> str:
    if is_provisional_family(family):
        return "대표 후보로는 포함하되 family·movement pattern taxonomy와 운영 적합성 검토가 남아 있어 provisional로 표시함."
    reasons = ["family 내 대표 1개를 선택"]
    name = normalized_name(rep)
    if any(name == anchor for anchor in ANCHORS.get(family, ())):
        reasons.append("표준 운동명이 명확함")
    elif any(anchor in name for anchor in ANCHORS.get(family, ())):
        reasons.append("family 핵심 동작명을 포함함")
    if rep.get("beginner_suitability_candidate") in {"SUITABLE", "CONDITIONAL"}:
        reasons.append("초보자 접근성 후보값이 있음")
    if rep.get("raw_source_instruction_en") or rep.get("source_description"):
        reasons.append("원천 설명·가이드 연결이 있음")
    if rep.get("selection_recommendation") == "RECOMMENDED":
        reasons.append("기존 선정 후보가 RECOMMENDED임")
    reasons.append("최종 안전·용량·권리 검수는 별도 유지")
    return "; ".join(reasons) + "."


def main() -> None:
    with INPUT.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        original_fields = list(rows[0].keys())

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        family = family_for_row(row)
        if family != "REVIEW_REQUIRED":
            grouped[family].append(row)

    missing_labels = sorted(set(grouped) - set(FAMILY_KO))
    if missing_labels:
        raise RuntimeError(f"Missing Korean representative labels: {missing_labels}")

    family_ids = {family: f"REX-{index:06d}" for index, family in enumerate(sorted(grouped), start=1)}
    representative_by_family: dict[str, dict[str, str]] = {}
    for family, family_rows in grouped.items():
        representative_by_family[family] = max(family_rows, key=lambda row: candidate_score(row, family))

    catalog_rows: list[dict[str, str]] = []
    for family in sorted(grouped):
        family_rows = grouped[family]
        rep = representative_by_family[family]
        current_codes = sorted({code for row in family_rows for code in codes(row.get("review_required_codes", ""))})
        removable = [] if is_provisional_family(family) else [code for code in current_codes if code in REMOVABLE_CODES]
        remaining = [code for code in current_codes if code not in REMOVABLE_CODES]
        variants = [
            {
                "source_id": f"{row.get('source_track', '')}:{row.get('source_id', '')}",
                "variant": variant_code(row, rep),
                "source_name": row.get("source_name", ""),
            }
            for row in family_rows
        ]
        catalog_rows.append(
            {
                "representative_id": family_ids[family],
                "representative_name_ko": FAMILY_KO[family],
                "exercise_family": family,
                "variant_list": json.dumps(variants, ensure_ascii=False, separators=(",", ":")),
                "source_ids": "|".join(f"{r.get('source_track', '')}:{r.get('source_id', '')}" for r in family_rows),
                "source_count": str(len(family_rows)),
                "movement_pattern": Counter(r.get("movement_pattern_candidate", "REVIEW_REQUIRED") for r in family_rows).most_common(1)[0][0],
                "training_type": Counter(r.get("training_type_code_candidate", "REVIEW_REQUIRED") for r in family_rows).most_common(1)[0][0],
                "target_muscle": normalize_target(family_rows),
                "equipment": normalize_equipment(rep.get("source_equipment", "")),
                "difficulty": difficulty(rep),
                "beginner_suitable": beginner(rep),
                "selection_reason": selection_reason(rep, family_rows, family),
                "merge_judgement": (
                    "PROVISIONAL_SINGLETON_REVIEW_REQUIRED"
                    if is_provisional_family(family)
                    else "MERGE_TO_FAMILY_KEEP_VARIANTS" if len(family_rows) > 1 else "SINGLETON_FAMILY"
                ),
                "merge_basis": merge_basis(family_rows, family),
                "removable_review_required_codes": "|".join(removable),
                "additional_review_required_codes": "|".join(remaining),
                "representative_source_id": f"{rep.get('source_track', '')}:{rep.get('source_id', '')}",
                "representative_source_name": rep.get("source_name", ""),
                "representative_review_status": "REVIEW_REQUIRED" if is_provisional_family(family) else "FAMILY_SELECTION_COMPLETE",
            }
        )

    new_fields = ["representative_id", "exercise_family", "variant", "representative_selected"]
    with UPDATED_OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=original_fields + new_fields)
        writer.writeheader()
        for row in rows:
            family = family_for_row(row)
            if family in grouped:
                rep = representative_by_family[family]
                row["representative_id"] = family_ids[family]
                row["exercise_family"] = family
                row["variant"] = variant_code(row, rep)
                row["representative_selected"] = "true" if row is rep else "false"
                if not is_provisional_family(family):
                    remaining_codes = [
                        code for code in codes(row.get("review_required_codes", "")) if code not in REMOVABLE_CODES
                    ]
                    row["review_required_codes"] = "|".join(remaining_codes)
                    row["review_required"] = "true" if remaining_codes else "false"
            else:
                raise RuntimeError(f"Unmapped family: {family}")
            writer.writerow(row)

    catalog_fields = list(catalog_rows[0].keys())
    with CATALOG_OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=catalog_fields)
        writer.writeheader()
        writer.writerows(catalog_rows)

    print(json.dumps({
        "input_rows": len(rows),
        "resolved_families": len(grouped),
        "unresolved_rows": sum(row.get("exercise_family_candidate") == "REVIEW_REQUIRED" for row in rows),
        "catalog_rows": len(catalog_rows),
        "representatives_selected": sum(row["representative_selected"] == "true" for row in rows),
        "catalog_output": str(CATALOG_OUTPUT),
        "updated_output": str(UPDATED_OUTPUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
