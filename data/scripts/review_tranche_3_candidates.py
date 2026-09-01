"""Apply and verify the complete agent-only tranche 3 review decision."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from build_exercise_catalog_seed import (
    BODY_AREA_CODES,
    DIFFICULTY_CODES,
    TIMING_MODE_CODES,
    load_taxonomy_registry,
)
from korean_display_name_rules import display_name_problems, duplicate_display_names
from kspo_fitness100_pipeline import PipelineError, sha256_bytes

DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
DEFAULT_PLAN = DATA_ROOT / "normalized" / "review_tranche_3.agent.json"
DEFAULT_OUTPUT = DATA_ROOT / "validation" / "review_results" / "review_tranche_3_results.json"
TAXONOMY = DATA_ROOT / "normalized" / "exercise_taxonomy_codes.json"
ROLE_STATUS = {
    "DATA_OWNER": "TECH_REVIEWED",
    "BACKEND_REVIEWER": "TECH_REVIEWED",
    "PM_REVIEWER": "TECH_REVIEWED",
    "DOMAIN_REVIEWER": "DOMAIN_APPROVED",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"JSON is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON is invalid: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"JSON root must be an object: {path}")
    return value


def repo_path(value: object) -> Path:
    path = Path(str(value))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise PipelineError(f"repository path is unsafe: {value}")
    return REPO_ROOT / path


def verified_reference(value: object, label: str) -> Path:
    if not isinstance(value, dict):
        raise PipelineError(f"{label} reference must be an object")
    path = repo_path(value.get("path"))
    if sha256_bytes(path.read_bytes()) != value.get("sha256"):
        raise PipelineError(f"{label} hash does not match")
    return path


def review_roles(policy: dict[str, Any]) -> dict[str, str]:
    if (
        policy.get("status") != "APPROVED_FOR_DRAFT_PIPELINE"
        or policy.get("review_method_code") != "AGENT_ONLY"
        or policy.get("production_eligible") is not False
    ):
        raise PipelineError("agent review policy state is invalid")
    roles = policy.get("roles")
    if not isinstance(roles, list):
        raise PipelineError("agent review policy has no roles")
    references = {
        str(role.get("reviewer_role_code")): str(role.get("reviewer_reference"))
        for role in roles
        if isinstance(role, dict)
    }
    if set(references) != set(ROLE_STATUS) or any(not value for value in references.values()):
        raise PipelineError("agent review policy role references are incomplete")
    return references


def existing_catalog_values(plan: dict[str, Any]) -> tuple[set[str], list[str]]:
    paths = plan.get("existing_catalogs")
    if not isinstance(paths, list) or not paths:
        raise PipelineError("review plan has no existing catalogs")
    codes: set[str] = set()
    names: list[str] = []
    for value in paths:
        directory = repo_path(value)
        manifest = load_json(directory / "seed_manifest.json")
        files = manifest.get("files")
        raw = (directory / "exercises.jsonl").read_bytes()
        if (
            not isinstance(files, list)
            or not files
            or not isinstance(files[0], dict)
            or files[0].get("sha256") != sha256_bytes(raw)
        ):
            raise PipelineError(f"existing catalog hash is invalid: {directory.name}")
        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            code = str(row.get("stable_code", ""))
            name = str(row.get("name_ko", ""))
            if not code or code in codes or not name:
                raise PipelineError("existing catalog contains a blank or duplicate value")
            codes.add(code)
            names.append(name)
    return codes, names


def positive_int(spec: dict[str, Any], field: str, *, allow_zero: bool = False) -> int:
    value = spec.get(field)
    minimum = 0 if allow_zero else 1
    if not isinstance(value, int) or value < minimum:
        raise PipelineError(f"include {field} must be an integer >= {minimum}")
    return value


def nonempty_codes(spec: dict[str, Any], field: str, allowed: set[str]) -> list[str]:
    values = spec.get(field)
    if not isinstance(values, list) or not values or any(value not in allowed for value in values):
        raise PipelineError(f"include {field} contains a missing or unapproved code")
    if len(values) != len(set(values)):
        raise PipelineError(f"include {field} contains duplicate codes")
    return [str(value) for value in values]


def validate_include(spec: dict[str, Any], registry: dict[str, set[str]]) -> dict[str, Any]:
    stable_code = str(spec.get("stable_code", ""))
    if not re.fullmatch(r"[a-z][a-z0-9_]+", stable_code):
        raise PipelineError(f"include stable code is invalid: {stable_code}")
    name = str(spec.get("name_ko", "")).strip()
    problems = display_name_problems(name)
    if problems:
        raise PipelineError(f"include display name is invalid: {problems[0]}")
    for field, registry_name in (
        ("training_type_code", "training_type_code"),
        ("body_focus_code", "body_focus_code"),
        ("movement_pattern_code", "movement_pattern_code"),
    ):
        if spec.get(field) not in registry[registry_name]:
            raise PipelineError(f"include {field} is not approved: {spec.get(field)}")
    if spec.get("difficulty_code") not in DIFFICULTY_CODES:
        raise PipelineError("include difficulty_code is invalid")
    if spec.get("beginner_suitability") not in {"YES", "CONDITIONAL"}:
        raise PipelineError("include beginner_suitability is invalid")
    timing = spec.get("timing_mode_code")
    if timing not in TIMING_MODE_CODES:
        raise PipelineError("include timing_mode_code is invalid")
    if timing == "REPS":
        positive_int(spec, "default_seconds_per_rep")
    else:
        positive_int(spec, "default_work_seconds")
    positive_int(spec, "default_rest_seconds", allow_zero=True)
    if not isinstance(spec.get("recovery_eligible"), bool):
        raise PipelineError("include recovery_eligible must be boolean")
    nonempty_codes(spec, "primary_body_area_codes", set(BODY_AREA_CODES))
    secondary = spec.get("secondary_body_area_codes")
    if not isinstance(secondary, list) or any(value not in BODY_AREA_CODES for value in secondary):
        raise PipelineError("include secondary_body_area_codes contains an invalid code")
    nonempty_codes(spec, "equipment_codes", registry["equipment_code"])
    nonempty_codes(spec, "location_codes", registry["location_code"])
    if not str(spec.get("instruction_summary_ko", "")).strip():
        raise PipelineError("include instruction summary is empty")
    cues = spec.get("form_cues_ko")
    if not isinstance(cues, list) or len(cues) < 3 or any(not str(cue).strip() for cue in cues):
        raise PipelineError("include needs at least three form cues")
    return spec


def build_results(plan_path: Path) -> dict[str, object]:
    plan = load_json(plan_path)
    if (
        plan.get("status") != "AGENT_REVIEWED_DRAFT"
        or plan.get("review_method_code") != "AGENT_ONLY"
        or plan.get("production_eligible") is not False
    ):
        raise PipelineError("review plan state is invalid")
    reviewed_at = str(plan.get("reviewed_at", ""))
    try:
        parsed_at = datetime.fromisoformat(reviewed_at)
    except ValueError as exc:
        raise PipelineError("reviewed_at is not ISO 8601") from exc
    if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
        raise PipelineError("reviewed_at must include timezone information")

    queue_path = verified_reference(plan.get("queue"), "candidate queue")
    policy_path = verified_reference(plan.get("review_policy"), "review policy")
    queue = load_json(queue_path)
    policy = load_json(policy_path)
    role_references = review_roles(policy)
    records = queue.get("records")
    if not isinstance(records, list) or not records:
        raise PipelineError("candidate queue has no records")
    by_position = {
        int(record["queue_position"]): record for record in records if isinstance(record, dict)
    }
    if len(by_position) != len(records):
        raise PipelineError("candidate queue positions are invalid or duplicated")

    includes_raw = plan.get("includes")
    excludes_raw = plan.get("excludes")
    if not isinstance(includes_raw, list) or not isinstance(excludes_raw, list):
        raise PipelineError("review plan must define includes and excludes")
    includes = {
        int(spec["queue_position"]): spec for spec in includes_raw if isinstance(spec, dict)
    }
    excludes = {
        int(spec["queue_position"]): spec for spec in excludes_raw if isinstance(spec, dict)
    }
    if len(includes) != len(includes_raw) or len(excludes) != len(excludes_raw):
        raise PipelineError("review plan positions are invalid or duplicated")
    if set(includes) & set(excludes) or set(includes) | set(excludes) != set(by_position):
        raise PipelineError("review plan must partition every candidate exactly once")

    registry = load_taxonomy_registry(TAXONOMY)
    existing_codes, existing_names = existing_catalog_values(plan)
    reviewed_includes = [validate_include(spec, registry) for spec in includes.values()]
    new_codes = [str(spec["stable_code"]) for spec in reviewed_includes]
    new_names = [str(spec["name_ko"]) for spec in reviewed_includes]
    if len(new_codes) != len(set(new_codes)) or set(new_codes) & existing_codes:
        raise PipelineError("included stable codes are duplicated in new or existing catalogs")
    duplicates = duplicate_display_names([*existing_names, *new_names])
    if duplicates:
        raise PipelineError(f"included display names are duplicated: {', '.join(duplicates)}")

    output_records: list[dict[str, object]] = []
    for position in sorted(by_position):
        source = by_position[position]
        decision = "INCLUDE" if position in includes else "EXCLUDE"
        evidence = [
            {
                "reviewer_role_code": role,
                "review_status_code": status,
                "reviewer_reference": role_references[role],
                "evidence_reference": plan_path.resolve().relative_to(REPO_ROOT).as_posix(),
                "reviewed_at": reviewed_at,
            }
            for role, status in ROLE_STATUS.items()
        ]
        record: dict[str, object] = {
            "queue_position": position,
            "track": source["track"],
            "source_identity": source["source_identity"],
            "source_name": source["source_facts"]["source_name"],
            "review_decision": decision,
            "review_status": "DOMAIN_APPROVED",
            "review_method_code": "AGENT_ONLY",
            "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
            "production_eligible": False,
            "evidence": evidence,
        }
        if decision == "INCLUDE":
            record["attributes"] = includes[position]
        else:
            exclusion = excludes[position]
            reason_code = str(exclusion.get("reason_code", ""))
            reason_ko = str(exclusion.get("reason_ko", "")).strip()
            if not re.fullmatch(r"[A-Z0-9_]+", reason_code) or not reason_ko:
                raise PipelineError("exclusion reason is invalid")
            record["exclusion"] = {"reason_code": reason_code, "reason_ko": reason_ko}
        output_records.append(record)

    return {
        "schema_version": "1.0",
        "result_version": plan.get("plan_version"),
        "status": "AGENT_REVIEWED_DRAFT",
        "review_method_code": "AGENT_ONLY",
        "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
        "production_eligible": False,
        "reviewed_at": reviewed_at,
        "inputs": {
            "queue_path": queue_path.relative_to(REPO_ROOT).as_posix(),
            "queue_sha256": sha256_bytes(queue_path.read_bytes()),
            "plan_path": plan_path.resolve().relative_to(REPO_ROOT).as_posix(),
            "plan_sha256": sha256_bytes(plan_path.read_bytes()),
            "policy_path": policy_path.relative_to(REPO_ROOT).as_posix(),
            "policy_sha256": sha256_bytes(policy_path.read_bytes()),
            "taxonomy_sha256": sha256_bytes(TAXONOMY.read_bytes()),
        },
        "summary": {
            "candidate_count": len(output_records),
            "included": len(includes),
            "excluded": len(excludes),
            "track_included": {
                track: sum(
                    record["track"] == track and record["review_decision"] == "INCLUDE"
                    for record in output_records
                )
                for track in ("kspo", "wger")
            },
        },
        "records": output_records,
    }


def write_results(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_results(plan_path: Path, output_path: Path) -> dict[str, object]:
    expected = build_results(plan_path)
    actual = load_json(output_path)
    if actual != expected:
        raise PipelineError("tranche 3 results do not match verified review inputs")
    summary = actual.get("summary")
    assert isinstance(summary, dict)
    return {"status": "valid", **summary}


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    build.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    verify.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "build":
            write_results(args.output, build_results(args.plan))
        result = verify_results(args.plan, args.output)
    except (PipelineError, OSError, ValueError, KeyError, AssertionError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
