"""Generate the integrated catalog data dictionary from the schema columns."""

# Markdown descriptions are intentionally kept readable in the generated dictionary.
# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path

from build_integrated_exercise_review import OUTPUT_COLUMNS

DATA_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = DATA_ROOT / "normalized" / "integrated_catalog_data_dictionary-v1.0.0.md"

DESCRIPTIONS = {
    "catalog_id": "카탈로그 레코드의 영구 불변 ID. registry에서 발급.",
    "normalized_exercise_id": "동일 운동으로 확정된 출처 레코드를 묶는 영구 표준 운동 ID.",
    "source_system": "원천 시스템 코드: gymvisual, wger, kspo.",
    "source_id": "원천 시스템의 기존 ID를 문자열 그대로 보존한 값.",
    "legacy_review_normalized_exercise_id": "기존 review_normalized_exercise_id 값. 새 표준 ID로 이관하면서 raw와 alias에도 보존.",
    "name_en": "영문 원천명. 영문 원천이 없으면 비워 두고 source_name을 사용.",
    "name_ko": "최종 한국어명. reviewed_name_ko를 이관하며 미검토 시 REVIEW_REQUIRED.",
    "duplicate_candidate_group_id": "동일 운동 의심 출처를 묶는 후보 그룹 ID. 확정 병합을 뜻하지 않음.",
    "duplicate_review_status": "중복 후보 검토 상태.",
    "duplicate_review_note": "중복 판정 및 병합 시 주의사항.",
    "review_required": "review_required_codes가 하나 이상이면 true인 파생 상태.",
    "review_required_codes": "남은 사람 검토 코드의 파이프 구분 목록. 비어 있을 때만 review_required=false.",
    "reviewer": "최종 검토자 비식별 참조. 없으면 결측 상태로 보존.",
    "reviewed_at": "최종 검토 시각(ISO 8601 timezone). 없으면 결측 상태로 보존.",
    "review_status": "DRAFT, INCLUSION_APPROVED, PARTIALLY_APPROVED, FINAL_APPROVED 등 검토 단계.",
    "review_status_interpretation": "현재 상태가 전체 승인인지 후보 포함 승인인지 설명하는 값.",
    "reviewed_decision": "검토자가 기록한 INCLUDE/REJECT 등 결정. INCLUDE만으로 최종 승인 아님.",
    "production_eligible": "분류·검토·안전·권리·미디어 게이트를 모두 통과한 경우에만 true.",
    "production_eligibility_blockers": "운영 배포를 막는 자동 검증 사유의 파이프 구분 목록.",
    "setup_guide": "사용자 노출 전 검토할 준비 자세 안내.",
    "execution_steps": "번호가 있는 실행 단계 목록. CSV에서는 JSON 문자열로 저장.",
    "breathing_guide": "호흡 안내. 근거·사람 검토 전에는 REVIEW_REQUIRED.",
    "finish_guide": "종료·복귀 자세 안내.",
    "guide_source_url": "가이드 근거 원천 URL.",
    "guide_review_status": "가이드 검토 상태. APPROVED 전 운영 노출 불가.",
    "guide_review_note": "가이드 근거의 범위와 남은 검토 사항.",
    "safety_warning": "운동별 핵심 주의사항.",
    "contraindications": "근거가 확인된 의료적 금기만 기재. 미확정이면 REVIEW_REQUIRED.",
    "common_mistakes": "관절 정렬·중립·반동·가동범위·장비 고정 관련 흔한 오류.",
    "stop_conditions": "통증·어지럼증·흉통·비정상 호흡곤란 등 즉시 중단 조건.",
    "safety_source_url": "안전 정보 근거 URL.",
    "safety_review_status": "안전 검토 상태. APPROVED 전 운영 배포 불가.",
    "source_url": "원천 데이터셋 또는 API URL.",
    "source_author": "원천 제공자·저작자.",
    "license_id": "정규화된 라이선스 통제 코드.",
    "license_name": "라이선스 정식명.",
    "license_version": "라이선스 버전.",
    "license_url": "라이선스 전문 URL.",
    "is_modified": "통합 과정에서 식별자·통제어휘·검토 필드를 추가했는지.",
    "modification_note": "원천 대비 변환·요약·필드 추가 내역.",
    "accessed_at": "원천 접근·수집 시각. 확인되지 않으면 REVIEW_REQUIRED.",
    "metadata_license_id": "메타데이터 권리 범위의 라이선스 코드.",
    "instruction_license_id": "동작 설명·지침 권리 범위의 라이선스 코드.",
    "image_license_id": "이미지 권리 범위의 라이선스 코드.",
    "gif_video_license_id": "GIF·영상 권리 범위의 라이선스 코드.",
    "attribution_text": "배포 시 사용할 출처·저작자 표시.",
    "license_review_status": "권리 범위 검토 상태.",
    "media_link_status": "미디어 실물 연결 상태. 이번 파이프라인은 PENDING_POST_INTEGRATION_VALIDATION.",
    "media_link_note": "미디어 후속 작업 안내.",
    "media_validation_status": "미디어 파일·경로·권리 검증 상태.",
    "media_source_reference": "원천 상대경로, 파일명·프레임 수, 이미지·영상 개수 등 참조값.",
    "raw_source_record_json": "변환 입력 원천 레코드 전체를 JSON으로 보존한 값.",
    "raw_review_required": "변환 전 review_required 원천값.",
    "raw_review_required_codes": "변환 전 review_required_codes 원천값.",
    "raw_review_status": "변환 전 review_status 원천값.",
    "raw_review_decision": "변환 전 review_decision 원천값.",
    "raw_reviewed_decision": "변환 전 reviewed_decision 원천값.",
    "raw_review_normalized_exercise_id": "변환 전 review_normalized_exercise_id 원천값.",
    "raw_source_attribution": "변환 전 source_attribution 원천값.",
    "raw_source_license": "변환 전 source_license 원천값.",
    "raw_source_license_author": "변환 전 source_license_author 원천값.",
    "raw_source_media_reference": "변환 전 source_media_reference 원천값.",
    "raw_source_instruction_en": "Gymvisual 원천 영어 instruction 원문.",
    "raw_source_instruction_steps_en": "Gymvisual 원천 영어 단계 목록 JSON.",
}


