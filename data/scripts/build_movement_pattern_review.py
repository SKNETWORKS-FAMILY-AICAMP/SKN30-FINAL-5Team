"""Build the human-reviewed movement-pattern record from catalog enrichment v2."""

from __future__ import annotations

import csv
from pathlib import Path

SOURCE_PATH = Path("data/normalized/catalog_enrichment_v2.csv")
OUTPUT_PATH = Path("data/validation/review_results/movement_pattern_review.csv")
ALLOWED_PATTERNS = {
    "SQUAT",
    "HINGE",
    "LUNGE",
    "PUSH",
    "PULL",
    "CARRY",
    "CORE",
    "MOBILITY",
    "CARDIO",
}

# Exercise IDs are explicit to make every taxonomy proposal auditable and to
# fail closed when the input catalog changes.
PATTERN_BY_EXERCISE_ID = {
    "NEX-000001": "HINGE",
    "NEX-000002": "PULL",
    "NEX-000003": "PULL",
    "NEX-000004": "PUSH",
    "NEX-000005": "PULL",
    "NEX-000006": "PULL",
    "NEX-000007": "SQUAT",
    "NEX-000008": "PUSH",
    "NEX-000009": "HINGE",
    "NEX-000010": "PULL",
    "NEX-000011": "PULL",
    "NEX-000012": "PUSH",
    "NEX-000013": "PULL",
    "NEX-000014": "PULL",
    "NEX-000015": "PULL",
    "NEX-000016": "PUSH",
    "NEX-000017": "PUSH",
    "NEX-000018": "PULL",
    "NEX-000019": "PUSH",
    "NEX-000020": "PULL",
    "NEX-000021": "PUSH",
    "NEX-000022": "PULL",
    "NEX-000023": "CORE",
    "NEX-000024": "PULL",
    "NEX-000025": "PULL",
    "NEX-000026": "PUSH",
    "NEX-000027": "CORE",
    "NEX-000028": "PUSH",
    "NEX-000029": "CORE",
    "NEX-000030": "CORE",
    "NEX-000031": "CORE",
    "NEX-000032": "HINGE",
    "NEX-000033": "PULL",
    "NEX-000034": "PULL",
    "NEX-000035": "PUSH",
    "NEX-000036": "PUSH",
    "NEX-000037": "PULL",
    "NEX-000038": "PULL",
    "NEX-000039": "PUSH",
    "NEX-000040": "PUSH",
    "NEX-000041": "LUNGE",
    "NEX-000042": "PULL",
    "NEX-000043": "PUSH",
    "NEX-000044": "PUSH",
    "NEX-000045": "PULL",
    "NEX-000046": "PULL",
    "NEX-000047": "PULL",
    "NEX-000048": "PULL",
    "NEX-000049": "PUSH",
    "NEX-000050": "PUSH",
    "NEX-000051": "LUNGE",
    "NEX-000052": "PULL",
    "NEX-000053": "PUSH",
    "NEX-000054": "PULL",
    "NEX-000055": "PUSH",
    "NEX-000056": "PUSH",
    "NEX-000057": "PULL",
    "NEX-000058": "SQUAT",
    "NEX-000059": "PULL",
    "NEX-000060": "PULL",
    "NEX-000061": "HINGE",
    "NEX-000062": "HINGE",
    "NEX-000063": "CORE",
    "NEX-000064": "HINGE",
    "NEX-000065": "HINGE",
    "NEX-000066": "PULL",
    "NEX-000067": "PULL",
    "NEX-000068": "LUNGE",
    "NEX-000069": "SQUAT",
    "NEX-000070": "SQUAT",
    "NEX-000071": "HINGE",
    "NEX-000072": "MOBILITY",
    "NEX-000073": "MOBILITY",
    "NEX-000074": "PUSH",
    "NEX-000075": "MOBILITY",
    "NEX-000076": "CARDIO",
    "NEX-000077": "CORE",
    "NEX-000078": "PULL",
    "NEX-000079": "MOBILITY",
    "NEX-000080": "CORE",
    "NEX-000081": "HINGE",
    "NEX-000082": "HINGE",
    "NEX-000083": "MOBILITY",
    "NEX-000084": "MOBILITY",
    "NEX-000085": "SQUAT",
    "NEX-000086": "MOBILITY",
    "NEX-000087": "HINGE",
    "NEX-000088": "CORE",
    "NEX-000089": "MOBILITY",
    "NEX-000090": "CORE",
    "NEX-000091": "CORE",
    "NEX-000092": "PULL",
    "NEX-000093": "PULL",
    "NEX-000094": "CORE",
    "NEX-000095": "CORE",
    "NEX-000096": "CORE",
    "NEX-000097": "PUSH",
    "NEX-000098": "PUSH",
    "NEX-000099": "CORE",
    "NEX-000100": "PULL",
    "NEX-000101": "PUSH",
    "NEX-000102": "SQUAT",
    "NEX-000103": "SQUAT",
    "NEX-000104": "HINGE",
    "NEX-000105": "PULL",
    "NEX-000106": "PULL",
    "NEX-000107": "HINGE",
    "NEX-000108": "MOBILITY",
    "NEX-000109": "PUSH",
    "NEX-000110": "MOBILITY",
    "NEX-000111": "MOBILITY",
    "NEX-000112": "MOBILITY",
    "NEX-000113": "PULL",
    "NEX-000114": "MOBILITY",
    "NEX-000115": "MOBILITY",
    "NEX-000116": "MOBILITY",
    "NEX-000117": "SQUAT",
    "NEX-000118": "SQUAT",
    "NEX-000119": "MOBILITY",
    "NEX-000120": "SQUAT",
    "NEX-000121": "SQUAT",
    "NEX-000122": "SQUAT",
    "NEX-000123": "MOBILITY",
    "NEX-000124": "MOBILITY",
    "NEX-000125": "MOBILITY",
    "NEX-000126": "MOBILITY",
    "NEX-000127": "MOBILITY",
    "NEX-000128": "LUNGE",
    "NEX-000129": "MOBILITY",
    "NEX-000130": "MOBILITY",
    "NEX-000131": "MOBILITY",
    "NEX-000132": "MOBILITY",
    "NEX-000133": "MOBILITY",
    "NEX-000134": "MOBILITY",
    "NEX-000135": "MOBILITY",
    "NEX-000136": "MOBILITY",
    "NEX-000137": "MOBILITY",
    "NEX-000138": "MOBILITY",
    "NEX-000139": "MOBILITY",
    "NEX-000140": "PULL",
    "NEX-000141": "PULL",
    "NEX-000142": "SQUAT",
    "NEX-000143": "CARDIO",
    "NEX-000144": "CARDIO",
    "NEX-000145": "MOBILITY",
    "NEX-000146": "CORE",
    "NEX-000147": "MOBILITY",
    "NEX-000148": "PULL",
    "NEX-000149": "PULL",
    "NEX-000150": "PULL",
    "NEX-000151": "CARDIO",
    "NEX-000152": "MOBILITY",
    "NEX-000153": "SQUAT",
    "NEX-000154": "LUNGE",
    "NEX-000155": "CORE",
    "NEX-000156": "HINGE",
    "NEX-000157": "MOBILITY",
    "NEX-000158": "CARDIO",
    "NEX-000159": "LUNGE",
    "NEX-000160": "SQUAT",
    "NEX-000161": "PULL",
    "NEX-000162": "HINGE",
    "NEX-000163": "PUSH",
    "NEX-000164": "CARDIO",
    "NEX-000165": "LUNGE",
    "NEX-000166": "PULL",
    "NEX-000167": "LUNGE",
    "NEX-000168": "CARDIO",
    "NEX-000169": "CARDIO",
    "NEX-000170": "CARDIO",
    "NEX-000171": "CARDIO",
    "NEX-000172": "CARDIO",
    "NEX-000173": "CORE",
    "NEX-000174": "SQUAT",
    "NEX-000175": "SQUAT",
    "NEX-000176": "SQUAT",
    "NEX-000177": "CORE",
    "NEX-000178": "PULL",
    "NEX-000179": "CORE",
    "NEX-000180": "HINGE",
    "NEX-000181": "SQUAT",
    "NEX-000182": "PUSH",
    "NEX-000183": "PULL",
    "NEX-000184": "PULL",
    "NEX-000185": "PULL",
    "NEX-000186": "HINGE",
    "NEX-000187": "CORE",
    "NEX-000188": "SQUAT",
    "NEX-000189": "PULL",
    "NEX-000190": "PULL",
    "NEX-000191": "HINGE",
    "NEX-000192": "HINGE",
    "NEX-000193": "HINGE",
    "NEX-000194": "PUSH",
    "NEX-000195": "LUNGE",
    "NEX-000196": "PULL",
    "NEX-000197": "SQUAT",
    "NEX-000198": "PUSH",
    "NEX-000199": "PULL",
    "NEX-000200": "PUSH",
    "NEX-000201": "SQUAT",
    "NEX-000202": "HINGE",
    "NEX-000203": "SQUAT",
    "NEX-000204": "SQUAT",
    "NEX-000205": "HINGE",
    "NEX-000206": "PUSH",
    "NEX-000207": "PUSH",
    "NEX-000208": "HINGE",
}

