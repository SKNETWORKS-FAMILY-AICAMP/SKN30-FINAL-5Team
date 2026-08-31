"""Publish exercise-catalog-v2.0.4-final: v2.0.3 plus the promoted compound lifts.

Seven compound movements passed domain review for v2.0.2 and were then dropped
before packaging. ``prune_v2_0_2_user_catalog.keep_base`` keeps a base record
only when the upstream payload marked it ``general_pool_included``, and these
seven were never marked, so they fell through a filter that was never aimed at
them. The prune report records ``deleted_record_count: 0``: nothing rejected
them.

The effect is recorded in the v2.0.3 approval itself, whose outstanding note
says MUSCLE_GAIN offers only seven CORE exercises. With squat, split squat, leg
press, kettlebell swing, pull-up, scapular pull-up and shoulder press restored,
every goal gains real compound work instead of filling the main block with
isolation and stretching.

v2.0.3 stays byte-identical. A catalog version is an immutable build identity --
the vector index and the approval registry pin themselves to it -- so restoring
records has to produce a new version rather than edit the active one.

Nothing here invents content. Exercise records and their form cues come from the
v2.0.2 canonical payload, safety rules from the v2.0.1 bundle where they were
approved, and prescriptions from the reviewed promotion sheet.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_VERSION = "exercise-catalog-v2.0.3-final"
TARGET_VERSION = "exercise-catalog-v2.0.4-final"
SOURCE_SUFFIX = "v2.0.3"
TARGET_SUFFIX = "v2.0.4"
GENERATOR_VERSION = "v2-0-4-backend-bundle-packager-1.0.0"
BUNDLE_VERSION = "v2-0-4-backend-bundle-2026-09-01"
SAFETY_SOURCE_VERSION = "exercise-catalog-v2.0.1-final"

DEFAULT_SOURCE = PROJECT_ROOT / f"data/generated/{SOURCE_VERSION}/backend_bundle"
DEFAULT_TARGET = PROJECT_ROOT / f"data/generated/{TARGET_VERSION}/backend_bundle"
DEFAULT_RESULTS = (
    PROJECT_ROOT / "data/validation/review_results/compound_promotion_review_results.csv"
)
DEFAULT_POLICY = PROJECT_ROOT / "data/normalized/compound_promotion_policy.json"
DEFAULT_CANONICAL = (
    PROJECT_ROOT
    / "data/generated/exercise-catalog-v2.0.2-final/audit/canonical_exercises_v2_final.jsonl"
)
DEFAULT_FAMILY_MAP = (
    PROJECT_ROOT
    / "data/generated/exercise-catalog-v2.0.2-final/audit/family_representative_mapping_v2_0_2.csv"
)
DEFAULT_SAFETY_SOURCE = (
    PROJECT_ROOT
    / f"data/generated/{SAFETY_SOURCE_VERSION}/backend_bundle/safety/safety_rules.jsonl"
)

SUB_MANIFESTS = (
    "catalog/seed_manifest.json",
    "alternatives/alternatives_manifest.json",
    "media/media_manifest.json",
    "safety/rules_manifest.json",
    "prescriptions/prescription_manifest.json",
)

# The shipped record shape. Carried straight from the canonical payload; the
# six fields the canonical payload does not carry are set explicitly below.
_CANONICAL_FIELDS = (
    "body_focus_code",
    "default_rest_seconds",
    "default_seconds_per_rep",
    "default_transition_seconds",
    "default_work_seconds",
    "difficulty_code",
    "equipment_codes",
    "form_cues_ko",
    "instruction_content_version",
    "instruction_summary_ko",
    "location_codes",
    "name_en",
    "name_ko",
    "primary_body_area_codes",
    "primary_movement_pattern_code",
    "recovery_eligible",
    "review_status_code",
    "secondary_body_area_codes",
    "source_identity",
    "source_track",
    "stable_code",
    "timing_mode_code",
    "training_type_code",
)

# Matches the 76 REPRESENTATIVE records already in the bundle: their cues carry
# the same provenance and the same (absent) separate cue review.
FORM_CUES_SOURCE = "canonical_exercises_v2_0_2_refined.csv"


class BundleBuildError(RuntimeError):
    """Raised when the v2.0.4 bundle cannot be produced faithfully."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    return len(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _retarget(value: Any) -> Any:
    """Move version strings onto v2.0.4 without touching anything else."""
    if isinstance(value, str):
        return value.replace(SOURCE_VERSION, TARGET_VERSION).replace(SOURCE_SUFFIX, TARGET_SUFFIX)
    if isinstance(value, list):
        return [_retarget(item) for item in value]
    if isinstance(value, dict):
        return {key: _retarget(item) for key, item in value.items()}
    return value


