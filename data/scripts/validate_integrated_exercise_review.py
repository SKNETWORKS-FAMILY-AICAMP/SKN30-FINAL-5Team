"""Fail-closed structural validation for the integrated exercise review catalog."""

# Report prose is intentionally kept as readable Korean sentences.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import cast

from build_integrated_exercise_review import (
    BODYWEIGHT_SUBSTITUTABLE_VARIANT_IDS,
    GYMVISUAL_CARDIO,
    GYMVISUAL_MOBILITY,
    GYMVISUAL_STRENGTH,
    GYMVISUAL_VARIANTS,
    KSPO,
    OUTPUT_ALIASES,
    OUTPUT_COLUMNS,
    OUTPUT_CSV,
    WGER_ATTRS,
    build,
    load_csv,
    validate_variant_references,
)
from integrated_catalog_registry import REGISTRY_PATH, load_registry
from integrated_catalog_schema import REVIEW_STATUS_CODES, SCHEMA_PATH

DATA_ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = DATA_ROOT / "reports" / "integrated_catalog_validation-v0.5.0.json"
REPORT_MD = DATA_ROOT / "reports" / "INTEGRATED_CATALOG_VALIDATION_v0.5.0.md"
HUMAN_REVIEW_CSV = DATA_ROOT / "reports" / "integrated_catalog_human_review_items.csv"


def normalized_text(value: str) -> str:
    return "".join(value.casefold().split())


def source_inventory() -> set[tuple[str, str]]:
    inventory: set[tuple[str, str]] = set()
    for path in (GYMVISUAL_CARDIO, GYMVISUAL_STRENGTH):
        for row in load_csv(path):
            if path == GYMVISUAL_STRENGTH and row.get("screening_decision") != "INCLUDE":
                continue
            inventory.add(("gymvisual", row["candidate_id"]))
    for row in load_csv(GYMVISUAL_VARIANTS):
        if row.get("variant_candidate_id") not in BODYWEIGHT_SUBSTITUTABLE_VARIANT_IDS:
            inventory.add(("gymvisual", row["variant_candidate_id"]))
    inventory.update(("gymvisual", row["candidate_id"]) for row in load_csv(GYMVISUAL_MOBILITY))
    inventory.update(("kspo", row["source_identity"]) for row in load_csv(KSPO))
    inventory.update(("wger", row["source_identity"]) for row in load_csv(WGER_ATTRS))
    return inventory


