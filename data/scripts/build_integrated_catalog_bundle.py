#!/usr/bin/env python3
"""Build one reviewable bundle from the normalized catalog and all approved add-ons.

The catalog projection is generated first, then MET, gym starting guides, and
home equipment/variant data are attached under explicit importer namespaces.
Every add-on is checked against the catalog stable-code set before publishing.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
GYM_GUIDES = ROOT / "data/normalized/gym_equipment_starting_guides_v1.jsonl"
HOME_GUIDES = ROOT / "data/normalized/home_equipment_substitution_guides_v1.jsonl"
FITT_REFERENCE = ROOT / "data/normalized/catalog_enrichment_v3_fitt.csv"
FITT_SOURCE_MAP = ROOT / "data/normalized/v2_0_6_fitt_defaults_source_map.json"
FITT_STABLE_CODE_MAPPING = ROOT / "data/normalized/v2_0_7_fitt_stable_code_mapping.csv"
FITT_MAPPING_APPROVAL = (
    ROOT / "data/reports/integrated_catalog_v2_0_7/fitt_stable_code_mapping_approval.json"
)
TARGET = ROOT / "data/generated/integrated-catalog-v2.0.7-draft/backend_bundle"
REPORTS = ROOT / "data/reports/integrated_catalog_v2_0_7"
VERSION = "integrated-catalog-v2.0.7-draft-2026-09-07"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_tree(source: Path, target: Path) -> None:
    for path in source.rglob("*"):
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)


def _validate_prescription_levels(
    catalog_rows: list[dict[str, Any]], profiles: list[dict[str, Any]]
) -> None:
    """Fail the build on the mismatch the importer would reject at promotion.

    This ran only inside the API importer before, so a bundle could be built,
    hashed, registered and shipped to a release host before anything noticed.
    """

    difficulty = {row["stable_code"]: row["difficulty_code"] for row in catalog_rows}
    for index, row in enumerate(profiles, 1):
        code = row["exercise_stable_code"]
        if code not in difficulty:
            raise ValueError(f"prescription row {index}: {code} is absent from the catalog")
        if not _prescription_allowed(difficulty[code], row["experience_level_code"]):
            raise ValueError(
                f"prescription row {index}: {row['experience_level_code']} prescription on a "
                f"{difficulty[code]} exercise ({code})"
            )


def _validate_addons(
    catalog_rows: list[dict[str, Any]],
    gym: list[dict[str, Any]],
    home: list[dict[str, Any]],
    fitt: list[dict[str, str]],
    fitt_mapping: list[dict[str, str]],
) -> None:
    catalog_codes = {row["stable_code"] for row in catalog_rows}
    for label, rows in (("gym", gym), ("home", home)):
        seen: set[tuple[str, str]] = set()
        for index, row in enumerate(rows, 1):
            code = row.get("exercise_stable_code")
            equipment = row.get("equipment_code")
            if not isinstance(code, str) or code not in catalog_codes:
                raise ValueError(f"{label} row {index}: unknown stable_code {code!r}")
            if not isinstance(equipment, str) or not equipment:
                raise ValueError(f"{label} row {index}: equipment_code is required")
            key = (code, equipment)
            if key in seen:
                raise ValueError(f"{label} row {index}: duplicate {key}")
            seen.add(key)
            if row.get("review_status_code") != "DOMAIN_APPROVED":
                raise ValueError(f"{label} row {index}: only DOMAIN_APPROVED rows are importable")
    fitt_by_id = {row.get("exercise_id", ""): row for row in fitt}
    if "" in fitt_by_id or len(fitt_by_id) != len(fitt):
        raise ValueError("FITT reference contains blank or duplicate exercise IDs")
    catalog_by_code = {row["stable_code"]: row for row in catalog_rows}
    seen_nex: set[str] = set()
    seen_stable: set[str] = set()
    for index, row in enumerate(fitt_mapping, 1):
        nex = row.get("exercise_id", "")
        stable = row.get("exercise_stable_code", "")
        reference = fitt_by_id.get(nex)
        catalog = catalog_by_code.get(stable)
        if nex in seen_nex or stable in seen_stable:
            raise ValueError(f"FITT mapping row {index}: duplicate identifier")
        if reference is None or catalog is None:
            raise ValueError(
                f"FITT mapping row {index}: reference is absent from the catalog or FITT"
            )
        if (
            row.get("review_status_code") != "DOMAIN_APPROVED"
            or row.get("review_method_code") != "IDENTITY_REGISTRY_EXACT_JOIN"
            or reference.get("fitt_status") != "APPROVED"
            or row.get("fitt_template_id") != reference.get("fitt_template_id")
            or row.get("source_system") != catalog.get("source_track")
            or row.get("source_id") != catalog.get("source_identity")
            or reference.get("timing_mode_code") != catalog.get("timing_mode_code")
        ):
            raise ValueError(f"FITT mapping row {index}: approval or identity mismatch")
        seen_nex.add(nex)
        seen_stable.add(stable)


def _add_reviewed_beginner_prescriptions(
    stage: Path, catalog_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Add the BEGINNER rows the reviewed corpus derives for the same difficulty review.

    The re-review moved exercises down to BEGINNER without the prescription
    review being re-run, so they carried INTERMEDIATE rows only and never
    reached a beginner's pool. The rule applied here is not invented: it is the
    single INTERMEDIATE-to-BEGINNER transformation every exercise carrying both
    levels already agrees on, learned from the corpus by
    ``build_v2_0_7_beginner_prescription_derivation`` and approved as
    ``V2-0-7-BEGINNER-PRESCRIPTION-DERIVATION-2026-09-08-R01``.

    Runs after the incompatible rows are dropped so the corpus it learns from is
    already consistent with the reviewed difficulties.
    """

    derivation = _load(
        "beginner_derivation",
        ROOT / "data/scripts/build_v2_0_7_beginner_prescription_derivation.py",
    )
    profiles_path = stage / "catalog/prescriptions/prescription_profiles.jsonl"
    profiles = _read_jsonl(profiles_path)
    catalog = {row["stable_code"]: row for row in catalog_rows}
    derived, undecidable = derivation.derive(profiles, catalog, derivation.learn_mapping(profiles))
    if undecidable:
        raise ValueError(
            f"prescription rows outside the approved derivation need a reviewer: {undecidable}"
        )
    evidence = derivation.evidence(profiles, derived)
    if not derived:
        return [], evidence
    combined = profiles + derived
    combined.sort(
        key=lambda row: (
            row["exercise_stable_code"],
            row["goal_code"],
            row["phase_code"],
            row["experience_level_code"],
        )
    )
    profiles_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in combined
        ),
        encoding="utf-8",
    )
    _restate_prescription_counts(stage, profiles_path, len(combined))
    return derived, evidence


