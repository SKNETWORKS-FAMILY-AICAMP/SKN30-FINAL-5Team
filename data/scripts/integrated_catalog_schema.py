"""Schema and controlled vocabulary for the integrated review catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = DATA_ROOT / "normalized" / "integrated_catalog_schema-v1.0.0.json"
SCHEMA_VERSION = "integrated-catalog-schema-v1.0.0"

IDENTIFIER_COLUMNS = (
    "catalog_id",
    "normalized_exercise_id",
    "source_system",
    "source_id",
)
NAME_COLUMNS = ("name_en", "name_ko")
DEDUP_COLUMNS = (
    "duplicate_candidate_group_id",
    "duplicate_review_status",
    "duplicate_review_note",
)
LEGACY_COLUMNS = ("legacy_review_normalized_exercise_id",)
REVIEW_COLUMNS = (
    "review_required",
    "review_required_codes",
    "reviewer",
    "reviewed_at",
    "review_status",
    "review_status_interpretation",
    "reviewed_decision",
    "production_eligible",
    "production_eligibility_blockers",
)
GUIDE_COLUMNS = (
    "setup_guide",
    "execution_steps",
    "breathing_guide",
    "finish_guide",
    "guide_source_url",
    "guide_review_status",
    "guide_review_note",
)
SAFETY_COLUMNS = (
    "safety_warning",
    "contraindications",
    "common_mistakes",
    "stop_conditions",
    "safety_source_url",
    "safety_review_status",
)
PROVENANCE_COLUMNS = (
    "source_url",
    "source_author",
    "license_id",
    "license_name",
    "license_version",
    "license_url",
    "is_modified",
    "modification_note",
    "accessed_at",
    "metadata_license_id",
    "instruction_license_id",
    "image_license_id",
    "gif_video_license_id",
    "attribution_text",
    "license_review_status",
)
MEDIA_COLUMNS = (
    "media_link_status",
    "media_link_note",
    "media_validation_status",
    "media_source_reference",
)
RAW_COLUMNS = (
    "raw_source_record_json",
    "raw_review_required",
    "raw_review_required_codes",
    "raw_review_status",
    "raw_review_decision",
    "raw_reviewed_decision",
    "raw_review_normalized_exercise_id",
    "raw_source_attribution",
    "raw_source_license",
    "raw_source_license_author",
    "raw_source_media_reference",
    "raw_source_instruction_en",
    "raw_source_instruction_steps_en",
)
DEDUP_COLUMNS = (
    "duplicate_candidate_group_id",
    "duplicate_review_status",
    "duplicate_review_note",
)
NAME_COLUMNS = ("name_en", "name_ko")
LEGACY_COLUMNS = ("legacy_review_normalized_exercise_id",)

REVIEW_STATUS_CODES = (
    "DRAFT",
    "INCLUSION_APPROVED",
    "PARTIALLY_APPROVED",
    "FINAL_APPROVED",
    "REJECTED",
    "DEPRECATED",
)
REVIEW_STATUS_INTERPRETATIONS = {
    "DRAFT": "검토 대기 또는 원천 후보 상태. 운영 사용 불가.",
    "INCLUSION_APPROVED": "통합 카탈로그 후보로 포함 승인. 전체 분류·안전·권리·미디어 승인이 아님.",
    "PARTIALLY_APPROVED": "일부 영역만 승인. 미해결 검토 코드가 있으면 운영 사용 불가.",
    "FINAL_APPROVED": "필수 분류·안전·가이드·출처·라이선스·미디어 검토를 완료한 최종 승인.",
    "REJECTED": "카탈로그에서 제외.",
    "DEPRECATED": "이력 보존용 비활성 상태.",
}

LICENSES: dict[str, dict[str, str]] = {
    "MIT": {
        "name": "MIT License",
        "version": "",
        "url": "https://opensource.org/license/mit/",
    },
    "CC-BY-SA 4": {
        "name": "Creative Commons Attribution-ShareAlike 4.0 International",
        "version": "4.0",
        "url": "https://creativecommons.org/licenses/by-sa/4.0/",
    },
    "CC-BY-SA 3": {
        "name": "Creative Commons Attribution-ShareAlike 3.0",
        "version": "3.0",
        "url": "https://creativecommons.org/licenses/by-sa/3.0/",
    },
    "CC0": {
        "name": "CC0 1.0 Universal",
        "version": "1.0",
        "url": "https://creativecommons.org/publicdomain/zero/1.0/",
    },
    "KOGL_TYPE_1": {
        "name": "공공누리 제1유형",
        "version": "1",
        "url": "https://www.kogl.or.kr/info/license.do",
    },
}


def schema_document(columns: list[str]) -> dict[str, Any]:
    required = [
        *IDENTIFIER_COLUMNS,
        *NAME_COLUMNS,
        *DEDUP_COLUMNS,
        *LEGACY_COLUMNS,
        *REVIEW_COLUMNS,
        *GUIDE_COLUMNS,
        *SAFETY_COLUMNS,
        *PROVENANCE_COLUMNS,
        *MEDIA_COLUMNS,
        *RAW_COLUMNS,
    ]
    properties: dict[str, Any] = {column: {"type": "string"} for column in columns}
    for column in ("is_modified",):
        properties[column] = {"type": "string", "enum": ["true", "false"]}
    for column in ("source_system",):
        properties[column] = {"type": "string", "enum": ["gymvisual", "wger", "kspo"]}
    properties["review_status"] = {"type": "string", "enum": list(REVIEW_STATUS_CODES)}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_VERSION,
        "title": "Integrated Exercise Review Catalog Row",
        "description": "CSV row schema; all values are serialized as strings.",
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": False,
        "x-controlled-vocabularies": {
            "review_status": REVIEW_STATUS_INTERPRETATIONS,
            "license_id": sorted(LICENSES),
            "pending_sentinel": "REVIEW_REQUIRED",
            "media_link_status": "PENDING_POST_INTEGRATION_VALIDATION",
        },
    }


def write_schema(columns: list[str], path: Path = SCHEMA_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(schema_document(columns), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