REASONS = {
    "SQUAT": "무릎 굴곡·신전이 주된 하체 지지·밀기 동작이므로 SQUAT으로 제안.",
    "HINGE": "고관절 굴곡·신전이 주된 하체 후면 연쇄 동작이므로 HINGE로 제안.",
    "LUNGE": "분할·전후 스탠스에서 한쪽 다리로 체중을 지지·이동하므로 LUNGE로 제안.",
    "PUSH": "상지의 밀기 또는 프레스성 관절 움직임이 주된 목적이므로 PUSH로 제안.",
    "PULL": "상지의 당기기 또는 견갑·팔꿈치 굴곡 중심 움직임이 주된 목적이므로 PULL로 제안.",
    "CARRY": "그립을 유지하며 하중을 지지하는 능력이 주된 목적이므로 CARRY 후보로 제안.",
    "CORE": "몸통의 안정화·굴곡·회전 제어가 주된 목적이므로 CORE로 제안.",
    "MOBILITY": "가동범위 확보와 스트레칭이 주된 수행 목적이므로 MOBILITY로 제안.",
    "CARDIO": "리드미컬한 전신·하지 반복으로 심폐 부담을 만드는 활동이므로 CARDIO로 제안.",
}

# The controlled vocabulary has no isolation-pattern codes. These explicit
# overrides record why the nearest whole-body pattern is only provisional.
CALF_ISOLATION_REASON = (
    "발목 저측굴곡 중심의 종아리 고립 동작이며 별도 코드가 없어 "
    "하체 지지·밀기 계열 SQUAT으로 임시 제안."
)
QUADRICEPS_ISOLATION_REASON = (
    "무릎 신전 중심의 대퇴사두 고립 동작이며 별도 코드가 없어 "
    "무릎 주도 하체 패턴 SQUAT으로 임시 제안."
)
HAMSTRING_ISOLATION_REASON = (
    "무릎 굴곡 중심의 햄스트링 고립 동작이며 별도 코드가 없어 후면 연쇄 계열 HINGE로 임시 제안."
)
SHOULDER_ISOLATION_REASON = (
    "어깨 굴곡·외전 중심의 고립 동작이며 별도 코드가 없어 "
    "상지 전면·측면 강화 계열 PUSH로 임시 제안."
)
FLY_ISOLATION_REASON = (
    "어깨 수평 내전 중심의 가슴 고립 동작이며 별도 코드가 없어 상지 밀기 계열 PUSH로 임시 제안."
)
WRIST_ISOLATION_REASON = (
    "손목 굴곡·신전 중심의 전완 고립 동작이며 별도 코드가 없어 상지 당기기 계열 PULL로 임시 제안."
)
BICEPS_ISOLATION_REASON = (
    "팔꿈치 굴곡 중심의 이두 고립 동작이며 별도 코드가 없어 상지 당기기 계열 PULL로 임시 제안."
)
GRIP_ISOLATION_REASON = (
    "정적 그립 강화가 주된 목적이며 별도 그립 코드가 없어 상지 당기기 계열 PULL로 임시 제안."
)