def validate(output_path: Path = OUTPUT_CSV) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    rows = load_csv(output_path)
    generated_rows = build()
    generated_keys = {(row["source_system"], row["source_id"]) for row in generated_rows}
    expected_keys = source_inventory()
    actual_keys = {(row.get("source_system", ""), row.get("source_id", "")) for row in rows}

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_columns = set(schema["properties"])
    if set(OUTPUT_COLUMNS) != schema_columns:
        errors.append("schema properties and generator output columns differ")
    if set(rows[0]) != set(OUTPUT_COLUMNS) if rows else True:
        errors.append("CSV header does not match the generated schema")
    if len(rows) != len(expected_keys):
        errors.append(f"source row count mismatch: expected {len(expected_keys)}, got {len(rows)}")
    if actual_keys != expected_keys:
        errors.append("source key inventory differs from the current source inputs")
    if actual_keys != generated_keys:
        errors.append("CSV keys differ from the generator result")

    catalog_ids = [row.get("catalog_id", "") for row in rows]
    if not all(catalog_ids) or len(catalog_ids) != len(set(catalog_ids)):
        errors.append("catalog_id is missing or duplicated")
    source_keys = [f"{row.get('source_system')}:{row.get('source_id')}" for row in rows]
    if not all(row.get("source_id", "") for row in rows) or len(source_keys) != len(
        set(source_keys)
    ):
        errors.append("source_system + source_id is missing or duplicated")
    normalized_ids = [row.get("normalized_exercise_id", "") for row in rows]
    if not all(normalized_ids):
        errors.append("normalized_exercise_id is missing")

    registry = load_registry(REGISTRY_PATH)
    registry_reuse = True
    for row in rows:
        key = (row["source_system"], row["source_id"])
        assignment = registry.get(key)
        if assignment is None or any(
            row[field] != assignment[field] for field in ("catalog_id", "normalized_exercise_id")
        ):
            registry_reuse = False
            errors.append(f"registry assignment mismatch: {key}")
    if not registry_reuse:
        errors.append("permanent ID registry was not reused")

    review_required_mismatches: list[str] = []
    final_approval_issues: list[str] = []
    production_blockers: Counter[str] = Counter()
    human_items: list[dict[str, str]] = []
    for row in rows:
        row_key = f"{row['source_system']}:{row['source_id']}"
        codes = [code for code in row["review_required_codes"].split("|") if code]
        expected_required = "true" if codes else "false"
        if row["review_required"] != expected_required:
            review_required_mismatches.append(row_key)
        if row["review_status"] not in REVIEW_STATUS_CODES:
            errors.append(f"unknown review status: {row_key}:{row['review_status']}")
        if row["review_status"] == "FINAL_APPROVED" and (
            not row["reviewer"] or not row["reviewed_at"]
        ):
            final_approval_issues.append(row_key)
        if row["production_eligible"] == "true" and row["production_eligibility_blockers"]:
            errors.append(f"production eligible row has blockers: {row_key}")
        for blocker in [item for item in row["production_eligibility_blockers"].split("|") if item]:
            production_blockers[blocker] += 1
        if row["production_eligibility_blockers"]:
            human_items.append(
                {
                    "source_system": row["source_system"],
                    "source_id": row["source_id"],
                    "catalog_id": row["catalog_id"],
                    "normalized_exercise_id": row["normalized_exercise_id"],
                    "source_name": row["source_name"],
                    "review_status": row["review_status"],
                    "review_required_codes": row["review_required_codes"],
                    "production_eligibility_blockers": row["production_eligibility_blockers"],
                    "duplicate_candidate_group_id": row["duplicate_candidate_group_id"],
                }
            )
        if not row["source_attribution"]:
            errors.append(f"source attribution missing: {row_key}")
        for field in (
            "source_url",
            "source_author",
            "license_id",
            "license_name",
            "license_version",
            "license_url",
            "attribution_text",
            "license_review_status",
        ):
            if not row[field]:
                errors.append(f"provenance field missing: {row_key}:{field}")
        if row["media_link_status"] != "PENDING_POST_INTEGRATION_VALIDATION":
            errors.append(f"media link status missing: {row_key}")
        if not row["raw_source_record_json"]:
            errors.append(f"raw source record missing: {row_key}")
        try:
            json.loads(row["raw_source_record_json"])
        except json.JSONDecodeError:
            errors.append(f"raw source record is invalid JSON: {row_key}")

    if review_required_mismatches:
        errors.append(f"review_required mismatch for {len(review_required_mismatches)} rows")
    if final_approval_issues:
        errors.append(
            f"final approval missing reviewer/reviewed_at for {len(final_approval_issues)} rows"
        )

    try:
        validate_variant_references(rows)
    except ValueError as exc:
        errors.append(str(exc))

    by_name: defaultdict[str, set[str]] = defaultdict(set)
    by_source_name: defaultdict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["name_ko"] != "REVIEW_REQUIRED":
            by_name[normalized_text(row["name_ko"])].add(row["normalized_exercise_id"])
        by_source_name[normalized_text(row["source_name"])].add(
            f"{row['source_system']}:{row['source_id']}"
        )
    normalized_name_duplicates = {
        name: sorted(ids) for name, ids in by_name.items() if len(ids) > 1
    }
    exact_source_name_duplicates = {
        name: sorted(keys) for name, keys in by_source_name.items() if name and len(keys) > 1
    }
    if normalized_name_duplicates:
        warnings.append("same normalized Korean name maps to multiple normalized IDs")
    if exact_source_name_duplicates:
        warnings.append("same raw source name appears under multiple source keys")

    alias_rows = load_csv(OUTPUT_ALIASES)
    alias_ids = {row["normalized_exercise_id"] for row in alias_rows}
    broken_aliases = sorted(alias_ids - set(normalized_ids))
    if broken_aliases:
        errors.append(f"alias rows reference missing normalized IDs: {broken_aliases}")

    auto_fixed = {
        "permanent_ids_assigned_or_reused": len(rows),
        "review_required_derived_from_codes": len(rows),
        "legacy_domain_approved_mapped_to_inclusion_approved": sum(
            row["raw_review_status"] == "DOMAIN_APPROVED"
            and row["review_status"] == "INCLUSION_APPROVED"
            for row in rows
        ),
        "source_attribution_normalized": sum(bool(row["source_attribution"]) for row in rows),
        "media_pending_status_explicit": sum(
            row["media_link_status"] == "PENDING_POST_INTEGRATION_VALIDATION" for row in rows
        ),
    }
    return {
        "schema_version": "integrated-catalog-schema-v1.0.0",
        "validation_version": "integrated-catalog-validation-v0.5.0",
        "validation_status": "FAIL" if errors else "PASS_WITH_PRODUCTION_BLOCKERS",
        "output": str(output_path.relative_to(DATA_ROOT.parent)),
        "row_count": len(rows),
        "source_key_count": len(actual_keys),
        "registry_reused": registry_reuse,
        "errors": errors,
        "warnings": warnings,
        "production_blockers": dict(production_blockers),
        "human_review_item_count": len(human_items),
        "human_review_items": human_items,
        "auto_fixed_items": auto_fixed,
        "duplicate_checks": {
            "normalized_name_duplicates": normalized_name_duplicates,
            "exact_source_name_duplicates": exact_source_name_duplicates,
            "broken_aliases": broken_aliases,
        },
        "source_reconciliation": {
            "expected_keys": len(expected_keys),
            "actual_keys": len(actual_keys),
            "keys_match": actual_keys == expected_keys,
        },
    }


