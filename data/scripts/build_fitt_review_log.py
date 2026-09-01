"""Review the catalog FITT mappings without changing their assigned values."""

from __future__ import annotations

import csv
from pathlib import Path

CATALOG_PATH = Path("data/normalized/catalog_enrichment_v3_fitt.csv")
TEMPLATE_PATH = Path("data/normalized/fitt_template_v1.csv")
OUTPUT_PATH = Path("data/validation/review_results/fitt_review_log.csv")
FIELDNAMES = [
    "exercise_id",
    "exercise_name",
    "assigned_template",
    "review_status",
    "issue_type",
    "review_comment",
]
TEMPLATE_VALUE_COLUMNS = [
    "experience_level_code",
    "prescription_unit",
    "default_sets",
    "min_sets",
    "max_sets",
    "default_reps",
    "min_reps",
    "max_reps",
    "default_work_seconds",
    "min_work_seconds",
    "max_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "default_intensity",
    "fitt_basis",
]
COMPOUND_PATTERNS = {"SQUAT", "HINGE", "LUNGE", "PUSH", "PULL"}
ISOLATION_PATTERNS = {"SQUAT", "HINGE", "PUSH", "PULL", "CARRY", "ISOLATION"}


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as input_file:
        return list(csv.DictReader(input_file))


def template_pattern_is_compatible(row: dict[str, str], template: dict[str, str]) -> bool:
    pattern = row["suggested_movement_pattern"]
    category = template["training_category"]
    return (
        (category == "COMPOUND_STRENGTH" and pattern in COMPOUND_PATTERNS)
        or (category == "ISOLATION_STRENGTH" and pattern in ISOLATION_PATTERNS)
        or (category == "ISOMETRIC_STRENGTH" and pattern == "PUSH")
        or (category == "POWER" and pattern == "HINGE")
        or (category in {"CORE_DYNAMIC", "CORE_ISOMETRIC"} and pattern == "CORE")
        or (category == "MOBILITY" and pattern == "MOBILITY")
        or (category == "CARDIO" and pattern == "CARDIO")
    )


def review_row(row: dict[str, str], template_by_id: dict[str, dict[str, str]]) -> dict[str, str]:
    issues: list[str] = []
    comments: list[str] = []
    template_id = row["fitt_template_id"]
    template = template_by_id.get(template_id)

    if template is None:
        issues.append("MISSING_TEMPLATE")
        comments.append("참조한 FITT 템플릿이 존재하지 않습니다.")
    else:
        if not template_pattern_is_compatible(row, template):
            issues.append("TEMPLATE_PATTERN_MISMATCH")
            comments.append("movement_pattern과 템플릿 카테고리의 호환성을 재검토해야 합니다.")
        if any(row[column] != template[column] for column in TEMPLATE_VALUE_COLUMNS):
            issues.append("FITT_VALUE_MISMATCH")
            comments.append("카탈로그 기본값이 참조 템플릿의 값과 일치하지 않습니다.")

    exception_code = row["fitt_mapping_exception_code"]
    if exception_code != "NONE":
        issues.append(exception_code)
        comments.append(row["fitt_mapping_note"])

    if not row["difficulty_code"]:
        issues.append("DIFFICULTY_MISSING")
        comments.append("난이도 정보가 없어 현재 기본 강도의 입문자 적합성을 확정할 수 없습니다.")

    if not issues:
        comments.append(
            "패턴·템플릿·기본값이 일치하며, 입문~중급 일반 성인용 보수적 기본값 범위입니다."
        )

    return {
        "exercise_id": row["exercise_id"],
        "exercise_name": row["exercise_name_ko"],
        "assigned_template": template_id,
        "review_status": "REVIEW_REQUIRED" if issues else "PASS",
        "issue_type": "|".join(issues) if issues else "NONE",
        "review_comment": " ".join(comments),
    }


def main() -> None:
    catalog_rows = load_rows(CATALOG_PATH)
    template_rows = load_rows(TEMPLATE_PATH)
    template_by_id = {row["fitt_template_id"]: row for row in template_rows}
    if len(template_by_id) != len(template_rows):
        raise ValueError("FITT template IDs must be unique")

    review_rows = [review_row(row, template_by_id) for row in catalog_rows]
    if len(review_rows) != len(catalog_rows):
        raise ValueError("Every catalog exercise must produce one FITT review row")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(review_rows)


if __name__ == "__main__":
    main()
