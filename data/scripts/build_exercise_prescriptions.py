"""Build the reviewed goal-tag and prescription artifact for one catalog seed."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from kspo_fitness100_pipeline import PipelineError, sha256_bytes
from validate_exercise_prescription_review_results import validate_results

GENERATOR_VERSION = "0.1.0"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "generated"


def _entry(path: Path, records: int) -> dict[str, object]:
    raw = path.read_bytes()
    return {"path": path.name, "sha256": sha256_bytes(raw), "bytes": len(raw), "records": records}


def build_prescriptions(
    seed_dir: Path,
    results_path: Path,
    output_root: Path,
    version_code: str,
) -> Path:
    seed_dir, results_path = seed_dir.resolve(), results_path.resolve()
    report = validate_results(seed_dir, results_path)
    from validate_exercise_prescription_review_results import load_results

    rows = load_results(results_path)
    catalog_version = json.loads((seed_dir / "seed_manifest.json").read_text(encoding="utf-8"))[
        "catalog_version"
    ]["version_code"]
    goals: dict[tuple[str, str], dict[str, object]] = {}
    profiles: list[dict[str, object]] = []
    for row in rows:
        goal_key = (row["stable_code"], row["goal_code"])
        goals[goal_key] = {
            "catalog_version_code": catalog_version,
            "exercise_stable_code": row["stable_code"],
            "goal_code": row["goal_code"],
            "role_eligibility_code": row["role_eligibility_code"],
            "review_status_code": row["review_status_code"],
        }
        profiles.append(
            {
                "catalog_version_code": catalog_version,
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

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    name = f"exercise-prescriptions-{version_code}"
    final_dir, partial_dir = output_root / name, output_root / f".{name}.partial"
    if final_dir.exists() or partial_dir.exists():
        raise PipelineError(f"prescription output already exists: {name}")
    partial_dir.mkdir()
    try:
        goal_path = partial_dir / "goal_tag_links.jsonl"
        profile_path = partial_dir / "prescription_profiles.jsonl"
        goal_path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in goal_rows
            ),
            encoding="utf-8",
            newline="\n",
        )
        profile_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in profiles),
            encoding="utf-8",
            newline="\n",
        )
        manifest = {
            "schema_version": "1.0",
            "generator_version": GENERATOR_VERSION,
            "prescription_set_version": {"version_code": version_code, "status_code": "DRAFT"},
            "source": {
                "catalog_version_code": catalog_version,
                "catalog_manifest_sha256": sha256_bytes(
                    (seed_dir / "seed_manifest.json").read_bytes()
                ),
                "review_results_path": "validation/review_results/prescription_results.csv",
                "review_results_sha256": sha256_bytes(results_path.read_bytes()),
            },
            "review": {
                "status": "DOMAIN_APPROVED",
                "review_method_code": "AGENT_ONLY",
                "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
                "production_eligible": False,
            },
            "summary": {
                "exercise_records": report["goal_tag_records"],
                "goal_tag_records": len(goal_rows),
                "prescription_records": len(profiles),
            },
            "files": [_entry(goal_path, len(goal_rows)), _entry(profile_path, len(profiles))],
        }
        (partial_dir / "prescription_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        verify_prescriptions(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def verify_prescriptions(output_dir: Path) -> dict[str, object]:
    try:
        manifest = json.loads(
            (output_dir / "prescription_manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("prescription manifest is missing or invalid") from exc
    if (
        manifest.get("schema_version") != "1.0"
        or manifest.get("review", {}).get("production_eligible") is not False
    ):
        raise PipelineError("prescription artifact must be schema 1.0 and production-ineligible")
    files = manifest.get("files")
    if not isinstance(files, list) or {entry.get("path") for entry in files} != {
        "goal_tag_links.jsonl",
        "prescription_profiles.jsonl",
    }:
        raise PipelineError("prescription manifest files are invalid")
    for entry in files:
        raw = (output_dir / entry["path"]).read_bytes()
        if len(raw) != entry["bytes"] or sha256_bytes(raw) != entry["sha256"]:
            raise PipelineError("prescription artifact hash or byte count mismatch")
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        if len(rows) != entry["records"]:
            raise PipelineError("prescription artifact record count mismatch")
    return {"status": "valid", **manifest["summary"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("seed", type=Path)
    build.add_argument("results", type=Path)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--version-code", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    try:
        report = (
            verify_prescriptions(
                build_prescriptions(args.seed, args.results, args.output_root, args.version_code)
            )
            if args.command == "build"
            else verify_prescriptions(args.artifact)
        )
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