def _int_or_none(value: str) -> int | None:
    text = value.strip()
    return int(text) if text else None


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _family_identity(path: Path, codes: set[str]) -> dict[str, dict[str, str]]:
    """Recover family code and representative id for each promoted record."""
    found = {
        row["stable_code"]: {
            "family_code": row["family_code"],
            "representative_exercise_id": row["representative_exercise_id"],
        }
        for row in _read_csv(path)
        if row.get("stable_code") in codes
    }
    missing = sorted(codes - set(found))
    if missing:
        raise BundleBuildError(f"family mapping does not carry {missing}")
    return found


def _promoted_exercises(
    canonical: list[dict[str, Any]],
    families: dict[str, dict[str, str]],
    codes: set[str],
) -> list[dict[str, Any]]:
    by_code = {row["stable_code"]: row for row in canonical}
    missing = sorted(codes - set(by_code))
    if missing:
        raise BundleBuildError(f"canonical payload does not carry {missing}")

    records: list[dict[str, Any]] = []
    for code in sorted(codes):
        source = by_code[code]
        if source.get("review_status_code") != "DOMAIN_APPROVED":
            raise BundleBuildError(f"{code} is not DOMAIN_APPROVED in the canonical payload")
        record = {field: source.get(field) for field in _CANONICAL_FIELDS}
        record["name_en"] = record.get("name_en") or ""
        record["record_type"] = "REPRESENTATIVE"
        record["representative_stable_code"] = None
        record["family_code"] = families[code]["family_code"]
        # The whole point of the promotion: these are base routine candidates.
        record["general_pool_included"] = True
        record["form_cues_source"] = FORM_CUES_SOURCE
        record["form_cues_review_status"] = None
        records.append(record)
    return records


def _promoted_prescriptions(
    rows: list[dict[str, str]], codes: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prescription_version = f"prescription-set-{TARGET_SUFFIX}-compound-promotion"
    reviewed = {row["stable_code"] for row in rows}
    if reviewed != codes:
        raise BundleBuildError(
            f"review sheet covers {sorted(reviewed)}, policy scope is {sorted(codes)}"
        )

    links: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["stable_code"], row["goal_code"])
        if key not in seen:
            seen.add(key)
            links.append(
                {
                    "catalog_version_code": TARGET_VERSION,
                    "exercise_stable_code": row["stable_code"],
                    "goal_code": row["goal_code"],
                    "review_status_code": "DOMAIN_APPROVED",
                    "role_eligibility_code": row["role_eligibility_code"],
                }
            )
        profiles.append(
            {
                "catalog_version_code": TARGET_VERSION,
                "exercise_stable_code": row["stable_code"],
                "experience_level_code": row["experience_level_code"],
                "goal_code": row["goal_code"],
                "intensity_code": row["intensity_code"],
                "phase_code": row["phase_code"],
                "prescription_version": prescription_version,
                "reps": _int_or_none(row["reps"]),
                "rest_seconds_per_set": int(row["rest_seconds_per_set"]),
                "review_status_code": "DOMAIN_APPROVED",
                "sets": int(row["sets"]),
                "work_seconds_per_set": _int_or_none(row["work_seconds_per_set"]),
            }
        )
    return links, profiles


def _promoted_safety_rules(source: Path, codes: set[str]) -> list[dict[str, Any]]:
    """Carry the approved v2.0.1 rules for the promoted exercises.

    A record with only a placeholder row could never be excluded for any
    reported pain area, which is the one failure the deterministic safety veto
    exists to prevent, so a substantive rule per exercise is required here
    rather than at recommendation time.
    """
    rules = [
        _retarget_version(rule)
        for rule in _read_jsonl(source)
        if rule.get("exercise_stable_code") in codes
    ]
    for rule in rules:
        if rule.get("review_status_code") != "DOMAIN_APPROVED":
            raise BundleBuildError(f"{rule['exercise_stable_code']} carries an unapproved rule")
    covered = {rule["exercise_stable_code"] for rule in rules if rule.get("rule_scope") is not None}
    uncovered = sorted(codes - covered)
    if uncovered:
        raise BundleBuildError(f"promoted exercises have no substantive safety rule: {uncovered}")
    return rules


def _retarget_version(rule: dict[str, Any]) -> dict[str, Any]:
    carried = dict(rule)
    carried["catalog_version_code"] = TARGET_VERSION
    rule_version = str(carried.get("rule_version") or "")
    carried["rule_version"] = rule_version.replace("v2.0.1", TARGET_SUFFIX)
    return carried


