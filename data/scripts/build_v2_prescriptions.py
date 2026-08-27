"""Materialize the V2 review input as backend-compatible DRAFT prescription files."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from kspo_fitness100_pipeline import PipelineError, sha256_bytes
from validate_v2_prescription_review_input import load_results, validate_results

GENERATOR_VERSION = "v2-prescription-generator-1.0.0"
CATALOG_VERSION = "exercise-catalog-v2.0.1-final"
DEFAULT_CATALOG = (
    Path(__file__).resolve().parents[1]
    / "generated/exercise-catalog-v2.0.1-final/representative_exercises_v2_final.csv"
)
DEFAULT_POLICY = (
    Path(__file__).resolve().parents[1] / "normalized/v2_prescription_review_policy.json"
)
DEFAULT_RESULTS = (
    Path(__file__).resolve().parents[1]
    / "validation/review_results/v2_prescription_review_input.csv"
)
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1] / "generated/exercise-prescriptions-v2.0.1-draft"
)


def _entry(path: Path, records: int) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": path.name,
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "records": records,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> int:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    return len(rows)


def build(
    catalog_path: Path = DEFAULT_CATALOG,
    results_path: Path = DEFAULT_RESULTS,
    output: Path = DEFAULT_OUTPUT,
    *,
    policy_path: Path = DEFAULT_POLICY,
    force: bool = False,
) -> Path:
    report = validate_results(catalog_path, results_path, policy_path=policy_path)
    rows = load_results(results_path)
    if output.exists():
        if not force:
            raise PipelineError(f"V2 prescription output already exists: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)

    goals: dict[tuple[str, str], dict[str, object]] = {}
    profiles: list[dict[str, object]] = []
    for row in rows:
        key = (row["stable_code"], row["goal_code"])
        goals[key] = {
            "catalog_version_code": CATALOG_VERSION,
            "exercise_stable_code": row["stable_code"],
            "goal_code": row["goal_code"],
            "role_eligibility_code": row["role_eligibility_code"],
            "review_status_code": row["review_status_code"],
        }
        profiles.append(
            {
                "catalog_version_code": CATALOG_VERSION,
                "exercise_stable_code": row["stable_code"],
                "goal_code": row["goal_code"],
                "experience_level_code": row["experience_level_code"],
                "phase_code": row["phase_code"],
                "sets": int(row["sets"]),
                "reps": int(row["reps"]) if row["reps"] else None,
                "work_seconds_per_set": (
                    int(row["work_seconds_per_set"]) if row["work_seconds_per_set"] else None
                ),
                "rest_seconds_per_set": int(row["rest_seconds_per_set"]),
                "intensity_code": row["intensity_code"],
                "prescription_version": row["prescription_version"],
                "review_status_code": row["review_status_code"],
            }
        )
    goal_rows = [goals[key] for key in sorted(goals)]
    profiles.sort(key=lambda item: (str(item["exercise_stable_code"]), str(item["phase_code"])))
    goal_path = output / "goal_tag_links.jsonl"
    profile_path = output / "prescription_profiles.jsonl"
    _write_jsonl(goal_path, goal_rows)
    _write_jsonl(profile_path, profiles)
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "generator_version": GENERATOR_VERSION,
        "prescription_set_version": {
            "version_code": "prescription-set-v2.0.1",
            "status_code": "DRAFT",
        },
        "source": {
            "catalog_version_code": CATALOG_VERSION,
            "catalog_review_input_path": str(catalog_path),
            "catalog_review_input_sha256": sha256_bytes(catalog_path.read_bytes()),
            "review_results_path": str(results_path),
            "review_results_sha256": sha256_bytes(results_path.read_bytes()),
            "policy_path": str(policy_path),
            "policy_sha256": sha256_bytes(policy_path.read_bytes()),
        },
        "review": {
            "status": "DOMAIN_APPROVED",
            "review_method_code": "AGENT_ONLY",
            "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
            "production_eligible": False,
        },
        "summary": {
            "exercise_records": report["catalog_records"],
            "goal_tag_records": len(goal_rows),
            "prescription_records": len(profiles),
        },
        "files": [_entry(goal_path, len(goal_rows)), _entry(profile_path, len(profiles))],
    }
    (output / "prescription_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    verify(output)
    return output


def verify(output: Path) -> dict[str, object]:
    try:
        manifest = json.loads((output / "prescription_manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("V2 prescription manifest is missing or invalid") from exc
    if manifest.get("prescription_set_version", {}).get("status_code") != "DRAFT":
        raise PipelineError("V2 prescription set must remain DRAFT")
    if manifest.get("review", {}).get("production_eligible") is not False:
        raise PipelineError("V2 prescription set must remain production-ineligible")
    entries = {entry.get("path"): entry for entry in manifest.get("files", [])}
    if set(entries) != {"goal_tag_links.jsonl", "prescription_profiles.jsonl"}:
        raise PipelineError("V2 prescription manifest files are invalid")
    for filename, entry in entries.items():
        raw = (output / filename).read_bytes()
        if len(raw) != entry["bytes"] or sha256_bytes(raw) != entry["sha256"]:
            raise PipelineError("V2 prescription hash or byte count mismatch")
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        if len(rows) != entry["records"]:
            raise PipelineError("V2 prescription record count mismatch")
    return {"status": "valid", **manifest["summary"], "production_eligible": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = build(
            args.catalog, args.results, args.output, policy_path=args.policy, force=args.force
        )
        print(json.dumps(verify(output), ensure_ascii=False, sort_keys=True))
    except (OSError, PipelineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
