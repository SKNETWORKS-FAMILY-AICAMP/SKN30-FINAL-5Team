"""Map reviewed movement patterns to conservative catalog FITT defaults.

The output retains the enrichment-v2 fields and appends a template reference
plus default FITT values. It is a DRAFT catalog artifact, not a clinical plan.
"""

from __future__ import annotations

import csv
from pathlib import Path

CATALOG_PATH = Path("data/normalized/catalog_enrichment_v2.csv")
PATTERN_REVIEW_PATH = Path("data/validation/review_results/movement_pattern_review.csv")
TEMPLATE_PATH = Path("data/normalized/fitt_template_v1.csv")
INTEGRATED_CATALOG_PATH = Path("data/reports/integrated_exercise_review_updated.csv")
OUTPUT_PATH = Path("data/normalized/catalog_enrichment_v3_fitt.csv")

FITT_COLUMNS = [
    "fitt_template_id",
    "default_sets",
    "default_reps",
    "default_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "default_intensity",
    "fitt_basis",
]
EXCEPTION_COLUMNS = ["fitt_mapping_exception_code", "fitt_mapping_note"]
COMPOUND_TEMPLATE_BY_PATTERN = {
    "SQUAT": "FITT-COMPOUND-SQUAT-V1",
    "HINGE": "FITT-COMPOUND-HINGE-V1",
    "LUNGE": "FITT-COMPOUND-LUNGE-V1",
    "PUSH": "FITT-COMPOUND-PUSH-V1",
    "PULL": "FITT-COMPOUND-PULL-V1",
}
DIRECT_TEMPLATE_BY_PATTERN = {
    "CORE": "FITT-CORE-STABILITY-V1",
    "MOBILITY": "FITT-MOBILITY-V1",
    "CARDIO": "FITT-CARDIO-V1",
}
TIMING_MODE_BY_TRAINING_CATEGORY = {
    "COMPOUND_STRENGTH": "REPS",
    "ISOLATION_STRENGTH": "REPS",
    "BODYWEIGHT_BEGINNER": "REPS",
    "CORE_STABILITY": "DURATION",
    "MOBILITY": "DURATION",
    "CARDIO": "DURATION",
}

# The source does not expose an equipment or joint-count field. These IDs are
# explicit exercise-characteristic decisions so the inferred categories remain
# auditable instead of being copied from body-focus codes.
ISOLATION_EXERCISE_IDS = {
    "NEX-000002",
    "NEX-000003",
    "NEX-000004",
    "NEX-000005",
    "NEX-000006",
    "NEX-000007",
    "NEX-000008",
    "NEX-000010",
    "NEX-000012",
    "NEX-000016",
    "NEX-000017",
    "NEX-000018",
    "NEX-000019",
    "NEX-000021",
    "NEX-000025",
    "NEX-000026",
    "NEX-000033",
    "NEX-000034",
    "NEX-000035",
    "NEX-000036",
    "NEX-000037",
    "NEX-000038",
    "NEX-000039",
    "NEX-000040",
    "NEX-000042",
    "NEX-000045",
    "NEX-000046",
    "NEX-000047",
    "NEX-000048",
    "NEX-000049",
    "NEX-000050",
    "NEX-000052",
    "NEX-000053",
    "NEX-000054",
    "NEX-000057",
    "NEX-000058",
    "NEX-000059",
    "NEX-000060",
    "NEX-000065",
    "NEX-000069",
    "NEX-000070",
    "NEX-000071",
    "NEX-000081",
    "NEX-000082",
    "NEX-000085",
    "NEX-000087",
    "NEX-000092",
    "NEX-000097",
    "NEX-000098",
    "NEX-000100",
    "NEX-000102",
    "NEX-000103",
    "NEX-000105",
    "NEX-000106",
    "NEX-000109",
    "NEX-000117",
    "NEX-000120",
    "NEX-000121",
    "NEX-000122",
    "NEX-000140",
    "NEX-000141",
    "NEX-000148",
    "NEX-000149",
    "NEX-000153",
    "NEX-000156",
    "NEX-000160",
    "NEX-000161",
    "NEX-000166",
    "NEX-000175",
    "NEX-000176",
    "NEX-000178",
    "NEX-000180",
    "NEX-000181",
    "NEX-000188",
    "NEX-000191",
    "NEX-000202",
    "NEX-000203",
}
BEGINNER_BODYWEIGHT_EXERCISE_IDS = {
    "NEX-000074",  # Push-up
    "NEX-000118",  # Bodyweight standing calf raise
    "NEX-000162",  # Floor glute bridge
    "NEX-000174",  # Chair-supported forward knee raise
    "NEX-000180",  # Chair-supported rear knee curl
    "NEX-000181",  # Seated hip flexion
}


def load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)
        return list(reader), list(reader.fieldnames or [])


