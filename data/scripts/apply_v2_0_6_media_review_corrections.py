#!/usr/bin/env python3
# ruff: noqa: E501
"""Apply user-approved GIF-review corrections to the v2.0.6 canonical catalog."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_REPORT = PROJECT_ROOT / "data/reports/v2_0_6_catalog_merge/media_review_corrections_apply_report.json"


class MediaReviewCorrectionError(ValueError):
    """Raised when an approved media-review batch cannot be safely applied."""


CORRECTIONS: dict[str, dict[str, str]] = {
    "0130": {
        "instruction_summary_ko": "1. 벤치에 양손과 한쪽 무릎을 올려 몸통을 안정적으로 지지합니다\n2. 반대쪽 다리를 무릎을 편 채 뒤로 들어 올려 엉덩이 높이까지 뻗습니다\n3. 골반을 유지하며 다리를 천천히 내린 뒤 반대쪽도 같은 순서로 수행합니다",
        "instruction_content_version": "gif-reviewed-natural-language-ko-v2.0.6",
    },
    "0137": {
        "name_ko": "푸시업",
        "primary_movement_pattern_code": "HORIZONTAL_PUSH",
        "instruction_summary_ko": "1. 바닥에 엎드려 양손을 어깨 아래에 두고 다리를 곧게 뻗습니다\n2. 손바닥으로 바닥을 밀어 팔을 펴며 상체를 들어 올립니다\n3. 몸통을 길게 유지하며 팔꿈치를 굽혀 천천히 시작 자세로 돌아옵니다",
        "form_cues_ko": "허리가 과하게 꺾이지 않도록 배 주변에 가볍게 힘을 줍니다|수행이 어렵다면 무릎을 바닥에 대고 범위를 줄여 진행합니다",
        "instruction_content_version": "gif-reviewed-natural-language-ko-v2.0.6",
    },
    "0613": {
        "name_ko": "옆으로 누워 대퇴사두근 스트레칭",
        "primary_body_area_codes": "quadriceps",
        "instruction_summary_ko": "1. 옆으로 누워 아래쪽 팔로 머리를 받치고 두 다리를 편안히 뻗습니다\n2. 위쪽 무릎을 굽혀 발목이나 발등을 잡고 발뒤꿈치를 엉덩이 쪽으로 부드럽게 당깁니다\n3. 허벅지 앞쪽이 당기는 범위에서 유지한 뒤 반대쪽도 수행합니다",
    },
    "1512": {
        "name_ko": "네발 대퇴사두근 스트레칭",
        "primary_body_area_codes": "quadriceps",
        "secondary_body_area_codes": "",
        "instruction_summary_ko": "1. 손은 어깨 아래, 무릎은 엉덩이 아래에 두고 네발기기 자세를 만듭니다\n2. 한쪽 무릎을 굽혀 발을 엉덩이 쪽으로 가져가며 허벅지 앞쪽이 당기는 범위로 골반을 천천히 낮춥니다\n3. 편안한 범위에서 유지한 뒤 반대쪽도 수행합니다",
    },
    "1564": {
        "name_ko": "고관절 굴곡근·대퇴사두근 스트레칭",
        "primary_body_area_codes": "quadriceps",
        "secondary_body_area_codes": "hip flexors",
        "instruction_summary_ko": "1. 한쪽 무릎을 굽혀 발목이나 발에 건 스트랩을 잡고 편안히 눕습니다\n2. 발을 엉덩이 쪽으로 부드럽게 당겨 허벅지 앞쪽과 고관절 앞쪽의 당김을 느낍니다\n3. 편안한 범위에서 유지한 뒤 반대쪽도 수행합니다",
    },
    "2204": {"primary_body_area_codes": "core"},
    "2206": {"primary_body_area_codes": "core"},
}


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [{key: value or "" for key, value in row.items()} for row in reader]
    except OSError as exc:
        raise MediaReviewCorrectionError(f"cannot read CSV: {path}") from exc
    if not fields or any(key is None for key in fields) or any(None in row for row in rows):
        raise MediaReviewCorrectionError(f"invalid CSV schema: {path}")
    return rows, fields


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_corrections(catalog_path: Path = DEFAULT_CATALOG, report_path: Path = DEFAULT_REPORT) -> dict:
    rows, fields = read_csv(catalog_path)
    required = {"source_identity", *{field for values in CORRECTIONS.values() for field in values}}
    missing_fields = sorted(required - set(fields))
    if missing_fields:
        raise MediaReviewCorrectionError(f"canonical CSV is missing fields: {', '.join(missing_fields)}")
    indexed = {row["source_identity"].strip(): row for row in rows}
    if "" in indexed or len(indexed) != len(rows):
        raise MediaReviewCorrectionError("source_identity is blank or duplicated")
    missing_ids = sorted(set(CORRECTIONS) - set(indexed))
    if missing_ids:
        raise MediaReviewCorrectionError(f"approved source identities absent: {', '.join(missing_ids)}")

    before = sha256(catalog_path)
    changes: list[dict[str, str]] = []
    for identity, values in CORRECTIONS.items():
        row = indexed[identity]
        for field, value in values.items():
            if row[field] != value:
                changes.append({"source_identity": identity, "stable_code": row.get("stable_code", ""), "field": field, "previous_value": row[field], "new_value": value})
                row[field] = value
    with catalog_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)

    report = {
        "status": "USER_APPROVED",
        "production_eligible": False,
        "policy": {"join_key": "source_identity_exact_match", "changed_source_identities": list(CORRECTIONS), "unchanged_domains": ["MET fields", "safety", "prescriptions", "alternatives", "media links"]},
        "inputs": {"catalog_path": str(catalog_path), "catalog_sha256_before": before, "catalog_records": len(rows)},
        "outputs": {"catalog_path": str(catalog_path), "catalog_sha256_after": sha256(catalog_path), "changed_fields": len(changes), "changed_records": len({change["source_identity"] for change in changes})},
        "changes": changes,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    print(json.dumps(apply_corrections(args.catalog, args.report)["outputs"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
