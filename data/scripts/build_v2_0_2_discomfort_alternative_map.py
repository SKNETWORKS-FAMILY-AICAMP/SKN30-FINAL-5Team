"""Build a pain-area alternative target map from the v2.0.2-final catalog.

The map is intentionally separate from Variant and Context Default data.  A
map row exists only when the source exercise uses the reported pain area in
its primary or secondary body-area targets and the target exercise does not
use that area in either target list.

The artifact remains production-ineligible.  ``NRS_7_10`` is not represented
as an alternative relation; it is handled by the generalized stop policy.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "generated/exercise-catalog-v2.0.2-final/catalog/exercises.jsonl"
DEFAULT_POLICY = ROOT / "normalized/discomfort_alternative_target_map_policy_v2_0_2.json"
DEFAULT_OUTPUT = ROOT / "generated/exercise-catalog-v2.0.2-final/alternatives"

REVIEWED_AT = "2026-08-28T00:00:00+09:00"
POLICY_VERSION = "discomfort-alternative-target-map-v2.0.2-v1.0.0"
REVIEW_STATUS = "REVIEW_REQUIRED"
PRODUCTION_ELIGIBLE = False
MAX_TARGETS_PER_SOURCE = 12
DIFFICULTY_RANK = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}
PAIN_AREAS = (
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
)
CONDITIONS = {
    "NRS_1_3": {
        "minimum_score": 1,
        "maximum_score": 3,
        "severity_code": "MILD",
        "service_action_code": "LOAD_REDUCED",
        "target_strategy_code": "AREA_AVOIDING_CROSS_TRAINING_WITH_REDUCED_LOAD",
    },
    "NRS_4_6": {
        "minimum_score": 4,
        "maximum_score": 6,
        "severity_code": "MODERATE",
        "service_action_code": "SKIP_AFFECTED_AREA",
        "target_strategy_code": "AREA_AVOIDING_LOW_LOAD_ACTIVE_RECOVERY",
    },
}
TARGET_RECORD_TYPES = {"REPRESENTATIVE", "SEPARATE_EXERCISE"}
AREA_TARGET_FORBIDDEN_PATTERNS = {"NECK": {"CORE_BRACE"}}
AREA_TARGET_FORBIDDEN_AREAS = {"NECK": {"NECK", "SHOULDER"}}

MAP_FIELDS = [
    "map_relation_id",
    "pain_discomfort_area_code",
    "condition_code",
    "pain_score_min",
    "pain_score_max",
    "severity_code",
    "service_action_code",
    "target_strategy_code",
    "source_exercise_stable_code",
    "source_exercise_id",
    "source_record_type",
    "source_exercise_name_ko",
    "source_primary_movement_pattern_code",
    "source_primary_body_area_codes",
    "source_secondary_body_area_codes",
    "source_difficulty_code",
    "source_training_type_code",
    "target_exercise_stable_code",
    "target_exercise_id",
    "target_record_type",
    "target_exercise_name_ko",
    "target_primary_movement_pattern_code",
    "target_primary_body_area_codes",
    "target_secondary_body_area_codes",
    "target_difficulty_code",
    "target_training_type_code",
    "source_load_to_avoid_code",
    "source_load_to_avoid_roles",
    "target_area_exclusion_check_code",
    "target_pain_area_overlap",
    "target_difficulty_not_higher",
    "target_recovery_eligible",
    "selection_rank",
    "selection_score",
    "selection_basis_codes",
    "direction_code",
    "evidence_source",
    "evidence_reviewer",
    "evidence_reviewed_at",
    "review_status_code",
    "production_eligible",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be an object: {path}:{line_number}")
            rows.append(value)
    if not rows:
        raise ValueError(f"JSONL input is empty: {path}")
    return rows


def read_json(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not value:
        raise ValueError(f"JSON input is empty: {path}")
    return value


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def json_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json_value(row.get(field, "")) for field in fields})


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def area_codes(row: dict[str, Any]) -> set[str]:
    return {
        str(value)
        for field in ("primary_body_area_codes", "secondary_body_area_codes")
        for value in row.get(field, [])
    }


def excluded(row: dict[str, Any]) -> bool:
    return str(row.get("record_type", "")) in {"EXCLUDED", "RETIRED"} or str(
        row.get("canonical_status", "")
    ).startswith("RETIRED")


def catalog_indexes(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = read_jsonl(path)
    by_code: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("stable_code", "")).strip()
        exercise_id = str(row.get("exercise_id", "")).strip()
        if not code or not exercise_id or code in by_code:
            raise ValueError(f"catalog stable code/id is blank or duplicated: {code}/{exercise_id}")
        by_code[code] = row
    return rows, by_code


def target_score(
    source: dict[str, Any],
    target: dict[str, Any],
    condition_code: str,
    anchor_target_codes: set[str],
) -> tuple[int, list[str]]:
    source_areas = area_codes(source)
    target_areas = area_codes(target)
    source_difficulty = DIFFICULTY_RANK[str(source["difficulty_code"])]
    target_difficulty = DIFFICULTY_RANK[str(target["difficulty_code"])]
    score = 0
    basis: list[str] = []
    if condition_code == "NRS_4_6" and target.get("recovery_eligible") is True:
        score += 70
        basis.append("RECOVERY_ELIGIBLE")
    if target.get("training_type_code") == source.get("training_type_code"):
        score += 25
        basis.append("SAME_TRAINING_TYPE")
    if target.get("primary_movement_pattern_code") == source.get("primary_movement_pattern_code"):
        score += 15
        basis.append("SAME_MOVEMENT_PATTERN")
    if target_areas.isdisjoint(source_areas):
        score += 25
        basis.append("CROSS_BODY_AREA_TARGET")
    if target_difficulty < source_difficulty:
        score += 15
        basis.append("LOWER_DIFFICULTY")
    if target.get("equipment_codes") == ["BODYWEIGHT"]:
        score += 5
        basis.append("BODYWEIGHT_TARGET")
    if target.get("record_type") == "REPRESENTATIVE":
        score += 3
        basis.append("REPRESENTATIVE_TARGET")
    if str(target["stable_code"]) in anchor_target_codes and condition_code == "NRS_1_3":
        score += 40
        basis.append("PAIN_AREA_CROSS_TRAINING_ANCHOR")
    return score, basis


def eligible_targets(
    source: dict[str, Any],
    pain_area: str,
    condition_code: str,
    targets: list[dict[str, Any]],
    anchor_target_codes: set[str],
) -> list[tuple[dict[str, Any], int, list[str]]]:
    source_code = str(source["stable_code"])
    source_family = str(source.get("family_code", ""))
    source_rank = DIFFICULTY_RANK.get(str(source.get("difficulty_code", "")))
    if source_rank is None:
        return []
    candidates: list[tuple[dict[str, Any], int, list[str]]] = []
    for target in targets:
        target_code = str(target["stable_code"])
        target_rank = DIFFICULTY_RANK.get(str(target.get("difficulty_code", "")))
        target_areas = area_codes(target)
        target_pattern = str(target.get("primary_movement_pattern_code", ""))
        if (
            target_code == source_code
            or str(target.get("family_code", "")) == source_family
            or excluded(target)
            or target.get("record_type") not in TARGET_RECORD_TYPES
            or target.get("review_status_code") != "DOMAIN_APPROVED"
            or pain_area in target_areas
            or target_pattern in AREA_TARGET_FORBIDDEN_PATTERNS.get(pain_area, set())
            or bool(target_areas & AREA_TARGET_FORBIDDEN_AREAS.get(pain_area, set()))
            or target_rank is None
            or target_rank > source_rank
            or (condition_code == "NRS_4_6" and target.get("recovery_eligible") is not True)
        ):
            continue
        score, basis = target_score(source, target, condition_code, anchor_target_codes)
        candidates.append((target, score, basis))
    candidates.sort(key=lambda item: (-item[1], str(item[0]["stable_code"])))
    return candidates[:MAX_TARGETS_PER_SOURCE]


def map_row(
    source: dict[str, Any],
    target: dict[str, Any],
    pain_area: str,
    condition_code: str,
    score: int,
    basis: list[str],
    rank: int,
    catalog_path: Path,
) -> dict[str, Any]:
    condition = CONDITIONS[condition_code]
    source_roles = [
        role
        for role, values in (
            ("PRIMARY", source.get("primary_body_area_codes", [])),
            ("SECONDARY", source.get("secondary_body_area_codes", [])),
        )
        if pain_area in {str(value) for value in values}
    ]
    identity = "|".join(
        (str(source["stable_code"]), str(target["stable_code"]), pain_area, condition_code)
    )
    relation_id = "ALT-MAP-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return {
        "map_relation_id": relation_id,
        "pain_discomfort_area_code": pain_area,
        "condition_code": condition_code,
        "pain_score_min": condition["minimum_score"],
        "pain_score_max": condition["maximum_score"],
        "severity_code": condition["severity_code"],
        "service_action_code": condition["service_action_code"],
        "target_strategy_code": condition["target_strategy_code"],
        "source_exercise_stable_code": source["stable_code"],
        "source_exercise_id": source["exercise_id"],
        "source_record_type": source["record_type"],
        "source_exercise_name_ko": source.get("display_name_ko", source.get("name_ko", "")),
        "source_primary_movement_pattern_code": source["primary_movement_pattern_code"],
        "source_primary_body_area_codes": source["primary_body_area_codes"],
        "source_secondary_body_area_codes": source["secondary_body_area_codes"],
        "source_difficulty_code": source["difficulty_code"],
        "source_training_type_code": source["training_type_code"],
        "target_exercise_stable_code": target["stable_code"],
        "target_exercise_id": target["exercise_id"],
        "target_record_type": target["record_type"],
        "target_exercise_name_ko": target.get("display_name_ko", target.get("name_ko", "")),
        "target_primary_movement_pattern_code": target["primary_movement_pattern_code"],
        "target_primary_body_area_codes": target["primary_body_area_codes"],
        "target_secondary_body_area_codes": target["secondary_body_area_codes"],
        "target_difficulty_code": target["difficulty_code"],
        "target_training_type_code": target["training_type_code"],
        "source_load_to_avoid_code": "PAIN_AREA_IN_SOURCE_PRIMARY_OR_SECONDARY_TARGET",
        "source_load_to_avoid_roles": source_roles,
        "target_area_exclusion_check_code": "TARGET_PRIMARY_AND_SECONDARY_EXCLUDE_PAIN_AREA",
        "target_pain_area_overlap": pain_area in area_codes(target),
        "target_difficulty_not_higher": DIFFICULTY_RANK[str(target["difficulty_code"])]
        <= DIFFICULTY_RANK[str(source["difficulty_code"])],
        "target_recovery_eligible": target.get("recovery_eligible") is True,
        "selection_rank": rank,
        "selection_score": score,
        "selection_basis_codes": basis,
        "direction_code": "A_TO_B",
        "evidence_source": str(catalog_path.relative_to(ROOT.parent)),
        "evidence_reviewer": "DATA_REVIEW_PIPELINE",
        "evidence_reviewed_at": REVIEWED_AT,
        "review_status_code": REVIEW_STATUS,
        "production_eligible": PRODUCTION_ELIGIBLE,
    }


def build_map(
    catalog_path: Path = DEFAULT_CATALOG,
    anchor_target_codes: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    catalog, _ = catalog_indexes(catalog_path)
    anchor_target_codes = anchor_target_codes or set()
    targets = [row for row in catalog if row.get("record_type") in TARGET_RECORD_TYPES]
    rows: list[dict[str, Any]] = []
    coverage: dict[str, dict[str, Any]] = {}
    for pain_area in PAIN_AREAS:
        sources = [row for row in catalog if pain_area in area_codes(row) and not excluded(row)]
        coverage[pain_area] = {
            "source_exercise_count": len(sources),
            "conditions": {},
        }
        for condition_code in CONDITIONS:
            condition_rows: list[dict[str, Any]] = []
            candidate_counts: dict[str, int] = {}
            for source in sources:
                candidates = eligible_targets(
                    source, pain_area, condition_code, targets, anchor_target_codes
                )
                candidate_counts[str(source["stable_code"])] = len(candidates)
                for rank, (target, score, basis) in enumerate(candidates, 1):
                    condition_rows.append(
                        map_row(
                            source,
                            target,
                            pain_area,
                            condition_code,
                            score,
                            basis,
                            rank,
                            catalog_path,
                        )
                    )
            rows.extend(condition_rows)
            target_codes = sorted(
                {str(row["target_exercise_stable_code"]) for row in condition_rows}
            )
            target_ids = sorted({str(row["target_exercise_id"]) for row in condition_rows})
            coverage[pain_area]["conditions"][condition_code] = {
                "source_exercise_count": len(sources),
                "sources_with_target": sum(count > 0 for count in candidate_counts.values()),
                "sources_without_target": sorted(
                    code for code, count in candidate_counts.items() if count == 0
                ),
                "minimum_candidates_per_source": min(candidate_counts.values(), default=0),
                "maximum_candidates_per_source": max(candidate_counts.values(), default=0),
                "target_exercise_count": len(target_codes),
                "target_exercise_stable_codes": target_codes,
                "target_exercise_ids": target_ids,
            }
    rows.sort(
        key=lambda row: (
            row["pain_discomfort_area_code"],
            row["condition_code"],
            row["source_exercise_stable_code"],
            row["selection_rank"],
            row["target_exercise_stable_code"],
        )
    )
    return rows, coverage


def integrity_report(
    rows: list[dict[str, Any]], coverage: dict[str, Any], catalog_path: Path
) -> dict[str, Any]:
    natural_keys = [
        (
            row["source_exercise_stable_code"],
            row["target_exercise_stable_code"],
            row["pain_discomfort_area_code"],
            row["condition_code"],
        )
        for row in rows
    ]
    natural_counts = Counter(natural_keys)
    catalog = {row["stable_code"]: row for row in read_jsonl(catalog_path)}
    source_area_errors = sum(
        row["pain_discomfort_area_code"]
        not in area_codes(catalog[row["source_exercise_stable_code"]])
        for row in rows
    )
    target_overlap = sum(row["target_pain_area_overlap"] is not False for row in rows)
    neck_unsafe_target = sum(
        row["pain_discomfort_area_code"] == "NECK"
        and (
            row["target_primary_movement_pattern_code"] == "CORE_BRACE"
            or bool(
                {"NECK", "SHOULDER"}
                & (
                    set(row["target_primary_body_area_codes"])
                    | set(row["target_secondary_body_area_codes"])
                )
            )
        )
        for row in rows
    )
    variant_target_count = sum(row["target_record_type"] == "VARIANT" for row in rows)
    missing_refs = sum(
        row["source_exercise_stable_code"] not in catalog
        or row["target_exercise_stable_code"] not in catalog
        for row in rows
    )
    excluded_refs = sum(
        excluded(catalog.get(row["source_exercise_stable_code"], {}))
        or excluded(catalog.get(row["target_exercise_stable_code"], {}))
        for row in rows
    )
    direction_errors = sum(
        row["direction_code"] != "A_TO_B"
        or row["source_exercise_stable_code"] == row["target_exercise_stable_code"]
        or row["target_difficulty_not_higher"] is not True
        for row in rows
    )
    coverage_errors = [
        f"{area}/{condition}"
        for area, area_data in coverage.items()
        for condition, condition_data in area_data["conditions"].items()
        if condition_data["source_exercise_count"] == 0 or condition_data["sources_without_target"]
    ]
    report = {
        "schema_version": "discomfort-alternative-target-map-integrity-v2.0.2-v1",
        "policy_version": POLICY_VERSION,
        "reviewed_at": REVIEWED_AT,
        "status": "DRAFT_REVIEW_REQUIRED",
        "production_eligible": PRODUCTION_ELIGIBLE,
        "source": {
            "final_catalog": {
                "path": str(catalog_path.relative_to(ROOT.parent)),
                "sha256": sha256_file(catalog_path),
                "exercise_count": len(catalog),
            }
        },
        "counts": {
            "map_relation_count": len(rows),
            "pain_area_count": len(PAIN_AREAS),
            "source_area_membership_count": sum(
                area_data["source_exercise_count"] for area_data in coverage.values()
            ),
            "condition_counts": dict(
                sorted(Counter(row["condition_code"] for row in rows).items())
            ),
        },
        "coverage": coverage,
        "natural_key": [
            "source_exercise_stable_code",
            "target_exercise_stable_code",
            "pain_discomfort_area_code",
            "condition_code",
        ],
        "invariants": {
            "no_self_reference": all(
                row["source_exercise_stable_code"] != row["target_exercise_stable_code"]
                for row in rows
            ),
            "no_duplicate_natural_key": sum(
                count - 1 for count in natural_counts.values() if count > 1
            )
            == 0,
            "no_missing_exercise_reference": missing_refs == 0,
            "no_excluded_exercise_reference": excluded_refs == 0,
            "no_target_pain_area_overlap": target_overlap == 0,
            "no_unsafe_neck_target": neck_unsafe_target == 0,
            "no_variant_target_as_alternative": variant_target_count == 0,
            "source_contains_pain_area": source_area_errors == 0,
            "target_difficulty_not_higher": all(
                row["target_difficulty_not_higher"] is True for row in rows
            ),
            "no_directionality_error": direction_errors == 0,
            "all_supported_pain_areas_covered": not coverage_errors,
            "no_nrs_7_10_alternative_rows": not any(
                row["condition_code"] == "NRS_7_10" for row in rows
            ),
        },
        "integrity_metrics": {
            "self_reference_count": sum(
                row["source_exercise_stable_code"] == row["target_exercise_stable_code"]
                for row in rows
            ),
            "duplicate_natural_key_count": sum(
                count - 1 for count in natural_counts.values() if count > 1
            ),
            "missing_exercise_reference_count": missing_refs,
            "excluded_exercise_reference_count": excluded_refs,
            "target_pain_area_overlap_count": target_overlap,
            "unsafe_neck_target_count": neck_unsafe_target,
            "variant_target_count": variant_target_count,
            "source_pain_area_missing_count": source_area_errors,
            "difficulty_increase_count": sum(
                row["target_difficulty_not_higher"] is not True for row in rows
            ),
            "directionality_error_count": direction_errors,
            "coverage_error_count": len(coverage_errors),
        },
    }
    return report


def build(
    catalog_path: Path = DEFAULT_CATALOG,
    policy_path: Path = DEFAULT_POLICY,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    policy = read_json(policy_path)
    if not isinstance(policy, dict) or policy.get("policy_version") != POLICY_VERSION:
        raise ValueError("target map policy version is invalid")
    raw_anchors = policy.get("anchor_target_stable_codes", [])
    if not isinstance(raw_anchors, list) or not all(isinstance(code, str) for code in raw_anchors):
        raise ValueError("target map anchor targets are invalid")
    rows, coverage = build_map(catalog_path, set(raw_anchors))
    report = integrity_report(rows, coverage, catalog_path)
    if not all(report["invariants"].values()):
        failed = [key for key, value in report["invariants"].items() if not value]
        raise ValueError(f"discomfort alternative map integrity failed: {failed}")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "map_jsonl": output_dir / "discomfort_alternative_map_v2_0_2.jsonl",
        "map_csv": output_dir / "discomfort_alternative_map_v2_0_2.csv",
        "target_sets": output_dir / "discomfort_alternative_target_sets_v2_0_2.json",
        "integrity_report": output_dir / "discomfort_alternative_map_integrity_report_v2_0_2.json",
    }
    write_jsonl(paths["map_jsonl"], rows)
    write_csv(paths["map_csv"], MAP_FIELDS, rows)
    write_json(
        paths["target_sets"],
        {
            "schema_version": "discomfort-alternative-target-sets-v2.0.2-v1",
            "policy_version": POLICY_VERSION,
            "status": "DRAFT_REVIEW_REQUIRED",
            "production_eligible": PRODUCTION_ELIGIBLE,
            "pain_areas": list(PAIN_AREAS),
            "conditions": CONDITIONS,
            "sets": coverage,
        },
    )
    write_json(paths["integrity_report"], report)
    manifest = {
        "schema_version": "discomfort-alternative-target-map-manifest-v2.0.2-v1",
        "policy_version": POLICY_VERSION,
        "reviewed_at": REVIEWED_AT,
        "status": "DRAFT_REVIEW_REQUIRED",
        "production_eligible": PRODUCTION_ELIGIBLE,
        "source": {
            "catalog_path": str(catalog_path.relative_to(ROOT.parent)),
            "catalog_sha256": sha256_file(catalog_path),
            "policy_path": str(policy_path.relative_to(ROOT.parent)),
            "policy_sha256": sha256_file(policy_path),
        },
        "counts": report["counts"],
        "artifacts": {
            name: {
                "path": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for name, path in paths.items()
        },
    }
    manifest_path = output_dir / "discomfort_alternative_map_manifest_v2_0_2.json"
    write_json(manifest_path, manifest)
    return {
        "output_dir": str(output_dir),
        "map_relation_count": len(rows),
        "integrity_metrics": report["integrity_metrics"],
        "manifest": str(manifest_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.catalog, args.policy, args.output_dir),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
