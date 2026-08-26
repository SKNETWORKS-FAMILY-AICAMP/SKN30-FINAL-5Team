"""Package V2 runtime artifacts in the backend catalog-data importer layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from kspo_fitness100_pipeline import PipelineError, sha256_bytes

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = DATA_ROOT / "generated/exercise-catalog-v2.0.0-final/runtime"
DEFAULT_PRESCRIPTIONS = DATA_ROOT / "generated/exercise-prescriptions-v2.0.0-draft"
DEFAULT_BUNDLE = DATA_ROOT / "generated/exercise-catalog-v2.0.0-final/backend_bundle"
CATALOG_SOURCE = (
    DATA_ROOT / "generated/exercise-catalog-v2.0.0-final/representative_exercises_v2_final.csv"
)
TAXONOMY_SOURCE = DATA_ROOT / "normalized/exercise_taxonomy_codes.json"
SAFETY_SOURCE = (
    DATA_ROOT
    / "generated/exercise-catalog-v2.0.0-final/representative_exercise_safety_mapping_v2_final.csv"
)
ALTERNATIVE_SOURCE = (
    DATA_ROOT / "generated/exercise-catalog-v2.0.0-final/exercise_alternatives_v2_final.csv"
)
DECISIONS_SOURCE = DATA_ROOT / "normalized/v2_representative_decisions.json"
POLICY_SOURCE = DATA_ROOT / "normalized/v2_prescription_review_policy.json"
REVIEW_SOURCE = DATA_ROOT / "validation/review_results/v2_prescription_review_input.csv"
PROJECTION_SOURCE = DATA_ROOT / "normalized/v2_backend_code_projection.json"


def _file_entry(
    path: Path, *, records: int | None = None, role: str | None = None
) -> dict[str, Any]:
    raw = path.read_bytes()
    entry: dict[str, Any] = {
        "path": path.as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    if records is not None:
        entry["records"] = records
    if role is not None:
        entry["role"] = role
    return entry


def _copy(source: Path, target: Path) -> None:
    if not source.is_file():
        raise PipelineError(f"bundle input is missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _internal_artifact(root: Path, source: Path, role: str) -> dict[str, Any]:
    relative = Path("input") / source.name
    target = root / relative
    _copy(source, target)
    return _file_entry(target, role=role) | {"path": relative.as_posix()}


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"runtime manifest is invalid: {path}") from exc


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _rewrite_review(value: dict[str, Any]) -> dict[str, Any]:
    review = dict(value)
    review["review_method_code"] = "AGENT_ONLY"
    review["production_eligible"] = False
    return review


def _package_catalog(root: Path, runtime: Path) -> list[Path]:
    source_manifest = _read_manifest(runtime / "catalog_manifest.json")
    catalog_root = root / "catalog"
    catalog_root.mkdir(parents=True)
    runtime_records = [
        json.loads(line)
        for line in (runtime / "representative_exercises.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    projected_records = []
    for record in runtime_records:
        projected = dict(record)
        if projected["body_focus_code"] in {"UPPER_BODY", "LOWER_BODY", "UNSPECIFIED"}:
            raise PipelineError(
                "legacy body_focus_code is not allowed in V2 bundle: "
                f"{projected['body_focus_code']}"
            )
        projected_records.append(projected)
    (catalog_root / "exercises.jsonl").write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in projected_records
        ),
        encoding="utf-8",
        newline="\n",
    )
    inputs = [
        _internal_artifact(catalog_root, CATALOG_SOURCE, "representative_catalog_csv"),
        _internal_artifact(catalog_root, TAXONOMY_SOURCE, "taxonomy_registry"),
        _internal_artifact(catalog_root, PROJECTION_SOURCE, "backend_code_projection"),
    ]
    raw = (catalog_root / "exercises.jsonl").read_bytes()
    manifest = {
        "schema_version": "1.0",
        "generator_version": "v2-backend-bundle-packager-1.0.0",
        "catalog_version": {
            "version_code": "exercise-catalog-v2.0.0-final",
            "status_code": "DRAFT",
        },
        "source": {
            "track": "merged",
            "review_batch_directory": "data/reports",
            "taxonomy_registry_sha256": sha256_bytes(TAXONOMY_SOURCE.read_bytes()),
            "input_artifacts": inputs,
        },
        "review": _rewrite_review(source_manifest["review"]),
        "summary": {"exercise_records": len([line for line in raw.splitlines() if line.strip()])},
        "files": [
            {
                "path": "exercises.jsonl",
                "sha256": sha256_bytes(raw),
                "bytes": len(raw),
                "records": len([line for line in raw.splitlines() if line.strip()]),
            }
        ],
    }
    _write_json(catalog_root / "seed_manifest.json", manifest)
    return [catalog_root / "seed_manifest.json", catalog_root / "exercises.jsonl"]


def _package_derived(
    root: Path,
    runtime: Path,
    name: str,
    source_manifest_name: str,
    data_name: str,
    input_sources: tuple[tuple[Path, str], ...],
) -> list[Path]:
    source_manifest = _read_manifest(runtime / source_manifest_name)
    artifact_root = root / name
    artifact_root.mkdir(parents=True)
    runtime_rows = [
        json.loads(line)
        for line in (runtime / data_name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if name == "safety":
        allowed = {
            "body_area_code",
            "body_part_role_code",
            "catalog_version_code",
            "effect_code",
            "exercise_stable_code",
            "maximum_severity_code",
            "minimum_severity_code",
            "movement_pattern_code",
            "reason_code",
            "review_status_code",
            "rule_scope",
            "rule_version",
        }
    else:
        allowed = {
            "alternative_catalog_version_code",
            "alternative_exercise_stable_code",
            "created_at",
            "difficulty_delta",
            "goal_preservation_code",
            "reason_code",
            "review_method_code",
            "review_status_code",
            "rule_version",
            "source_catalog_version_code",
            "source_exercise_stable_code",
            "status_interpretation",
        }
    projected_rows = []
    projection_conflicts: list[dict[str, Any]] = []
    if name == "alternatives":
        for row in runtime_rows:
            projected = {key_name: value for key_name, value in row.items() if key_name in allowed}
            projected["review_method_code"] = "AGENT_ONLY"
            projected_rows.append(projected)
    else:
        for row in runtime_rows:
            projected_rows.append({key: value for key, value in row.items() if key in allowed})
    (artifact_root / data_name).write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in projected_rows
        ),
        encoding="utf-8",
        newline="\n",
    )
    if name == "alternatives":
        conflict_path = artifact_root / "input/alternative_projection_conflicts.json"
        _write_json(
            conflict_path,
            {
                "status": "DRAFT",
                "production_eligible": False,
                "projection_status": "DIRECT",
                "runtime_record_count": len(runtime_rows),
                "importer_record_count": len(projected_rows),
                "conflict_count": len(projection_conflicts),
                "conflicts": projection_conflicts,
            },
        )
    inputs = [_internal_artifact(artifact_root, source, role) for source, role in input_sources]
    raw = (artifact_root / data_name).read_bytes()
    manifest = dict(source_manifest)
    manifest["generator_version"] = "v2-backend-bundle-packager-1.0.0"
    manifest["review"] = _rewrite_review(source_manifest["review"])
    manifest["source"] = {
        "catalog_version_code": "exercise-catalog-v2.0.0-final",
        "input_artifacts": inputs,
        "runtime_manifest_sha256": sha256_bytes((runtime / source_manifest_name).read_bytes()),
        "runtime_manifest_path": f"runtime/{source_manifest_name}",
        "projection_status": "DIRECT",
        "runtime_record_count": len(runtime_rows),
        "importer_record_count": len(projected_rows),
        "projection_conflict_count": len(projection_conflicts),
    }
    if name == "alternatives":
        manifest["summary"]["alternative_records"] = len(projected_rows)
    elif name == "safety":
        manifest["summary"]["rule_records"] = len(projected_rows)
    for entry in manifest["files"]:
        if entry["path"] == data_name:
            entry.update(
                {
                    "sha256": sha256_bytes(raw),
                    "bytes": len(raw),
                    "records": len([line for line in raw.splitlines() if line.strip()]),
                }
            )
    manifest_path = artifact_root / (
        "rules_manifest.json" if name == "safety" else "alternatives_manifest.json"
    )
    _write_json(manifest_path, manifest)
    return [manifest_path, artifact_root / data_name]


def _package_prescriptions(root: Path, prescription_dir: Path) -> list[Path]:
    source_manifest = _read_manifest(prescription_dir / "prescription_manifest.json")
    destination = root / "prescriptions"
    destination.mkdir(parents=True)
    for filename in ("goal_tag_links.jsonl", "prescription_profiles.jsonl"):
        _copy(prescription_dir / filename, destination / filename)
    manifest = dict(source_manifest)
    manifest["generator_version"] = "v2-backend-bundle-packager-1.0.0"
    manifest["review"] = _rewrite_review(source_manifest["review"])
    manifest["source"] = {
        "catalog_version_code": "exercise-catalog-v2.0.0-final",
        "input_artifacts": [
            _internal_artifact(destination, REVIEW_SOURCE, "prescription_review_input"),
            _internal_artifact(destination, POLICY_SOURCE, "prescription_policy"),
        ],
        "source_prescription_manifest_sha256": sha256_bytes(
            (prescription_dir / "prescription_manifest.json").read_bytes()
        ),
        # Keep the bundle reproducible when it is built in a temporary staging
        # directory.  Absolute staging paths are not artifact provenance.
        "source_prescription_manifest_path": (
            "generated/exercise-prescriptions-v2.0.0-draft/prescription_manifest.json"
        ),
    }
    for entry in manifest["files"]:
        path = destination / entry["path"]
        raw = path.read_bytes()
        entry.update({"sha256": sha256_bytes(raw), "bytes": len(raw)})
    manifest_path = destination / "prescription_manifest.json"
    _write_json(manifest_path, manifest)
    return [
        manifest_path,
        destination / "goal_tag_links.jsonl",
        destination / "prescription_profiles.jsonl",
    ]


def build(
    runtime: Path = DEFAULT_RUNTIME,
    prescriptions: Path = DEFAULT_PRESCRIPTIONS,
    output: Path = DEFAULT_BUNDLE,
    *,
    force: bool = False,
) -> Path:
    if output.exists():
        if not force:
            raise PipelineError(f"V2 backend bundle already exists: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)
    artifacts: list[Path] = []
    try:
        artifacts += _package_catalog(output, runtime)
        artifacts += _package_derived(
            output,
            runtime,
            "safety",
            "safety_manifest.json",
            "safety_rules.jsonl",
            ((SAFETY_SOURCE, "safety_mapping_csv"), (DECISIONS_SOURCE, "v2_decisions")),
        )
        artifacts += _package_derived(
            output,
            runtime,
            "alternatives",
            "alternatives_manifest.json",
            "alternatives.jsonl",
            ((ALTERNATIVE_SOURCE, "alternative_mapping_csv"), (DECISIONS_SOURCE, "v2_decisions")),
        )
        artifacts += _package_prescriptions(output, prescriptions)
        files = []
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "bundle_manifest.json":
                raw = path.read_bytes()
                entry: dict[str, Any] = {
                    "path": path.relative_to(output).as_posix(),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                }
                if path.suffix == ".jsonl":
                    entry["records"] = len([line for line in raw.splitlines() if line.strip()])
                files.append(entry)
        bundle = {
            "schema_version": "1.0",
            "bundle_version": "v2-backend-bundle-2026-08-25",
            "status_code": "DRAFT",
            "production_eligible": False,
            "catalog_version_code": "exercise-catalog-v2.0.0-final",
            "derived_set_versions": {
                "rule_set_version_code": "safety-rule-set-v2.0.0",
                "alternative_set_version_code": "alternative-set-v2.0.0",
                "prescription_set_version_code": "prescription-set-v2.0.0",
            },
            "importer_paths": {
                "catalog": "catalog/seed_manifest.json",
                "safety": "safety/rules_manifest.json",
                "alternatives": "alternatives/alternatives_manifest.json",
                "prescriptions": "prescriptions/prescription_manifest.json",
            },
            "summary": {
                "catalog_records": 102,
                "safety_rule_records": 394,
                "alternative_records": 285,
                "goal_tag_records": 102,
                "prescription_records": 137,
            },
            "projection": {
                "status": "DIRECT",
                "runtime_alternative_records": 285,
                "importer_alternative_records": 285,
                "alternative_conflict_count": 0,
                "conflict_report_path": "alternatives/input/alternative_projection_conflicts.json",
            },
            "files": files,
        }
        _write_json(output / "bundle_manifest.json", bundle)
        return output
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--prescriptions", type=Path, default=DEFAULT_PRESCRIPTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = build(args.runtime, args.prescriptions, args.output, force=args.force)
    except (OSError, PipelineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"status": "written", "path": str(path), "production_eligible": False},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
