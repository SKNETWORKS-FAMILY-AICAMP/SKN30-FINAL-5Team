"""Materialize reviewed goal prescriptions as backend bundle records.

Consumes the reviewer-stamped results sheet and appends FAT_LOSS/MUSCLE_GAIN
rows to the catalog bundle's goal tag links and prescription profiles. Only
DOMAIN_APPROVED rows are emitted, and the existing GENERAL_FITNESS records are
carried through untouched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUNDLE = PROJECT_ROOT / "data/generated/exercise-catalog-v2.0.2-final/backend_bundle/prescriptions"
DEFAULT_RESULTS = (
    PROJECT_ROOT / "data/validation/review_results/goal_expansion_prescription_review_results.csv"
)
DEFAULT_POLICY = PROJECT_ROOT / "data/normalized/goal_prescription_review_policy.json"
CATALOG_VERSION_CODE = "exercise-catalog-v2.0.2-final"


class BundleError(RuntimeError):
    """Raised when reviewed rows cannot be turned into bundle records."""


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


def _int_or_none(value: str) -> int | None:
    text = value.strip()
    return int(text) if text else None


def build(
    *,
    results_path: Path = DEFAULT_RESULTS,
    policy_path: Path = DEFAULT_POLICY,
    bundle_dir: Path = BUNDLE,
) -> dict[str, int]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("review_status_code") != "DOMAIN_APPROVED":
        raise BundleError("policy is not DOMAIN_APPROVED; record the review verdict first")
    approval_method = policy["approval_method_code"]
    approval_reference = policy["reviewer_reference"]
    approved_at = policy["reviewed_at"]
    prescription_version = policy["prescription_version"]

    with results_path.open(encoding="utf-8", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle) if row["review_status_code"] == "DOMAIN_APPROVED"
        ]
    if not rows:
        raise BundleError("no DOMAIN_APPROVED rows to materialize")

    goal_links = _read_jsonl(bundle_dir / "goal_tag_links.jsonl")
    profiles = _read_jsonl(bundle_dir / "prescription_profiles.jsonl")
    expansion_goals = set(policy["scope"]["goal_codes"])

    # Regenerating is idempotent: drop any previous expansion output first.
    goal_links = [row for row in goal_links if row["goal_code"] not in expansion_goals]
    profiles = [row for row in profiles if row["goal_code"] not in expansion_goals]

    seen_links: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["stable_code"], row["goal_code"])
        if key in seen_links:
            continue
        seen_links.add(key)
        goal_links.append(
            {
                "approval_method_code": approval_method,
                "approval_reference": approval_reference,
                "approved_at": approved_at,
                "catalog_version_code": CATALOG_VERSION_CODE,
                "exercise_stable_code": row["stable_code"],
                "goal_code": row["goal_code"],
                "review_status_code": "DOMAIN_APPROVED",
                "role_eligibility_code": row["role_eligibility_code"],
                "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
            }
        )

    for row in rows:
        profiles.append(
            {
                "approval_method_code": approval_method,
                "approval_reference": approval_reference,
                "approved_at": approved_at,
                "catalog_version_code": CATALOG_VERSION_CODE,
                "exercise_difficulty_code": row["exercise_difficulty_code"],
                "exercise_stable_code": row["stable_code"],
                "experience_level_code": row["experience_level_code"],
                "goal_code": row["goal_code"],
                "intensity_code": row["intensity_code"],
                "phase_code": row["phase_code"],
                "prescription_version": prescription_version,
                "production_eligible": True,
                "reps": _int_or_none(row["reps"]),
                "rest_seconds_per_set": int(row["rest_seconds_per_set"]),
                "review_status_code": "DOMAIN_APPROVED",
                "sets": int(row["sets"]),
                "work_seconds_per_set": _int_or_none(row["work_seconds_per_set"]),
            }
        )

    goal_links.sort(key=lambda row: (row["exercise_stable_code"], row["goal_code"]))
    profiles.sort(
        key=lambda row: (
            row["exercise_stable_code"],
            row["goal_code"],
            row["experience_level_code"],
            row["phase_code"],
        )
    )
    link_count = _write_jsonl(bundle_dir / "goal_tag_links.jsonl", goal_links)
    profile_count = _write_jsonl(bundle_dir / "prescription_profiles.jsonl", profiles)

    manifest_path = bundle_dir / "prescription_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        target = bundle_dir / entry["path"]
        raw = target.read_bytes()
        entry["sha256"] = hashlib.sha256(raw).hexdigest()
        entry["bytes"] = len(raw)
        entry["records"] = link_count if entry["path"].startswith("goal") else profile_count
    manifest["summary"]["goal_tag_records"] = link_count
    manifest["summary"]["prescription_records"] = profile_count
    manifest["goal_expansion"] = {
        "goal_codes": sorted(expansion_goals),
        "approval_method_code": approval_method,
        "approval_reference": approval_reference,
        "approved_at": approved_at,
        "policy_version": policy["policy_version"],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"goal_tag_links": link_count, "prescription_profiles": profile_count}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    args = parser.parse_args()
    counts = build(results_path=args.results, policy_path=args.policy, bundle_dir=args.bundle)
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
