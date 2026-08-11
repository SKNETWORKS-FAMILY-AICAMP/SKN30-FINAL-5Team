"""Build and verify a traceable, production-ineligible follow-up candidate queue."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from kspo_fitness100_pipeline import PipelineError, sha256_bytes
from profile_kspo_fitness100 import verify_profile as verify_kspo_profile
from profile_wger_exercises import verify_profile as verify_wger_profile

DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
DEFAULT_POLICY = DATA_ROOT / "normalized" / "review_tranche_3_selection.json"
DEFAULT_OUTPUT = DATA_ROOT / "normalized" / "review_tranche_3_candidates.json"
IDENTITY_FIELDS = {"kspo": "source_candidate_id", "wger": "source_exercise_id"}


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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise PipelineError(f"JSONL is missing: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"JSONL line {line_number} is invalid: {path}") from exc
        if not isinstance(value, dict):
            raise PipelineError(f"JSONL line {line_number} is not an object: {path}")
        rows.append(value)
    return rows


def repo_path(value: object) -> Path:
    text = str(value).strip()
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise PipelineError(f"repository path is unsafe: {text}")
    return REPO_ROOT / path


def taxonomy_patterns() -> set[str]:
    registry = load_json(DATA_ROOT / "normalized" / "exercise_taxonomy_codes.json")
    if registry.get("status") != "APPROVED":
        raise PipelineError("exercise taxonomy registry is not approved")
    code_sets = registry.get("code_sets")
    if not isinstance(code_sets, dict):
        raise PipelineError("taxonomy registry has no code_sets")
    values = code_sets.get("movement_pattern_code")
    if not isinstance(values, list):
        raise PipelineError("taxonomy registry has no movement pattern codes")
    return {str(item.get("code")) for item in values if isinstance(item, dict)}


def source_name(track: str, row: dict[str, Any]) -> str:
    if track == "kspo":
        return str(row.get("source_training_name", "")).strip()
    names = row.get("source_names_en")
    if not isinstance(names, list) or not names:
        raise PipelineError("wger candidate has no English source name")
    return sorted(str(name).strip() for name in names if str(name).strip())[0]


def source_facts(track: str, row: dict[str, Any]) -> dict[str, object]:
    if track == "kspo":
        return {
            "source_name": source_name(track, row),
            "source_file_name": row.get("source_file_name"),
            "places": row.get("places", []),
            "tools": row.get("tools", []),
            "age_groups": row.get("age_groups", []),
            "source_frame_rows": row.get("source_frame_rows"),
        }
    category = row.get("source_category")
    equipment = row.get("source_equipment")
    license_value = row.get("source_base_license")
    if not isinstance(category, dict) or not isinstance(equipment, list):
        raise PipelineError("wger candidate source metadata is malformed")
    if not isinstance(license_value, dict):
        raise PipelineError("wger candidate source license is malformed")
    return {
        "source_name": source_name(track, row),
        "source_exercise_uuid": row.get("source_exercise_uuid"),
        "source_category": category.get("name"),
        "source_equipment": [
            item.get("name") for item in equipment if isinstance(item, dict) and item.get("name")
        ],
        "source_license": {
            "short_name": license_value.get("short_name"),
            "url": license_value.get("url"),
            "author": license_value.get("license_author"),
        },
    }


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("status") != "DRAFT":
        raise PipelineError("selection policy must remain DRAFT")
    if policy.get("review_method_code") != "AGENT_ONLY":
        raise PipelineError("selection policy must use AGENT_ONLY")
    if policy.get("production_eligible") is not False:
        raise PipelineError("selection policy must remain production-ineligible")
    guards = policy.get("interpretation_guards")
    if not isinstance(guards, list) or "SELECTION_IS_NOT_CATALOG_INCLUSION" not in guards:
        raise PipelineError("selection policy is missing its catalog guard")
    if not isinstance(policy.get("sources"), dict) or not isinstance(
        policy.get("candidates"), list
    ):
        raise PipelineError("selection policy sources or candidates are missing")


def build_payload(policy_path: Path) -> dict[str, object]:
    policy = load_json(policy_path)
    validate_policy(policy)
    allowed_patterns = taxonomy_patterns()
    sources = policy["sources"]
    candidates = policy["candidates"]
    assert isinstance(sources, dict) and isinstance(candidates, list)

    inventories: dict[str, dict[object, dict[str, Any]]] = {}
    excluded: dict[str, set[object]] = {}
    profile_provenance: dict[str, object] = {}
    for track in IDENTITY_FIELDS:
        config = sources.get(track)
        if not isinstance(config, dict):
            raise PipelineError(f"selection policy has no source config for {track}")
        profile_dir = repo_path(config.get("profile_directory"))
        if track == "kspo":
            verify_kspo_profile(profile_dir)
        else:
            verify_wger_profile(profile_dir)
        inventory_path = profile_dir / str(config.get("inventory_file", ""))
        rows = load_jsonl(inventory_path)
        identity_field = IDENTITY_FIELDS[track]
        inventories[track] = {row.get(identity_field): row for row in rows}
        if None in inventories[track] or len(inventories[track]) != len(rows):
            raise PipelineError(f"{track} inventory contains missing or duplicate identities")
        batch_path = repo_path(config.get("excluded_review_batch"))
        batch_rows = load_jsonl(batch_path)
        excluded[track] = {row.get(identity_field) for row in batch_rows}
        manifest_path = profile_dir / "profile_manifest.json"
        profile_provenance[track] = {
            "profile_directory": profile_dir.relative_to(REPO_ROOT).as_posix(),
            "profile_manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "inventory_sha256": sha256_bytes(inventory_path.read_bytes()),
            "excluded_review_batch": batch_path.relative_to(REPO_ROOT).as_posix(),
            "excluded_review_batch_sha256": sha256_bytes(batch_path.read_bytes()),
        }

    records: list[dict[str, object]] = []
    seen: set[tuple[str, object]] = set()
    for position, spec_value in enumerate(candidates, start=1):
        if not isinstance(spec_value, dict):
            raise PipelineError("candidate selection entry must be an object")
        track = str(spec_value.get("track", ""))
        identity = spec_value.get("source_identity")
        key = (track, identity)
        if track not in IDENTITY_FIELDS or identity is None or key in seen:
            raise PipelineError(f"candidate track or identity is invalid: {key}")
        seen.add(key)
        if identity in excluded[track]:
            raise PipelineError(f"candidate was already reviewed: {key}")
        source_row = inventories[track].get(identity)
        if source_row is None:
            raise PipelineError(f"candidate is missing from verified inventory: {key}")
        if (
            source_row.get("review_status") != "DRAFT"
            or source_row.get("production_eligible") is not False
        ):
            raise PipelineError(f"source candidate has an invalid review state: {key}")
        pattern = str(spec_value.get("target_movement_pattern_code", ""))
        if pattern not in allowed_patterns:
            raise PipelineError(f"candidate uses an unregistered movement pattern: {pattern}")
        reasons = spec_value.get("selection_reason_codes")
        if (
            not isinstance(reasons, list)
            or not reasons
            or any(not re.fullmatch(r"[A-Z0-9_]+", str(reason)) for reason in reasons)
        ):
            raise PipelineError(f"candidate selection reasons are invalid: {key}")
        required_reviews = source_row.get("required_review_codes")
        if not isinstance(required_reviews, list) or not required_reviews:
            raise PipelineError(f"candidate has no required review gates: {key}")
        records.append(
            {
                "queue_position": position,
                "track": track,
                "source_identity": identity,
                "target_movement_pattern_code": pattern,
                "selection_reason_codes": reasons,
                "source_facts": source_facts(track, source_row),
                "required_review_codes": required_reviews,
                "review_decision": "PENDING",
                "review_status": "DRAFT",
                "review_method_code": "AGENT_ONLY",
                "production_eligible": False,
            }
        )

    if not records:
        raise PipelineError("selection policy produced no candidates")
    counts = {
        track: sum(record["track"] == track for record in records) for track in IDENTITY_FIELDS
    }
    return {
        "schema_version": "1.0",
        "selection_version": policy.get("selection_version"),
        "status": "DRAFT",
        "review_method_code": "AGENT_ONLY",
        "production_eligible": False,
        "selected_on": policy.get("selected_on"),
        "policy": {
            "path": policy_path.resolve().relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_bytes(policy_path.read_bytes()),
        },
        "interpretation_guards": policy.get("interpretation_guards"),
        "sources": profile_provenance,
        "summary": {"candidate_count": len(records), "track_counts": counts},
        "records": records,
    }


def write_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_output(policy_path: Path, output_path: Path) -> dict[str, object]:
    expected = build_payload(policy_path)
    actual = load_json(output_path)
    if actual != expected:
        raise PipelineError("candidate queue does not match its verified inputs")
    summary = actual.get("summary")
    assert isinstance(summary, dict)
    return {
        "status": "valid",
        "candidate_count": summary.get("candidate_count"),
        "track_counts": summary.get("track_counts"),
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    build.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    verify.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "build":
            write_payload(args.output, build_payload(args.policy))
        result = verify_output(args.policy, args.output)
    except (PipelineError, OSError, ValueError, AssertionError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
