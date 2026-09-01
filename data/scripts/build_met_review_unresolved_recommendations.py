#!/usr/bin/env python3
"""Create conditional, non-approved recommendations for unresolved MET rows."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from process_met_review_recommendations import read_recommendations

OUTPUT_FIELDS = [
    "exercise_id",
    "exercise_name",
    "assumed_execution_condition",
    "recommended_intensity",
    "recommended_met",
    "alternative_met_options",
    "compendium_activity_code",
    "compendium_activity_name",
    "recommendation_type",
    "recommendation_reason",
    "reviewer_decision",
    "reviewer_comment",
]

SOURCE_URL = "https://pacompendium.com/"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in OUTPUT_FIELDS} for row in rows)


def rec(
    condition: str,
    intensity: str,
    met: str,
    alternatives: str,
    code: str,
    name: str,
    kind: str,
    reason: str,
) -> dict[str, str]:
    return {
        "assumed_execution_condition": condition,
        "recommended_intensity": intensity,
        "recommended_met": met,
        "alternative_met_options": alternatives,
        "compendium_activity_code": code,
        "compendium_activity_name": name,
        "recommendation_type": kind,
        "recommendation_reason": reason + f" 출처: {SOURCE_URL}",
        "reviewer_decision": "",
        "reviewer_comment": "",
    }


CONDITIONALS: dict[str, dict[str, str]] = {
    "NEX-000002": rec(
        "바벨 풀오버, 8–15회, 세트 간 60–90초, 중량은 통제 가능한 보통 부하, 느린-중간 템포",
        "MODERATE",
        "3.5",
        "02054 / 3.5 MET / 8–15회· varied resistance 일반 저항운동의 조건부 대안",
        "02054",
        "Resistance (weight) training, multiple exercises, 8-15 reps at varied resistance",
        "PROVISIONAL_ESTIMATE",
        "풀오버 직접 항목은 없으므로 일반 저항운동 02054를 상위 유형의 참고값으로만 "
        "제안합니다. 운동별 부하·휴식이 확인되기 전에는 승인하지 않습니다.",
    ),
    "NEX-000003": rec(
        "바벨 풀오버, 8–15회, 세트 간 60–90초, 중량은 통제 가능한 보통 부하, 느린-중간 템포",
        "MODERATE",
        "3.5",
        "02054 / 3.5 MET / 8–15회· varied resistance 일반 저항운동의 조건부 대안",
        "02054",
        "Resistance (weight) training, multiple exercises, 8-15 reps at varied resistance",
        "PROVISIONAL_ESTIMATE",
        "와이드 그립·디클라인 변형의 직접 항목은 없으므로 02054를 참고값으로만 "
        "제안합니다. 자세·부하 조건 확인이 필요합니다.",
    ),
    "NEX-000005": rec(
        "바벨 풀오버, 8–15회, 세트 간 60–90초, 중량은 통제 가능한 보통 부하, 느린-중간 템포",
        "MODERATE",
        "3.5",
        "02054 / 3.5 MET / 8–15회· varied resistance 일반 저항운동의 조건부 대안",
        "02054",
        "Resistance (weight) training, multiple exercises, 8-15 reps at varied resistance",
        "PROVISIONAL_ESTIMATE",
        "풀오버 직접 항목은 없으므로 02054를 상위 유형의 참고값으로만 제안합니다. "
        "실제 부하와 휴식 확인이 필요합니다.",
    ),
    "NEX-000065": rec(
        "벤치 보조·자체 체중 역방향 레그 컬, 통제된 8–15회, 세트 간 60–90초, 외부 중량 없음",
        "MODERATE",
        "3.0",
        "02056 / 3.0 MET / body weight resistance general",
        "02056",
        "Body weight resistance exercises, general",
        "PROVISIONAL_ESTIMATE",
        "역방향 레그 컬 직접 항목은 없으므로 자체 체중 저항운동 일반값을 참고합니다. "
        "벤치 보조 수준과 반복 속도 확인이 필요합니다.",
    ),
    "NEX-000076": rec(
        "자기 선택 조깅 속도(보통 성인의 지속 가능한 조깅), 평지, 중단 없는 지속 수행",
        "VIGOROUS",
        "7.5",
        "12028 / 6.5 MET / 4.0–4.2 mph | 12029 / 7.8 MET / 4.3–4.8 mph | "
        "12030 / 8.5 MET / 5.0–5.2 mph | 12045 / 9.0 MET / 5.5–5.8 mph | "
        "12050 / 9.3 MET / 6.0–6.3 mph",
        "12020",
        "Jogging, general, self-selected pace",
        "CONDITIONAL_MATCH",
        "운동명만으로 속도를 확정할 수 없으므로 자기 선택 조깅을 기본 조건으로 둔 "
        "조건부 제안입니다. 실제 속도에 따라 선택지를 바꿔야 합니다.",
    ),
    "NEX-000081": rec(
        "바닥에서 자체 체중 역방향 레그 컬, 통제된 8–15회, 세트 간 60–90초, 외부 중량 없음",
        "MODERATE",
        "3.0",
        "02056 / 3.0 MET / body weight resistance general",
        "02056",
        "Body weight resistance exercises, general",
        "PROVISIONAL_ESTIMATE",
        "직접 대응 항목이 없어 자체 체중 저항운동 일반값을 참고합니다. "
        "바닥 변형의 난이도와 반복 속도 확인이 필요합니다.",
    ),
    "NEX-000082": rec(
        "자체 체중 역방향 레그 컬, 통제된 8–15회, 세트 간 60–90초, 외부 중량 없음",
        "MODERATE",
        "3.0",
        "02056 / 3.0 MET / body weight resistance general",
        "02056",
        "Body weight resistance exercises, general",
        "PROVISIONAL_ESTIMATE",
        "직접 대응 항목이 없어 자체 체중 저항운동 일반값을 참고합니다. "
        "수행 보조와 반복 속도 확인이 필요합니다.",
    ),
    "NEX-000087": rec(
        "서서 자체 체중 싱글 레그 컬, 통제된 8–15회, 세트 간 60–90초, 외부 중량 없음",
        "MODERATE",
        "3.0",
        "02056 / 3.0 MET / body weight resistance general",
        "02056",
        "Body weight resistance exercises, general",
        "PROVISIONAL_ESTIMATE",
        "직접 대응 항목이 없어 자체 체중 저항운동 일반값을 참고합니다. "
        "균형 보조 여부와 반복 속도 확인이 필요합니다.",
    ),
    "NEX-000112": rec(
        "체중만 사용하는 코어 컬, 느린 통제 동작, 8–15회, 세트 간 60–90초",
        "LIGHT",
        "2.8",
        "02024 / 2.8 MET / light calisthenics: curl-ups, abdominal crunches, plank",
        "02024",
        "Calisthenics (e.g., curl ups, abdominal crunches, plank), light effort",
        "PROVISIONAL_ESTIMATE",
        "하부 등 컬 직접 항목은 없으므로 유사한 저강도 코어·복부 운동을 참고합니다. "
        "동작 범위와 속도 확인이 필요합니다.",
    ),
    "NEX-000113": rec(
        "벽을 이용한 체중 저항성 동작, 통제된 8–15회 또는 20–30초 등척성 유지, 세트 간 60–90초",
        "MODERATE",
        "3.0",
        "02056 / 3.0 MET / body weight resistance general",
        "02056",
        "Body weight resistance exercises, general",
        "PROVISIONAL_ESTIMATE",
        "사용자 확인에 따라 저항성 운동으로 분류합니다. 직접 대응 항목은 없으므로 "
        "자체 체중 저항운동 일반값을 참고값으로만 제안하며 실제 동작·유지시간·반복수를 "
        "확인해야 합니다.",
    ),
    "NEX-000129": rec(
        "버터플라이 자세를 정적으로 유지하는 가벼운 요가·스트레칭, 호흡 중심, 휴식 포함",
        "LIGHT",
        "2.3",
        "02101 / 2.3 MET / Stretching, mild",
        "02175",
        "Yoga, general",
        "CONDITIONAL_MATCH",
        "자세 단독 수행은 전체 요가 세션과 다르므로 일반 요가값을 조건부로만 "
        "제안합니다. 정적 스트레칭으로 확인되면 02101을 검토합니다.",
    ),
    "NEX-000143": rec(
        "고정식 자전거, 60 W, 일정 케이던스, 중간 강도, 지속 수행",
        "MODERATE",
        "5.0",
        "01210 / 3.5 MET / 25–30 W | 01214 / 4.0 MET / 50 W | "
        "01218 / 5.8 MET / 70–80 W | 01220 / 6.0 MET / 90–100 W | "
        "01224 / 6.8 MET / 101–125 W | 01228 / 8.0 MET / 126–150 W | "
        "01232 / 10.3 MET / 151–199 W",
        "01216",
        "Bicycling, stationary, 60 watts, light to moderate effort",
        "CONDITIONAL_MATCH",
        "사용자 확인에 따라 운동명을 stationary bike로 정규화합니다. 출력·저항에 따라 "
        "MET가 달라지므로 60 W를 일반적인 중간 강도 기본조건으로 두고 조건별 선택지를 "
        "함께 제시합니다.",
    ),
    "NEX-000152": rec(
        "정적 또는 느린 척추 회전 스트레칭, 체중만 사용, 가벼운 호흡 중심 수행",
        "LIGHT",
        "2.3",
        "02175 / 2.3 MET / Yoga, general",
        "02101",
        "Stretching, mild",
        "CONDITIONAL_MATCH",
        "척추 트위스트가 스트레칭으로 수행된다는 조건에서 mild stretching과 대응합니다. "
        "동적·고반복 회전이면 재검토해야 합니다.",
    ),
    "NEX-000156": rec(
        "풀업 케이블 머신을 보조로 사용하는 자체 체중 역방향 레그 컬, 통제된 8–15회",
        "MODERATE",
        "3.0",
        "02056 / 3.0 MET / body weight resistance general",
        "02056",
        "Body weight resistance exercises, general",
        "PROVISIONAL_ESTIMATE",
        "직접 대응 항목이 없어 자체 체중 저항운동 일반값을 참고합니다. "
        "케이블 보조량과 반복 속도 확인이 필요합니다.",
    ),
    "NEX-000160": rec(
        "저항 밴드 레그 익스텐션, 8–15회, 세트 간 60–90초, 통제된 중간 템포",
        "MODERATE",
        "3.5",
        "02054 / 3.5 MET / multiple resistance exercises, 8–15 reps",
        "02054",
        "Resistance (weight) training, multiple exercises, 8-15 reps at varied resistance",
        "PROVISIONAL_ESTIMATE",
        "밴드 레그 익스텐션 직접 항목이 없어 8–15회 일반 저항운동을 참고합니다. "
        "밴드 장력과 휴식 조건 확인이 필요합니다.",
    ),
    "NEX-000161": rec(
        "EZ바 풀오버, 8–15회, 세트 간 60–90초, 중량은 통제 가능한 보통 부하",
        "MODERATE",
        "3.5",
        "02054 / 3.5 MET / 8–15회· varied resistance 일반 저항운동의 조건부 대안",
        "02054",
        "Resistance (weight) training, multiple exercises, 8-15 reps at varied resistance",
        "PROVISIONAL_ESTIMATE",
        "EZ바 풀오버 직접 항목은 없으므로 02054를 상위 유형의 참고값으로만 "
        "제안합니다. 실제 부하와 휴식 확인이 필요합니다.",
    ),
    "NEX-000169": rec(
        "평지에서 자기 선택 조깅 속도, 짧은 보폭이지만 속도·지속시간은 별도 확인",
        "VIGOROUS",
        "7.5",
        "12028 / 6.5 MET / 4.0–4.2 mph | 12029 / 7.8 MET / 4.3–4.8 mph | "
        "12030 / 8.5 MET / 5.0–5.2 mph | 12045 / 9.0 MET / 5.5–5.8 mph | "
        "12050 / 9.3 MET / 6.0–6.3 mph",
        "12020",
        "Jogging, general, self-selected pace",
        "CONDITIONAL_MATCH",
        "short stride만으로 속도와 에너지 비용을 결정할 수 없어 자기 선택 조깅을 "
        "조건부 기본값으로 제안합니다. 실제 속도에 따라 선택지를 적용합니다.",
    ),
    "NEX-000170": rec(
        "트레드밀 3.0–3.4 mph 가정, 1–5% 경사, 중간~빠른 걷기, 무부하",
        "MODERATE",
        "5.3",
        "17035 / 7.0 MET / 6–10% grade | 17036 / 8.8 MET / 11–20% grade",
        "17034",
        "Climbing hills, no load, 1 to 5% grade, moderate-to-brisk pace",
        "PROVISIONAL_ESTIMATE",
        "경사 트레드밀 직접 항목 대신 경사 걷기 상위 유형을 사용한 조건부 참고값입니다. "
        "실제 속도·경사도에 따라 선택지를 바꿔야 합니다.",
    ),
    "NEX-000172": rec(
        "4인치 스텝박스, 자기 선택의 중간 속도, 반복적인 오르내리기",
        "MODERATE",
        "5.5",
        "02002 / 7.3 MET / 6–8 inch step | 02003 / 9.0 MET / 10–12 inch step",
        "02001",
        "Aerobic, step, with 4-inch step",
        "CONDITIONAL_MATCH",
        "스텝박스 높이와 속도가 없어 4인치·중간 속도를 기본 조건으로 제안합니다. "
        "높이와 속도 확인 후 선택지를 적용해야 합니다.",
    ),
    "NEX-000173": rec(
        "의자 보조 없음, 이동 없음, 한 발 정적 유지. 한 발 유지시간·반복 횟수·반복 간 "
        "휴식에 따라 총 수행시간과 부담을 조절",
        "LIGHT",
        "2.3",
        "02150 / 2.3 MET / Yoga, Hatha (정적 균형운동 프록시; 직접 대응 아님)",
        "02150",
        "Yoga, Hatha",
        "USER_APPROVED_PROXY",
        "직접 대응하는 한 발 정적 균형 항목은 없으므로 02150 Hatha yoga를 보수적 "
        "프록시로 사용합니다. 이 값은 사용자 승인으로 확정하지만 운동 자체의 직접 "
        "측정값으로 해석하지 않습니다.",
    ),
    "NEX-000180": rec(
        "의자 보조 자체 체중 레그 컬, 통제된 8–15회, 세트 간 60–90초, 외부 중량 없음",
        "MODERATE",
        "3.0",
        "02056 / 3.0 MET / body weight resistance general",
        "02056",
        "Body weight resistance exercises, general",
        "PROVISIONAL_ESTIMATE",
        "의자 보조 레그 컬 직접 항목이 없어 자체 체중 저항운동 일반값을 참고합니다. "
        "보조 정도와 반복 속도 확인이 필요합니다.",
    ),
    "NEX-000191": rec(
        "저항 밴드 레그 컬, 8–15회, 세트 간 60–90초, 통제된 중간 템포",
        "MODERATE",
        "3.5",
        "02054 / 3.5 MET / multiple resistance exercises, 8–15 reps",
        "02054",
        "Resistance (weight) training, multiple exercises, 8-15 reps at varied resistance",
        "PROVISIONAL_ESTIMATE",
        "밴드 레그 컬 직접 항목이 없어 8–15회 일반 저항운동을 참고합니다. "
        "밴드 장력·휴식·반복 속도 확인이 필요합니다.",
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recommendations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_rows = read_recommendations(args.recommendations)
    unresolved = [
        row
        for row in source_rows
        if row.get("recommended_intensity") == "REVIEW_REQUIRED"
        or not row.get("recommended_met", "").strip()
    ]
    missing = {row["exercise_id"] for row in unresolved} - set(CONDITIONALS)
    if missing:
        raise ValueError(f"No conditional recommendation defined for: {sorted(missing)}")
    if len(unresolved) != len(CONDITIONALS):
        raise ValueError(f"Expected {len(CONDITIONALS)} unresolved rows, found {len(unresolved)}")
    output_rows = []
    for source in sorted(unresolved, key=lambda row: row["exercise_id"]):
        proposal = dict(CONDITIONALS[source["exercise_id"]])
        proposal["exercise_id"] = source["exercise_id"]
        proposal["exercise_name"] = (
            "stationary bike" if source["exercise_id"] == "NEX-000143" else source["exercise_name"]
        )
        output_rows.append(proposal)
    write_csv(args.output, output_rows)


if __name__ == "__main__":
    main()
