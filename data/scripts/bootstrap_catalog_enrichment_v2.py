"""Create the initial catalog enrichment v2 working table from preserved inputs."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from build_exercise_catalog_v1 import (
    ENRICHMENT_COLUMNS,
    FOCUS_PRIMARY_AREAS,
    VALID_DIFFICULTY_CODES,
)

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTEGRATED = DATA_ROOT / "reports" / "integrated_exercise_review_updated.csv"
DEFAULT_FOCUS = DATA_ROOT / "normalized" / "body_focus_mapping_v2.csv"
DEFAULT_OUTPUT = DATA_ROOT / "normalized" / "catalog_enrichment_v2.csv"
SPECIAL_PRIMARY_FALLBACKS = {"FULL_BODY": ["HIP"], "CARDIO": ["HIP"], "MOBILITY": ["SHOULDER"]}
KOREAN_NAME_PHRASES = {
    "all fours": "네발기기",
    "back and forth": "앞뒤",
    "bodyweight": "맨몸",
    "close-grip": "클로즈그립",
    "cross trainer": "크로스 트레이너",
    "front of shoulder": "앞쪽 어깨",
    "high knee": "하이 니",
    "one arm": "원암",
    "one leg": "한발",
    "pull-up": "풀업",
    "russian twists": "러시안 트위스트",
    "russian twist": "러시안 트위스트",
    "short stride": "짧은 보폭",
    "step-up": "스텝업",
    "wide-grip": "와이드그립",
    "world greatest": "월드 그레이티스트",
}
KOREAN_NAME_WORDS = {
    "against": "벽 대고",
    "alternate": "교대",
    "and": "및",
    "angle": "앵글",
    "ankle": "발목",
    "arm": "암",
    "arms": "암",
    "assisted": "보조",
    "attachment": "어태치먼트",
    "back": "등",
    "ball": "볼",
    "band": "밴드",
    "bar": "바",
    "barbell": "바벨",
    "bench": "벤치",
    "bent": "벤트",
    "biceps": "이두",
    "bike": "자전거",
    "bicycle": "바이시클",
    "both": "양쪽",
    "bridge": "브리지",
    "bug": "버그",
    "butterfly": "버터플라이",
    "cable": "케이블",
    "calf": "카프",
    "chair": "의자",
    "chest": "체스트",
    "circles": "서클",
    "contralateral": "대각",
    "crunch": "크런치",
    "curl": "컬",
    "dead": "데드",
    "deadlift": "데드리프트",
    "decline": "디클라인",
    "deltoid": "델토이드",
    "donkey": "동키",
    "dumbbell": "덤벨",
    "dynamic": "다이내믹",
    "elliptical": "일립티컬",
    "exercise": "운동",
    "extended": "펴기",
    "extension": "익스텐션",
    "ez": "이지",
    "flexor": "플렉서",
    "floor": "바닥",
    "fly": "플라이",
    "forth": "앞",
    "forward": "전방",
    "fours": "네발",
    "front": "프론트",
    "glute": "둔근",
    "goblet": "고블릿",
    "greatest": "그레이티스트",
    "grip": "그립",
    "hammer": "해머",
    "hamstring": "햄스트링",
    "hand": "손",
    "hands": "손",
    "head": "머리",
    "high": "하이",
    "hip": "힙",
    "hyperextension": "하이퍼익스텐션",
    "incline": "인클라인",
    "intermediate": "중급",
    "inverse": "인버스",
    "inverted": "인버티드",
    "jack": "잭",
    "jump": "점프",
    "kettlebell": "케틀벨",
    "knee": "니",
    "kneeling": "니링",
    "lat": "랫",
    "lateral": "레터럴",
    "leg": "레그",
    "legs": "레그",
    "lever": "레버",
    "low": "로우",
    "lower": "로워",
    "lunge": "런지",
    "lying": "라잉",
    "machine": "머신",
    "male": "남성",
    "neck": "목",
    "of": "의",
    "on": "온",
    "over": "오버",
    "overhead": "오버헤드",
    "parallel": "패럴렐",
    "pass": "패스",
    "peroneals": "비골근",
    "piriformis": "이상근",
    "plank": "플랭크",
    "pose": "포즈",
    "preacher": "프리처",
    "press": "프레스",
    "pull": "풀",
    "pulldown": "풀다운",
    "pullover": "풀오버",
    "push": "푸시",
    "pushdown": "푸시다운",
    "quad": "대퇴사두",
    "quads": "대퇴사두",
    "raise": "레이즈",
    "raises": "레이즈",
    "rear": "리어",
    "resistance": "저항",
    "revers": "리버스",
    "reverse": "리버스",
    "roller": "롤러",
    "rope": "로프",
    "row": "로우",
    "run": "달리기",
    "runners": "러너",
    "scapular": "견갑",
    "seated": "시티드",
    "self": "셀프",
    "sequence": "시퀀스",
    "side": "사이드",
    "single": "싱글",
    "smith": "스미스",
    "spine": "척추",
    "split": "스플릿",
    "squad": "스쿼트",
    "squat": "스쿼트",
    "squats": "스쿼트",
    "squeeze": "스퀴즈",
    "stability": "스태빌리티",
    "standing": "스탠딩",
    "step": "스텝",
    "stepmill": "스텝밀",
    "stiff": "스티프",
    "straight": "스트레이트",
    "strap": "스트랩",
    "straps": "스트랩",
    "stretch": "스트레칭",
    "support": "서포트",
    "suspended": "서스펜디드",
    "through": "스루",
    "to": "투",
    "trainer": "트레이너",
    "treadmill": "트레드밀",
    "triceps": "삼두",
    "shoulder": "숄더",
    "shrug": "슈러그",
    "stationary": "고정식",
    "tuck": "턱",
    "two": "양쪽",
    "twist": "트위스트",
    "twisting": "트위스팅",
    "twists": "트위스트",
    "up": "업",
    "under": "아래",
    "upper": "어퍼",
    "wide": "와이드",
    "walk": "걷기",
    "walking": "워킹",
    "wall": "벽",
    "weighted": "중량",
    "with": "위드",
    "wrist": "리스트",
    "y": "와이",
    "yoga": "요가",
    "zottman": "조트만",
}
VERSION_DECISIONS = {
    "NEX-000033": {
        "exercise_name_ko": "덤벨 디클라인 슈러그",
        "catalog_exposure_code": "MEDIA_VARIANT",
        "canonical_exercise_id": "NEX-000034",
        "variant_relation_code": "SAME_MOVEMENT_MEDIA_VARIANT",
        "variant_basis": (
            "Same target, equipment, decline posture, and movement; "
            "0304 differs only in media and cues."
        ),
    },
    "NEX-000034": {
        "exercise_name_ko": "덤벨 디클라인 슈러그",
        "catalog_exposure_code": "PRIMARY",
        "canonical_exercise_id": "NEX-000034",
        "variant_relation_code": "NONE",
        "variant_basis": "Canonical user-facing record for the decline dumbbell shrug source pair.",
    },
    "NEX-000035": {
        "exercise_name_ko": "덤벨 프론트 레이즈",
        "catalog_exposure_code": "MEDIA_VARIANT",
        "canonical_exercise_id": "NEX-000036",
        "variant_relation_code": "SAME_MOVEMENT_MEDIA_VARIANT",
        "variant_basis": (
            "Same target, equipment, stance, and shoulder-height range; 0309 only adds a core cue."
        ),
    },
    "NEX-000036": {
        "exercise_name_ko": "덤벨 프론트 레이즈",
        "catalog_exposure_code": "PRIMARY",
        "canonical_exercise_id": "NEX-000036",
        "variant_relation_code": "NONE",
        "variant_basis": "Canonical user-facing record for the dumbbell front raise source pair.",
    },
    "NEX-000043": {
        "exercise_name_ko": "원암 덤벨 숄더 프레스",
        "catalog_exposure_code": "MEDIA_VARIANT",
        "canonical_exercise_id": "NEX-000044",
        "variant_relation_code": "SAME_MOVEMENT_MEDIA_VARIANT",
        "variant_basis": (
            "Same target, equipment, stance, and overhead press; 0360 only adds a core cue."
        ),
    },
    "NEX-000044": {
        "exercise_name_ko": "원암 덤벨 숄더 프레스",
        "catalog_exposure_code": "PRIMARY",
        "canonical_exercise_id": "NEX-000044",
        "variant_relation_code": "NONE",
        "variant_basis": "Canonical user-facing record for the one-arm shoulder press source pair.",
    },
    "NEX-000091": {
        "exercise_name_ko": "중량 러시안 트위스트(바닥 터치)",
        "catalog_exposure_code": "PRIMARY",
        "canonical_exercise_id": "NEX-000091",
        "variant_relation_code": "NONE",
        "variant_basis": (
            "Canonical floor-touch range-of-motion record for the weighted Russian twist pair."
        ),
    },
    "NEX-000155": {
        "exercise_name_ko": "중량 러시안 트위스트(몸통 옆 회전)",
        "catalog_exposure_code": "DISTINCT_VARIANT",
        "canonical_exercise_id": "NEX-000091",
        "variant_relation_code": "RANGE_OF_MOTION_VARIANT",
        "variant_basis": (
            "Source 2371 rotates beside the torso; 0846 directs the weight toward the floor."
        ),
    },
    "NEX-000117": {
        "exercise_name_ko": "밴드 양발 카프 레이즈",
        "catalog_exposure_code": "PRIMARY",
        "canonical_exercise_id": "NEX-000117",
        "variant_relation_code": "NONE",
        "variant_basis": (
            "No unversioned peer exists in the preserved source; omit the source version suffix."
        ),
    },
    "NEX-000143": {
        "exercise_name_ko": "실내 자전거 타기",
        "catalog_exposure_code": "PRIMARY",
        "canonical_exercise_id": "NEX-000143",
        "variant_relation_code": "NONE",
        "variant_basis": (
            "No unversioned peer exists in the preserved source; omit the source version suffix."
        ),
    },
    "NEX-000113": {
        "exercise_name_ko": "벽 짚고 한 팔 광배근 등척성 운동",
        "catalog_exposure_code": "PRIMARY",
        "canonical_exercise_id": "NEX-000113",
        "variant_relation_code": "NONE",
        "variant_basis": (
            "Wall press isometric lat activation is a distinct reviewed exercise identity."
        ),
    },
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def split_area_codes(value: str) -> list[str]:
    value = value.strip()
    if not value or value == "REVIEW_REQUIRED":
        return []
    return list(
        dict.fromkeys(item.strip() for item in value.replace("|", ",").split(",") if item.strip())
    )


def korean_draft_name(value: str) -> str:
    localized = re.sub(r"\s+v\.?\s*\d+\b", "", value.strip().lower())
    for source, replacement in KOREAN_NAME_PHRASES.items():
        localized = localized.replace(source, replacement)

    def replace_word(match: re.Match[str]) -> str:
        word = match.group(0)
        if word not in KOREAN_NAME_WORDS:
            raise ValueError(f"missing Korean draft-name translation for: {word}")
        return KOREAN_NAME_WORDS[word]

    return re.sub(r"[a-z]+", replace_word, localized).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integrated", type=Path, default=DEFAULT_INTEGRATED)
    parser.add_argument("--body-focus-mapping", type=Path, default=DEFAULT_FOCUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists() and not args.force:
        parser.error(f"refusing to overwrite existing source of truth: {args.output}")
    integrated = {row["normalized_exercise_id"].strip(): row for row in read_csv(args.integrated)}
    focus = {row["exercise_id"].strip(): row for row in read_csv(args.body_focus_mapping)}
    if set(integrated) != set(focus) or len(integrated) != 208:
        parser.error(
            "integrated catalog and body focus mapping must contain the same 208 exercise IDs"
        )
    rows: list[dict[str, str]] = []
    for exercise_id in sorted(integrated):
        source, mapping = integrated[exercise_id], focus[exercise_id]
        body_focus = mapping["body_focus_code"].strip()
        primary = split_area_codes(source.get("reviewed_body_area_codes", "")) or split_area_codes(
            source.get("body_area_codes_candidate", "")
        )
        if not primary:
            primary = sorted(
                FOCUS_PRIMARY_AREAS.get(
                    body_focus, SPECIAL_PRIMARY_FALLBACKS.get(body_focus, ["HIP"])
                )
            )
        localized = source.get("name_ko", "").strip()
        name_basis = "integrated name_ko"
        if not localized or localized == "REVIEW_REQUIRED":
            localized = korean_draft_name(
                source.get("source_display_name_ko", "").strip()
                or source.get("source_name", "").strip()
                or source["name_en"].strip()
            )
            name_basis = (
                "source title converted to Korean draft; Korean localization review required"
            )
        proposed_difficulty = source.get("reviewed_difficulty_code", "").strip()
        if proposed_difficulty not in VALID_DIFFICULTY_CODES:
            proposed_difficulty = ""
        decision = VERSION_DECISIONS.get(
            exercise_id,
            {
                "catalog_exposure_code": "PRIMARY",
                "canonical_exercise_id": exercise_id,
                "variant_relation_code": "NONE",
                "variant_basis": "No versioned source-pair decision recorded.",
            },
        )
        rows.append(
            {
                "exercise_id": exercise_id,
                "exercise_name_ko": decision.get("exercise_name_ko", localized),
                "name_en": source.get("name_en", "").strip()
                or source.get("source_name", "").strip(),
                "body_focus_code": body_focus,
                "primary_body_area_codes": json.dumps(
                    primary, ensure_ascii=False, separators=(",", ":")
                ),
                "secondary_body_area_codes": "[]",
                "proposed_body_focus_code": "",
                "proposed_difficulty_code": proposed_difficulty,
                "difficulty_code": "",
                "timing_mode_code": "",
                "default_sets": "",
                "default_reps": "",
                "default_work_seconds": "",
                "default_rest_seconds": "",
                "default_transition_seconds": "",
                "intensity_level": "",
                "name_ko_status": "REVIEW_REQUIRED",
                "body_focus_status": "REVIEW_REQUIRED",
                "body_area_status": "REVIEW_REQUIRED",
                "difficulty_status": "REVIEW_REQUIRED",
                "fitt_status": "REVIEW_REQUIRED",
                "name_ko_basis": name_basis,
                "body_focus_basis": mapping["mapping_basis"].strip(),
                "body_area_basis": (
                    "integrated reviewed/candidate body area; domain review required"
                ),
                "difficulty_basis": (
                    "integrated reviewed difficulty proposal; domain review required"
                ),
                "fitt_basis": "no reviewed FITT value in source; domain review required",
                "catalog_exposure_code": decision["catalog_exposure_code"],
                "canonical_exercise_id": decision["canonical_exercise_id"],
                "variant_relation_code": decision["variant_relation_code"],
                "variant_basis": decision["variant_basis"],
                "reviewer": "",
                "reviewed_at": "",
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENRICHMENT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