def _validate_foreign_keys(
    exercises: list[dict[str, Any]],
    safety: list[dict[str, Any]],
    links: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    alternatives: list[dict[str, Any]],
) -> None:
    codes = {row["stable_code"] for row in exercises}
    if len(codes) != len(exercises):
        raise BundleBuildError("v2.0.4 catalog contains duplicate stable codes")
    referenced = (
        ("safety", (row["exercise_stable_code"] for row in safety)),
        ("goal", (row["exercise_stable_code"] for row in links)),
        ("prescription", (row["exercise_stable_code"] for row in profiles)),
        ("alternative source", (row["source_exercise_stable_code"] for row in alternatives)),
        ("alternative target", (row["alternative_exercise_stable_code"] for row in alternatives)),
    )
    for label, referenced_codes in referenced:
        orphans = {code for code in referenced_codes if code not in codes}
        if orphans:
            raise BundleBuildError(f"{label} references {len(orphans)} codes outside the catalog")
    uncovered = sorted(
        codes - {row["exercise_stable_code"] for row in safety if row.get("rule_scope") is not None}
    )
    if uncovered:
        raise BundleBuildError(
            f"{len(uncovered)} exercises have no safety rule (e.g. {uncovered[0]})"
        )


def build(
    *,
    source: Path = DEFAULT_SOURCE,
    target: Path = DEFAULT_TARGET,
    results_path: Path = DEFAULT_RESULTS,
    policy_path: Path = DEFAULT_POLICY,
    canonical_path: Path = DEFAULT_CANONICAL,
    family_map_path: Path = DEFAULT_FAMILY_MAP,
    safety_source_path: Path = DEFAULT_SAFETY_SOURCE,
) -> dict[str, Any]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("review_status_code") != "DOMAIN_APPROVED":
        raise BundleBuildError("policy is not DOMAIN_APPROVED; record the review verdict first")
    codes = set(policy["scope"]["exercise_stable_codes"])

    rows = [
        row for row in _read_csv(results_path) if row["review_status_code"] == "DOMAIN_APPROVED"
    ]
    if not rows:
        raise BundleBuildError("no DOMAIN_APPROVED rows to publish")

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)

    # Every carried-over record keeps its content and moves version strings only.
    for jsonl in sorted(target.rglob("*.jsonl")):
        _write_jsonl(jsonl, [_retarget(row) for row in _read_jsonl(jsonl)])

    catalog_path = target / "catalog/exercises.jsonl"
    exercises = _read_jsonl(catalog_path)
    already = sorted(codes & {row["stable_code"] for row in exercises})
    if already:
        raise BundleBuildError(f"source bundle already carries {already}")

    families = _family_identity(family_map_path, codes)
    exercises.extend(_promoted_exercises(_read_jsonl(canonical_path), families, codes))
    exercises.sort(key=lambda row: str(row["stable_code"]))
    catalog_count = _write_jsonl(catalog_path, exercises)

    safety_path = target / "safety/safety_rules.jsonl"
    safety = _read_jsonl(safety_path)
    safety.extend(_promoted_safety_rules(safety_source_path, codes))
    safety.sort(
        key=lambda row: (
            str(row["exercise_stable_code"]),
            str(row["body_area_code"]),
            str(row["effect_code"]),
        )
    )
    safety_count = _write_jsonl(safety_path, safety)

    prescriptions = target / "prescriptions"
    links = _read_jsonl(prescriptions / "goal_tag_links.jsonl")
    profiles = _read_jsonl(prescriptions / "prescription_profiles.jsonl")
    new_links, new_profiles = _promoted_prescriptions(rows, codes)
    links.extend(new_links)
    profiles.extend(new_profiles)
    links.sort(key=lambda row: (row["exercise_stable_code"], row["goal_code"]))
    profiles.sort(
        key=lambda row: (
            row["exercise_stable_code"],
            row["goal_code"],
            row["experience_level_code"],
            row["phase_code"],
        )
    )
    link_count = _write_jsonl(prescriptions / "goal_tag_links.jsonl", links)
    profile_count = _write_jsonl(prescriptions / "prescription_profiles.jsonl", profiles)

    alternatives = _read_jsonl(target / "alternatives/alternatives.jsonl")
    _validate_foreign_keys(exercises, safety, links, profiles, alternatives)

    # The representative registry names every packaged record, so the promoted
    # ones join it under the ids the family mapping already assigned them.
    registry_path = target / "catalog/input/representative_exercises.csv"
    registry = _read_csv(registry_path)
    registry.extend(
        {
            "representative_exercise_id": families[code]["representative_exercise_id"],
            "stable_code": code,
        }
        for code in sorted(codes)
    )
    registry.sort(key=lambda row: (row["representative_exercise_id"], row["stable_code"]))
    identities = [row["representative_exercise_id"] for row in registry]
    if len(identities) != len(set(identities)):
        raise BundleBuildError("representative registry reuses an exercise id")
    with registry_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("representative_exercise_id", "stable_code"),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(registry)

    media_count = len(_read_jsonl(target / "media/media_assets.jsonl"))
    alternative_count = len(alternatives)

    # Sub-manifests first: the bundle manifest hashes them in turn.
    for relative in SUB_MANIFESTS:
        path = target / relative
        manifest = _retarget(json.loads(path.read_text(encoding="utf-8")))
        manifest["generator_version"] = GENERATOR_VERSION
        for entry in manifest.get("files", []):
            entry_path = path.parent / entry["path"]
            entry["sha256"] = _sha256(entry_path)
            entry["bytes"] = entry_path.stat().st_size
            if entry["path"].endswith(".jsonl"):
                entry["records"] = len(_read_jsonl(entry_path))
        for artifact in manifest.get("source", {}).get("input_artifacts", []):
            artifact_path = path.parent / artifact["path"]
            artifact["sha256"] = _sha256(artifact_path)
            artifact["bytes"] = artifact_path.stat().st_size
        summary = manifest.get("summary", {})
        if "exercise_records" in summary:
            summary["exercise_records"] = catalog_count
        if "rule_records" in summary:
            summary["rule_records"] = safety_count
        if "goal_tag_records" in summary:
            summary["goal_tag_records"] = link_count
        if "prescription_records" in summary:
            summary["prescription_records"] = profile_count
        _write_json(path, manifest)

    bundle_manifest_path = target / "bundle_manifest.json"
    bundle_manifest = _retarget(json.loads(bundle_manifest_path.read_text(encoding="utf-8")))
    bundle_manifest["bundle_version"] = BUNDLE_VERSION
    # Record the derivation so v2.0.4 can be traced back and re-verified. The
    # source manifest hash makes the claim checkable rather than a bare label.
    bundle_manifest["derived_from"] = {
        "catalog_version_code": SOURCE_VERSION,
        "bundle_manifest_sha256": _sha256(source / "bundle_manifest.json"),
        "change_summary": (
            "Restores seven DOMAIN_APPROVED compound exercises that a v2.0.2 "
            "prune filter dropped, with their approved safety rules and "
            "reviewed prescriptions for all three goals. Alternatives and media "
            "are carried over unchanged."
        ),
        "compound_promotion": {
            "exercise_stable_codes": sorted(codes),
            "policy_version": policy["policy_version"],
            "approval_method_code": policy["approval_method_code"],
            "approval_reference": policy["reviewer_reference"],
            "approved_at": policy["reviewed_at"],
            "safety_rules_carried_from": SAFETY_SOURCE_VERSION,
            "alternatives_carried": False,
        },
    }
    bundle_manifest["summary"] = {
        "alternative_records": alternative_count,
        "catalog_records": catalog_count,
        "goal_tag_records": link_count,
        "media_asset_records": media_count,
        "prescription_records": profile_count,
        "safety_rule_records": safety_count,
    }
    for entry in bundle_manifest["files"]:
        entry_path = target / entry["path"]
        entry["sha256"] = _sha256(entry_path)
        entry["bytes"] = entry_path.stat().st_size
        if entry["path"].endswith(".jsonl"):
            entry["records"] = len(_read_jsonl(entry_path))
    _write_json(bundle_manifest_path, bundle_manifest)

    return {
        "catalog_version_code": TARGET_VERSION,
        "catalog_records": catalog_count,
        "safety_rule_records": safety_count,
        "goal_tag_records": link_count,
        "prescription_records": profile_count,
        "promoted_exercise_count": len(codes),
        "bundle_manifest_sha256": _sha256(bundle_manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--family-map", type=Path, default=DEFAULT_FAMILY_MAP)
    parser.add_argument("--safety-source", type=Path, default=DEFAULT_SAFETY_SOURCE)
    args = parser.parse_args()
    summary = build(
        source=args.source,
        target=args.target,
        results_path=args.results,
        policy_path=args.policy,
        canonical_path=args.canonical,
        family_map_path=args.family_map,
        safety_source_path=args.safety_source,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
