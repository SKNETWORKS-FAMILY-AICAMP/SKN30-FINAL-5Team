"""Package the v2.0.2 canonical payloads in the backend importer's bundle layout.

The v2.0.2 final directory ships one ``manifest.json`` plus 24 audit artifacts,
while the backend importer requires a ``bundle_manifest.json`` whose file set
matches the directory exactly. Rather than teach the importer a second manifest
dialect, this packager reads only the six payloads named in
``import_contract.canonical_payloads`` and writes the same bundle shape the
v2.0.1 packager produces (TASK-CATALOG-V2_0_2-IMPORT decision A1).

Two projections are needed, and both are mechanical:

* The alternative map is keyed for review, not for import. It carries the pain
  area, NRS band, service action and strategy already; this adds the relation
  fields the backend contract requires and derives nothing that is not already
  determined by the reviewed row.
* Media rows that have no asset are not packaged at all (decision B1). The
  backend column is ``NOT NULL`` with a ``catalog-media/`` pattern, and an
  absent row already means "no media" to every reader.

Nothing here approves data. The bundle stays ``DRAFT`` and
``production_eligible=false``; promotion is the backend's approval registry.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from kspo_fitness100_pipeline import PipelineError

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FINAL = DATA_ROOT / "generated/exercise-catalog-v2.0.2-final"
DEFAULT_BUNDLE = DATA_ROOT / "generated/exercise-catalog-v2.0.2-final/backend_bundle"
TAXONOMY_SOURCE = DATA_ROOT / "normalized/exercise_taxonomy_codes.json"

CATALOG_VERSION_CODE = "exercise-catalog-v2.0.2-final"
RULE_SET_VERSION_CODE = "safety-rule-set-v2.0.2"
ALTERNATIVE_SET_VERSION_CODE = "alternative-set-v2.0.2"
PRESCRIPTION_SET_VERSION_CODE = "prescription-set-v2.0.2"
MEDIA_SET_VERSION_CODE = "media-set-v2.0.2"
ALTERNATIVE_RULE_VERSION = "alternative-rule-v2.0.2"
GENERATOR_VERSION = "v2-0-2-backend-bundle-packager-1.0.0"
# The reviewed batch approval timestamp, not the packaging run. Re-packaging the
# same payloads has to produce byte-identical output.
GENERATED_AT = "2026-08-29T00:00:00+09:00"

# NRS_1_3 keeps the training goal and lowers load; NRS_4_6 leaves the painful
# area alone and offers recovery work. This mirrors the DOMAIN_RULES table and
# the v2.0.1 alternative policy; it is a restatement, not a new decision.
_GOAL_PRESERVATION_BY_CONDITION = {
    "NRS_1_3": "SAME_GOAL",
    "NRS_4_6": "ACTIVE_RECOVERY",
}
_SERVICE_ACTION_BY_CONDITION = {
    "NRS_1_3": "LOAD_REDUCED",
    "NRS_4_6": "SKIP_AFFECTED_AREA",
}
_DIFFICULTY_RANK = {"BEGINNER": 0, "INTERMEDIATE": 1}

_CATALOG_FIELDS = (
    "stable_code",
    "name_ko",
    "name_en",
    "training_type_code",
    "body_focus_code",
    "primary_movement_pattern_code",
    "difficulty_code",
    "timing_mode_code",
    "default_seconds_per_rep",
    "default_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "recovery_eligible",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "equipment_codes",
    "location_codes",
    "instruction_summary_ko",
    "form_cues_ko",
    "instruction_content_version",
    "review_status_code",
    "source_identity",
    "record_type",
    "family_code",
    "general_pool_included",
)
_SAFETY_FIELDS = (
    "review_status_code",
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
)
_GOAL_FIELDS = (
    "catalog_version_code",
    "exercise_stable_code",
    "goal_code",
    "role_eligibility_code",
    "review_status_code",
)
_PRESCRIPTION_FIELDS = (
    "review_status_code",
    "catalog_version_code",
    "exercise_stable_code",
    "goal_code",
    "experience_level_code",
    "phase_code",
    "intensity_code",
    "sets",
    "reps",
    "work_seconds_per_set",
    "rest_seconds_per_set",
    "prescription_version",
)
_MEDIA_FIELDS = (
    "representative_exercise_id",
    "s3_key",
    "media_status",
    "rights_review_status",
    "rights_reviewer",
    "rights_reviewed_at",
    "rights_evidence_reference",
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"v2.0.2 artifact is invalid: {path}") from exc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineError(f"v2.0.2 payload is missing: {path}") from exc
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise PipelineError(f"v2.0.2 payload is missing: {path}") from exc


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return path.read_bytes()


def _draft_review(review_method_code: str = "AGENT_ONLY") -> dict[str, Any]:
    return {
        "status": "DOMAIN_APPROVED",
        "review_method_code": review_method_code,
        "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
        "production_eligible": False,
    }


def _file_entry(path: Path, root: Path, *, records: int | None = None) -> dict[str, Any]:
    raw = path.read_bytes()
    entry: dict[str, Any] = {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(raw),
        "bytes": len(raw),
    }
    if records is not None:
        entry["records"] = records
    return entry


def _verify_canonical_payloads(final: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    """Resolve the six canonical payloads and fail closed on any hash drift."""
    contract = manifest.get("import_contract") or {}
    payloads = contract.get("canonical_payloads") or {}
    expected_kinds = {"catalog", "safety", "alternatives", "goals", "fitt", "media"}
    if set(payloads) != expected_kinds:
        raise PipelineError(
            f"v2.0.2 import contract does not name the six canonical payloads: {sorted(payloads)}"
        )
    recorded = manifest.get("artifact_sha256") or {}
    resolved: dict[str, Path] = {}
    for kind, relative in sorted(payloads.items()):
        path = final / relative
        if not path.is_file():
            raise PipelineError(f"v2.0.2 canonical payload is missing: {relative}")
        expected = recorded.get(relative)
        if expected is None:
            raise PipelineError(f"v2.0.2 manifest records no hash for {relative}")
        actual = _sha256(path.read_bytes())
        if actual != expected:
            raise PipelineError(
                f"v2.0.2 canonical payload hash does not match the manifest: {relative}"
            )
        resolved[kind] = path
    return resolved


def _project_catalog(
    rows: list[dict[str, Any]], *, exclude_incomplete: bool = False
) -> tuple[list[dict[str, Any]], list[str]]:
    by_exercise_id = {str(row.get("exercise_id")): row for row in rows}
    projected: list[dict[str, Any]] = []
    for row in rows:
        record = {field: row.get(field) for field in _CATALOG_FIELDS}
        record["source_track"] = row.get("source_track")
        # The payload points a VARIANT at its representative by external id; the
        # backend keys every relation by stable code.
        record_type = row.get("record_type")
        parent_id = str(row.get("representative_exercise_id") or "")
        if record_type == "VARIANT":
            parent = by_exercise_id.get(parent_id)
            if parent is None:
                raise PipelineError(
                    f"VARIANT names a representative outside the catalog: {row.get('stable_code')}"
                )
            record["representative_stable_code"] = parent["stable_code"]
        else:
            record["representative_stable_code"] = None
        if not record.get("name_en"):
            record["name_en"] = ""
        # A record the payload never marked as a base candidate is not one.
        record["general_pool_included"] = bool(row.get("general_pool_included"))
        projected.append(record)
    if not exclude_incomplete:
        _require_catalog_content(projected)
        return projected, []
    # Withholding is explicit and recorded: a record the backend cannot accept is
    # left out of the bundle entirely rather than padded to fit, and every
    # dependent row is dropped with it so no orphan reaches the importer.
    incomplete = _incomplete_catalog_records(projected)
    excluded = sorted({code for codes in incomplete.values() for code in codes})
    kept = [record for record in projected if record["stable_code"] not in set(excluded)]
    _require_catalog_content(kept)
    return kept, excluded


def _incomplete_catalog_records(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Name every record the backend contract cannot accept, by missing field."""
    gaps: dict[str, list[str]] = {
        "form_cues_ko": [],
        "default_rest_seconds": [],
        "default_transition_seconds": [],
        "instruction_summary_ko": [],
    }
    for record in records:
        code = str(record.get("stable_code"))
        if not record.get("form_cues_ko"):
            gaps["form_cues_ko"].append(code)
        if record.get("default_rest_seconds") is None:
            gaps["default_rest_seconds"].append(code)
        if record.get("default_transition_seconds") is None:
            gaps["default_transition_seconds"].append(code)
        if not record.get("instruction_summary_ko"):
            gaps["instruction_summary_ko"].append(code)
    return {field: codes for field, codes in gaps.items() if codes}