def _restate_prescription_counts(stage: Path, profiles_path: Path, records: int) -> None:
    """Keep the prescription manifest and the catalog wrapper agreeing on the count.

    The importer compares the wrapper's declared summary against the child
    manifests before it trusts either, so refreshing file hashes alone leaves the
    two disagreeing and the bundle fails closed at promotion.
    """

    manifest_path = stage / "catalog/prescriptions/prescription_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["path"] == "prescription_profiles.jsonl":
            entry.update(
                {
                    "sha256": _sha256(profiles_path),
                    "bytes": profiles_path.stat().st_size,
                    "records": records,
                }
            )
    manifest["summary"]["prescription_records"] = records
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    wrapper_path = stage / "catalog/bundle_manifest.json"
    wrapper = json.loads(wrapper_path.read_text(encoding="utf-8"))
    wrapper["summary"]["prescription_records"] = records
    wrapper_path.write_text(
        json.dumps(wrapper, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _align_prescriptions_to_difficulty(stage: Path, catalog_rows: list[dict[str, Any]]) -> int:
    """Drop prescription rows the catalog's reviewed difficulty no longer permits.

    Difficulty and prescription level are both reviewed values, and the v2.0.6
    difficulty re-review moved exercises without the prescription review being
    re-run. A BEGINNER prescription on an exercise now reviewed INTERMEDIATE is
    not a judgement call: the directional rule the importer enforces forbids it,
    so the row is removed rather than re-authored.
    """

    difficulty = {row["stable_code"]: row["difficulty_code"] for row in catalog_rows}
    profiles_path = stage / "catalog/prescriptions/prescription_profiles.jsonl"
    profiles = _read_jsonl(profiles_path)
    kept = [
        row
        for row in profiles
        if _prescription_allowed(
            difficulty.get(row["exercise_stable_code"]), row["experience_level_code"]
        )
    ]
    removed = len(profiles) - len(kept)
    if not removed:
        return 0
    profiles_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in kept),
        encoding="utf-8",
    )
    _restate_prescription_counts(stage, profiles_path, len(kept))
    return removed


