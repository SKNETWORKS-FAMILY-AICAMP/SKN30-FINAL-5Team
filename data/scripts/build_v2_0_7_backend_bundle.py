"""Build and verify a MET-only v2.0.7 draft using the unchanged v2.0.6 generator.

No database writes or production promotion. Output is staged and published only
when source approvals, frozen baseline semantics, counts and hashes all match.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VERSION = "exercise-catalog-v2.0.7-draft"
MET_FIELDS = (
    "met_value",
    "met_source_code",
    "met_source_activity_code",
    "met_mapping_method_code",
    "met_review_status_code",
    "met_policy_version",
)
APPROVAL = Path("data/reports/v2_0_6_met/met_review_approval_manifest.json")
BASELINE = Path("data/generated/exercise-catalog-v2.0.6-final/backend_bundle")
TARGET = Path(f"data/generated/{VERSION}/backend_bundle")
REPORTS = Path("data/reports/v2_0_7_catalog")
COUNTS = {
    "catalog/exercises.jsonl": 237,
    "safety/safety_rules.jsonl": 2131,
    "prescriptions/goal_tag_links.jsonl": 711,
    "prescriptions/prescription_profiles.jsonl": 1449,
    "media/media_assets.jsonl": 237,
    "alternatives/alternatives.jsonl": 1,
}
# Only these provenance fields may change in derived records.
RETARGET_FIELDS = {
    "catalog_version_code",
    "source_catalog_version_code",
    "alternative_catalog_version_code",
    "source_manifest_hash",
}


def load_builder(root: Path) -> Any:
    spec = importlib.util.spec_from_file_location(
        "v206_met_base", root / "data/scripts/build_v2_0_6_backend_bundle.py"
    )
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    return builder


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def project_met(
    rows: list[dict[str, str]], approval: dict[str, Any], source_hash: str
) -> dict[str, dict[str, Any]]:
    if approval.get("source_catalog_sha256") != source_hash:
        raise ValueError("MET approval source catalog hash mismatch")
    if approval.get("review_status_code") != "DOMAIN_APPROVED":
        raise ValueError("MET manifest is not approved")
    result = {}
    for row in rows:
        code = row["stable_code"]
        if not code or code in result or any(key not in row for key in MET_FIELDS):
            raise ValueError(f"{code}: missing MET columns or duplicate stable_code")
        met: dict[str, Any] = {key: row[key] or None for key in MET_FIELDS}
        status = met["met_review_status_code"]
        if status not in {"DOMAIN_APPROVED", "REVIEW_REQUIRED"}:
            raise ValueError(f"{code}: invalid MET approval status {status}")
        if met["met_value"] is not None:
            try:
                value = float(met["met_value"])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{code}: invalid MET numeric value") from exc
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{code}: MET must be positive and finite")
            if not all(met[key] for key in MET_FIELDS[1:]):
                raise ValueError(f"{code}: MET provenance is incomplete")
            if status != "DOMAIN_APPROVED":
                raise ValueError(f"{code}: unapproved MET must be NULL")
            met["met_value"] = value
        elif status != "REVIEW_REQUIRED":
            raise ValueError(f"{code}: NULL MET must remain REVIEW_REQUIRED")
        result[code] = met
    approved = sum(m["met_review_status_code"] == "DOMAIN_APPROVED" for m in result.values())
    if approved != approval.get("approved_record_count"):
        raise ValueError("MET approved record count mismatch")
    return result


def snapshot(root: Path, builder: Any) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): builder._sha256(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def verify_manifests(root: Path, builder: Any) -> None:
    bundle = json.loads((root / "bundle_manifest.json").read_text())
    manifests = [root / p for p in bundle["importer_paths"].values()]
    manifests.append(root / "bundle_manifest.json")
    for path in manifests:
        manifest = json.loads(path.read_text())
        for entry in manifest["files"]:
            artifact = path.parent / entry["path"]
            if (
                builder._sha256(artifact) != entry["sha256"]
                or artifact.stat().st_size != entry["bytes"]
            ):
                raise ValueError(f"manifest hash/size mismatch: {artifact}")
            if artifact.suffix == ".jsonl" and len(read_jsonl(artifact)) != entry["records"]:
                raise ValueError(f"manifest count mismatch: {artifact}")
    listed = {entry["path"] for entry in bundle["files"]}
    actual = set(snapshot(root, builder)) - {"bundle_manifest.json"}
    if listed != actual or len(listed) != len(bundle["files"]):
        raise ValueError("root manifest file inventory mismatch")
    summaries = {
        "catalog": {"exercise_records": 237},
        "safety": {
            "rule_records": 2131,
            "exercise_records": 237,
            "pattern_scope_rules": 0,
            "exercise_scope_rules": 2131,
        },
        "prescriptions": {
            "exercise_records": 237,
            "goal_tag_records": 711,
            "prescription_records": 1449,
        },
        "media": {"media_asset_records": 237},
        "alternatives": {"alternative_records": 1},
    }
    for name, expected in summaries.items():
        child = json.loads((root / bundle["importer_paths"][name]).read_text())
        if child["summary"] != expected:
            raise ValueError(f"child summary mismatch: {name}")
    if bundle["summary"] != {
        "catalog_records": 237,
        "safety_rule_records": 2131,
        "goal_tag_records": 711,
        "prescription_records": 1449,
        "media_asset_records": 237,
        "alternative_records": 1,
    }:
        raise ValueError("root summary mismatch")


def verify_semantics(stage: Path, baseline: Path, met: dict[str, dict[str, Any]]) -> None:
    bundle = json.loads((stage / "bundle_manifest.json").read_text())
    source_hash = bundle["derived_from"]["catalog_source_sha256"]
    for relative, count in COUNTS.items():
        current, previous = read_jsonl(stage / relative), read_jsonl(baseline / relative)
        if len(current) != count or len(previous) != count:
            raise ValueError(f"required record count mismatch: {relative}")
        cleaned = []
        for record in current:
            row = dict(record)
            if relative == "catalog/exercises.jsonl":
                if {k: row.pop(k) for k in MET_FIELDS} != met[row["stable_code"]]:
                    raise ValueError(f"MET projection mismatch: {row['stable_code']}")
            elif any(k in row for k in MET_FIELDS):
                raise ValueError(f"MET outside catalog: {relative}")
            for key in RETARGET_FIELDS & row.keys():
                expected = source_hash if key == "source_manifest_hash" else VERSION
                if row[key] != expected:
                    raise ValueError(f"incorrect version/hash reference: {relative}: {key}")
            cleaned.append({k: v for k, v in row.items() if k not in RETARGET_FIELDS})
        old = [{k: v for k, v in row.items() if k not in RETARGET_FIELDS} for row in previous]
        if cleaned != old:
            codes = [
                row.get(
                    "stable_code",
                    row.get("exercise_stable_code", row.get("source_exercise_stable_code")),
                )
                for row, prior in zip(cleaned, old, strict=True)
                if row != prior
            ]
            raise ValueError(f"non-MET semantic changes: {relative}: {codes}")


def build(
    *,
    root: Path = ROOT,
    target: Path | None = None,
    reports: Path | None = None,
    media_directory: Path | None = None,
) -> dict[str, Any]:
    builder = load_builder(root)
    target = target or root / TARGET
    reports = reports or root / REPORTS
    baseline = root / BASELINE
    if target.exists() or reports.exists():
        raise ValueError("refusing to overwrite existing bundle or reports")
    if any(path.resolve().is_relative_to(baseline.parent.resolve()) for path in (target, reports)):
        raise ValueError("v2.0.6-final is immutable")
    frozen = snapshot(baseline.parent, builder)
    source_hash = builder._sha256(builder.NORMALIZED_CATALOG)
    approval = json.loads((root / APPROVAL).read_text())
    met = project_met(builder._read_csv(builder.NORMALIZED_CATALOG), approval, source_hash)
    builder.CATALOG_VERSION = VERSION
    builder.BUNDLE_VERSION = "v2-0-7-met-backend-bundle-draft-2026-09-06"
    if media_directory is not None:
        builder.MEDIA_DIRECTORY = media_directory
    with tempfile.TemporaryDirectory(prefix="met-v207-") as temporary:
        stage = Path(temporary) / "backend_bundle"
        builder.build(target=stage)
        catalog_path = stage / "catalog/exercises.jsonl"
        catalog = read_jsonl(catalog_path)
        for row in catalog:
            row.update(met[row["stable_code"]])
        builder._write_jsonl(catalog_path, catalog)
        approval_copy = stage / "catalog/input/met_review_approval_manifest.json"
        shutil.copyfile(root / APPROVAL, approval_copy)
        seed_path = stage / "catalog/seed_manifest.json"
        seed = json.loads(seed_path.read_text())
        seed["files"] = [builder._manifest_file(catalog_path, seed_path.parent, len(catalog))]
        seed["source"]["input_artifacts"].append(
            {
                "role": "met_review_approval_manifest",
                "path": "input/" + approval_copy.name,
                "sha256": builder._sha256(approval_copy),
                "bytes": approval_copy.stat().st_size,
            }
        )
        seed["generator_version"] = "v2-0-7-met-projection-1.0.0"
        builder._write_json(seed_path, seed)
        bundle_path = stage / "bundle_manifest.json"
        bundle = json.loads(bundle_path.read_text())
        bundle["derived_from"]["generator_version"] = seed["generator_version"]
        bundle["derived_from"]["baseline_bundle_manifest_sha256"] = builder._sha256(
            baseline / "bundle_manifest.json"
        )
        bundle["derived_from"]["change_summary"] = (
            "MET six-field projection only; exercise, safety, prescription, media and "
            "alternative semantics unchanged. Catalog version and provenance hashes retargeted."
        )
        bundle["files"] = []
        for path in sorted(stage.rglob("*")):
            if not path.is_file() or path == bundle_path:
                continue
            entry = {
                "path": path.relative_to(stage).as_posix(),
                "sha256": builder._sha256(path),
                "bytes": path.stat().st_size,
            }
            if path.suffix == ".jsonl":
                entry["records"] = len(read_jsonl(path))
            bundle["files"].append(entry)
        builder._write_json(bundle_path, bundle)
        verify_semantics(stage, baseline, met)
        verify_manifests(stage, builder)
        if frozen != snapshot(baseline.parent, builder):
            raise ValueError("v2.0.6-final changed")
        if source_hash != builder._sha256(builder.NORMALIZED_CATALOG):
            raise ValueError("source changed during generation")
        if (root / APPROVAL).read_bytes() != approval_copy.read_bytes():
            raise ValueError("approval changed during generation")
        report = {
            "status": "PASS",
            "catalog_version_code": VERSION,
            "source_path": str(builder.NORMALIZED_CATALOG.relative_to(root)),
            "source_sha256": source_hash,
            "bundle_root_sha256_definition": "SHA-256 of bundle_manifest.json bytes",
            "bundle_root_sha256": builder._sha256(bundle_path),
            "met_non_null_count": sum(m["met_value"] is not None for m in met.values()),
            "met_null_count": sum(m["met_value"] is None for m in met.values()),
            "domain_approved_count": approval["approved_record_count"],
            "met_approval_manifest_sha256": builder._sha256(approval_copy),
            "required_counts": COUNTS,
            "checks": {
                "met_projection": True,
                "approval_hash_and_count": True,
                "manifest_hash_size_count": True,
                "non_met_semantics_unchanged": True,
                "v206_final_unchanged": True,
            },
            "v206_final_file_hashes": frozen,
            "artifacts": bundle["files"],
            "backend_import_executed": False,
        }
        report_stage = Path(temporary) / "reports"
        builder._write_json(report_stage / "met_bundle_validation_report.json", report)
        lines = [
            "# MET v2.0.7 Backend handoff",
            "",
            "Status: verified DRAFT; not promoted.",
            "",
            f"- Source: `{report['source_path']}`",
            f"- Source SHA-256: `{source_hash}`",
            f"- Bundle root: `{TARGET}`",
            f"- Bundle root SHA-256 (bundle_manifest.json): `{report['bundle_root_sha256']}`",
            f"- MET approval manifest SHA-256: `{report['met_approval_manifest_sha256']}`",
            f"- MET non-null / NULL: {report['met_non_null_count']} / {report['met_null_count']}",
            f"- DOMAIN_APPROVED: {report['domain_approved_count']}",
            "",
            "v2.0.6 대비 운동 데이터 변경은 MET 6개 projection뿐입니다. 버전 참조와 출처 해시는 "
            "새 bundle에 맞게 생성했으며 safety/처방/media/대체운동 의미는 동일합니다.",
            "기존 규칙·처방·media set version은 의미가 같으므로 유지합니다.",
            "",
            "승인: 2026-09-06 사용자 승인. Adult Compendium 2024의 기존 DIRECT / "
            "SIMILAR_ACTIVITY 값과 PDF/HOME 출처 코드를 그대로 유지했습니다.",
            "",
            "| Artifact | Records | Bytes | SHA-256 |",
            "|---|---:|---:|---|",
        ]
        for entry in bundle["files"]:
            lines.append(
                f"| {entry['path']} | {entry.get('records', '—')} | "
                f"{entry['bytes']} | {entry['sha256']} |"
            )
        lines += [
            "",
            "## Backend 후속 작업",
            "",
            "- [ ] exercises 테이블 MET 6개 nullable 컬럼 migration",
            "- [ ] ExerciseRecord/importer의 6개 필드 검증·저장 지원",
            "- [ ] 새 bundle hash approval/promotion 등록 및 최종 승인 후 별도 final 생성",
            "- [ ] import·activate 및 237개 MET 저장 확인",
            "- [ ] kcal 계산 연결",
            "",
            "## 검증·재현",
            "",
            "`python data/scripts/build_v2_0_7_backend_bundle.py` (출력 경로가 없어야 함)",
            "`python -m pytest data/scripts/tests/test_build_v2_0_7_backend_bundle.py "
            "data/scripts/tests/test_build_v2_0_6_backend_bundle.py`",
            "",
            "수동 검수: validation report의 root hash를 bundle_manifest.json의 SHA-256과 "
            "대조하고, child artifact의 hash/bytes/records를 확인합니다.",
            "",
            "## 제한",
            "",
            "met_reviewed_at/met_reviewer_code는 이번 bundle의 운동 레코드에 "
            "포함하지 않았습니다. 승인 manifest의 기존 감사 메타데이터는 증적으로 보존합니다.",
            "backend kcal 계산/DB 적재, API·schema 변경은 수행하지 않았습니다. "
            "현재 ExerciseRecord는 MET를 지원하지 않으므로 그대로 적재하면 안 됩니다.",
            "개인정보·건강 기록을 추가하거나 외부로 전송하지 않았습니다.",
            "",
        ]
        (report_stage / "MET_BUNDLE_HANDOFF.md").write_text("\n".join(lines))
        # Check report/bundle binding before publishing the verified draft.
        saved = json.loads((report_stage / "met_bundle_validation_report.json").read_text())
        if (
            saved["bundle_root_sha256"] != builder._sha256(bundle_path)
            or saved["artifacts"] != bundle["files"]
            or saved["met_approval_manifest_sha256"] != builder._sha256(approval_copy)
        ):
            raise ValueError("validation report root hash mismatch")
        target.parent.mkdir(parents=True, exist_ok=True)
        reports.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, target)
        shutil.copytree(report_stage, reports)
        verify_manifests(target, builder)
        if snapshot(target, builder) != snapshot(stage, builder):
            raise ValueError("published bundle differs from verified stage")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--reports", type=Path)
    parser.add_argument("--media-directory", type=Path)
    args = parser.parse_args()
    result = build(target=args.target, reports=args.reports, media_directory=args.media_directory)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "status",
                    "bundle_root_sha256",
                    "met_non_null_count",
                    "met_null_count",
                    "domain_approved_count",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