def choose_template(exercise_id: str, pattern: str) -> tuple[str, str, str]:
    """Return template ID, exception code, and an auditable mapping note."""
    if pattern in DIRECT_TEMPLATE_BY_PATTERN:
        return DIRECT_TEMPLATE_BY_PATTERN[pattern], "NONE", "패턴 전용 FITT 템플릿 적용."

    if exercise_id in BEGINNER_BODYWEIGHT_EXERCISE_IDS:
        return (
            "FITT-BODYWEIGHT-BEGINNER-V1",
            "NONE",
            "초급 맨몸 운동 특성으로 BODYWEIGHT_BEGINNER 템플릿 적용.",
        )

    if exercise_id in ISOLATION_EXERCISE_IDS:
        return (
            "FITT-ISOLATION-STRENGTH-V1",
            "NONE",
            "단일관절 또는 고립 저항운동 특성으로 ISOLATION_STRENGTH 템플릿 적용.",
        )

    if pattern in COMPOUND_TEMPLATE_BY_PATTERN:
        return (
            COMPOUND_TEMPLATE_BY_PATTERN[pattern],
            "NONE",
            "다관절 저항운동 패턴 전용 복합 템플릿 적용.",
        )

    raise ValueError(f"No FITT template mapping for exercise_id={exercise_id}, pattern={pattern}")


def validate_mapping(
    output_rows: list[dict[str, str]], template_by_id: dict[str, dict[str, str]]
) -> None:
    if not output_rows or any(not row["fitt_template_id"] for row in output_rows):
        raise ValueError("Every exercise must have exactly one FITT template")

    for row in output_rows:
        template_id = row["fitt_template_id"]
        pattern = row["suggested_movement_pattern"]
        category = template_by_id[template_id]["training_category"]
        compatible = (
            (category == "COMPOUND_STRENGTH" and pattern in COMPOUND_TEMPLATE_BY_PATTERN)
            or (
                category == "ISOLATION_STRENGTH"
                and pattern in {"SQUAT", "HINGE", "PUSH", "PULL", "CARRY"}
            )
            or (
                category == "BODYWEIGHT_BEGINNER"
                and pattern in {"SQUAT", "HINGE", "PUSH", "PULL", "LUNGE"}
            )
            or (category == "CORE_STABILITY" and pattern == "CORE")
            or (category == "MOBILITY" and pattern == "MOBILITY")
            or (category == "CARDIO" and pattern == "CARDIO")
        )
        if not compatible:
            raise ValueError(
                "Movement-pattern/template mismatch: "
                f"exercise_id={row['exercise_id']}, pattern={pattern}, template_id={template_id}"
            )


def enrich_row(
    catalog_row: dict[str, str],
    review_row: dict[str, str],
    template_by_id: dict[str, dict[str, str]],
    name_en: str,
) -> dict[str, str]:
    """Apply an auditable FITT template to one catalog row."""
    exercise_id = catalog_row["exercise_id"]
    pattern = review_row["suggested_movement_pattern"]
    template_id, exception_code, note = choose_template(exercise_id, pattern)
    template = template_by_id.get(template_id)
    if template is None:
        raise ValueError(f"Referenced FITT template does not exist: {template_id}")
    category = template["training_category"]
    try:
        timing_mode = TIMING_MODE_BY_TRAINING_CATEGORY[category]
    except KeyError as exc:
        raise ValueError(f"FITT template has no timing mode: {template_id}") from exc

    return {
        **catalog_row,
        "name_en": name_en,
        "timing_mode_code": timing_mode,
        **{column: template[column] for column in FITT_COLUMNS[1:]},
        "intensity_level": template["default_intensity"],
        "fitt_status": "APPROVED",
        "fitt_template_id": template_id,
        "fitt_mapping_exception_code": exception_code,
        "fitt_mapping_note": note,
        "suggested_movement_pattern": pattern,
        "current_training_type": review_row["current_training_type"],
    }


def main() -> None:
    catalog_rows, catalog_fields = load_rows(CATALOG_PATH)
    review_rows, _ = load_rows(PATTERN_REVIEW_PATH)
    template_rows, _ = load_rows(TEMPLATE_PATH)
    integrated_rows, _ = load_rows(INTEGRATED_CATALOG_PATH)

    review_by_id = {row["exercise_id"]: row for row in review_rows}
    template_by_id = {row["fitt_template_id"]: row for row in template_rows}
    name_en_by_id = {
        row["normalized_exercise_id"]: row.get("name_en", "").strip()
        or row.get("source_name", "").strip()
        for row in integrated_rows
    }
    catalog_ids = {row["exercise_id"] for row in catalog_rows}
    if catalog_ids != set(review_by_id):
        raise ValueError("Catalog and movement-pattern review exercise IDs must exactly match")
    if len(template_by_id) != len(template_rows):
        raise ValueError("FITT template IDs must be unique")
    if catalog_ids != set(name_en_by_id) or any(not name_en_by_id[item] for item in catalog_ids):
        raise ValueError("Catalog and integrated English names must exactly match and be non-empty")

    output_rows = []
    for catalog_row in catalog_rows:
        exercise_id = catalog_row["exercise_id"]
        review_row = review_by_id[exercise_id]
        output_rows.append(
            enrich_row(catalog_row, review_row, template_by_id, name_en_by_id[exercise_id])
        )

    validate_mapping(output_rows, template_by_id)
    output_fields = (
        catalog_fields
        + [field for field in ("name_en",) if field not in catalog_fields]
        + [column for column in FITT_COLUMNS if column not in catalog_fields]
        + EXCEPTION_COLUMNS
        + [
            "suggested_movement_pattern",
            "current_training_type",
        ]
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(output_rows)


if __name__ == "__main__":
    main()