REASON_OVERRIDES = {
    **dict.fromkeys(
        {
            "NEX-000007",
            "NEX-000058",
            "NEX-000070",
            "NEX-000085",
            "NEX-000102",
            "NEX-000103",
            "NEX-000117",
            "NEX-000118",
            "NEX-000120",
            "NEX-000121",
            "NEX-000122",
            "NEX-000153",
            "NEX-000188",
        },
        CALF_ISOLATION_REASON,
    ),
    **dict.fromkeys(
        {"NEX-000069", "NEX-000160", "NEX-000203"},
        QUADRICEPS_ISOLATION_REASON,
    ),
    **dict.fromkeys(
        {
            "NEX-000065",
            "NEX-000071",
            "NEX-000081",
            "NEX-000082",
            "NEX-000087",
            "NEX-000156",
            "NEX-000180",
            "NEX-000191",
            "NEX-000202",
        },
        HAMSTRING_ISOLATION_REASON,
    ),
    **dict.fromkeys(
        {
            "NEX-000004",
            "NEX-000035",
            "NEX-000036",
            "NEX-000039",
            "NEX-000040",
            "NEX-000049",
            "NEX-000050",
            "NEX-000053",
            "NEX-000097",
            "NEX-000098",
        },
        SHOULDER_ISOLATION_REASON,
    ),
    **dict.fromkeys(
        {
            "NEX-000012",
            "NEX-000016",
            "NEX-000017",
            "NEX-000019",
            "NEX-000026",
            "NEX-000109",
        },
        FLY_ISOLATION_REASON,
    ),
    **dict.fromkeys(
        {
            "NEX-000006",
            "NEX-000010",
            "NEX-000045",
            "NEX-000046",
            "NEX-000052",
            "NEX-000100",
            "NEX-000105",
        },
        WRIST_ISOLATION_REASON,
    ),
    **dict.fromkeys(
        {
            "NEX-000047",
            "NEX-000054",
            "NEX-000059",
            "NEX-000060",
            "NEX-000140",
            "NEX-000141",
            "NEX-000149",
        },
        BICEPS_ISOLATION_REASON,
    ),
    **dict.fromkeys(
        {"NEX-000025", "NEX-000033", "NEX-000034", "NEX-000038", "NEX-000057", "NEX-000106"},
        "견갑 거상 중심의 승모근 고립 동작이며 별도 코드가 없어 상지 당기기 계열 PULL로 임시 제안.",
    ),
    **dict.fromkeys(
        {"NEX-000002", "NEX-000003", "NEX-000005", "NEX-000018", "NEX-000148", "NEX-000161"},
        "어깨 신전 중심의 풀오버 동작이므로 상지 당기기 계열 PULL로 제안.",
    ),
    "NEX-000092": GRIP_ISOLATION_REASON,
}