def _require_catalog_content(records: list[dict[str, Any]]) -> None:
    """Refuse to package a catalog the backend contract cannot accept.

    The packager only moves reviewed values. It will not invent a form cue, a
    rest interval or a transition interval to satisfy a NOT NULL column: those
    are user-facing coaching content and FITT dosage, and data/AGENTS.md puts
    both behind explicit review. Failing here names what is missing so the gap
    is closed in the pipeline that owns the content.
    """
    incomplete = _incomplete_catalog_records(records)
    if incomplete:
        summary = ", ".join(
            f"{field}={len(codes)} (e.g. {codes[0]})" for field, codes in sorted(incomplete.items())
        )
        raise PipelineError(
            "v2.0.2 catalog is not importable: required exercise content is missing - "
            + summary
            + " (pass --exclude-incomplete to package the complete records only)"
        )


def _project_alternatives(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for row in rows:
        condition_code = row.get("condition_code")
        if condition_code not in _GOAL_PRESERVATION_BY_CONDITION:
            raise PipelineError(
                f"alternative relation has an unsupported NRS band: {condition_code}"
            )
        if row.get("service_action_code") != _SERVICE_ACTION_BY_CONDITION[condition_code]:
            raise PipelineError(
                f"service_action_code does not match {condition_code}: {row.get('map_relation_id')}"
            )
        if row.get("direction_code") != "A_TO_B":
            raise PipelineError("alternative relation direction must be A_TO_B")
        source_rank = _DIFFICULTY_RANK.get(str(row.get("source_difficulty_code")))
        target_rank = _DIFFICULTY_RANK.get(str(row.get("target_difficulty_code")))
        if source_rank is None or target_rank is None:
            raise PipelineError(
                f"alternative relation has an unknown difficulty: {row.get('map_relation_id')}"
            )
        difficulty_delta = target_rank - source_rank
        if difficulty_delta > 0:
            raise PipelineError(
                f"an alternative must not be harder than its source: {row.get('map_relation_id')}"
            )
        projected.append(
            {
                "source_catalog_version_code": CATALOG_VERSION_CODE,
                "source_exercise_stable_code": row["source_exercise_stable_code"],
                "alternative_catalog_version_code": CATALOG_VERSION_CODE,
                "alternative_exercise_stable_code": row["target_exercise_stable_code"],
                "reason_code": "DISCOMFORT",
                "goal_preservation_code": _GOAL_PRESERVATION_BY_CONDITION[condition_code],
                "difficulty_delta": difficulty_delta,
                "review_status_code": row["review_status_code"],
                "review_method_code": "AGENT_ONLY",
                "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
                "rule_version": ALTERNATIVE_RULE_VERSION,
                "created_at": GENERATED_AT,
                "pain_discomfort_area_code": row["pain_discomfort_area_code"],
                "condition_code": condition_code,
                "service_action_code": row["service_action_code"],
                "target_strategy_code": row["target_strategy_code"],
            }
        )
    return projected


def _project_media(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], int]:
    projected: list[dict[str, Any]] = []
    withheld = 0
    for row in rows:
        if row.get("media_status") != "AVAILABLE" or not row.get("s3_key"):
            withheld += 1
            continue
        projected.append({field: (row.get(field) or None) for field in _MEDIA_FIELDS})
    return projected, withheld


