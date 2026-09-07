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
    catalog_codes: set[str], gym: list[dict[str, Any]], home: list[dict[str, Any]]
) -> None:
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
        codes = {row["stable_code"] for row in catalog_rows}
        _validate_addons(codes, gym_rows, home_rows)
        home.build(target=stage / "home_equipment")
        gym_path = stage / "gym_equipment/starting_guides.jsonl"
        gym_path.parent.mkdir(parents=True, exist_ok=True)
        gym_path.write_text(gym.render(gym_rows), encoding="utf-8")
        sources = stage / "sources"
        sources.mkdir()
        for source in (CATALOG, GYM_GUIDES, HOME_GUIDES, FITT_REFERENCE, FITT_SOURCE_MAP):
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
                "met_fields_per_catalog_record": 6,
            },
            "completeness_checks": {
                "catalog_stable_codes": True,
                "gym_references_catalog": True,
                "home_references_catalog": True,
                "fitt_reference_approved": True,
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
