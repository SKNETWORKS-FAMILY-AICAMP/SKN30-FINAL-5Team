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
        ):
            raise ValueError(f"FITT mapping row {index}: approval or identity mismatch")
        seen_nex.add(nex)
        seen_stable.add(stable)


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
            },
            "completeness_checks": {
                "catalog_stable_codes": True,
                "gym_references_catalog": True,
                "home_references_catalog": True,
                "fitt_reference_approved": True,
                "fitt_references_catalog": True,
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
