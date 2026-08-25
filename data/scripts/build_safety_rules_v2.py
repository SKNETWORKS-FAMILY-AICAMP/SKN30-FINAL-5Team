"""Build the v2 safety-policy migration artifacts for catalog v1.

The legacy rules JSONL is an immutable reference.  This migration deliberately
keeps every legacy row and creates separate, review-required bridge rules for
the new catalog's proposed movement-pattern vocabulary.  It never marks a new
rule production-active.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_RULES = (
    DATA_ROOT / "generated/exercise-safety-rules-merged-mvp-v0.5.0/safety_rules.jsonl"
)
DEFAULT_CATALOG = DATA_ROOT / "generated/exercise-catalog-v1.0.0/exercise_catalog_v1.csv"
DEFAULT_PATTERN_REVIEW = DATA_ROOT / "validation/review_results/movement_pattern_review.csv"
DEFAULT_OUTPUT_DIR = DATA_ROOT / "generated/exercise-safety-rules-v2.0.0"
PAIN_ACTION_POLICY_PATH = DATA_ROOT / "normalized/v2_pain_action_policy.json"

# This pins the immutable legacy reference used by the migration.  Update it
# only through an explicitly reviewed source-rules version change, never as a
# side effect of rebuilding v2.
SOURCE_RULES_SHA256 = "a2667e53f6f335a8438679a60204cd01d62baeffa3a03f1c942416a32e292c3d"

RULE_FIELDS = (
    "rule_id",
    "movement_pattern",
    "body_area",
    "pain_level",
    "pain_score_policy_version",
    "pain_score_decisions",
    "service_action_policy_version",
    "red_flag_override_code",
    "action",
    "reason",
    "priority",
    "source_rule_id",
    "migration_status",
)
MAPPING_FIELDS = (
    "exercise_id",
    "movement_pattern",
    "body_focus",
    "difficulty",
    "rule_id",
    "action",
    "alternative_required",
    "source_rule_id",
)
REVIEW_FIELDS = (
    "exercise_id",
    "old_rule_match",
    "new_rule_id",
    "missing_rule",
    "new_rule_created",
    "review_required",
    "comment",
)
TEMPLATE_FIELDS = (
    "field_name",
    "required",
    "data_type",
    "allowed_values",
    "validation_rule",
    "operational_note",
)

VALID_ACTIONS = {"EXCLUDE", "CAUTION"}
VALID_PAIN_LEVELS = {"MILD", "MILD-SEVERE", "MODERATE-SEVERE"}
APPROVED_MOVEMENT_PATTERNS = {
    "BALANCE",
    "CORE_BRACE",
    "CYCLING",
    "ELLIPTICAL",
    "GAIT",
    "HIP_DOMINANT",
    "HORIZONTAL_PULL",
    "HORIZONTAL_PUSH",
    "ISOLATION",
    "JUMP_PLYOMETRIC",
    "KNEE_DOMINANT",
    "KNEE_FLEXION",
    "MOBILITY_STRETCH",
    "VERTICAL_PULL",
    "VERTICAL_PUSH",
}
# This migration still reads the immutable catalog-v1 review batch.  These
# legacy values remain accepted at the bridge boundary and are not part of the
# v2 runtime code registry.
LEGACY_CATALOG_MOVEMENT_PATTERNS = {
    "CARDIO",
    "CORE",
    "HINGE",
    "LUNGE",
    "MOBILITY",
    "PULL",
    "PUSH",
    "SQUAT",
}
PAIN_SCORE_POLICY_VERSION = "pain-intensity-action-v2"
VALID_AREAS = {
    "NECK",
    "SHOULDER",
    "ELBOW",
    "WRIST_HAND",
    "UPPER_BACK",
    "LOWER_BACK",
    "HIP",
    "KNEE",
    "ANKLE_FOOT",
    "CHEST",
    "ABDOMEN",
    "GENERALIZED",
}


class MigrationError(ValueError):
    """Raised when a migration input is incomplete or inconsistent."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise MigrationError(f"CSV header is missing: {path}")
        missing = sorted(set(fields) - set(reader.fieldnames))
        if missing:
            raise MigrationError(f"CSV columns are missing from {path}: {missing}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def read_legacy_rules(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    digest = sha256_bytes(raw)
    if digest != SOURCE_RULES_SHA256:
        raise MigrationError(
            "legacy safety_rules.jsonl hash changed; "
            "create a reviewed source version before migration"
        )

    rules: list[dict[str, Any]] = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rule = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MigrationError(f"legacy rule is invalid JSON at line {number}") from exc
        required = {
            "body_area_code",
            "effect_code",
            "maximum_severity_code",
            "minimum_severity_code",
            "reason_code",
            "rule_scope",
        }
        if not isinstance(rule, dict) or required - set(rule):
            raise MigrationError(f"legacy rule fields are incomplete at line {number}")
        if rule["effect_code"] not in VALID_ACTIONS:
            raise MigrationError(f"legacy rule action is invalid at line {number}")
        rules.append({"source_rule_id": f"LEGACY-RULE-{number:04d}", **rule})
    if not rules:
        raise MigrationError("legacy rules are empty")
    return rules


def pain_level(minimum: str, maximum: str) -> str:
    value = minimum if minimum == maximum else f"{minimum}-{maximum}"
    if value not in VALID_PAIN_LEVELS:
        raise MigrationError(f"unsupported severity range: {value}")
    return value


def priority(action: str) -> str:
    return "P0" if action == "EXCLUDE" else "P1"


def read_pain_action_policy(path: Path = PAIN_ACTION_POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("status") != "DOMAIN_APPROVED":
        raise MigrationError("pain action policy is not domain approved")
    bands = policy.get("score_bands")
    if not isinstance(bands, list) or len(bands) != 3:
        raise MigrationError("pain action policy must define exactly three score bands")
    expected_ranges = [(1, 3), (4, 6), (7, 10)]
    actual_ranges = [(band.get("minimum_score"), band.get("maximum_score")) for band in bands]
    if actual_ranges != expected_ranges:
        raise MigrationError(f"pain action score bands are invalid: {actual_ranges}")
    return policy


PAIN_ACTION_POLICY = read_pain_action_policy()


def pain_score_decisions(level: str, action: str) -> list[dict[str, Any]]:
    """Return service actions for every score band; red flags override them."""
    del level, action
    decisions: list[dict[str, Any]] = []
    for band in PAIN_ACTION_POLICY["score_bands"]:
        service_action = band["service_action_code"]
        decisions.append(
            {
                "minimum_score": band["minimum_score"],
                "maximum_score": band["maximum_score"],
                "decision_code": service_action,
                "service_action_code": service_action,
                "alternative_strategy_code": band["alternative_strategy_code"],
                "fallback_action_code": band.get(
                    "fallback_action_code", "ROM_REDUCED" if service_action == "LOAD_REDUCED" else service_action
                ),
                "alternative_available": service_action != "STOP_EXERCISE",
                "decision_scope": (
                    "SESSION_OVERRIDE" if service_action == "STOP_EXERCISE" else "MATCHED_RULE"
                ),
            }
        )
    return decisions


def parse_area_list(
    value: str, field: str, exercise_id: str, *, allow_empty: bool = False
) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise MigrationError(f"{field} must be a JSON array: {exercise_id}") from exc
    if (
        not isinstance(parsed, list)
        or (not allow_empty and not parsed)
        or any(item not in VALID_AREAS for item in parsed)
    ):
        raise MigrationError(f"{field} has an invalid body area: {exercise_id}")
    if len(parsed) != len(set(parsed)):
        raise MigrationError(f"{field} has duplicate body areas: {exercise_id}")
    return parsed


def load_catalog_and_patterns(
    catalog_path: Path, pattern_review_path: Path
) -> list[dict[str, Any]]:
    catalog = read_csv(
        catalog_path,
        (
            "exercise_id",
            "body_focus_code",
            "difficulty_code",
            "primary_body_area_codes",
            "secondary_body_area_codes",
        ),
    )
    review = read_csv(
        pattern_review_path,
        (
            "exercise_id",
            "current_body_focus",
            "difficulty",
            "suggested_movement_pattern",
            "review_required",
        ),
    )
    by_id = {row["exercise_id"]: row for row in review}
    catalog_ids = {row["exercise_id"] for row in catalog}
    if len(catalog_ids) != len(catalog) or len(by_id) != len(review):
        raise MigrationError("catalog or movement-pattern review has duplicate exercise_id")
    if catalog_ids != set(by_id):
        raise MigrationError(
            "catalog and movement-pattern review do not cover the same exercise_id set"
        )

    merged: list[dict[str, Any]] = []
    for row in sorted(catalog, key=lambda item: item["exercise_id"]):
        review_row = by_id[row["exercise_id"]]
        if review_row["current_body_focus"] != row["body_focus_code"]:
            raise MigrationError(f"body focus differs from movement review: {row['exercise_id']}")
        if review_row["difficulty"] != row["difficulty_code"]:
            raise MigrationError(f"difficulty differs from movement review: {row['exercise_id']}")
        pattern = review_row["suggested_movement_pattern"]
        if (
            not pattern
            or pattern not in APPROVED_MOVEMENT_PATTERNS | LEGACY_CATALOG_MOVEMENT_PATTERNS
            or pattern != pattern.upper()
            or " " in pattern
        ):
            raise MigrationError(f"movement pattern is invalid: {row['exercise_id']}")
        if review_row["review_required"] != "NO":
            raise MigrationError(f"movement-pattern review is not complete: {row['exercise_id']}")
        primary = parse_area_list(
            row["primary_body_area_codes"], "primary_body_area_codes", row["exercise_id"]
        )
        secondary = (
            parse_area_list(
                row["secondary_body_area_codes"],
                "secondary_body_area_codes",
                row["exercise_id"],
                allow_empty=True,
            )
            if row["secondary_body_area_codes"]
            else []
        )
        if set(primary) & set(secondary):
            raise MigrationError(f"catalog body areas overlap: {row['exercise_id']}")
        merged.append(
            {
                "exercise_id": row["exercise_id"],
                "movement_pattern": pattern,
                "body_focus": row["body_focus_code"],
                "difficulty": row["difficulty_code"],
                "primary": primary,
                "secondary": secondary,
            }
        )
    return merged


def legacy_v2_rows(legacy_rules: list[dict[str, Any]]) -> list[dict[str, str]]:
    migrated: list[dict[str, str]] = []
    for rule in legacy_rules:
        scope = rule["rule_scope"]
        if scope == "MOVEMENT_PATTERN":
            pattern = rule.get("movement_pattern_code")
            status = "MIGRATED_LEGACY_REFERENCE"
        elif scope == "EXERCISE":
            # The v2 rule schema deliberately has no legacy exercise key.
            # Unmapped legacy exercise rules remain in the immutable source
            # only and are not loaded into the v2 migration artifact.
            continue
        else:
            raise MigrationError(f"legacy rule scope is invalid: {scope}")
        if not pattern or rule["body_area_code"] not in VALID_AREAS:
            raise MigrationError(f"legacy rule data is invalid: {rule['source_rule_id']}")
        migrated.append(
            {
                "rule_id": f"SRV2-{rule['source_rule_id']}",
                "movement_pattern": pattern,
                "body_area": rule["body_area_code"],
                "pain_level": pain_level(
                    rule["minimum_severity_code"], rule["maximum_severity_code"]
                ),
                "pain_score_policy_version": PAIN_SCORE_POLICY_VERSION,
                "pain_score_decisions": pain_score_decisions(
                    pain_level(rule["minimum_severity_code"], rule["maximum_severity_code"]),
                    rule["effect_code"],
                ),
                "service_action_policy_version": PAIN_ACTION_POLICY["policy_version"],
                "red_flag_override_code": PAIN_ACTION_POLICY["red_flag_override"][
                    "service_action_code"
                ],
                "action": rule["effect_code"],
                "reason": rule["reason_code"],
                "priority": priority(rule["effect_code"]),
                "source_rule_id": rule["source_rule_id"],
                "migration_status": status,
            }
        )
    return migrated


def legacy_matches_by_effect(
    legacy_rules: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str], list[str]]:
    matches: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    for rule in legacy_rules:
        key = (
            rule["body_area_code"],
            pain_level(rule["minimum_severity_code"], rule["maximum_severity_code"]),
            rule["effect_code"],
            rule["reason_code"],
        )
        matches[key].append(rule["source_rule_id"])
    return matches


def bridge_rule_specs(catalog: list[dict[str, Any]]) -> list[tuple[str, str, str, str, str]]:
    specs: set[tuple[str, str, str, str, str]] = set()
    for exercise in catalog:
        for area in exercise["primary"]:
            specs.add(
                (exercise["movement_pattern"], area, "MILD-SEVERE", "EXCLUDE", "DIRECT_JOINT_LOAD")
            )
        for area in exercise["secondary"]:
            specs.add((exercise["movement_pattern"], area, "MILD", "CAUTION", "STABILIZER_LOAD"))
            specs.add(
                (
                    exercise["movement_pattern"],
                    area,
                    "MODERATE-SEVERE",
                    "EXCLUDE",
                    "STABILIZER_LOAD",
                )
            )
    return sorted(specs)


def bridge_v2_rows(
    catalog: list[dict[str, Any]], legacy_rules: list[dict[str, Any]]
) -> list[dict[str, str]]:
    matches = legacy_matches_by_effect(legacy_rules)
    rows: list[dict[str, str]] = []
    for index, (pattern, area, level, action, reason) in enumerate(bridge_rule_specs(catalog), 1):
        source_ids = matches.get((area, level, action, reason), [])
        # A newly introduced direct body-area assignment has no equivalent
        # legacy row.  Preserve that absence explicitly instead of inventing
        # a legacy lineage; the status keeps it non-active until review.
        lineage = "|".join(sorted(source_ids)) if source_ids else "NO_EXACT_LEGACY_RULE"
        rows.append(
            {
                "rule_id": f"SRV2-NEW-{index:04d}",
                "movement_pattern": pattern,
                "body_area": area,
                "pain_level": level,
                "pain_score_policy_version": PAIN_SCORE_POLICY_VERSION,
                "pain_score_decisions": pain_score_decisions(level, action),
                "service_action_policy_version": PAIN_ACTION_POLICY["policy_version"],
                "red_flag_override_code": PAIN_ACTION_POLICY["red_flag_override"][
                    "service_action_code"
                ],
                "action": action,
                "reason": reason,
                "priority": priority(action),
                "source_rule_id": lineage,
                "migration_status": "NEW_PATTERN_RULE_REVIEW_REQUIRED",
            }
        )
    return rows


def mapping_rows(
    catalog: list[dict[str, Any]], bridge_rules: list[dict[str, str]]
) -> list[dict[str, str]]:
    by_key = {
        (
            rule["movement_pattern"],
            rule["body_area"],
            rule["pain_level"],
            rule["action"],
            rule["reason"],
        ): rule
        for rule in bridge_rules
    }
    rows: list[dict[str, str]] = []
    for exercise in catalog:
        targets: list[tuple[str, str, str, str]] = []
        targets.extend(
            (area, "MILD-SEVERE", "EXCLUDE", "DIRECT_JOINT_LOAD") for area in exercise["primary"]
        )
        for area in exercise["secondary"]:
            targets.extend(
                (
                    (area, "MILD", "CAUTION", "STABILIZER_LOAD"),
                    (area, "MODERATE-SEVERE", "EXCLUDE", "STABILIZER_LOAD"),
                )
            )
        for area, level, action, reason in targets:
            rule = by_key.get((exercise["movement_pattern"], area, level, action, reason))
            if rule is None:
                raise MigrationError(
                    f"new catalog exercise has no bridge rule: {exercise['exercise_id']}"
                )
            rows.append(
                {
                    "exercise_id": exercise["exercise_id"],
                    "movement_pattern": exercise["movement_pattern"],
                    "body_focus": exercise["body_focus"],
                    "difficulty": exercise["difficulty"],
                    "rule_id": rule["rule_id"],
                    "action": action,
                    "alternative_required": "YES" if action == "EXCLUDE" else "NO",
                    "source_rule_id": rule["source_rule_id"],
                }
            )
    return sorted(rows, key=lambda row: (row["exercise_id"], row["rule_id"]))


def review_rows(
    catalog: list[dict[str, Any]], mappings: list[dict[str, str]]
) -> list[dict[str, str]]:
    by_exercise: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in mappings:
        by_exercise[row["exercise_id"]].append(row)
    output: list[dict[str, str]] = []
    for exercise in catalog:
        related = by_exercise[exercise["exercise_id"]]
        if not related:
            raise MigrationError(f"new exercise is unmapped: {exercise['exercise_id']}")
        output.append(
            {
                "exercise_id": exercise["exercise_id"],
                "old_rule_match": "|".join(
                    sorted(
                        {source for row in related for source in row["source_rule_id"].split("|")}
                    )
                ),
                "new_rule_id": "|".join(sorted(row["rule_id"] for row in related)),
                "missing_rule": "NO",
                "new_rule_created": "YES",
                "review_required": "YES",
                "comment": (
                    "movement_pattern 사람 검수 완료값과 body-area 기반 bridge rule입니다. "
                    "외부 도메인 검수 전에는 운영 활성화하지 않습니다."
                ),
            }
        )
    return output


def template_rows() -> list[dict[str, str]]:
    values = {
        "field_name": "field_name",
        "required": "YES",
        "data_type": "string",
    }
    return [
        {
            **values,
            "field_name": "rule_id",
            "allowed_values": "SRV2-LEGACY-*|SRV2-NEW-*",
            "validation_rule": "unique; immutable after publish",
            "operational_note": "v2 loader uses this ID only.",
        },
        {
            **values,
            "field_name": "movement_pattern",
            "allowed_values": (
                "catalog-v1 proposed movement patterns; LEGACY_EXERCISE_SCOPE reference only"
            ),
            "validation_rule": "must exist in mapping or be legacy reference",
            "operational_note": "legacy exercise scope is never an active pattern match.",
        },
        {
            **values,
            "field_name": "body_area",
            "allowed_values": (
                "NECK|SHOULDER|ELBOW|WRIST_HAND|UPPER_BACK|LOWER_BACK|HIP|KNEE|"
                "ANKLE_FOOT|CHEST|ABDOMEN|GENERALIZED"
            ),
            "validation_rule": "stable body-area machine code",
            "operational_note": "match only the normalized check-in body area.",
        },
        {
            **values,
            "field_name": "pain_level",
            "allowed_values": "MILD|MILD-SEVERE|MODERATE-SEVERE",
            "validation_rule": "inclusive severity interval",
            "operational_note": "SEVERE session REST remains higher priority.",
        },
        {
            **values,
            "field_name": "pain_score_policy_version",
            "allowed_values": PAIN_SCORE_POLICY_VERSION,
            "validation_rule": "required stable policy version",
            "operational_note": "store with the original score for reproducible decisions.",
        },
        {
            **values,
            "field_name": "pain_score_decisions",
            "data_type": "json-array",
            "allowed_values": (
                "1-3=LOAD_REDUCED;4-6=SKIP_AFFECTED_AREA;7-10=STOP_EXERCISE"
            ),
            "validation_rule": "ordered non-overlapping score bands; 7-10 has no alternative",
            "operational_note": "red-flag codes override every score band with STOP_AND_SEEK_HELP.",
        },
        {
            **values,
            "field_name": "service_action_policy_version",
            "allowed_values": "pain-intensity-action-v2",
            "validation_rule": "must match the approved score/action policy",
            "operational_note": "service action is separate from legacy EXCLUDE or CAUTION effect.",
        },
        {
            **values,
            "field_name": "red_flag_override_code",
            "allowed_values": "STOP_AND_SEEK_HELP",
            "validation_rule": "always takes precedence over score-band actions",
            "operational_note": "the code list is maintained in v2_pain_action_policy.json.",
        },
        {
            **values,
            "field_name": "action",
            "allowed_values": "EXCLUDE|CAUTION",
            "validation_rule": "EXCLUDE is higher priority than CAUTION",
            "operational_note": "no free-text or LLM action is allowed.",
        },
        {
            **values,
            "field_name": "reason",
            "allowed_values": "DIRECT_JOINT_LOAD|STABILIZER_LOAD",
            "validation_rule": "stable reason code",
            "operational_note": "user-facing wording is maintained separately.",
        },
        {
            **values,
            "field_name": "priority",
            "allowed_values": "P0|P1",
            "validation_rule": "EXCLUDE=P0; CAUTION=P1",
            "operational_note": "lower priority cannot override P0.",
        },
        {
            **values,
            "field_name": "source_rule_id",
            "allowed_values": (
                "LEGACY-RULE-####, pipe-separated when multiple, or NO_EXACT_LEGACY_RULE"
            ),
            "validation_rule": (
                "LEGACY IDs resolve to immutable JSONL line order; no-exact lineage requires review"
            ),
            "operational_note": "source rows are reference-only.",
        },
        {
            **values,
            "field_name": "migration_status",
            "allowed_values": (
                "MIGRATED_LEGACY_REFERENCE|LEGACY_EXERCISE_UNMAPPED_REVIEW_REQUIRED|"
                "NEW_PATTERN_RULE_REVIEW_REQUIRED|ACTIVE_V2"
            ),
            "validation_rule": "only reviewed ACTIVE_V2 rows may be enabled",
            "operational_note": (
                "runtime must load v2 files only and fail closed for non-ACTIVE_V2 rules."
            ),
        },
    ]


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(
    source_rules_path: Path = DEFAULT_SOURCE_RULES,
    catalog_path: Path = DEFAULT_CATALOG,
    pattern_review_path: Path = DEFAULT_PATTERN_REVIEW,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, int]:
    legacy_rules = read_legacy_rules(source_rules_path)
    catalog = load_catalog_and_patterns(catalog_path, pattern_review_path)
    legacy_rows = legacy_v2_rows(legacy_rules)
    bridge_rows = bridge_v2_rows(catalog, legacy_rules)
    all_rules = legacy_rows + bridge_rows
    if len({row["rule_id"] for row in all_rules}) != len(all_rules):
        raise MigrationError("v2 rule_id is not unique")
    mappings = mapping_rows(catalog, bridge_rows)
    reviews = review_rows(catalog, mappings)
    patterns = {row["movement_pattern"] for row in catalog}
    mapped_patterns = {row["movement_pattern"] for row in mappings}
    if patterns != mapped_patterns:
        raise MigrationError("not every new movement pattern is connected to a safety rule")
    legacy_excludes = {
        row["source_rule_id"]
        for row in legacy_rules
        if row["rule_scope"] == "MOVEMENT_PATTERN" and row["effect_code"] == "EXCLUDE"
    }
    v2_legacy_excludes = {
        row["source_rule_id"] for row in legacy_rows if row["action"] == "EXCLUDE"
    }
    if legacy_excludes != v2_legacy_excludes:
        raise MigrationError("legacy EXCLUDE rules were lost during migration")

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "safety_rules_v2.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in all_rules:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")
    write_csv(output_dir / "exercise_safety_mapping_v2.csv", MAPPING_FIELDS, mappings)
    write_csv(output_dir / "safety_rule_template_v2.csv", TEMPLATE_FIELDS, template_rows())
    write_csv(output_dir / "safety_migration_review_log.csv", REVIEW_FIELDS, reviews)
    return {
        "legacy_rules": len(legacy_rows),
        "new_rules": len(bridge_rows),
        "mapped_exercises": len(reviews),
        "mapping_records": len(mappings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-rules", type=Path, default=DEFAULT_SOURCE_RULES)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--pattern-review", type=Path, default=DEFAULT_PATTERN_REVIEW)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    summary = build(args.source_rules, args.catalog, args.pattern_review, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