def _require_safety_coverage(catalog: list[dict[str, Any]], safety: list[dict[str, Any]]) -> None:
    """Refuse a catalog whose records carry no substantive safety rule.

    A row that names an exercise but leaves ``rule_scope`` empty is a
    placeholder, not a rule. Importing an exercise behind one would put it in
    front of users with nothing for the safety evaluation to match on, so it
    could never be excluded for any reported pain area. That is the one failure
    mode the deterministic safety veto exists to prevent, so it fails closed
    here rather than at recommendation time.
    """
    covered = {
        str(rule.get("exercise_stable_code"))
        for rule in safety
        if rule.get("rule_scope") is not None
    }
    uncovered = sorted(
        str(record["stable_code"]) for record in catalog if record["stable_code"] not in covered
    )
    if uncovered:
        raise PipelineError(
            f"v2.0.2 catalog is not importable: {len(uncovered)} exercises have no safety rule, "
            f"only a placeholder row (e.g. {uncovered[0]})"
        )


def _validate_foreign_keys(
    catalog: list[dict[str, Any]],
    safety: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    prescriptions: list[dict[str, Any]],
    alternatives: list[dict[str, Any]],
) -> None:
    stable_codes = {row["stable_code"] for row in catalog}
    if len(stable_codes) != len(catalog):
        raise PipelineError("v2.0.2 catalog contains duplicate stable codes")
    referenced = (
        ("safety", (row["exercise_stable_code"] for row in safety)),
        ("goal", (row["exercise_stable_code"] for row in goals)),
        ("prescription", (row["exercise_stable_code"] for row in prescriptions)),
        ("alternative source", (row["source_exercise_stable_code"] for row in alternatives)),
        ("alternative target", (row["alternative_exercise_stable_code"] for row in alternatives)),
    )
    for label, codes in referenced:
        orphans = {code for code in codes if code not in stable_codes}
        if orphans:
            raise PipelineError(
                f"{label} references {len(orphans)} stable codes outside the catalog"
            )
    variants = {
        row["representative_stable_code"]
        for row in catalog
        if row.get("representative_stable_code")
    }
    missing_parents = variants - stable_codes
    if missing_parents:
        raise PipelineError(f"variant parents are outside the catalog: {sorted(missing_parents)}")
    # The database identifies a relation by band and area as well, so a
    # collision here would be silently dropped at import.
    relation_keys = {
        (
            row["source_exercise_stable_code"],
            row["alternative_exercise_stable_code"],
            row["reason_code"],
            row["goal_preservation_code"],
            row["rule_version"],
            row["condition_code"],
            row["pain_discomfort_area_code"],
        )
        for row in alternatives
    }
    if len(relation_keys) != len(alternatives):
        raise PipelineError("v2.0.2 alternatives contain duplicate relation keys")