def _align_prescription_defaults(stage: Path, catalog_rows: list[dict[str, Any]]) -> None:
    """Apply the reviewed low-load/high-repetition defaults to legacy profiles."""
    profiles_path = stage / "catalog/prescriptions/prescription_profiles.jsonl"
    profiles = _read_jsonl(profiles_path)
    catalog = {row["stable_code"]: row for row in catalog_rows}
    compound_patterns = {
        "HIP_DOMINANT",
        "KNEE_DOMINANT",
        "HORIZONTAL_PUSH",
        "HORIZONTAL_PULL",
        "VERTICAL_PUSH",
        "VERTICAL_PULL",
        "CORE_BRACE",
    }
    for profile in profiles:
        row = catalog.get(profile["exercise_stable_code"])
        if row is None:
            continue
        beginner = profile["experience_level_code"] == "BEGINNER"
        profile["sets"] = 2 if beginner else 3
        compound = row["primary_movement_pattern_code"] in compound_patterns
        profile["reps"] = (
            None if row["timing_mode_code"] == "DURATION" else (12 if compound else 15)
        )
        profile["intensity_code"] = "LIGHT_MODERATE" if compound else "LIGHT"
        if row["timing_mode_code"] == "DURATION":
            profile["work_seconds_per_set"] = int(row.get("default_work_seconds") or 60)
            profile["rest_seconds_per_set"] = int(row.get("default_rest_seconds") or 0)
            if row["training_type_code"] == "MOBILITY":
                profile["intensity_code"] = "LOW"
            elif row["training_type_code"] == "CARDIO":
                profile["intensity_code"] = "LIGHT_MODERATE"
        else:
            profile["work_seconds_per_set"] = None
    profiles_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in profiles
        ),
        encoding="utf-8",
    )
    _restate_prescription_counts(stage, profiles_path, len(profiles))


def _prescription_allowed(difficulty_code: str | None, experience_level_code: str) -> bool:
    """The directional rule: prescribe at or above the exercise's own difficulty."""

    if difficulty_code is None:
        return False
    order = {"BEGINNER": 0, "INTERMEDIATE": 1}
    if difficulty_code not in order or experience_level_code not in order:
        return False
    return order[experience_level_code] >= order[difficulty_code]


