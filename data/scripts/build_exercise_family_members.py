#!/usr/bin/env python3
"""Normalize existing catalog relationships to representative exercise IDs.

This generator never creates a relationship from family, name, muscle,
equipment, difficulty, or movement-pattern similarity. A relationship must be
present in the integrated catalog's explicit variant relation fields.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TAXONOMY = ROOT / "data/reports/representative_exercise_taxonomy_reviewed.csv"
DEFAULT_CATALOG = ROOT / "data/reports/integrated_exercise_review_updated.csv"
DEFAULT_OUTPUT = ROOT / "data/reports/exercise_family_members.csv"
DEFAULT_LOG = ROOT / "data/reports/variant_relationship_review_log.csv"

MEMBER_FIELDS = (
    "family_id",
    "exercise_id",
    "variant_type",
    "is_representative",
    "review_status_code",
)
LOG_FIELDS = (
    "family_id",
    "exercise_id",
    "related_exercise_id",
    "decision_code",
    "variant_type",
    "reason_code",
    "reason",
    "movement_pattern_left",
    "movement_pattern_right",
    "equipment_left",
    "equipment_right",
    "difficulty_left",
    "difficulty_right",
    "review_status_code",
    "production_eligible",
    "source_catalog_reference",
    "relationship_basis",
    "validation_result",
)

TAXONOMY_APPROVED = "TAXONOMY_APPROVED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
DOMAIN_APPROVED = "DOMAIN_APPROVED"
UNRESOLVED = {"", "REVIEW_REQUIRED"}

CATALOG_FIELDS = {
    "catalog_id",
    "normalized_exercise_id",
    "candidate_id",
    "representative_id",
    "representative_selected",
    "variant_relation_representative_ids",
    "variant_relation_review_decision",
    "variant_relation_note",
    "reviewed_movement_pattern_code",
    "movement_pattern_code_candidate",
    "reviewed_equipment_codes",
    "equipment_code_candidate",
    "reviewed_difficulty_code",
    "difficulty_code_candidate",
    "review_status",
    "production_eligible",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_taxonomy(path: Path) -> list[dict[str, str]]:
    rows = read_csv(path)
    required = {
        "representative_id",
        "reviewed_family",
        "reviewed_movement_pattern",
        "reviewed_equipment",
        "taxonomy_review_status",
    }
    if not rows or not required.issubset(rows[0]):
        missing = sorted(required.difference(rows[0] if rows else set()))
        raise ValueError(f"taxonomy input is missing required fields: {missing}")
    ids = [row["representative_id"] for row in rows]
    if len(rows) != 102:
        raise ValueError(f"expected 102 representative taxonomy rows, found {len(rows)}")
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        raise ValueError("representative_id values must be present and unique")
    return rows


def load_catalog(path: Path) -> list[dict[str, str]]:
    rows = read_csv(path)
    if not rows or not CATALOG_FIELDS.issubset(rows[0]):
        missing = sorted(CATALOG_FIELDS.difference(rows[0] if rows else set()))
        raise ValueError(f"integrated catalog is missing required fields: {missing}")
    catalog_ids = [row["normalized_exercise_id"] for row in rows]
    if len(catalog_ids) != len(set(catalog_ids)):
        raise ValueError("normalized_exercise_id values must be unique")
    return rows


def family_id(row: dict[str, str]) -> str:
    return row["reviewed_family"] or "REVIEW_REQUIRED"


def taxonomy_status(row: dict[str, str]) -> str:
    return (
        TAXONOMY_APPROVED if row["taxonomy_review_status"] == TAXONOMY_APPROVED else REVIEW_REQUIRED
    )


def catalog_reference(row: dict[str, str]) -> str:
    return (
        f"catalog_id={row['catalog_id']}|normalized_exercise_id="
        f"{row['normalized_exercise_id']}|candidate_id={row['candidate_id']}"
    )


def catalog_pattern(row: dict[str, str]) -> str:
    return row["reviewed_movement_pattern_code"] or row["movement_pattern_code_candidate"]


def catalog_equipment(row: dict[str, str]) -> str:
    return row["reviewed_equipment_codes"] or row["equipment_code_candidate"]


def catalog_difficulty(row: dict[str, str]) -> str:
    return row["reviewed_difficulty_code"] or row["difficulty_code_candidate"]


def is_catalog_production_eligible(row: dict[str, str]) -> bool:
    return (
        row["review_status"] == "INCLUSION_APPROVED"
        and row["production_eligible"].lower() == "true"
    )


def relation_targets(row: dict[str, str]) -> list[str]:
    return [
        target.strip()
        for target in row["variant_relation_representative_ids"].split("|")
        if target.strip()
    ]


def log_row(
    current: dict[str, str],
    target: dict[str, str] | None,
    *,
    decision_code: str,
    variant_type: str,
    reason_code: str,
    reason: str,
    source_reference: str,
    relationship_basis: str,
    validation_result: str,
) -> dict[str, str]:
    target = target or current
    production = (
        decision_code == "VARIANT_GENERATED"
        and is_catalog_production_eligible(current)
        and is_catalog_production_eligible(target)
    )
    return {
        "family_id": target.get(
            "representative_family", current.get("representative_family", "REVIEW_REQUIRED")
        ),
        "exercise_id": current["representative_id"],
        "related_exercise_id": "" if target is current else target["representative_id"],
        "decision_code": decision_code,
        "variant_type": variant_type,
        "reason_code": reason_code,
        "reason": reason,
        "movement_pattern_left": catalog_pattern(current),
        "movement_pattern_right": catalog_pattern(target),
        "equipment_left": catalog_equipment(current),
        "equipment_right": catalog_equipment(target),
        "difficulty_left": catalog_difficulty(current),
        "difficulty_right": catalog_difficulty(target),
        "review_status_code": DOMAIN_APPROVED if production else REVIEW_REQUIRED,
        "production_eligible": "true" if production else "false",
        "source_catalog_reference": source_reference,
        "relationship_basis": relationship_basis,
        "validation_result": validation_result,
    }


def build(
    taxonomy_rows: Iterable[dict[str, str]],
    catalog_rows: Iterable[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    taxonomy_rows = list(taxonomy_rows)
    catalog_rows = list(catalog_rows)
    taxonomy_by_id = {row["representative_id"]: row for row in taxonomy_rows}

    for row in catalog_rows:
        if row["representative_id"] not in taxonomy_by_id:
            raise ValueError(
                f"catalog row {row['normalized_exercise_id']} maps to unknown representative "
                f"{row['representative_id']}"
            )

    selected_by_candidate = {
        row["candidate_id"]: row for row in catalog_rows if row["representative_selected"] == "true"
    }
    catalog_by_rep: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in catalog_rows:
        row["representative_family"] = family_id(taxonomy_by_id[row["representative_id"]])
        catalog_by_rep[row["representative_id"]].append(row)

    members = [
        {
            "family_id": family_id(row),
            "exercise_id": row["representative_id"],
            "variant_type": "STANDARD",
            "is_representative": "true",
            "review_status_code": taxonomy_status(row),
        }
        for row in sorted(taxonomy_rows, key=lambda item: item["representative_id"])
    ]
    logs: list[dict[str, str]] = []

    for _representative_id, catalog_for_rep in sorted(catalog_by_rep.items()):
        relation_rows = [row for row in catalog_for_rep if relation_targets(row)]
        if not relation_rows:
            references = ";".join(catalog_reference(row) for row in catalog_for_rep)
            canonical = next(
                (row for row in catalog_for_rep if row["representative_selected"] == "true"),
                catalog_for_rep[0],
            )
            logs.append(
                log_row(
                    canonical,
                    None,
                    decision_code="NO_VARIANT",
                    variant_type="STANDARD",
                    reason_code="NO_EXPLICIT_CATALOG_RELATION",
                    reason="no existing variant or parent-child relation field was found",
                    source_reference=references,
                    relationship_basis="INTEGRATED_CATALOG_MAPPING_ONLY",
                    validation_result="NO_VARIANT_GENERATED",
                )
            )
            continue

        for row in relation_rows:
            for target_candidate_id in relation_targets(row):
                target = selected_by_candidate.get(target_candidate_id)
                source_reference = (
                    f"{catalog_reference(row)}|relation_representative_candidate_id="
                    f"{target_candidate_id}"
                )
                if target is None:
                    logs.append(
                        log_row(
                            row,
                            None,
                            decision_code="REVIEW_REQUIRED",
                            variant_type="",
                            reason_code="RELATION_TARGET_NOT_MAPPED",
                            reason="catalog relation target has no representative mapping",
                            source_reference=source_reference,
                            relationship_basis="EXPLICIT_CATALOG_VARIANT_RELATION_FIELD",
                            validation_result="REVIEW_REQUIRED_NO_MEMBER_GENERATED",
                        )
                    )
                    continue

                if target["representative_id"] == row["representative_id"]:
                    logs.append(
                        log_row(
                            row,
                            target,
                            decision_code="NO_VARIANT",
                            variant_type="STANDARD",
                            reason_code="SELF_REFERENCE_AFTER_REPRESENTATIVE_NORMALIZATION",
                            reason=(
                                "catalog variant relation collapses to the same "
                                "representative exercise ID"
                            ),
                            source_reference=source_reference,
                            relationship_basis="EXPLICIT_CATALOG_VARIANT_RELATION_FIELD",
                            validation_result="SELF_REFERENCE_REJECTED_NO_MEMBER_GENERATED",
                        )
                    )
                    continue

                current_pattern = catalog_pattern(row)
                target_pattern = catalog_pattern(target)
                if (
                    current_pattern in UNRESOLVED
                    or target_pattern in UNRESOLVED
                    or current_pattern != target_pattern
                ):
                    logs.append(
                        log_row(
                            row,
                            target,
                            decision_code="REVIEW_REQUIRED",
                            variant_type="",
                            reason_code="MOVEMENT_PATTERN_MISMATCH_OR_UNRESOLVED",
                            reason=(
                                "explicit catalog relation conflicts with or lacks "
                                "taxonomy movement pattern evidence"
                            ),
                            source_reference=source_reference,
                            relationship_basis="EXPLICIT_CATALOG_VARIANT_RELATION_FIELD",
                            validation_result="REVIEW_REQUIRED_NO_MEMBER_GENERATED",
                        )
                    )
                    continue

                if catalog_equipment(row) == catalog_equipment(target):
                    logs.append(
                        log_row(
                            row,
                            target,
                            decision_code="REVIEW_REQUIRED",
                            variant_type="",
                            reason_code="VARIANT_TYPE_NOT_EXPLICIT",
                            reason=(
                                "catalog relation exists but no permitted variant type is explicit"
                            ),
                            source_reference=source_reference,
                            relationship_basis="EXPLICIT_CATALOG_VARIANT_RELATION_FIELD",
                            validation_result="REVIEW_REQUIRED_NO_MEMBER_GENERATED",
                        )
                    )
                    continue

                logs.append(
                    log_row(
                        row,
                        target,
                        decision_code="REVIEW_REQUIRED",
                        variant_type="EQUIPMENT_VARIANT",
                        reason_code="EXPLICIT_CATALOG_RELATION_NOT_PRODUCTION_ELIGIBLE",
                        reason=(
                            "explicit cross-representative catalog relation retained "
                            "for review only"
                        ),
                        source_reference=source_reference,
                        relationship_basis="EXPLICIT_CATALOG_VARIANT_RELATION_FIELD_AND_EQUIPMENT_FIELDS",
                        validation_result="REVIEW_REQUIRED_NO_PRODUCTION_MEMBER_GENERATED",
                    )
                )

    if {row["exercise_id"] for row in members} != set(taxonomy_by_id):
        raise AssertionError("representative exercise ID set was not preserved")
    return members, logs


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def validate(
    members: list[dict[str, str]],
    logs: list[dict[str, str]],
    *,
    expected_count: int | None = None,
) -> None:
    if expected_count is not None and (
        len(members) != expected_count
        or len({row["exercise_id"] for row in members}) != expected_count
    ):
        raise ValueError("output must preserve exactly 102 unique representative exercise IDs")
    if any(row["production_eligible"] == "true" for row in logs):
        raise ValueError("no relation may be production eligible without explicit catalog approval")
    generated = [row for row in logs if row["decision_code"] == "VARIANT_GENERATED"]
    for row in generated:
        if not row["source_catalog_reference"] or not row["relationship_basis"]:
            raise ValueError("generated relation is missing source evidence")
    directed = {(row["exercise_id"], row["related_exercise_id"]) for row in generated}
    if any((right, left) in directed for left, right in directed):
        raise ValueError("reverse relationship was automatically generated")


def main() -> None:
    args = parse_args()
    taxonomy_rows = load_taxonomy(args.taxonomy)
    catalog_rows = load_catalog(args.catalog)
    members, logs = build(taxonomy_rows, catalog_rows)
    validate(members, logs, expected_count=102)
    write_csv(args.output, MEMBER_FIELDS, members)
    write_csv(args.log, LOG_FIELDS, logs)
    print(f"wrote {len(members)} membership rows to {args.output}")
    print(f"wrote {len(logs)} review log rows to {args.log}")


if __name__ == "__main__":
    main()
