"""Apply a complete, production-ineligible agent review plan to review CSVs.

This command is intentionally narrower than a generic review editor. It only
accepts a plan that partitions every currently PENDING mapping row into an
INCLUDE or EXCLUDE decision, keeps existing decisions unchanged, and records
agent-only provenance on every newly included exercise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from build_exercise_catalog_seed import ATTRIBUTE_FIELDS, TRACKS, TrackSpec, read_csv, write_csv
from korean_display_name_rules import display_name_problems, duplicate_display_names
from kspo_fitness100_pipeline import PipelineError

ROLE_STATUS = {
    "DATA_OWNER": "TECH_REVIEWED",
    "BACKEND_REVIEWER": "TECH_REVIEWED",
    "PM_REVIEWER": "TECH_REVIEWED",
    "DOMAIN_REVIEWER": "DOMAIN_APPROVED",
}
AGENT_DRAFT_SOURCE = "AGENT_REVIEW_v2.0.0"


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"JSON is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise PipelineError(f"JSON root must be an object: {path}")
    return payload


def plan_for_track(payload: dict[str, Any], track: TrackSpec) -> dict[str, Any]:
    if payload.get("status") != "AGENT_REVIEWED_DRAFT":
        raise PipelineError("review plan must have status AGENT_REVIEWED_DRAFT")
    if payload.get("review_method_code") != "AGENT_ONLY":
        raise PipelineError("review plan must use review_method_code AGENT_ONLY")
    if payload.get("production_eligible") is not False:
        raise PipelineError("agent-only review plan must remain production-ineligible")
    tranches = payload.get("tranches")
    if not isinstance(tranches, list):
        raise PipelineError("review plan has no tranches list")
    for tranche in tranches:
        if isinstance(tranche, dict) and tranche.get("track") == track.name:
            return tranche
    raise PipelineError(f"review plan has no tranche for {track.name}")


def reviewer_references(policy: dict[str, Any]) -> dict[str, str]:
    if policy.get("review_method_code") != "AGENT_ONLY":
        raise PipelineError("review policy must use AGENT_ONLY")
    if policy.get("production_eligible") is not False:
        raise PipelineError("review policy must remain production-ineligible")
    roles = policy.get("roles")
    if not isinstance(roles, list):
        raise PipelineError("review policy has no roles list")
    result = {
        str(role.get("reviewer_role_code", "")): str(role.get("reviewer_reference", ""))
        for role in roles
        if isinstance(role, dict)
    }
    if set(result) != set(ROLE_STATUS) or any(not value for value in result.values()):
        raise PipelineError("review policy must define all four reviewer references")
    return result


def positions_from_plan(
    tranche: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    includes_raw = tranche.get("includes")
    excludes_raw = tranche.get("exclude_groups")
    if not isinstance(includes_raw, list) or not isinstance(excludes_raw, list):
        raise PipelineError("tranche must define includes and exclude_groups")

    includes: dict[str, dict[str, Any]] = {}
    for item in includes_raw:
        if not isinstance(item, dict):
            raise PipelineError("include entry must be an object")
        position = str(item.get("batch_position", ""))
        if not position or position in includes:
            raise PipelineError(f"duplicate or missing include position: {position}")
        includes[position] = item

    excludes: dict[str, dict[str, str]] = {}
    for group in excludes_raw:
        if not isinstance(group, dict) or not isinstance(group.get("positions"), list):
            raise PipelineError("exclude group must define positions")
        reason_code = str(group.get("reason_code", ""))
        reason_ko = str(group.get("reason_ko", ""))
        if not reason_code or not reason_ko:
            raise PipelineError("exclude group must define a code and Korean reason")
        for raw_position in group["positions"]:
            position = str(raw_position)
            if position in excludes:
                raise PipelineError(f"duplicate exclude position: {position}")
            excludes[position] = {"reason_code": reason_code, "reason_ko": reason_ko}

    overlap = set(includes) & set(excludes)
    if overlap:
        raise PipelineError(f"include/exclude positions overlap: {', '.join(sorted(overlap))}")
    return includes, excludes


def _joined(value: Any) -> str:
    if not isinstance(value, list) or not value or any(not str(item).strip() for item in value):
        raise PipelineError("reviewed list attribute must contain at least one non-empty value")
    return " | ".join(str(item).strip() for item in value)


def _attribute_row(
    track: TrackSpec, mapping_row: dict[str, str], spec: dict[str, Any]
) -> dict[str, object]:
    name_ko = str(spec.get("name_ko", "")).strip()
    source_name = mapping_row[track.source_name_field]
    problems = display_name_problems(name_ko, source_name=source_name)
    if problems:
        raise PipelineError(
            f"display name at position {mapping_row['batch_position']}: {problems[0]}"
        )
    form_cues = spec.get("form_cues_ko")
    if not isinstance(form_cues, list) or len(form_cues) < 3:
        raise PipelineError(
            f"position {mapping_row['batch_position']} needs at least three form cues"
        )
    timing_mode = str(spec.get("timing_mode_code", ""))
    seconds_per_rep = spec.get("default_seconds_per_rep", "") if timing_mode == "REPS" else ""
    work_seconds = spec.get("default_work_seconds", "") if timing_mode == "DURATION" else ""
    return {
        "source_identity": mapping_row[track.identity_field],
        "review_normalized_exercise_id": str(spec.get("stable_code", "")).strip(),
        "review_display_name_ko": name_ko,
        "training_type_code": spec.get("training_type_code", ""),
        "body_focus_code": spec.get("body_focus_code", ""),
        "primary_movement_pattern_code": spec.get("movement_pattern_code", ""),
        "difficulty_code": spec.get("difficulty_code", ""),
        "timing_mode_code": timing_mode,
        "default_seconds_per_rep": seconds_per_rep,
        "default_work_seconds": work_seconds,
        "default_rest_seconds": spec.get("default_rest_seconds", ""),
        "default_transition_seconds": 15,
        "recovery_eligible": str(bool(spec.get("recovery_eligible"))).upper(),
        "primary_body_area_codes": _joined(spec.get("primary_body_area_codes")),
        "secondary_body_area_codes": _joined(spec.get("secondary_body_area_codes")),
        "equipment_codes": _joined(spec.get("equipment_codes")),
        "location_codes": _joined(spec.get("location_codes")),
        "instruction_summary_ko": str(spec.get("instruction_summary_ko", "")).strip(),
        "form_cues_ko": _joined(form_cues),
        "instruction_content_version": "1.0.0",
        "draft_source": AGENT_DRAFT_SOURCE,
        "attribute_status": "DOMAIN_APPROVED",
    }


def apply_plan(
    track: TrackSpec,
    plan_path: Path,
    policy_path: Path,
    mapping_path: Path,
    evidence_path: Path,
    attributes_path: Path,
    mapping_out: Path,
    evidence_out: Path,
    attributes_out: Path,
) -> dict[str, object]:
    plan = load_json(plan_path)
    policy = load_json(policy_path)
    tranche = plan_for_track(plan, track)
    role_references = reviewer_references(policy)
    includes, excludes = positions_from_plan(tranche)

    mapping_rows = read_csv(mapping_path)
    evidence_rows = read_csv(evidence_path)
    attribute_rows = read_csv(attributes_path, ATTRIBUTE_FIELDS)
    if not mapping_rows or not evidence_rows:
        raise PipelineError("mapping and evidence inputs must not be empty")

    mapping_fields = list(mapping_rows[0])
    evidence_fields = list(evidence_rows[0])
    by_position = {row["batch_position"]: row for row in mapping_rows}
    pending = {
        position
        for position, row in by_position.items()
        if row["review_decision"].strip() == "PENDING"
    }
    planned = set(includes) | set(excludes)
    if planned != pending:
        missing = sorted(pending - planned, key=int)
        extra = sorted(planned - pending, key=int)
        raise PipelineError(
            f"plan must partition all pending rows; missing={missing}, extra={extra}"
        )

    reviewed_at = str(plan.get("reviewed_at", "")).strip()
    if not reviewed_at:
        raise PipelineError("review plan must define reviewed_at")
    evidence_reference = plan_path.as_posix()

    evidence_by_identity_and_role = {
        (row[track.identity_field], row["reviewer_role_code"]): row for row in evidence_rows
    }
    new_attributes: list[dict[str, object]] = []
    for position, spec in includes.items():
        row = by_position[position]
        attribute = _attribute_row(track, row, spec)
        stable_code = str(attribute["review_normalized_exercise_id"])
        if not stable_code:
            raise PipelineError(f"position {position} has no stable code")
        row["review_normalized_exercise_id"] = stable_code
        row["review_display_name_ko"] = str(attribute["review_display_name_ko"])
        row["review_taxonomy_code"] = str(spec.get("movement_pattern_code", ""))
        row["review_beginner_suitability"] = str(spec.get("beginner_suitability", ""))
        row["review_execution_guidance_status"] = "APPROVED"
        if track.name == "wger":
            row["review_license_status"] = "APPROVED"
        else:
            row["review_media_rights_status"] = "APPROVED"
        row["review_domain_safety_status"] = "APPROVED"
        row["review_decision"] = "INCLUDE"
        row["reviewer_notes"] = (
            f"AGENT_ONLY {plan.get('plan_version')}: 일반 운동 정보 기준 DRAFT 검토. "
            "외부 전문가 승인이 아니며 production_eligible=false."
        )
        for role, status in ROLE_STATUS.items():
            evidence = evidence_by_identity_and_role.get((row[track.identity_field], role))
            if evidence is None:
                raise PipelineError(f"missing {role} evidence row for position {position}")
            evidence["review_status_code"] = status
            evidence["reviewer_reference"] = role_references[role]
            evidence["evidence_reference"] = evidence_reference
            evidence["reviewed_at"] = reviewed_at
        new_attributes.append(attribute)

    for position, reason in excludes.items():
        row = by_position[position]
        row["review_decision"] = "EXCLUDE"
        row["reviewer_notes"] = (
            f"AGENT_ONLY {plan.get('plan_version')} EXCLUDE/{reason['reason_code']}: "
            f"{reason['reason_ko']} production_eligible=false."
        )

    merged_attributes: list[dict[str, object]] = [
        *(cast(dict[str, object], row) for row in attribute_rows),
        *new_attributes,
    ]
    stable_codes = [str(row["review_normalized_exercise_id"]).strip() for row in merged_attributes]
    if any(not code for code in stable_codes) or len(stable_codes) != len(set(stable_codes)):
        raise PipelineError("attributes contain blank or duplicate stable codes")
    names = [str(row["review_display_name_ko"]).strip() for row in merged_attributes]
    duplicates = duplicate_display_names(names)
    if duplicates:
        raise PipelineError(f"attributes contain duplicate Korean names: {', '.join(duplicates)}")

    mapping_out.parent.mkdir(parents=True, exist_ok=True)
    evidence_out.parent.mkdir(parents=True, exist_ok=True)
    attributes_out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(mapping_out, mapping_fields, cast(list[dict[str, object]], mapping_rows))
    write_csv(evidence_out, evidence_fields, cast(list[dict[str, object]], evidence_rows))
    write_csv(attributes_out, ATTRIBUTE_FIELDS, merged_attributes)
    return {
        "track": track.name,
        "included": len(includes),
        "excluded": len(excludes),
        "previously_reviewed": len(mapping_rows) - len(pending),
        "remaining_pending": 0,
        "attribute_rows": len(merged_attributes),
        "review_method_code": "AGENT_ONLY",
        "production_eligible": False,
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("track", choices=sorted(TRACKS))
    parser.add_argument("plan", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("attributes", type=Path)
    parser.add_argument("--mapping-out", type=Path, required=True)
    parser.add_argument("--evidence-out", type=Path, required=True)
    parser.add_argument("--attributes-out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        result = apply_plan(
            TRACKS[args.track],
            args.plan,
            args.policy,
            args.mapping,
            args.evidence,
            args.attributes,
            args.mapping_out,
            args.evidence_out,
            args.attributes_out,
        )
    except (PipelineError, OSError, KeyError, ValueError, TypeError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