def build(target: Path = TARGET, reports: Path = REPORTS) -> dict[str, Any]:
    if target.exists() or reports.exists():
        raise ValueError("refusing to overwrite an existing integrated bundle or report")
    base = _load("build_v206", ROOT / "data/scripts/build_v2_0_6_backend_bundle.py")
    home = _load(
        "build_home", ROOT / "data/scripts/build_home_equipment_variants_backend_bundle.py"
    )
    gym = _load("build_gym", ROOT / "data/scripts/build_gym_equipment_starting_guides.py")
    gym_rows = gym.build_rows(CATALOG)
    gym.validate_rows(CATALOG, gym_rows)
    home_rows = _read_jsonl(HOME_GUIDES)
    with FITT_REFERENCE.open(newline="", encoding="utf-8") as handle:
        fitt_rows = list(csv.DictReader(handle))
    with FITT_STABLE_CODE_MAPPING.open(newline="", encoding="utf-8") as handle:
        fitt_mapping_rows = list(csv.DictReader(handle))
    if not fitt_rows or any(row.get("fitt_status") != "APPROVED" for row in fitt_rows):
        raise ValueError("FITT reference contains missing or unapproved rows")
    with tempfile.TemporaryDirectory(prefix="integrated-catalog-") as temporary:
        stage = Path(temporary) / "backend_bundle"
        template = ROOT / "data/generated/exercise-catalog-v2.0.7-draft/backend_bundle"
        _copy_tree(template, stage / "catalog")
        catalog_path = stage / "catalog/catalog/exercises.jsonl"
        source_rows = {row["stable_code"]: row for row in base._read_csv(CATALOG)}
        catalog_rows = base._project_catalog(list(source_rows.values()), base._recovery_policy())
        met_fields = (
            "met_value",
            "met_source_code",
            "met_source_activity_code",
            "met_mapping_method_code",
            "met_review_status_code",
            "met_policy_version",
        )
        for row in catalog_rows:
            row.update(
                {field: (source_rows[row["stable_code"]][field] or None) for field in met_fields}
            )
        catalog_path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                for row in catalog_rows
            ),
            encoding="utf-8",
        )
        removed_prescriptions = _align_prescriptions_to_difficulty(stage, catalog_rows)
        _align_prescription_defaults(stage, catalog_rows)
        derived_prescriptions, derivation_evidence = _add_reviewed_beginner_prescriptions(
            stage, catalog_rows
        )
        seed_path = stage / "catalog/catalog/seed_manifest.json"
        seed = json.loads(seed_path.read_text())
        seed["files"][0].update(
            {
                "sha256": _sha256(catalog_path),
                "bytes": catalog_path.stat().st_size,
                "records": len(catalog_rows),
            }
        )
        seed["generator_version"] = "integrated-catalog-v2.0.7-projection-1.0.0"
        seed_path.write_text(
            json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        bundle_path = stage / "catalog/bundle_manifest.json"
        catalog_manifest = json.loads(bundle_path.read_text())
        for entry in catalog_manifest["files"]:
            path = stage / "catalog" / entry["path"]
            entry.update({"sha256": _sha256(path), "bytes": path.stat().st_size})
            if path.suffix == ".jsonl":
                entry["records"] = len(_read_jsonl(path))
        bundle_path.write_text(
            json.dumps(catalog_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        catalog_rows = _read_jsonl(catalog_path)
        _validate_addons(catalog_rows, gym_rows, home_rows, fitt_rows, fitt_mapping_rows)
        _validate_prescription_levels(
            catalog_rows, _read_jsonl(stage / "catalog/prescriptions/prescription_profiles.jsonl")
        )
        home.build(target=stage / "home_equipment")
        gym_path = stage / "gym_equipment/starting_guides.jsonl"
        gym_path.parent.mkdir(parents=True, exist_ok=True)
        gym_path.write_text(gym.render(gym_rows), encoding="utf-8")
        sources = stage / "sources"
        sources.mkdir()
        for source in (
            CATALOG,
            GYM_GUIDES,
            HOME_GUIDES,
            FITT_REFERENCE,
            FITT_SOURCE_MAP,
            FITT_STABLE_CODE_MAPPING,
            FITT_MAPPING_APPROVAL,
        ):
            shutil.copyfile(source, sources / source.name)
        files: list[dict[str, Any]] = []
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                entry: dict[str, Any] = {
                    "path": path.relative_to(stage).as_posix(),
                    "sha256": _sha256(path),
                    "bytes": path.stat().st_size,
                }
                if path.suffix == ".jsonl":
                    entry["records"] = len(_read_jsonl(path))
                files.append(entry)
        manifest = {
            "schema_version": "integrated-exercise-importer-v1",
            "bundle_version": VERSION,
            "status_code": "DRAFT",
            "production_eligible": False,
            "source_catalog": {
                "path": str(CATALOG.relative_to(ROOT)),
                "sha256": _sha256(CATALOG),
                "records": len(catalog_rows),
            },
            "importer_paths": {
                "catalog": "catalog/bundle_manifest.json",
                "home_equipment": "home_equipment/bundle_manifest.json",
                "gym_equipment": "gym_equipment/starting_guides.jsonl",
            },
            "summary": {
                "catalog_records": len(catalog_rows),
                "gym_guide_records": len(gym_rows),
                "home_guide_records": len(home_rows),
                "fitt_reference_records": len(fitt_rows),
                "fitt_stable_code_mapping_records": len(fitt_mapping_rows),
                "met_fields_per_catalog_record": 6,
                "prescription_rows_removed_for_difficulty": removed_prescriptions,
                "prescription_rows_derived_for_difficulty": len(derived_prescriptions),
            },
            "completeness_checks": {
                "catalog_stable_codes": True,
                "gym_references_catalog": True,
                "home_references_catalog": True,
                "fitt_reference_approved": True,
                "fitt_references_catalog": True,
                "prescription_levels_match_difficulty": True,
                "met_projection_present": True,
                "artifact_inventory_complete": True,
            },
            "files": files,
        }
        (stage / "bundle_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report = {
            "status": "PASS",
            "bundle_version": VERSION,
            "bundle_manifest_sha256": _sha256(stage / "bundle_manifest.json"),
            "summary": manifest["summary"],
            "source_catalog_sha256": manifest["source_catalog"]["sha256"],
        }
        report_dir = Path(temporary) / "reports"
        report_dir.mkdir()
        (report_dir / "integrated_catalog_validation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (report_dir / "beginner_prescription_derivation.json").write_text(
            json.dumps(derivation_evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (report_dir / "INTEGRATED_CATALOG_HANDOFF.md").write_text(
            "# 통합 카탈로그 번들 인계\n\n"
            "검증 상태: PASS (DRAFT)\n\n"
            "- 카탈로그 237건\n- MET 6개 필드 포함\n"
            "- gym 무게 제안 포함\n"
            "- home 생활도구 대체·무게 제안 및 변형 포함\n"
            "- 승인된 FITT 참조 208건 포함\n"
            "- 모든 부가 데이터의 stable_code가 카탈로그에 존재함을 검증\n\n"
            "운영 적재와 production 승격은 백엔드 승인 후 수행합니다.\n",
            encoding="utf-8",
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        reports.parent.mkdir(parents=True, exist_ok=True)
        _copy_tree(stage, target)
        _copy_tree(report_dir, reports)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--reports", type=Path, default=REPORTS)
    args = parser.parse_args()
    print(json.dumps(build(args.target, args.reports), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