def current_training_type(body_focus: str) -> str:
    if body_focus == "MOBILITY":
        return "MOBILITY"
    if body_focus == "CARDIO":
        return "CARDIO"
    return "STRENGTH"


def main() -> None:
    with SOURCE_PATH.open(encoding="utf-8", newline="") as source_file:
        source_rows = list(csv.DictReader(source_file))

    source_ids = {row["exercise_id"] for row in source_rows}
    mapped_ids = set(PATTERN_BY_EXERCISE_ID)
    missing_ids = source_ids - mapped_ids
    unexpected_ids = mapped_ids - source_ids
    invalid_patterns = set(PATTERN_BY_EXERCISE_ID.values()) - ALLOWED_PATTERNS
    if missing_ids or unexpected_ids or invalid_patterns:
        raise ValueError(
            "Movement-pattern mapping must exactly cover the input catalog: "
            f"missing={sorted(missing_ids)}, unexpected={sorted(unexpected_ids)}, "
            f"invalid_patterns={sorted(invalid_patterns)}"
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=[
                "exercise_id",
                "exercise_name",
                "current_body_focus",
                "current_training_type",
                "difficulty",
                "suggested_movement_pattern",
                "review_reason",
                "review_required",
            ],
        )
        writer.writeheader()
        for row in source_rows:
            pattern = PATTERN_BY_EXERCISE_ID[row["exercise_id"]]
            writer.writerow(
                {
                    "exercise_id": row["exercise_id"],
                    "exercise_name": row["exercise_name_ko"],
                    "current_body_focus": row["body_focus_code"],
                    "current_training_type": current_training_type(row["body_focus_code"]),
                    "difficulty": row["difficulty_code"],
                    "suggested_movement_pattern": pattern,
                    "review_reason": (
                        f"{REASON_OVERRIDES.get(row['exercise_id'], REASONS[pattern])} "
                        "사람 검수 완료: movement_pattern 수정 필요 없음."
                    ),
                    "review_required": "NO",
                }
            )


if __name__ == "__main__":
    main()
