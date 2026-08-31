"""Publish exercise-catalog-v2.0.3-final: v2.0.2 plus the reviewed goal expansion.

v2.0.2 stays byte-identical. A catalog version is an immutable build identity --
the vector index and the registry are pinned to it -- so adding FAT_LOSS and
MUSCLE_GAIN prescriptions has to produce a new version rather than edit the
active one in place.

Everything except the prescription set is carried over unchanged; only the
catalog version strings and the derived set versions move to v2.0.3.
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
SOURCE_VERSION = "exercise-catalog-v2.0.2-final"
TARGET_VERSION = "exercise-catalog-v2.0.3-final"
SOURCE_SUFFIX = "v2.0.2"
TARGET_SUFFIX = "v2.0.3"
GENERATOR_VERSION = "v2-0-3-backend-bundle-packager-1.0.0"
BUNDLE_VERSION = "v2-0-3-backend-bundle-2026-08-31"

DEFAULT_SOURCE = PROJECT_ROOT / f"data/generated/{SOURCE_VERSION}/backend_bundle"
DEFAULT_TARGET = PROJECT_ROOT / f"data/generated/{TARGET_VERSION}/backend_bundle"
DEFAULT_RESULTS = (
    PROJECT_ROOT / "data/validation/review_results/goal_expansion_prescription_review_results.csv"
)
DEFAULT_POLICY = PROJECT_ROOT / "data/normalized/goal_prescription_review_policy.json"

SUB_MANIFESTS = (
    "catalog/seed_manifest.json",
    "alternatives/alternatives_manifest.json",
    "media/media_manifest.json",
    "safety/rules_manifest.json",
    "prescriptions/prescription_manifest.json",
)


class BundleBuildError(RuntimeError):
    """Raised when the v2.0.3 bundle cannot be produced faithfully."""


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
    """Move version strings onto v2.0.3 without touching anything else."""

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


def _expansion_records(
    rows: list[dict[str, str]], policy: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prescription_version = f"prescription-set-{TARGET_SUFFIX}-goal-expansion"

    links: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    # The bundle record shape is exactly what the importer schema accepts:
    # lean rows, no approval columns. Approval lives in the approval registry
    # and the bundle manifest, not on every row.
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


def build(
    *,
    source: Path = DEFAULT_SOURCE,
    target: Path = DEFAULT_TARGET,
    results_path: Path = DEFAULT_RESULTS,
    policy_path: Path = DEFAULT_POLICY,
) -> dict[str, Any]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("review_status_code") != "DOMAIN_APPROVED":
        raise BundleBuildError("policy is not DOMAIN_APPROVED; record the review verdict first")

    with results_path.open(encoding="utf-8", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle) if row["review_status_code"] == "DOMAIN_APPROVED"
        ]
    if not rows:
        raise BundleBuildError("no DOMAIN_APPROVED rows to publish")

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)

    # Every carried-over record keeps its content and moves version strings only.
    for jsonl in sorted(target.rglob("*.jsonl")):
        _write_jsonl(jsonl, [_retarget(row) for row in _read_jsonl(jsonl)])

    prescriptions = target / "prescriptions"
    links = _read_jsonl(prescriptions / "goal_tag_links.jsonl")
    profiles = _read_jsonl(prescriptions / "prescription_profiles.jsonl")
    expansion_goals = set(policy["scope"]["goal_codes"])
    carried_goals = {row["goal_code"] for row in profiles}
    if carried_goals & expansion_goals:
        raise BundleBuildError(f"source bundle already carries {carried_goals & expansion_goals}")

    new_links, new_profiles = _expansion_records(rows, policy)
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
        if relative.startswith("prescriptions/"):
            manifest["summary"]["goal_tag_records"] = link_count
            manifest["summary"]["prescription_records"] = profile_count
        # The expansion is recorded once, in the bundle manifest's derived_from.
        # Repeating it per sub-manifest would duplicate provenance and widen
        # another forbidden-extras schema for no additional information.
        _write_json(path, manifest)

    bundle_manifest_path = target / "bundle_manifest.json"
    bundle_manifest = _retarget(json.loads(bundle_manifest_path.read_text(encoding="utf-8")))
    bundle_manifest["bundle_version"] = BUNDLE_VERSION
    # Record the derivation so v2.0.3 can be traced back and re-verified. The
    # source manifest hash makes the claim checkable rather than a bare label.
    bundle_manifest["derived_from"] = {
        "catalog_version_code": SOURCE_VERSION,
        "bundle_manifest_sha256": _sha256(source / "bundle_manifest.json"),
        "change_summary": (
            "Adds DOMAIN_APPROVED FAT_LOSS and MUSCLE_GAIN prescriptions and goal "
            "tag links. Catalog, media, safety rules and alternatives are carried "
            "over unchanged."
        ),
        "goal_expansion": {
            "goal_codes": sorted(expansion_goals),
            "policy_version": policy["policy_version"],
            "approval_method_code": policy["approval_method_code"],
            "approval_reference": policy["reviewer_reference"],
            "approved_at": policy["reviewed_at"],
        },
    }
    bundle_manifest["summary"]["goal_tag_records"] = link_count
    bundle_manifest["summary"]["prescription_records"] = profile_count
    for entry in bundle_manifest["files"]:
        entry_path = target / entry["path"]
        entry["sha256"] = _sha256(entry_path)
        entry["bytes"] = entry_path.stat().st_size
        if entry["path"].endswith(".jsonl"):
            entry["records"] = len(_read_jsonl(entry_path))
    _write_json(bundle_manifest_path, bundle_manifest)

    return {
        "catalog_version_code": TARGET_VERSION,
        "goal_tag_records": link_count,
        "prescription_records": profile_count,
        "bundle_manifest_sha256": _sha256(bundle_manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()
    summary = build(
        source=args.source,
        target=args.target,
        results_path=args.results,
        policy_path=args.policy,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
