"""Evaluate deterministic golden scenarios against DRAFT exercise data artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from build_exercise_alternatives import (
    artifact_entry,
    load_catalogs,
    load_json,
    string_set,
    verify_alternatives,
)
from kspo_fitness100_pipeline import PipelineError, sha256_bytes

VALID_SEVERITIES = {"NONE", "MILD", "MODERATE"}
VALID_ACTIONS = {"KEEP", "CHANGE", "FALLBACK_REQUIRED"}
VALID_BODY_AREAS = {
    "NECK",
    "SHOULDER",
    "ELBOW",
    "WRIST_HAND",
    "UPPER_BACK",
    "LOWER_BACK",
    "HIP",
    "KNEE",
    "ANKLE_FOOT",
    "CHEST",
    "ABDOMEN",
    "GENERALIZED",
    "OTHER",
}
GENERATOR_VERSION = "0.1.0"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "validation" / "golden_scenarios"


def load_scenarios(path: Path) -> dict[str, Any]:
    payload = load_json(path, "golden scenario definition")
    if payload.get("status") != "DRAFT" or payload.get("production_eligible") is not False:
        raise PipelineError("golden scenario definition must remain production-ineligible DRAFT")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise PipelineError("golden scenario definition has no scenarios")
    codes = [str(row.get("scenario_code", "")) for row in scenarios if isinstance(row, dict)]
    if (
        len(codes) != len(scenarios)
        or any(not code for code in codes)
        or len(codes) != len(set(codes))
    ):
        raise PipelineError("golden scenario codes are blank or duplicated")
    return payload


def load_alternative_rows(path: Path) -> list[dict[str, Any]]:
    verify_alternatives(path)
    rows = [
        json.loads(line)
        for line in (path / "alternatives.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not all(isinstance(row, dict) for row in rows):
        raise PipelineError("alternative rows must be objects")
    return rows


def excluded_codes(safety_dir: Path, body_area: str, severity: str) -> set[str]:
    if severity == "NONE":
        return set()
    coverage = load_json(safety_dir / "coverage_report.json", "safety coverage report")
    body = coverage.get(body_area)
    if not isinstance(body, dict) or not isinstance(body.get(severity), dict):
        raise PipelineError(f"safety coverage has no {body_area}/{severity}")
    values = body[severity].get("excluded_codes")
    if not isinstance(values, list):
        raise PipelineError("safety coverage excluded_codes must be a list")
    return {str(value) for value in values}


def eligible_alternatives(
    original_code: str,
    location_code: str,
    available_equipment: set[str],
    excluded: set[str],
    exercises: dict[str, dict[str, Any]],
    relations: list[dict[str, Any]],
) -> list[str]:
    eligible: set[str] = set()
    for relation in relations:
        if relation.get("source_exercise_stable_code") != original_code:
            continue
        if int(relation.get("difficulty_delta", 1)) > 0:
            continue
        candidate_code = str(relation.get("alternative_exercise_stable_code", ""))
        candidate = exercises.get(candidate_code)
        if candidate is None:
            raise PipelineError(
                f"alternative relation references unknown exercise: {candidate_code}"
            )
        if candidate_code in excluded:
            continue
        if location_code not in string_set(candidate, "location_codes"):
            continue
        if not string_set(candidate, "equipment_codes") <= available_equipment:
            continue
        eligible.add(candidate_code)
    return sorted(eligible)


def evaluate_scenario(
    scenario: dict[str, Any],
    exercises: dict[str, dict[str, Any]],
    relations: list[dict[str, Any]],
    safety_dir: Path,
) -> dict[str, object]:
    scenario_code = str(scenario.get("scenario_code", ""))
    original_code = str(scenario.get("original_exercise_code", ""))
    body_area = str(scenario.get("body_area_code", ""))
    severity = str(scenario.get("severity_code", ""))
    location = str(scenario.get("location_code", ""))
    equipment_raw = scenario.get("available_equipment_codes")
    if original_code not in exercises:
        raise PipelineError(f"scenario {scenario_code} has unknown original exercise")
    if body_area not in VALID_BODY_AREAS or severity not in VALID_SEVERITIES:
        raise PipelineError(f"scenario {scenario_code} has invalid body area or severity")
    if not location or not isinstance(equipment_raw, list):
        raise PipelineError(f"scenario {scenario_code} has invalid location or equipment")
    expected_action = str(scenario.get("expected_action_code", ""))
    if expected_action not in VALID_ACTIONS:
        raise PipelineError(f"scenario {scenario_code} has invalid expected action")

    excluded = excluded_codes(safety_dir, body_area, severity)
    original_excluded = original_code in excluded
    candidates = (
        eligible_alternatives(
            original_code,
            location,
            {str(value) for value in equipment_raw},
            excluded,
            exercises,
            relations,
        )
        if original_excluded
        else []
    )
    action = "KEEP" if not original_excluded else ("CHANGE" if candidates else "FALLBACK_REQUIRED")
    proposed = str(scenario.get("proposed_alternative_code", ""))
    proposal_accepted = proposed in candidates if proposed else None

    minimum = int(scenario.get("minimum_alternative_candidates", 0))
    maximum_raw = scenario.get("maximum_alternative_candidates")
    maximum = int(maximum_raw) if maximum_raw is not None else None
    checks = {
        "action": action == expected_action,
        "original_excluded": original_excluded is bool(scenario.get("expected_original_excluded")),
        "minimum_candidates": len(candidates) >= minimum,
        "maximum_candidates": maximum is None or len(candidates) <= maximum,
    }
    if "expected_proposal_accepted" in scenario:
        checks["proposal_veto"] = proposal_accepted is bool(scenario["expected_proposal_accepted"])
    passed = all(checks.values())
    return {
        "scenario_code": scenario_code,
        "passed": passed,
        "actual_action_code": action,
        "original_excluded": original_excluded,
        "alternative_candidate_codes": candidates,
        "proposal_accepted": proposal_accepted,
        "checks": checks,
    }


def evaluate_all(
    scenario_payload: dict[str, Any],
    exercises: dict[str, dict[str, Any]],
    relations: list[dict[str, Any]],
    safety_dir: Path,
) -> list[dict[str, object]]:
    scenarios = scenario_payload["scenarios"]
    if not isinstance(scenarios, list):
        raise PipelineError("golden scenarios must be a list")
    results = [evaluate_scenario(row, exercises, relations, safety_dir) for row in scenarios]
    failures = [str(result["scenario_code"]) for result in results if not result["passed"]]
    if failures:
        raise PipelineError(f"golden scenarios failed: {', '.join(failures)}")
    return results


def build_results(
    seed_dirs: list[Path],
    safety_dir: Path,
    alternatives_dir: Path,
    scenarios_path: Path,
    output_root: Path,
    version_code: str,
) -> Path:
    seed_dirs = [path.resolve() for path in seed_dirs]
    safety_dir = safety_dir.resolve()
    alternatives_dir = alternatives_dir.resolve()
    scenarios_path = scenarios_path.resolve()
    exercises = load_catalogs(seed_dirs)
    relations = load_alternative_rows(alternatives_dir)
    scenario_payload = load_scenarios(scenarios_path)
    results = evaluate_all(scenario_payload, exercises, relations, safety_dir)

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    final_dir = output_root / f"data-golden-scenarios-{version_code}"
    partial_dir = output_root / f".data-golden-scenarios-{version_code}.partial"
    if final_dir.exists() or partial_dir.exists():
        raise PipelineError(f"golden scenario output already exists: {final_dir.name}")
    partial_dir.mkdir()
    try:
        result_path = partial_dir / "scenario_results.json"
        result_payload = {
            "schema_version": "1.0",
            "scenario_set_version": scenario_payload.get("scenario_set_version"),
            "evaluation_version": version_code,
            "status": "PASSED",
            "production_eligible": False,
            "summary": {"scenarios": len(results), "passed": len(results), "failed": 0},
            "results": results,
        }
        result_path.write_text(
            json.dumps(result_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        inputs = [artifact_entry("scenario_definition", scenarios_path)]
        for seed_dir in seed_dirs:
            inputs.extend(
                [
                    artifact_entry(f"{seed_dir.name}:manifest", seed_dir / "seed_manifest.json"),
                    artifact_entry(f"{seed_dir.name}:exercises", seed_dir / "exercises.jsonl"),
                ]
            )
        inputs.extend(
            [
                artifact_entry("safety_manifest", safety_dir / "rules_manifest.json"),
                artifact_entry("safety_coverage", safety_dir / "coverage_report.json"),
                artifact_entry(
                    "alternatives_manifest", alternatives_dir / "alternatives_manifest.json"
                ),
                artifact_entry("alternatives", alternatives_dir / "alternatives.jsonl"),
            ]
        )
        raw = result_path.read_bytes()
        manifest = {
            "schema_version": "1.0",
            "generator_version": GENERATOR_VERSION,
            "evaluation_version": version_code,
            "source": {"input_artifacts": inputs},
            "review": {
                "status": "DRAFT_VALIDATED",
                "production_eligible": False,
            },
            "files": [
                {
                    "path": "scenario_results.json",
                    "sha256": sha256_bytes(raw),
                    "bytes": len(raw),
                    "records": len(results),
                }
            ],
        }
        (partial_dir / "scenario_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        verify_results(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def verify_results(output_dir: Path) -> dict[str, object]:
    manifest = load_json(output_dir / "scenario_manifest.json", "scenario manifest")
    review = manifest.get("review")
    if not isinstance(review, dict) or review.get("production_eligible") is not False:
        raise PipelineError("golden scenario results must remain production-ineligible")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        raise PipelineError("scenario manifest file entry is invalid")
    entry = files[0]
    raw = (output_dir / str(entry.get("path", ""))).read_bytes()
    if sha256_bytes(raw) != entry.get("sha256") or len(raw) != int(entry.get("bytes", -1)):
        raise PipelineError("golden scenario result hash or size mismatch")
    payload = json.loads(raw.decode("utf-8"))
    results = payload.get("results")
    if payload.get("status") != "PASSED" or not isinstance(results, list):
        raise PipelineError("golden scenario result status is invalid")
    if len(results) != int(entry.get("records", -1)) or not all(
        isinstance(result, dict) and result.get("passed") is True for result in results
    ):
        raise PipelineError("golden scenario result records are invalid")
    return {
        "scenario_set": output_dir.name,
        "scenarios": len(results),
        "status": "valid",
        "production_eligible": False,
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="evaluate golden scenarios")
    build.add_argument("seeds", type=Path, nargs="+")
    build.add_argument("--safety-rules", type=Path, required=True)
    build.add_argument("--alternatives", type=Path, required=True)
    build.add_argument("--scenarios", type=Path, required=True)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--version-code", required=True)
    verify = subparsers.add_parser("verify", help="verify stored scenario results")
    verify.add_argument("results", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "build":
            output = build_results(
                args.seeds,
                args.safety_rules,
                args.alternatives,
                args.scenarios,
                args.output_root,
                args.version_code,
            )
            result: dict[str, object] = {"status": "built", "results": str(output)}
        else:
            result = verify_results(args.results)
    except (PipelineError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