def write_outputs(report: dict[str, object]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    items = cast(list[dict[str, str]], report["human_review_items"])
    columns = [
        "source_system",
        "source_id",
        "catalog_id",
        "normalized_exercise_id",
        "source_name",
        "review_status",
        "review_required_codes",
        "production_eligibility_blockers",
        "duplicate_candidate_group_id",
    ]
    with HUMAN_REVIEW_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(items)
    blockers = cast(dict[str, int], report["production_blockers"])
    auto_fixed = cast(dict[str, int], report["auto_fixed_items"])
    source_reconciliation = cast(dict[str, object], report["source_reconciliation"])
    errors = cast(list[str], report["errors"])
    warnings = cast(list[str], report["warnings"])
    markdown = [
        "# 통합 운동 카탈로그 검증 결과",
        "",
        f"- 검증 버전: `{report['validation_version']}`",
        f"- 결과: `{report['validation_status']}`",
        f"- 행 수: `{report['row_count']}`",
        f"- source key 일치: `{source_reconciliation['keys_match']}`",
        f"- registry 재사용: `{report['registry_reused']}`",
        "",
        "## 구조 검증",
        "",
        f"- 오류: `{len(errors)}`",
        f"- 경고: `{len(warnings)}`",
        "- catalog_id·source key·raw JSON·alias 관계·review_required 파생 규칙을 검사했다.",
        "",
        "## 운영 배포 차단 사유",
        "",
        "| 차단 코드 | 행 수 |",
        "|---|---:|",
    ]
    markdown.extend(f"| `{key}` | {value} |" for key, value in blockers.items())
    markdown.extend(
        [
            "",
            "## 자동 수정·정규화",
            "",
        ]
    )
    markdown.extend(f"- `{key}`: `{value}`" for key, value in auto_fixed.items())
    markdown.extend(
        [
            "",
            "## 사람 검토 목록",
            "",
            f"전체 `{report['human_review_item_count']}`행. 상세 목록은 `{HUMAN_REVIEW_CSV.relative_to(DATA_ROOT.parent)}`를 참조한다.",
            "",
            "중복 후보 `DUP-CANDIDATE-001`은 Gymvisual 0300 / Wger 1370, `DUP-CANDIDATE-002`는 Gymvisual 1760 / Wger 203이며, 현재 normalized ID를 병합하지 않았다.",
            "",
            "## 출처",
            "",
            "`AGENTS.md`, `data/AGENTS.md`, `docs/DATA_MODEL.md`, `data/raw/*/source.json`, 통합 생성기와 ID registry.",
        ]
    )
    REPORT_MD.write_text("\n".join(markdown) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV)
    args = parser.parse_args()
    report = validate(args.output)
    write_outputs(report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("validation_status", "row_count", "errors", "production_blockers")
            },
            ensure_ascii=False,
        )
    )
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