def fallback_description(column: str) -> str:
    if column.startswith("source_"):
        return "원천·정렬 배치에서 복사한 값. 원천명·분류·미디어·라이선스 입력을 보존."
    if column.startswith("reviewed_"):
        return "사람 검토 결과 입력값. 미확정이면 빈 값 또는 REVIEW_REQUIRED."
    if column.endswith("_candidate") or column.endswith("_candidates"):
        return "자동 변환 또는 원천에서 얻은 검토 후보값이며 최종 승인값이 아님."
    if column.endswith("_status"):
        return "해당 대상의 검토·검증 상태 코드."
    return "통합 검토 배치의 기존 호환 필드. 원천 또는 검토 배치 정의를 따른다."


def main() -> None:
    lines = [
        "# 통합 운동 카탈로그 데이터 사전",
        "",
        "스키마 버전: `integrated-catalog-schema-v1.0.0`",
        "",
        "모든 CSV 값은 문자열이다. `REVIEW_REQUIRED`는 미확정 sentinel이며 사용자 노출용 값이 아니다.",
        "`DOMAIN_APPROVED` 원천값은 `INCLUSION_APPROVED`로 해석하고, 최종 승인에는 reviewer와 reviewed_at가 필요하다.",
        "",
        "## 컬럼",
        "",
        "| 컬럼 | 의미 |",
        "|---|---|",
    ]
    for column in OUTPUT_COLUMNS:
        lines.append(f"| `{column}` | {DESCRIPTIONS.get(column, fallback_description(column))} |")
    lines.extend(
        [
            "",
            "## 통제 상태",
            "",
            "| 상태 | 의미 |",
            "|---|---|",
            "| `DRAFT` | 검토 대기 또는 원천 후보. 운영 사용 불가 |",
            "| `INCLUSION_APPROVED` | 통합 카탈로그 후보 포함 승인. 전체 승인 아님 |",
            "| `PARTIALLY_APPROVED` | 일부 검토만 승인. 미해결 코드는 운영 차단 |",
            "| `FINAL_APPROVED` | 필수 분류·안전·가이드·권리·미디어 검토 완료 |",
            "| `PENDING_POST_INTEGRATION_VALIDATION` | 통합 검증 후 미디어 실물 연결 대기 |",
            "",
            "## 영구 ID",
            "",
            "`catalog_id`는 카탈로그 행, `normalized_exercise_id`는 확인된 동일 운동 그룹의 ID다. 둘 다 이름·분류 변경으로 재발급하지 않는다. registry 키는 `source_system + source_id`이며 source_id의 0-padding·해시 형식을 바꾸지 않는다.",
        ]
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