def build(
    final: Path = DEFAULT_FINAL,
    output: Path = DEFAULT_BUNDLE,
    *,
    force: bool = False,
    exclude_incomplete: bool = False,
) -> Path:
    manifest = _read_json(final / "manifest.json")
    if manifest.get("catalog_version_code") != CATALOG_VERSION_CODE:
        raise PipelineError("v2.0.2 manifest names a different catalog version")
    payloads = _verify_canonical_payloads(final, manifest)

    catalog_rows, excluded_codes = _project_catalog(
        _read_jsonl(payloads["catalog"]), exclude_incomplete=exclude_incomplete
    )
    excluded = set(excluded_codes)
    safety_rows = [
        {field: row.get(field) for field in _SAFETY_FIELDS}
        for row in _read_jsonl(payloads["safety"])
        if row.get("exercise_stable_code") not in excluded
    ]
    goal_rows = [
        {field: row.get(field) for field in _GOAL_FIELDS}
        for row in _read_jsonl(payloads["goals"])
        if row.get("exercise_stable_code") not in excluded
    ]
    prescription_rows = [
        {field: row.get(field) for field in _PRESCRIPTION_FIELDS}
        for row in _read_jsonl(payloads["fitt"])
        if row.get("exercise_stable_code") not in excluded
    ]
    alternative_rows = [
        row
        for row in _project_alternatives(_read_jsonl(payloads["alternatives"]))
        if row["source_exercise_stable_code"] not in excluded
        and row["alternative_exercise_stable_code"] not in excluded
    ]
    media_rows, withheld_media = _project_media(_read_csv(payloads["media"]))
    _require_safety_coverage(catalog_rows, safety_rows)
    _validate_foreign_keys(
        catalog_rows, safety_rows, goal_rows, prescription_rows, alternative_rows
    )

    if output.exists():
        if not force:
            raise PipelineError(f"v2.0.2 backend bundle already exists: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        taxonomy_sha256 = _sha256(TAXONOMY_SOURCE.read_bytes())

        catalog_root = output / "catalog"
        _write_jsonl(catalog_root / "exercises.jsonl", catalog_rows)
        _write_json(
            catalog_root / "seed_manifest.json",
            {
                "schema_version": "1.1",
                "generator_version": GENERATOR_VERSION,
                "catalog_version": {
                    "version_code": CATALOG_VERSION_CODE,
                    "status_code": "DRAFT",
                },
                "source": {
                    "track": "merged",
                    "review_batch_directory": "data/reports",
                    "taxonomy_registry_sha256": taxonomy_sha256,
                    "input_artifacts": [],
                },
                "review": _draft_review(),
                "summary": {"exercise_records": len(catalog_rows)},
                "files": [
                    _file_entry(
                        catalog_root / "exercises.jsonl", catalog_root, records=len(catalog_rows)
                    )
                ],
            },
        )

        safety_root = output / "safety"
        _write_jsonl(safety_root / "safety_rules.jsonl", safety_rows)
        _write_json(
            safety_root / "rules_manifest.json",
            {
                "schema_version": "1.0",
                "generator_version": GENERATOR_VERSION,
                "rule_set_version": {
                    "version_code": RULE_SET_VERSION_CODE,
                    "status_code": "DRAFT",
                },
                "source": {"catalog_version_code": CATALOG_VERSION_CODE, "input_artifacts": []},
                "review": _draft_review(),
                "summary": {"rule_records": len(safety_rows)},
                "files": [
                    _file_entry(
                        safety_root / "safety_rules.jsonl", safety_root, records=len(safety_rows)
                    )
                ],
            },
        )

        alternative_root = output / "alternatives"
        _write_jsonl(alternative_root / "alternatives.jsonl", alternative_rows)
        _write_json(
            alternative_root / "alternatives_manifest.json",
            {
                "schema_version": "1.0",
                "generator_version": GENERATOR_VERSION,
                "alternative_set_version": {
                    "version_code": ALTERNATIVE_SET_VERSION_CODE,
                    "status_code": "DRAFT",
                },
                "source": {"catalog_version_code": CATALOG_VERSION_CODE, "input_artifacts": []},
                "review": _draft_review("DOMAIN_REVIEWER"),
                "summary": {"alternative_records": len(alternative_rows)},
                "files": [
                    _file_entry(
                        alternative_root / "alternatives.jsonl",
                        alternative_root,
                        records=len(alternative_rows),
                    )
                ],
            },
        )

        prescription_root = output / "prescriptions"
        _write_jsonl(prescription_root / "goal_tag_links.jsonl", goal_rows)
        _write_jsonl(prescription_root / "prescription_profiles.jsonl", prescription_rows)
        _write_json(
            prescription_root / "prescription_manifest.json",
            {
                "schema_version": "1.0",
                "generator_version": GENERATOR_VERSION,
                "prescription_set_version": {
                    "version_code": PRESCRIPTION_SET_VERSION_CODE,
                    "status_code": "DRAFT",
                },
                "source": {"catalog_version_code": CATALOG_VERSION_CODE, "input_artifacts": []},
                "review": _draft_review(),
                "summary": {
                    "exercise_records": len(catalog_rows),
                    "goal_tag_records": len(goal_rows),
                    "prescription_records": len(prescription_rows),
                },
                "files": [
                    _file_entry(
                        prescription_root / "goal_tag_links.jsonl",
                        prescription_root,
                        records=len(goal_rows),
                    ),
                    _file_entry(
                        prescription_root / "prescription_profiles.jsonl",
                        prescription_root,
                        records=len(prescription_rows),
                    ),
                ],
            },
        )

        media_root = output / "media"
        _write_jsonl(media_root / "media_assets.jsonl", media_rows)
        _write_json(
            media_root / "media_manifest.json",
            {
                "schema_version": "1.0",
                "generator_version": GENERATOR_VERSION,
                "media_set_version": {
                    "version_code": MEDIA_SET_VERSION_CODE,
                    "status_code": "DRAFT",
                },
                "catalog_version_code": CATALOG_VERSION_CODE,
                "source": {
                    "catalog_version_code": CATALOG_VERSION_CODE,
                    "withheld_records": withheld_media,
                    "withheld_reason": "no media asset; the row would carry an empty s3_key",
                    "input_artifacts": [],
                },
                "review": _draft_review("DOMAIN_REVIEWER"),
                "summary": {"media_asset_records": len(media_rows)},
                "files": [
                    _file_entry(
                        media_root / "media_assets.jsonl", media_root, records=len(media_rows)
                    )
                ],
            },
        )

        files = [
            _file_entry(path, output, records=None)
            if path.suffix != ".jsonl"
            else _file_entry(
                path,
                output,
                records=len([line for line in path.read_bytes().splitlines() if line.strip()]),
            )
            for path in sorted(output.rglob("*"))
            if path.is_file() and path.name != "bundle_manifest.json"
        ]
        _write_json(
            output / "bundle_manifest.json",
            {
                "schema_version": "1.0",
                "bundle_version": "v2-0-2-backend-bundle-2026-08-30",
                "status_code": "DRAFT",
                "production_eligible": False,
                "catalog_version_code": CATALOG_VERSION_CODE,
                "derived_set_versions": {
                    "rule_set_version_code": RULE_SET_VERSION_CODE,
                    "alternative_set_version_code": ALTERNATIVE_SET_VERSION_CODE,
                    "prescription_set_version_code": PRESCRIPTION_SET_VERSION_CODE,
                    "media_set_version_code": MEDIA_SET_VERSION_CODE,
                },
                "importer_paths": {
                    "catalog": "catalog/seed_manifest.json",
                    "safety": "safety/rules_manifest.json",
                    "alternatives": "alternatives/alternatives_manifest.json",
                    "prescriptions": "prescriptions/prescription_manifest.json",
                    "media": "media/media_manifest.json",
                },
                "summary": {
                    "catalog_records": len(catalog_rows),
                    "safety_rule_records": len(safety_rows),
                    "alternative_records": len(alternative_rows),
                    "goal_tag_records": len(goal_rows),
                    "prescription_records": len(prescription_rows),
                    "media_asset_records": len(media_rows),
                },
                "projection": {
                    "status": "DIRECT" if not excluded else "PARTIAL",
                    "source_manifest_sha256": _sha256((final / "manifest.json").read_bytes()),
                    "withheld_media_records": withheld_media,
                    "excluded_exercise_count": len(excluded),
                    "excluded_exercise_stable_codes": sorted(excluded),
                    "excluded_reason": (
                        "required exercise content is missing; the record and every "
                        "row referencing it are withheld"
                    )
                    if excluded
                    else "",
                },
                "files": files,
            },
        )
        return output
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", type=Path, default=DEFAULT_FINAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--exclude-incomplete",
        action="store_true",
        help="package only the records the backend contract accepts, and record the rest",
    )
    args = parser.parse_args(argv)
    bundle = build(
        args.final,
        args.output,
        force=args.force,
        exclude_incomplete=args.exclude_incomplete,
    )
    manifest = _read_json(bundle / "bundle_manifest.json")
    print(
        json.dumps(
            {
                "status": "written",
                "path": str(bundle),
                "bundle_manifest_sha256": _sha256((bundle / "bundle_manifest.json").read_bytes()),
                **manifest["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
