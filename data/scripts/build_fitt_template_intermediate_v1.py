"""Build the reviewable INTERMEDIATE FITT draft from the BEGINNER template library."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

BEGINNER_PATH = Path(
    "data/generated/exercise-prescriptions-v2.0.2-draft/fitt_template_beginner_v1.csv"
)
OUTPUT_DIR = Path("data/generated/exercise-prescriptions-v2.0.2-draft")
OUTPUT_PATH = OUTPUT_DIR / "fitt_template_intermediate_v1.json"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"

SOURCE_URLS = [
    "https://pubmed.ncbi.nlm.nih.gov/19204579/",
    "https://acsm.org/resistance-training-guidelines-update-2026/",
    "https://odphp.health.gov/sites/default/files/2019-09/Physical_Activity_Guidelines_2nd_edition.pdf",
]


def intermediate_values(row: dict[str, str]) -> dict[str, str]:
    category = row["training_category"]
    values = dict(row)
    values["experience_level_code"] = "INTERMEDIATE"
    values["fitt_template_id"] = row["fitt_template_id"].replace("-V1", "-INTERMEDIATE-V1")

    if category == "COMPOUND_STRENGTH":
        values.update(default_sets="3", min_sets="2", max_sets="3", default_reps="10")
    elif category == "ISOLATION_STRENGTH":
        values.update(default_sets="3", min_sets="2", max_sets="3", default_reps="12")
    elif category == "CORE_DYNAMIC":
        values.update(
            default_sets="3",
            min_sets="2",
            max_sets="3",
            default_reps="12",
            min_reps="10",
            max_reps="15",
        )
    elif category == "CORE_ISOMETRIC":
        values.update(
            default_sets="3",
            min_sets="2",
            max_sets="3",
            default_work_seconds="30",
            min_work_seconds="30",
            max_work_seconds="45",
        )
    elif category == "MOBILITY":
        values.update(default_sets="2", min_sets="2", max_sets="2", default_work_seconds="15")
    elif category == "CARDIO":
        values.update(
            default_work_seconds="1800",
            min_work_seconds="1800",
            max_work_seconds="2700",
        )
    elif category == "POWER":
        values.update(default_sets="3", min_sets="2", max_sets="3")
    elif category == "ISOMETRIC_STRENGTH":
        values.update(default_sets="2", min_sets="2", max_sets="2")
    else:
        raise ValueError(f"Unsupported FITT category: {category}")

    values["fitt_basis"] = (
        f"BEGINNER 대비 {category}의 중급 기본값을 적용하되, 허용 범위는 별도 보존한다. "
        "목표·회복·수행 품질·요청 시간에 따른 최종 선택은 Agent가 결정하며 임상 처방이 아니다."
    )
    return values


def build_document(beginner_rows: list[dict[str, str]]) -> dict[str, object]:
    return {
        "schema_version": "1.1",
        "artifact_version": "fitt-template-intermediate-v1",
        "target_prescription_version": "exercise-prescriptions-v2.0.2-draft",
        "target_catalog_version": "exercise-catalog-v2.0.2-draft",
        "status_code": "DRAFT",
        "review_status_code": "REVIEW_REQUIRED",
        "production_eligible": False,
        "review_required": True,
        "review_reason": "운동 전공 검수 전의 INTERMEDIATE FITT 카탈로그 초안이다.",
        "templates": [intermediate_values(row) for row in beginner_rows],
        "application_notes": {
            "range_and_default_policy": (
                "min/max는 허용 범위이고 default는 Agent가 최초 후보를 만들 때 쓰는 "
                "실제 기본값이다. "
                "클라이언트에는 최종 선택된 단일 값만 표시한다."
            ),
            "equipment_policy": (
                "맨몸은 운동군이 아니다. PUSH·HINGE·ISOLATION 등 운동 특성과 "
                "BODYWEIGHT·KETTLEBELL 등 equipment를 별도 축으로 기록한다."
            ),
            "power_policy": (
                "케틀벨 스윙은 HINGE + POWER로 분리하며 일반 HINGE 8–12회 템플릿을 "
                "자동 상속하지 않는다. "
                "빠른 concentric과 기술 품질을 우선하고 부하·속도는 자동 추천하지 않는다."
            ),
            "core_unit_policy": (
                "Plank류는 SECONDS, Crunch류는 REPS, Dead bug·Bird dog 등 좌우 구분 동작은 "
                "REPS_PER_SIDE를 사용한다."
            ),
            "mobility_policy": (
                "초급·중급 모두 2회·15–30초를 기본으로 하고 ROM과 당일 상태에 따라 조정한다."
            ),
            "goal_adjustment_policy": {
                "FAT_LOSS": (
                    "다이어트가 고반복·저강도를 뜻하지 않는다. 저항운동 강도는 "
                    "근육량 보존을 위해 유지하고, "
                    "필요시 총량·밀도·유산소·주당 빈도와 실행 가능성을 조정한다. "
                    "에너지 적자는 운동 FITT만으로 결정하지 않는다."
                ),
                "MUSCLE_GAIN": (
                    "근육 증량은 무조건 고중량으로 고정하지 않는다. 기본 반복 범위 안에서 "
                    "양질의 세트와 피로 근접도, 주당 근육군별 총량을 우선 조정하며 "
                    "회복·자세·안전 조건을 함께 통과해야 한다."
                ),
            },
        },
        "domain_review_items": [
            "중급 복합·고립·코어·유산소 기본값과 허용 범위 검토",
            "목표별 총량·밀도·유산소 조정 규칙 검토",
        ],
        "completed_domain_review_items": [
            "케틀벨 스윙 POWER 예외의 실제 세트·반복·휴식 검수 완료",
            "벽 짚고 한 팔 광배근 등척성 운동의 유지시간 검수 완료",
        ],
        "sources": [
            {
                "source_id": "REPOSITORY_BEGINNER_FITT",
                "path": str(BEGINNER_PATH),
                "role": "초급 기준",
            },
            {
                "source_id": "ACSM_2009_POSITION_STAND",
                "url": SOURCE_URLS[0],
                "role": "반복·세트·휴식 참고",
            },
            {
                "source_id": "ACSM_2026_POSITION_STAND_SUMMARY",
                "url": SOURCE_URLS[1],
                "role": "세트·파워·개인화 참고",
            },
            {
                "source_id": "HHS_PHYSICAL_ACTIVITY_GUIDELINES",
                "url": SOURCE_URLS[2],
                "role": "유산소·근력 공중보건 참고",
            },
        ],
    }


def main() -> None:
    with BEGINNER_PATH.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))
    if not rows:
        raise ValueError("BEGINNER FITT template is empty")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    document = build_document(rows)
    templates = document["templates"]
    if not isinstance(templates, list):
        raise ValueError("INTERMEDIATE FITT document templates must be a list")
    serialized = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    OUTPUT_PATH.write_text(serialized, encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "prescription_set_version_code": "exercise-prescriptions-v2.0.2-draft",
        "catalog_version_code": "exercise-catalog-v2.0.2-draft",
        "status_code": "DRAFT",
        "review_status_code": "REVIEW_REQUIRED",
        "production_eligible": False,
        "generator_version": "build_fitt_template_intermediate_v1-1.0.0",
        "files": [
            {
                "path": OUTPUT_PATH.name,
                "bytes": len(serialized.encode("utf-8")),
                "sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
                "records": len(templates),
                "role": "intermediate_fitt_template_prescription_draft",
            }
        ],
        "source": {"baseline": str(BEGINNER_PATH), "external_references": SOURCE_URLS},
        "notes": [
            "v2.0.1-final은 변경하지 않는다.",
            "본 산출물은 운동 처방이 아닌 카탈로그 초안이다.",
        ],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
