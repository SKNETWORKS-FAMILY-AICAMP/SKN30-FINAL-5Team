#!/usr/bin/env python3
"""Materialize independent Safety/FITT/Goal bindings from reviewed source data."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "generated/exercise-catalog-v2.0.2-final"
ENRICHMENT = ROOT / "normalized/catalog_enrichment_v3_fitt.csv"
SAFETY_SOURCE = ROOT / "generated/exercise-safety-rules-v2.0.0/exercise_safety_mapping_v2.csv"
OLD_CATALOG = ROOT / "generated/exercise-catalog-v2.0.1-final/representative_exercises_v2_final.csv"
GOAL_SOURCE = ROOT / "generated/exercise-catalog-v2.0.2-draft/prescriptions/goal_tag_links.jsonl"
BEGINNER_TEMPLATES = (
    ROOT / "generated/exercise-prescriptions-v2.0.2-draft/fitt_template_beginner_v1.csv"
)
INTERMEDIATE_TEMPLATES = (
    ROOT / "generated/exercise-prescriptions-v2.0.2-draft/fitt_template_intermediate_v1.json"
)
CATALOG_VERSION = "exercise-catalog-v2.0.2-final"
MATERIALIZATION_VERSION = "v2.0.2-independent-bindings-source-match-v1.0.0"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (list, dict))
                    else value
                    for key, value in row.items()
                }
            )


def source_metadata(path: Path) -> dict[str, str]:
    return {
        "path": str(path.relative_to(ROOT.parent)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
    }


def normalize_name(value: str) -> str:
    value = re.sub(r"\s*머신\s*$", "", value.strip())
    return re.sub(r"[\s·()\-]+", "", value).lower()


def parse_json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(value or "[]")
        except (ValueError, SyntaxError):
            parsed = []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def number(value: str | None) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def level_template_id(template_id: str, level: str) -> str:
    if level == "BEGINNER":
        return template_id
    if template_id.endswith("-INTERMEDIATE-V1"):
        return template_id
    return template_id[:-3] + "-INTERMEDIATE-V1" if template_id.endswith("-V1") else template_id


def resolve_template(
    template_id: str,
    level: str,
    beginner: dict[str, dict[str, Any]],
    intermediate: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any] | None, str]:
    """Resolve the latest template, retaining an explicit fallback for legacy bodyweight IDs.

    The enrichment source contains BODYWEIGHT template IDs, while the latest template
    registry intentionally groups bodyweight work by movement pattern.  This fallback
    uses the existing isolation template only when the source ID is absent and records
    the reason in the generated binding.
    """
    requested_id = level_template_id(template_id, level)
    pool = intermediate if level == "INTERMEDIATE" else beginner
    template = pool.get(requested_id)
    if template:
        return requested_id, template, "DIRECT_TEMPLATE_MATCH"
    fallback_base = "FITT-ISOLATION-STRENGTH-V1"
    fallback_id = level_template_id(fallback_base, level)
    template = pool.get(fallback_id)
    if template and template_id.startswith("FITT-BODYWEIGHT-"):
        return fallback_id, template, "BODYWEIGHT_TEMPLATE_MOVEMENT_PATTERN_FALLBACK"
    return requested_id, None, "TEMPLATE_NOT_FOUND"


def load_sources() -> tuple[
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, dict[str, Any]],
]:
    enrichment_rows = list(csv.DictReader(ENRICHMENT.open(encoding="utf-8")))
    enrichment_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in enrichment_rows:
        enrichment_by_name[normalize_name(row.get("exercise_name_ko", ""))].append(row)
    old_catalog = list(csv.DictReader(OLD_CATALOG.open(encoding="utf-8")))
    old_by_rex = {row["representative_exercise_id"]: row for row in old_catalog}
    safety_rows = list(csv.DictReader(SAFETY_SOURCE.open(encoding="utf-8")))
    safety_by_nex: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in safety_rows:
        safety_by_nex[row["exercise_id"]].append(row)
    goal_rows = read_jsonl(GOAL_SOURCE)
    goals_by_stable = {str(row["exercise_stable_code"]): row for row in goal_rows}
    n2stable: dict[str, dict[str, Any]] = {}
    for row in old_catalog:
        for nex in parse_json_list(row.get("nex_exercise_ids", "")):
            n2stable[nex] = goals_by_stable.get(row.get("stable_code", ""), {})
    beginner = {
        row["fitt_template_id"]: row
        for row in csv.DictReader(BEGINNER_TEMPLATES.open(encoding="utf-8"))
    }
    intermediate_data = json.loads(INTERMEDIATE_TEMPLATES.read_text(encoding="utf-8"))
    intermediate = {row["fitt_template_id"]: row for row in intermediate_data["templates"]}
    return (
        enrichment_rows,
        enrichment_by_name,
        old_by_rex,
        safety_by_nex,
        {
            "n2stable": n2stable,
            "beginner": beginner,
            "intermediate": intermediate,
        },
    )


def choose_enrichment(
    row: dict[str, Any],
    enrichment_by_name: dict[str, list[dict[str, Any]]],
    old_by_rex: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str, str]:
    candidates = enrichment_by_name.get(normalize_name(str(row.get("name_ko") or "")), [])
    if candidates:
        return sorted(candidates, key=lambda item: item.get("exercise_id", ""))[0], "NAME_MATCH", ""
    base_id = str(
        row.get("alternative_source_base_exercise_id")
        or row.get("representative_exercise_id")
        or ""
    )
    old = old_by_rex.get(base_id, {})
    nex_ids = parse_json_list(old.get("nex_exercise_ids", ""))
    all_rows = [item for values in enrichment_by_name.values() for item in values]
    by_nex = {str(item.get("exercise_id")): item for item in all_rows}
    for nex in sorted(nex_ids):
        if nex in by_nex:
            return by_nex[nex], "BASE_EXERCISE_NEX_MATCH", nex
    raise ValueError(
        f"no latest enrichment match for {row.get('exercise_id')}:{row.get('name_ko')}"
    )


def build(final_dir: Path = FINAL) -> dict[str, Any]:
    catalog_path = final_dir / "catalog/exercises.jsonl"
    catalog = read_jsonl(catalog_path)
    targets = [
        row
        for row in catalog
        if row.get("record_type") == "VARIANT"
        or row.get("alternative_only")
        or row.get("record_type") == "SEPARATE_EXERCISE"
    ]
    enrichment_rows, enrichment_by_name, old_by_rex, safety_by_nex, lookup = load_sources()
    target_codes = {str(row["stable_code"]) for row in targets}
    mappings: dict[str, dict[str, Any]] = {}
    generated_fitt: list[dict[str, Any]] = []
    generated_safety: list[dict[str, Any]] = []
    generated_goals: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    for row in targets:
        try:
            enrichment, match_method, matched_nex = choose_enrichment(
                row, enrichment_by_name, old_by_rex
            )
        except ValueError as error:
            unmatched.append({"exercise_id": row.get("exercise_id", ""), "reason": str(error)})
            continue
        nex_id = matched_nex or str(enrichment.get("exercise_id") or "")
        if not nex_id or nex_id not in safety_by_nex:
            unmatched.append(
                {
                    "exercise_id": row.get("exercise_id", ""),
                    "reason": "latest Safety source missing",
                }
            )
            continue
        code = str(row["stable_code"])
        difficulty = str(
            row.get("difficulty_code") or enrichment.get("difficulty_code") or "BEGINNER"
        )
        # FITT timing normally comes from the latest enrichment row; an explicitly
        # restored legacy Alternative target keeps the reviewed catalog timing so
        # its existing prescription shape remains consistent.
        timing = str(
            row.get("timing_mode_code")
            if row.get("canonical_decision_code") == "RESTORED_LEGACY_ALTERNATIVE_TARGET"
            else enrichment.get("timing_mode_code") or row.get("timing_mode_code") or "REPS"
        )
        row["timing_mode_code"] = timing
        for field in (
            "default_sets",
            "default_work_seconds",
            "default_rest_seconds",
            "default_transition_seconds",
        ):
            source_value = number(enrichment.get(field))
            if source_value is not None:
                row[field] = source_value
        levels = [difficulty] if difficulty == "INTERMEDIATE" else ["BEGINNER", "INTERMEDIATE"]
        fitt_ids: dict[str, str] = {}
        template_fallbacks: dict[str, str] = {}
        for level in levels:
            template_id, template, template_resolution = resolve_template(
                str(enrichment.get("fitt_template_id") or ""),
                level,
                lookup["beginner"],
                lookup["intermediate"],
            )
            if not template:
                unmatched.append(
                    {
                        "exercise_id": row.get("exercise_id", ""),
                        "reason": f"FITT template missing: {template_id}",
                    }
                )
                continue
            if template_resolution != "DIRECT_TEMPLATE_MATCH":
                template_fallbacks[level] = template_resolution
            fitt_ids[level] = template_id
            generated_fitt.append(
                {
                    "catalog_version_code": CATALOG_VERSION,
                    "exercise_stable_code": code,
                    "exercise_difficulty_code": difficulty,
                    "experience_level_code": level,
                    "fitt_template_id": template_id,
                    "goal_code": "GENERAL_FITNESS",
                    "intensity_code": template.get(
                        "default_intensity", enrichment.get("intensity_level", "MODERATE")
                    ),
                    "phase_code": "MAIN" if timing == "REPS" else "WARMUP",
                    "prescription_version": "prescription-set-v2.0.2-draft",
                    "sets": number(template.get("default_sets")),
                    "reps": number(template.get("default_reps")) if timing == "REPS" else None,
                    "work_seconds_per_set": number(template.get("default_work_seconds"))
                    if timing == "DURATION"
                    else None,
                    "rest_seconds_per_set": number(template.get("default_rest_seconds")),
                    "user_review_decision_code": "USER_DIRECT_REVIEW_2026_08_29",
                    "user_review_status": "COMPLETED",
                    "review_status_code": "DOMAIN_APPROVED"
                    if template_resolution == "DIRECT_TEMPLATE_MATCH"
                    else "REVIEW_REQUIRED",
                    "production_eligible": False,
                    "binding_source": "catalog_enrichment_v3_fitt.csv",
                    "binding_source_exercise_id": nex_id,
                    "binding_match_method": match_method,
                    "template_resolution_code": template_resolution,
                    "source_fitt_template_id": enrichment.get("fitt_template_id", ""),
                    "materialization_version": MATERIALIZATION_VERSION,
                }
            )
        for safety in safety_by_nex[nex_id]:
            mapped = deepcopy(safety)
            mapped["exercise_stable_code"] = code
            mapped["catalog_version_code"] = CATALOG_VERSION
            mapped["review_status_code"] = "DOMAIN_APPROVED"
            mapped["production_eligible"] = False
            mapped["binding_source"] = "exercise_safety_mapping_v2.csv"
            mapped["binding_source_exercise_id"] = nex_id
            mapped["binding_match_method"] = match_method
            mapped["materialization_version"] = MATERIALIZATION_VERSION
            generated_safety.append(mapped)
        goal = lookup["n2stable"].get(nex_id)
        if goal:
            mapped_goal = deepcopy(goal)
            mapped_goal["exercise_stable_code"] = code
            mapped_goal["catalog_version_code"] = CATALOG_VERSION
            mapped_goal["review_status_code"] = "DOMAIN_APPROVED"
            mapped_goal["status_interpretation"] = "SOURCE_EXERCISE_NAME_OR_NEX_MAPPING"
            mapped_goal["binding_source"] = "v2.0.2-draft/prescriptions/goal_tag_links.jsonl"
            mapped_goal["binding_source_exercise_id"] = nex_id
            mapped_goal["binding_match_method"] = match_method
            mapped_goal["materialization_version"] = MATERIALIZATION_VERSION
            generated_goals.append(mapped_goal)
        fitt_status_code = "DOMAIN_APPROVED" if not template_fallbacks else "REVIEW_REQUIRED"
        mappings[code] = {
            "exercise_id": row["exercise_id"],
            "stable_code": code,
            "representative_exercise_id": row.get("representative_exercise_id", ""),
            "variant_type_code": row.get("variant_type_code", ""),
            "safety_mapping_status_code": "DOMAIN_APPROVED",
            "safety_mapping_source_representative_exercise_id": row.get(
                "representative_exercise_id", ""
            ),
            "safety_rule_binding_status_code": "BOUND_INDEPENDENT_SOURCE",
            "fitt_mapping_status_code": fitt_status_code,
            "fitt_mapping_source_representative_exercise_id": row.get(
                "representative_exercise_id", ""
            ),
            "fitt_template_ids_by_experience": fitt_ids,
            "review_status_code": "DOMAIN_APPROVED",
            "production_eligible": False,
            "binding_source_exercise_id": nex_id,
            "binding_match_method": match_method,
            "fitt_template_resolution_codes": template_fallbacks,
            "materialization_version": MATERIALIZATION_VERSION,
        }

    # Replace only target bindings; representative rows remain untouched.
    old_fitt = [
        row
        for row in read_jsonl(final_dir / "prescriptions/prescription_profiles.jsonl")
        if row.get("exercise_stable_code") not in target_codes
    ]
    old_safety = [
        row
        for row in read_jsonl(final_dir / "runtime/safety_rules.jsonl")
        if row.get("exercise_stable_code") not in target_codes
    ]
    old_goals = [
        row
        for row in read_jsonl(final_dir / "prescriptions/goal_tag_links.jsonl")
        if row.get("exercise_stable_code") not in target_codes
    ]
    fitt = sorted(
        old_fitt + generated_fitt,
        key=lambda row: (
            str(row.get("exercise_stable_code")),
            str(row.get("experience_level_code")),
            str(row.get("phase_code")),
        ),
    )
    safety = sorted(
        old_safety + generated_safety,
        key=lambda row: (
            str(row.get("exercise_stable_code")),
            str(row.get("body_area_code")),
            str(row.get("effect_code")),
        ),
    )
    goals = sorted(
        old_goals + generated_goals, key=lambda row: str(row.get("exercise_stable_code"))
    )
    for row in catalog:
        mapping = mappings.get(str(row.get("stable_code")))
        if mapping:
            row.update(
                {
                    "safety_mapping_status_code": "DOMAIN_APPROVED",
                    "safety_rule_binding_status_code": "BOUND_INDEPENDENT_SOURCE",
                    "fitt_mapping_status_code": mapping["fitt_mapping_status_code"],
                    "fitt_mapping_source_representative_exercise_id": mapping[
                        "representative_exercise_id"
                    ],
                    "fitt_template_ids_by_experience": mapping["fitt_template_ids_by_experience"],
                    "fitt_allowed_experience_level_codes": sorted(
                        mapping["fitt_template_ids_by_experience"]
                    ),
                    "review_required_codes": [
                        code
                        for code in row.get("review_required_codes", [])
                        if code
                        not in {
                            "INDEPENDENT_SAFETY_RULE_REVIEW_REQUIRED",
                            "GOAL_ROLE_REVIEW_REQUIRED",
                        }
                        and (
                            mapping["fitt_mapping_status_code"] == "DOMAIN_APPROVED"
                            or code != "INDEPENDENT_FITT_REVIEW_REQUIRED"
                        )
                    ],
                }
            )
    bindings = read_jsonl(final_dir / "audit/reference_binding_status_v2_0_2.jsonl")
    for binding in bindings:
        mapping = mappings.get(str(binding.get("stable_code")))
        if mapping:
            binding.update(
                {
                    "safety_binding_state_code": "AVAILABLE",
                    "fitt_binding_state_code": "AVAILABLE",
                    "goal_binding_state_code": "AVAILABLE",
                    "binding_state_reason_code": "INDEPENDENT_SOURCE_DATA_MATERIALIZED",
                    "production_eligible": False,
                }
            )
    write_jsonl(catalog_path, catalog)
    write_csv(final_dir / "audit/catalog/exercises.csv", catalog)
    write_jsonl(final_dir / "audit/runtime/catalog.jsonl", catalog)
    write_jsonl(final_dir / "runtime/safety_rules.jsonl", safety)
    write_jsonl(final_dir / "prescriptions/prescription_profiles.jsonl", fitt)
    write_jsonl(final_dir / "prescriptions/goal_tag_links.jsonl", goals)
    write_jsonl(
        final_dir / "audit/variant_safety_fitt_mapping_v2_0_2.jsonl", list(mappings.values())
    )
    write_csv(final_dir / "audit/variant_safety_fitt_mapping_v2_0_2.csv", list(mappings.values()))
    write_jsonl(final_dir / "audit/reference_binding_status_v2_0_2.jsonl", bindings)
    write_csv(final_dir / "audit/reference_binding_status_v2_0_2.csv", bindings)
    manifest_path = final_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["reference_repair"]["safety_fitt_goal_values_generated"] = True
    manifest["independent_bindings_materialization"] = {
        "version": MATERIALIZATION_VERSION,
        "source_files": {
            "fitt_enrichment": source_metadata(ENRICHMENT),
            "safety_mapping": source_metadata(SAFETY_SOURCE),
            "goal_links": source_metadata(GOAL_SOURCE),
        },
        "target_record_count": len(targets),
        "materialized_record_count": len(mappings),
    }
    hashed_paths = [
        "catalog/exercises.jsonl",
        "audit/catalog/exercises.csv",
        "audit/runtime/catalog.jsonl",
        "runtime/safety_rules.jsonl",
        "prescriptions/prescription_profiles.jsonl",
        "prescriptions/goal_tag_links.jsonl",
        "audit/reference_binding_status_v2_0_2.jsonl",
        "audit/reference_binding_status_v2_0_2.csv",
        "audit/variant_safety_fitt_mapping_v2_0_2.jsonl",
        "audit/variant_safety_fitt_mapping_v2_0_2.csv",
    ]
    for relative in hashed_paths:
        path = final_dir / relative
        manifest.setdefault("artifact_sha256", {})[relative] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = {
        "schema_version": "exercise-catalog-v2.0.2-independent-bindings-materialization-v1",
        "catalog_version_code": CATALOG_VERSION,
        "materialization_version": MATERIALIZATION_VERSION,
        "production_eligible": False,
        "source_files": {
            "fitt_enrichment": source_metadata(ENRICHMENT),
            "safety_mapping": source_metadata(SAFETY_SOURCE),
            "old_nex_mapping": source_metadata(OLD_CATALOG),
            "goal_links": source_metadata(GOAL_SOURCE),
        },
        "target_record_count": len(targets),
        "materialized_record_count": len(mappings),
        "unmatched_record_count": len(unmatched),
        "fitt_row_count_added": len(generated_fitt),
        "safety_row_count_added": len(generated_safety),
        "goal_row_count_added": len(generated_goals),
        "match_method_counts": dict(
            Counter(item["binding_match_method"] for item in mappings.values())
        ),
        "unmatched": unmatched,
    }
    write_json(
        final_dir / "audit/integrity/independent_bindings_materialization_report_v2_0_2.json",
        report,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final-dir", type=Path, default=FINAL)
    args = parser.parse_args()
    print(json.dumps(build(args.final_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
