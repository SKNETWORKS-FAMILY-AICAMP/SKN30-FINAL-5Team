"""Create a DRAFT profile for Gym Visual mobility and stretching candidates.

The script reads the immutable raw snapshot and a declarative selection policy.
It creates no catalog seed, safety rule, or alternative relation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = REPO_ROOT / "data/raw/gym_visual"
DEFAULT_POLICY = REPO_ROOT / "data/normalized/mobility_selection_policy.json"
DEFAULT_OUTPUT = REPO_ROOT / "data/validation/profiles/gymvisual_mobility_profile.json"

PROFILE_VERSION = "gymvisual-mobility-profile-v0.1.0"
REQUIRED_SOURCE_FIELDS = ("id", "name", "body_part", "target", "equipment")


class ProfileError(ValueError):
    """Fail-closed profile validation error."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileError(f"invalid JSON: {path}") from exc


def relative_path(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def load_inputs(
    raw_dir: Path, policy_path: Path
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    records = load_json(raw_dir / "exercises.json")
    source = load_json(raw_dir / "source.json")
    policy = load_json(policy_path)
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ProfileError("Gym Visual exercises.json must be an array of objects")
    if not isinstance(source, dict) or source.get("record_count") != len(records):
        raise ProfileError("Gym Visual source record_count does not match exercises.json")
    if policy.get("production_eligible") is not False:
        raise ProfileError("mobility policy must remain production-ineligible")
    by_id: dict[str, dict[str, Any]] = {}
    for row in records:
        missing = [field for field in REQUIRED_SOURCE_FIELDS if not str(row.get(field, "")).strip()]
        if missing:
            raise ProfileError(f"raw record {row.get('id', '<unknown>')} misses {missing}")
        identifier = str(row["id"])
        if identifier in by_id:
            raise ProfileError(f"duplicate raw id: {identifier}")
        by_id[identifier] = row
    return records, policy, by_id


def equipment_codes(value: str) -> tuple[str, list[str]]:
    normalized = value.strip().lower()
    mapping = {
        "body weight": ("BODYWEIGHT", ["HOME", "GYM"]),
        "band": ("RESISTANCE_BAND", ["HOME", "GYM"]),
        "resistance band": ("RESISTANCE_BAND", ["HOME", "GYM"]),
        "rope": ("ROPE_REVIEW_REQUIRED", ["HOME", "GYM"]),
        "stability ball": ("STABILITY_BALL", ["HOME", "GYM"]),
        "roller": ("ROLLER_REVIEW_REQUIRED", ["HOME", "GYM"]),
        "assisted": ("ASSISTED_SUPPORT_REVIEW_REQUIRED", ["GYM"]),
        "cable": ("CABLE_MACHINE", ["GYM"]),
    }
    return mapping.get(normalized, (f"UNMAPPED:{value}", ["HOME", "GYM"]))


def build_profile(raw_dir: Path, policy_path: Path) -> dict[str, Any]:
    records, policy, by_id = load_inputs(raw_dir, policy_path)
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    group_counts: Counter[str] = Counter()
    body_area_counts: Counter[str] = Counter()
    equipment_counts: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()
    beginner_counts: Counter[str] = Counter()
    family_members: defaultdict[str, list[str]] = defaultdict(list)

    groups = policy.get("candidate_groups")
    if not isinstance(groups, list) or not groups:
        raise ProfileError("mobility policy candidate_groups is empty")
    for group in groups:
        if not isinstance(group, dict):
            raise ProfileError("mobility policy contains an invalid group")
        goal = str(group.get("mobility_goal_code", ""))
        areas = group.get("body_area_codes")
        entries = group.get("candidates")
        if not goal or not isinstance(areas, list) or not isinstance(entries, list):
            raise ProfileError("mobility policy group is incomplete")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ProfileError("mobility policy candidate is not an object")
            identifier = str(entry.get("id", ""))
            if not identifier or identifier in seen_ids:
                raise ProfileError(f"blank or duplicate mobility candidate: {identifier}")
            row = by_id.get(identifier)
            if row is None:
                raise ProfileError(
                    f"mobility candidate is missing from immutable raw source: {identifier}"
                )
            seen_ids.add(identifier)
            equipment_code, locations = equipment_codes(str(row["equipment"]))
            family = str(entry.get("family", ""))
            variant_group = str(entry.get("variant_group", ""))
            difficulty = str(entry.get("difficulty", ""))
            beginner_fit = str(entry.get("beginner_fit", ""))
            if not family or not variant_group or not difficulty or not beginner_fit:
                raise ProfileError(f"mobility candidate metadata is incomplete: {identifier}")
            record = {
                "candidate_id": identifier,
                "source_identity": identifier,
                "source_name": str(row["name"]),
                "source_body_part": str(row["body_part"]),
                "source_target": str(row["target"]),
                "source_equipment": str(row["equipment"]),
                "mobility_goal_code": goal,
                "body_area_codes_candidate": [str(value) for value in areas],
                "training_type_code_candidate": "MOBILITY",
                "movement_pattern_code_candidate": "MOBILITY_STRETCH",
                "exercise_family_candidate": family,
                "variant_group_candidate": variant_group,
                "selection_rank": int(entry["rank"]),
                "difficulty_code_candidate": difficulty,
                "beginner_suitability_candidate": beginner_fit,
                "equipment_code_candidate": equipment_code,
                "location_code_candidates": locations,
                "load_profile_candidate": "UNREVIEWED",
                "screening_decision": "INCLUDE_CANDIDATE",
                "review_status_code": "DRAFT",
                "production_eligible": False,
                "review_required_codes": list(policy["review_required_codes"]),
                "alternative_relation_status": "NOT_CREATED_BY_DESIGN",
                "source_media_id": str(row.get("media_id", "")),
                "source_image": str(row.get("image", "")),
                "source_gif_url": str(row.get("gif_url", "")),
            }
            candidates.append(record)
            group_counts[goal] += 1
            for area in areas:
                body_area_counts[str(area)] += 1
            equipment_counts[equipment_code] += 1
            difficulty_counts[difficulty] += 1
            beginner_counts[beginner_fit] += 1
            family_members[family].append(identifier)

    expected_count = sum(len(group["candidates"]) for group in groups)
    if len(candidates) != expected_count or len(candidates) != len(seen_ids):
        raise ProfileError("mobility candidate count is inconsistent")
    duplicate_families = {family: ids for family, ids in family_members.items() if len(ids) > 1}
    return {
        "profile_version": PROFILE_VERSION,
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "scope": {
            "stage": "4_MOBILITY_STRETCHING_SELECTION",
            "selection_target": (
                "대표 family를 충분히 선정하되 동일 family 중복은 검토 큐에서 명시적으로 확인"
            ),
            "source_filter": "declarative mobility_selection_policy candidate groups",
            "candidate_count": len(candidates),
        },
        "source": {
            "directory": relative_path(raw_dir),
            "source_manifest": source_manifest(raw_dir / "source.json"),
            "raw_sha256": {
                "exercises.json": sha256_file(raw_dir / "exercises.json"),
                "source.json": sha256_file(raw_dir / "source.json"),
            },
            "selection_policy": relative_path(policy_path),
            "selection_policy_sha256": sha256_file(policy_path),
        },
        "selection_policy": {
            "policy_version": policy["policy_version"],
            "guards": policy["selection_guards"],
            "family_variant_boundary": (
                "family/variant is review metadata only; no alternative relation is created"
            ),
        },
        "coverage": {
            "mobility_goal_counts": dict(sorted(group_counts.items())),
            "body_area_candidate_counts": dict(sorted(body_area_counts.items())),
            "equipment_candidate_counts": dict(sorted(equipment_counts.items())),
            "difficulty_candidate_counts": dict(sorted(difficulty_counts.items())),
            "beginner_suitability_candidate_counts": dict(sorted(beginner_counts.items())),
            "duplicate_family_groups": duplicate_families,
            "coverage_gaps": [],
        },
        "baseline_preservation": baseline_preservation(REPO_ROOT),
        "candidates": candidates,
        "next_stage_gate": policy["next_stage_gate"],
    }


def source_manifest(path: Path) -> dict[str, Any]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise ProfileError("source.json must be an object")
    return {
        "source_name": value.get("source_name"),
        "retrieved_at": value.get("retrieved_at"),
        "record_count": value.get("record_count"),
        "license": value.get("license"),
        "media_license_attribution": value.get("media_license_attribution"),
        "status": value.get("status"),
    }


def baseline_preservation(repo_root: Path) -> dict[str, Any]:
    artifacts: dict[str, list[Path]] = {
        "catalog": [
            repo_root / "data/generated/exercise-catalog-seed-wger-mvp-v0.2.0/exercises.jsonl",
            repo_root / "data/generated/exercise-catalog-seed-kspo-mvp-v0.2.0/exercises.jsonl",
            repo_root / "data/generated/exercise-catalog-seed-wger-tranche3-v0.1.0/exercises.jsonl",
            repo_root / "data/generated/exercise-catalog-seed-kspo-tranche3-v0.1.0/exercises.jsonl",
        ],
        "safety_rules": [
            repo_root / "data/generated/exercise-safety-rules-mvp-v0.3.0/safety_rules.jsonl"
        ],
        "alternatives": [
            repo_root / "data/generated/exercise-alternatives-mvp-v0.2.0/alternatives.jsonl"
        ],
    }
    result: dict[str, Any] = {}
    expected_counts = {"catalog": 56, "safety_rules": 354, "alternatives": 238}
    for name, paths in artifacts.items():
        if any(not path.exists() for path in paths):
            missing = next(path for path in paths if not path.exists())
            raise ProfileError(f"baseline artifact is missing: {missing}")
        raws = [path.read_bytes() for path in paths]
        record_count = sum(len(raw.splitlines()) for raw in raws)
        result[name] = {
            "paths": [relative_path(path) for path in paths],
            "record_count": record_count,
            "expected_record_count": expected_counts[name],
            "sha256": [hashlib.sha256(raw).hexdigest() for raw in raws],
            "preservation": "READ_ONLY_INPUT_REFERENCE",
        }
        if result[name]["record_count"] != expected_counts[name]:
            raise ProfileError(f"baseline record count changed for {name}")
    return result


def verify_profile(profile: dict[str, Any], raw_dir: Path, policy_path: Path) -> dict[str, Any]:
    if profile.get("profile_version") != PROFILE_VERSION:
        raise ProfileError("unsupported mobility profile version")
    if profile.get("production_eligible") is not False:
        raise ProfileError("mobility profile must remain production-ineligible")
    candidates = profile.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ProfileError("mobility profile has no candidates")
    _, _, by_id = load_inputs(raw_dir, policy_path)
    seen: set[str] = set()
    for candidate in candidates:
        identifier = str(candidate.get("candidate_id", ""))
        if not identifier or identifier in seen or identifier not in by_id:
            raise ProfileError(f"invalid or duplicate profile candidate: {identifier}")
        seen.add(identifier)
        if candidate.get("movement_pattern_code_candidate") != "MOBILITY_STRETCH":
            raise ProfileError(f"mobility candidate has invalid movement pattern: {identifier}")
        if candidate.get("alternative_relation_status") != "NOT_CREATED_BY_DESIGN":
            raise ProfileError(f"mobility candidate has an alternative relation: {identifier}")
    return {"status": "valid", "profile": PROFILE_VERSION, "candidates": len(candidates)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("profile")
    build.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    build.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    build.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    verify = subparsers.add_parser("verify")
    verify.add_argument("profile", type=Path)
    verify.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    verify.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()
    try:
        if args.command == "profile":
            payload = build_profile(args.raw_dir, args.policy)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            result = {
                "status": "built",
                "profile": str(args.output),
                "candidates": len(payload["candidates"]),
            }
        else:
            profile = load_json(args.profile)
            result = verify_profile(profile, args.raw_dir, args.policy)
    except (OSError, ProfileError, KeyError, TypeError, ValueError) as exc:
        print(f"failed: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
