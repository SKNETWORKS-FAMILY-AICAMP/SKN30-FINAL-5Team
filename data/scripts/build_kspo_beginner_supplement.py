"""Build a review-only KSPO beginner supplement batch from immutable inventory."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from align_source_candidates import (
    COMMON_COLUMNS,
    align_inventory_rows,
    load_csv,
    load_jsonl,
    validate_rows,
)

DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
DEFAULT_OUTPUT = DATA_ROOT / "validation" / "review_batches" / "kspo-beginner-supplement-v0.1.0"
INVENTORY = (
    DATA_ROOT
    / "validation"
    / "profiles"
    / "20260810T053458Z-training-video-profile-v0.2.0"
    / "candidate_inventory.jsonl"
)
REVIEW_RESULTS = DATA_ROOT / "validation" / "review_results" / "kspo_mapping_results.csv"
VERSION = "kspo-beginner-supplement-v0.1.0"

SHORTLIST = (
    {
        "source_identity": "00c41c823f6141adb2f3b7da95c1213fea98dac6cb3bfaf453f1a4989133d2d2",
        "supplement_category": "BEGINNER",
        "selection_reason": "저충격 홈 유산소 후보. 스텝 높이·속도·무릎 부담 검토 필요.",
    },
    {
        "source_identity": "dfd7eaa07d42e118610eb6756d8dcdc351f5b1f3c9a1262fa94aa18d92a87e09",
        "supplement_category": "BEGINNER",
        "selection_reason": "의자에 앉아 수행하는 고관절 굽힘 후보.",
    },
    {
        "source_identity": "46ea8fdbe34474fac354a051f63b114e0a6d20a21f71226ae0db5da216d14861",
        "supplement_category": "BEGINNER",
        "selection_reason": "의자 지지형 무릎 들기 후보.",
    },
    {
        "source_identity": "ddff78f01b0aa7c568bb66781954f5bbb7a7f882745b3490702d63e6467f924e",
        "supplement_category": "BEGINNER",
        "selection_reason": "의자 지지형 무릎 굽힘 후보.",
    },
    {
        "source_identity": "19af0f76cad5e01830e662585e3cea621cf8563f1955f83114bef440606379c4",
        "supplement_category": "BEGINNER",
        "selection_reason": "의자 지지형 한발 균형 후보. 낙상 위험 검토 필요.",
    },
    {
        "source_identity": "ab41f78cd9e548e1217b4460122ca0a1e9824cd570da589f1b37ffe86d6db937",
        "supplement_category": "BEGINNER",
        "selection_reason": "앉은 자세의 밴드 상체 당기기 후보. 원천 제목과 도구·자세 대조 필요.",
    },
    {
        "source_identity": "66e29f752b845bd1bcfa4cb737be1ede40daa81d869ea4b531c882b02ffb3c28",
        "supplement_category": "BEGINNER",
        "selection_reason": "의자에서 짐볼을 다리로 조이는 허벅지 안쪽 후보.",
    },
    {
        "source_identity": "ce0ab5a88d5e6c4243b2a910aa53ecff3aa783c716fa193711a1a6e44542b3a0",
        "supplement_category": "BEGINNER",
        "selection_reason": "네발기기 팔·다리 들기 버드독 계열 후보.",
    },
    {
        "source_identity": "9cbed9e85b778b40b4786394c774c081fcfb39e3cf13df612476c9d0bf56c9e7",
        "supplement_category": "BEGINNER",
        "selection_reason": "누운 자세의 복부 브레이싱 후보. I·II 중 대표 선정 필요.",
    },
    {
        "source_identity": "72cc612abf8747105b33f64e0661b713012fb3f2ae378cd5c5142215eedc899b",
        "supplement_category": "BEGINNER",
        "selection_reason": "누운 자세의 밴드 다리 밀기 후보.",
    },
)

EXTRA_COLUMNS = [
    "supplement_category",
    "selection_reason",
    "source_video_title",
    "source_description",
    "source_review_decision",
    "source_candidate_status",
]
OUTPUT_COLUMNS = [*COMMON_COLUMNS, *EXTRA_COLUMNS]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_records(inventory: Path, reviews: Path) -> dict[str, dict[str, Any]]:
    rows = load_jsonl(inventory)
    review_rows = load_csv(reviews)
    aligned = align_inventory_rows([], rows, [], review_rows)
    return {row["source_identity"]: row for row in aligned}


def raw_source_records(inventory: Path) -> dict[str, dict[str, Any]]:
    return {
        str(row["source_candidate_id"]): row
        for row in load_jsonl(inventory)
        if row.get("source_candidate_id")
    }


def existing_kspo_ids() -> set[str]:
    identities: set[str] = set()
    for path in (DATA_ROOT / "generated").glob("exercise-catalog-seed-kspo-*/exercises.jsonl"):
        if "tranche1" in path.as_posix():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                identities.add(str(json.loads(line)["source_identity"]))
    return identities


def build_rows(inventory: Path, reviews: Path) -> list[dict[str, str]]:
    records = source_records(inventory, reviews)
    raw_records = raw_source_records(inventory)
    existing = existing_kspo_ids()
    rows: list[dict[str, str]] = []
    for rank, spec in enumerate(SHORTLIST, start=1):
        identity = str(spec["source_identity"])
        if identity not in records:
            raise ValueError(f"shortlist source identity is missing: {identity}")
        if identity in existing:
            raise ValueError(f"shortlist overlaps the existing KSPO catalog: {identity}")
        if identity not in raw_records:
            raise ValueError(f"shortlist raw source identity is missing: {identity}")
        row = dict(records[identity])
        raw = raw_records[identity]
        original_decision = row["review_decision"]
        row.update(
            {
                "difficulty_code_candidate": "BEGINNER",
                "beginner_suitability_candidate": "CONDITIONAL",
                "selection_rank": str(rank),
                "selection_recommendation": "RECOMMENDED",
                "screening_decision": "HOLD",
                "screening_reason_code": "BEGINNER_SUPPLEMENT_SHORTLIST",
                "screening_reason": (
                    "사용자 요청으로 초보자 카테고리 후보에 선정; 사람 검토 전 보류."
                ),
                "review_decision": "PENDING",
                "review_reason_code": "BEGINNER_CATEGORY_REVIEW_REQUIRED",
                "review_note": (
                    "BEGINNER_CATEGORY_REQUESTED; source evidence and safety review pending."
                ),
                "review_status": "DRAFT",
                "production_eligible": "false",
                "supplement_category": str(spec["supplement_category"]),
                "selection_reason": str(spec["selection_reason"]),
                "source_video_title": " | ".join(
                    str(value) for value in raw.get("source_video_titles", [])
                ),
                "source_description": " | ".join(
                    str(value) for value in raw.get("source_descriptions", [])
                ),
                "source_review_decision": original_decision,
                "source_candidate_status": "NEW_CANDIDATE",
            }
        )
        rows.append({column: row.get(column, "") for column in OUTPUT_COLUMNS})
    return rows


def write_output(rows: list[dict[str, str]], output: Path, inventory: Path, reviews: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    common_validation = validate_rows([{key: row[key] for key in COMMON_COLUMNS} for row in rows])
    if common_validation["status"] != "PASS":
        raise ValueError(json.dumps(common_validation, ensure_ascii=False))
    output.mkdir(parents=True)
    try:
        csv_path = output / "kspo_beginner_supplement.csv"
        jsonl_path = output / "kspo_beginner_supplement.jsonl"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        manifest = {
            "schema_version": "1.0",
            "version_code": VERSION,
            "status_code": "DRAFT_REVIEW_QUEUE",
            "production_eligible": False,
            "selection_policy": {
                "record_count": 10,
                "difficulty_code_candidate": "BEGINNER",
                "beginner_suitability_candidate": "CONDITIONAL",
                "note": "초보자 카테고리 후보 지정이며 최종 안전·실행·도메인 승인이 아님.",
            },
            "inputs": [
                {"path": str(inventory.relative_to(REPO_ROOT)), "sha256": sha256_file(inventory)},
                {"path": str(reviews.relative_to(REPO_ROOT)), "sha256": sha256_file(reviews)},
            ],
            "summary": {
                "records": len(rows),
                "new_candidates": len(rows),
                "existing_catalog_overlap": 0,
            },
            "files": [
                {
                    "path": csv_path.name,
                    "sha256": sha256_file(csv_path),
                    "bytes": csv_path.stat().st_size,
                    "records": len(rows),
                },
                {
                    "path": jsonl_path.name,
                    "sha256": sha256_file(jsonl_path),
                    "bytes": jsonl_path.stat().st_size,
                    "records": len(rows),
                },
            ],
        }
        (output / "review_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception:
        for path in output.iterdir():
            path.unlink()
        output.rmdir()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--reviews", type=Path, default=REVIEW_RESULTS)
    args = parser.parse_args()
    rows = build_rows(args.inventory, args.reviews)
    write_output(rows, args.output.resolve(), args.inventory, args.reviews)
    print(json.dumps({"version": VERSION, "records": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
