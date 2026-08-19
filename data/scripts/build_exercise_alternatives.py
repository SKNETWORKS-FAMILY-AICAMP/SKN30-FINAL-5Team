"""Build and verify production-ineligible exercise alternative relations."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kspo_fitness100_pipeline import PipelineError, sha256_bytes

GENERATOR_VERSION = "0.1.0"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "generated"
DEFAULT_POLICY = (
    Path(__file__).resolve().parents[1] / "normalized" / "exercise_alternative_policy.json"
)
REASON_CODES = {"DIFFICULTY", "EQUIPMENT", "LOCATION", "DISCOMFORT"}


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"{label} is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise PipelineError(f"{label} root must be an object")
    return payload


def load_policy(path: Path) -> dict[str, Any]:
    policy = load_json(path, "alternative policy")
    if policy.get("status") != "APPROVED_FOR_DRAFT_PIPELINE":
        raise PipelineError("alternative policy is not approved for the DRAFT pipeline")
    if policy.get("review_method_code") != "AGENT_ONLY":
        raise PipelineError("alternative policy must use AGENT_ONLY")
    if policy.get("production_eligible") is not False:
        raise PipelineError("alternative policy must remain production-ineligible")
    ranks = policy.get("difficulty_rank")
    if not isinstance(ranks, dict) or set(ranks) != {"BEGINNER", "INTERMEDIATE", "ADVANCED"}:
        raise PipelineError("alternative policy difficulty ranks are invalid")
    reasons = policy.get("reason_codes")
    if not isinstance(reasons, list) or set(map(str, reasons)) != REASON_CODES:
        raise PipelineError("alternative policy reason codes are invalid")
    return policy


def load_catalogs(seed_dirs: list[Path]) -> dict[str, dict[str, Any]]:
    exercises: dict[str, dict[str, Any]] = {}
    for seed_dir in seed_dirs:
        manifest = load_json(seed_dir / "seed_manifest.json", "seed manifest")
        review = manifest.get("review")
        if not isinstance(review, dict) or review.get("production_eligible") is not False:
            raise PipelineError("input catalog seed must remain production-ineligible")
        catalog = manifest.get("catalog_version")
        if not isinstance(catalog, dict) or not str(catalog.get("version_code", "")):
            raise PipelineError(f"catalog version is missing: {seed_dir.name}")
        raw = (seed_dir / "exercises.jsonl").read_bytes()
        files = manifest.get("files")
        if not isinstance(files, list) or not files or not isinstance(files[0], dict):
            raise PipelineError(f"seed manifest files are invalid: {seed_dir.name}")
        if sha256_bytes(raw) != files[0].get("sha256"):
            raise PipelineError(f"seed exercises hash mismatch: {seed_dir.name}")
        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise PipelineError("catalog exercise record must be an object")
            code = str(record.get("stable_code", ""))
            if not code or code in exercises:
                raise PipelineError(f"catalog stable code is blank or duplicated: {code}")
            if record.get("review_status_code") != "DOMAIN_APPROVED":
                raise PipelineError(f"catalog exercise is not reviewed: {code}")
            record["catalog_version_code"] = str(catalog["version_code"])
            exercises[code] = record
    if not exercises:
        raise PipelineError("no catalog exercises were loaded")
    return exercises


def goal_groups(
    policy: dict[str, Any], exercises: dict[str, dict[str, Any]]
) -> dict[str, list[str]]:
    raw_groups = policy.get("exact_goal_groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        raise PipelineError("alternative policy has no exact goal groups")
    groups: dict[str, list[str]] = {}
    assigned: set[str] = set()
    for raw_group in raw_groups:
        if not isinstance(raw_group, dict) or not isinstance(raw_group.get("exercise_codes"), list):
            raise PipelineError("alternative goal group is invalid")
        goal = str(raw_group.get("goal_preservation_code", ""))
        codes = [str(code) for code in raw_group["exercise_codes"]]
        if not goal or goal in groups or len(codes) < 2 or len(codes) != len(set(codes)):
            raise PipelineError(
                f"alternative goal group is blank, duplicated, or too small: {goal}"
            )
        unknown = set(codes) - set(exercises)
        overlap = set(codes) & assigned
        if unknown or overlap:
            raise PipelineError(
                f"alternative goal group {goal} has unknown={sorted(unknown)} "
                f"overlap={sorted(overlap)}"
            )
        groups[goal] = codes
        assigned.update(codes)
    return groups


def string_set(record: dict[str, Any], field: str) -> set[str]:
    value = record.get(field)
    if not isinstance(value, list):
        raise PipelineError(f"catalog {field} must be a list")
    return {str(item) for item in value}


def exact_reason(source: dict[str, Any], alternative: dict[str, Any], delta: int) -> str | None:
    if delta < 0:
        return "DIFFICULTY"
    if string_set(source, "location_codes") != string_set(alternative, "location_codes"):
        return "LOCATION"
    if string_set(source, "equipment_codes") != string_set(alternative, "equipment_codes"):
        return "EQUIPMENT"
    return None


def relation_record(
    source: dict[str, Any],
    alternative: dict[str, Any],
    reason: str,
    goal: str,
    delta: int,
    policy: dict[str, Any],
) -> dict[str, object]:
    return {
        "source_exercise_stable_code": source["stable_code"],
        "source_catalog_version_code": source["catalog_version_code"],
        "alternative_exercise_stable_code": alternative["stable_code"],
        "alternative_catalog_version_code": alternative["catalog_version_code"],
        "reason_code": reason,
        "goal_preservation_code": goal,
        "difficulty_delta": delta,
        "review_status_code": "DOMAIN_APPROVED",
        "review_method_code": "AGENT_ONLY",
        "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
        "rule_version": str(policy["policy_version"]),
        "created_at": str(policy["reviewed_at"]),
    }


def build_relations(
    policy: dict[str, Any], exercises: dict[str, dict[str, Any]]
) -> list[dict[str, object]]:
    groups = goal_groups(policy, exercises)
    ranks = {str(key): int(value) for key, value in policy["difficulty_rank"].items()}
    relations: list[dict[str, object]] = []

    for goal, codes in groups.items():
        for source_code in codes:
            source = exercises[source_code]
            source_rank = ranks[str(source["difficulty_code"])]
            for alternative_code in codes:
                if source_code == alternative_code:
                    continue
                alternative = exercises[alternative_code]
                delta = ranks[str(alternative["difficulty_code"])] - source_rank
                if delta > 0:
                    continue
                reason = exact_reason(source, alternative, delta)
                if reason is not None:
                    relations.append(
                        relation_record(source, alternative, reason, goal, delta, policy)
                    )

    cross_rules = policy.get("discomfort_cross_group_rules")
    if not isinstance(cross_rules, list):
        raise PipelineError("alternative policy discomfort rules are invalid")
    for raw_rule in cross_rules:
        if not isinstance(raw_rule, dict):
            raise PipelineError("discomfort rule must be an object")
        source_group = str(raw_rule.get("source_goal_group", ""))
        alternative_group = str(raw_rule.get("alternative_goal_group", ""))
        if source_group not in groups or alternative_group not in groups:
            raise PipelineError("discomfort rule references an unknown goal group")
        directions = [(source_group, alternative_group)]
        if raw_rule.get("bidirectional") is True:
            directions.append((alternative_group, source_group))
        required_difficulty = str(raw_rule.get("alternative_difficulty_code", ""))
        reason = str(raw_rule.get("reason_code", ""))
        goal = str(raw_rule.get("goal_preservation_code", ""))
        if required_difficulty not in ranks or reason != "DISCOMFORT" or not goal:
            raise PipelineError("discomfort rule fields are invalid")
        for from_group, to_group in directions:
            for source_code in groups[from_group]:
                source = exercises[source_code]
                source_rank = ranks[str(source["difficulty_code"])]
                for alternative_code in groups[to_group]:
                    alternative = exercises[alternative_code]
                    if alternative["difficulty_code"] != required_difficulty:
                        continue
                    delta = ranks[str(alternative["difficulty_code"])] - source_rank
                    if delta <= 0:
                        relations.append(
                            relation_record(source, alternative, reason, goal, delta, policy)
                        )

    relations.sort(
        key=lambda row: (
            str(row["source_exercise_stable_code"]),
            str(row["reason_code"]),
            str(row["goal_preservation_code"]),
            str(row["alternative_exercise_stable_code"]),
        )
    )
    natural_keys = {
        (
            row["source_exercise_stable_code"],
            row["alternative_exercise_stable_code"],
            row["reason_code"],
            row["goal_preservation_code"],
        )
        for row in relations
    }
    if len(natural_keys) != len(relations):
        raise PipelineError("duplicate alternative relations were generated")
    return relations


def safety_exclusions(safety_dir: Path, body_area: str, severity: str) -> set[str]:
    report = load_json(safety_dir / "coverage_report.json", "safety coverage report")
    body = report.get(body_area)
    if not isinstance(body, dict) or not isinstance(body.get(severity), dict):
        raise PipelineError(f"safety coverage has no {body_area}/{severity}")
    excluded = body[severity].get("excluded_codes")
    if not isinstance(excluded, list):
        raise PipelineError("safety coverage excluded_codes must be a list")
    return {str(code) for code in excluded}


def coverage_report(
    exercises: dict[str, dict[str, Any]],
    relations: list[dict[str, object]],
    policy: dict[str, Any],
    safety_dir: Path,
) -> dict[str, object]:
    outgoing: dict[str, list[dict[str, object]]] = defaultdict(list)
    for relation in relations:
        outgoing[str(relation["source_exercise_stable_code"])].append(relation)
    groups = goal_groups(policy, exercises)
    knee_sources = groups["KNEE_EXTENSION_STRENGTH"]
    knee_result: dict[str, object] = {}
    for severity in ("MILD", "MODERATE"):
        excluded = safety_exclusions(safety_dir, "KNEE", severity)
        counts: dict[str, int] = {}
        same_location_counts: dict[str, int] = {}
        for source_code in knee_sources:
            candidates = [
                exercises[str(row["alternative_exercise_stable_code"])]
                for row in outgoing[source_code]
                if row["reason_code"] == "DISCOMFORT"
                and str(row["alternative_exercise_stable_code"]) not in excluded
            ]
            counts[source_code] = len(candidates)
            source_locations = string_set(exercises[source_code], "location_codes")
            same_location_counts[source_code] = sum(
                bool(source_locations & string_set(candidate, "location_codes"))
                for candidate in candidates
            )
        knee_result[severity] = {
            "source_exercises": len(knee_sources),
            "sources_with_safe_candidate": sum(count > 0 for count in counts.values()),
            "sources_with_same_location_candidate": sum(
                count > 0 for count in same_location_counts.values()
            ),
            "minimum_safe_candidates": min(counts.values()),
            "maximum_safe_candidates": max(counts.values()),
            "fallback_required_sources": sorted(
                code for code, count in counts.items() if count == 0
            ),
        }
    if int(knee_result["MILD"]["sources_with_safe_candidate"]) != len(knee_sources):  # type: ignore[index]
        raise PipelineError("every knee-dominant source needs a MILD-safe lower-body alternative")

    sources_with = set(outgoing)
    return {
        "total_exercises": len(exercises),
        "relation_records": len(relations),
        "sources_with_alternatives": len(sources_with),
        "sources_without_alternatives": sorted(set(exercises) - sources_with),
        "reason_counts": dict(
            sorted(Counter(str(row["reason_code"]) for row in relations).items())
        ),
        "goal_counts": dict(
            sorted(Counter(str(row["goal_preservation_code"]) for row in relations).items())
        ),
        "knee_discomfort": knee_result,
        "selection_guards": [
            "REAPPLY_SAFETY_RULES",
            "REQUIRE_CURRENT_LOCATION",
            "REQUIRE_AVAILABLE_EQUIPMENT",
            "DO_NOT_INCREASE_DIFFICULTY",
        ],
        "production_eligible": False,
    }


def artifact_entry(role: str, path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"role": role, "path": path.name, "sha256": sha256_bytes(raw), "bytes": len(raw)}


def build_alternatives(
    seed_dirs: list[Path],
    safety_dir: Path,
    policy_path: Path,
    output_root: Path,
    version_code: str,
) -> Path:
    seed_dirs = [path.resolve() for path in seed_dirs]
    safety_dir = safety_dir.resolve()
    policy_path = policy_path.resolve()
    policy = load_policy(policy_path)
    exercises = load_catalogs(seed_dirs)
    relations = build_relations(policy, exercises)
    coverage = coverage_report(exercises, relations, policy, safety_dir)

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    directory_name = f"exercise-alternatives-{version_code}"
    final_dir = output_root / directory_name
    partial_dir = output_root / f".{directory_name}.partial"
    if final_dir.exists() or partial_dir.exists():
        raise PipelineError(f"alternative output already exists: {directory_name}")
    partial_dir.mkdir()
    try:
        relations_path = partial_dir / "alternatives.jsonl"
        relations_path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in relations
            ),
            encoding="utf-8",
            newline="\n",
        )
        coverage_path = partial_dir / "coverage_report.json"
        coverage_path.write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        input_artifacts = [artifact_entry("alternative_policy", policy_path)]
        for seed_dir in seed_dirs:
            input_artifacts.extend(
                [
                    artifact_entry(f"{seed_dir.name}:manifest", seed_dir / "seed_manifest.json"),
                    artifact_entry(f"{seed_dir.name}:exercises", seed_dir / "exercises.jsonl"),
                ]
            )
        input_artifacts.extend(
            [
                artifact_entry("safety_rules_manifest", safety_dir / "rules_manifest.json"),
                artifact_entry("safety_coverage", safety_dir / "coverage_report.json"),
            ]
        )
        relation_raw = relations_path.read_bytes()
        coverage_raw = coverage_path.read_bytes()
        manifest = {
            "schema_version": "1.0",
            "generator_version": GENERATOR_VERSION,
            "alternative_set_version": {"version_code": version_code, "status_code": "DRAFT"},
            "source": {
                "catalog_seeds": [path.name for path in seed_dirs],
                "safety_rule_set": safety_dir.name,
                "input_artifacts": input_artifacts,
            },
            "review": {
                "status": "DOMAIN_APPROVED",
                "review_method_code": "AGENT_ONLY",
                "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
                "production_eligible": False,
            },
            "summary": {
                "exercise_records": len(exercises),
                "alternative_records": len(relations),
                "sources_with_alternatives": coverage["sources_with_alternatives"],
            },
            "files": [
                {
                    "path": "alternatives.jsonl",
                    "sha256": sha256_bytes(relation_raw),
                    "bytes": len(relation_raw),
                    "records": len(relations),
                },
                {
                    "path": "coverage_report.json",
                    "sha256": sha256_bytes(coverage_raw),
                    "bytes": len(coverage_raw),
                    "records": 1,
                },
            ],
        }
        (partial_dir / "alternatives_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        verify_alternatives(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def verify_alternatives(output_dir: Path) -> dict[str, object]:
    manifest = load_json(output_dir / "alternatives_manifest.json", "alternatives manifest")
    if manifest.get("schema_version") != "1.0":
        raise PipelineError("unsupported alternatives manifest schema")
    review = manifest.get("review")
    if not isinstance(review, dict) or review.get("production_eligible") is not False:
        raise PipelineError("alternative set must remain production-ineligible")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 2:
        raise PipelineError("alternatives manifest must list relation and coverage files")
    for entry in files:
        if not isinstance(entry, dict):
            raise PipelineError("alternatives manifest file entry must be an object")
        raw = (output_dir / str(entry.get("path", ""))).read_bytes()
        if sha256_bytes(raw) != entry.get("sha256") or len(raw) != int(entry.get("bytes", -1)):
            raise PipelineError("alternative artifact hash or size mismatch")
    raw_text = (output_dir / "alternatives.jsonl").read_text(encoding="utf-8")
    relations = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
    expected = next(entry for entry in files if entry.get("path") == "alternatives.jsonl")
    if len(relations) != int(expected.get("records", -1)):
        raise PipelineError("alternative relation count mismatch")
    keys: set[tuple[str, str, str, str]] = set()
    for row in relations:
        source = str(row.get("source_exercise_stable_code", ""))
        alternative = str(row.get("alternative_exercise_stable_code", ""))
        reason = str(row.get("reason_code", ""))
        goal = str(row.get("goal_preservation_code", ""))
        if not source or source == alternative or reason not in REASON_CODES or not goal:
            raise PipelineError("alternative relation fields are invalid")
        if int(row.get("difficulty_delta", 1)) > 0:
            raise PipelineError("alternative relation increases difficulty")
        if row.get("review_method_code") != "AGENT_ONLY":
            raise PipelineError("alternative relation review method is invalid")
        key = (source, alternative, reason, goal)
        if key in keys:
            raise PipelineError("alternative relation is duplicated")
        keys.add(key)
    return {
        "alternative_set": output_dir.name,
        "relations": len(relations),
        "status": "valid",
        "production_eligible": False,
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build alternative relations")
    build.add_argument("seeds", type=Path, nargs="+")
    build.add_argument("--safety-rules", type=Path, required=True)
    build.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--version-code", required=True)
    verify = subparsers.add_parser("verify", help="verify alternative artifacts")
    verify.add_argument("alternatives", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "build":
            output = build_alternatives(
                args.seeds,
                args.safety_rules,
                args.policy,
                args.output_root,
                args.version_code,
            )
            result: dict[str, object] = {"status": "built", "alternatives": str(output)}
        else:
            result = verify_alternatives(args.alternatives)
    except (PipelineError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
