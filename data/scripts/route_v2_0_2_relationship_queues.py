"""Route the v2.0.2 relationship review batch into policy-based queues.

The source batch remains complete.  Routing metadata is appended to every
record, and each queue is materialized as CSV and JSONL for focused review.
Candidate relation fields are preserved as provenance; ``decision_*`` fields
record the deterministic routing decision separately.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH_DIR = (
    ROOT / "validation/review_batches/exercise-catalog-v2.0.2-relationship-review-v0.1.0"
)
DEFAULT_JSONL = DEFAULT_BATCH_DIR / "review_batch.jsonl"
DEFAULT_CSV = DEFAULT_BATCH_DIR / "review_batch.csv"

HOME_SUPPORTED_EQUIPMENT = frozenset(
    {
        "BODYWEIGHT",
        "DUMBBELL",
        "HOUSEHOLD_WEIGHT",
        "MAT",
        "FOAM_ROLLER",
        "JUMP_ROPE",
        "RESISTANCE_BAND",
    }
)

HUMAN_REVIEW_REASON_FIELD = "human_review_reason_ko"

ROUTING_FIELDS = [
    "queue_code",
    "decision_code",
    "decision_source",
    "decision_reason_code",
    "decision_note",
    "human_review_required",
    HUMAN_REVIEW_REASON_FIELD,
]

QUEUE_FILES = {
    "VARIANT_CANDIDATE_QUEUE": "variant_candidate_queue",
    "SEPARATE_EXERCISE_QUEUE": "separate_exercise_queue",
    "HOME_POLICY_EXCLUDED_QUEUE": "home_policy_excluded_queue",
    "HUMAN_REVIEW_QUEUE": "human_review_queue",
}

DIMENSION_REASON_KO = {
    "SOURCE_IDENTITY": "원천 운동 식별자가 다름",
    "STABLE_CODE": "stable code가 다름",
    "EQUIPMENT": "사용 장비가 다름",
    "POSTURE": "운동 자세가 다름",
    "GRIP": "그립이 다름",
    "STANCE": "스탠스 또는 발 위치가 다름",
    "ROM": "가동범위가 다름",
    "ACTUAL_METHOD": "실제 수행 방법 또는 명칭 정보가 다름",
}


def parse_list(value: str) -> set[str]:
    if not value.strip():
        return set()
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError(f"expected JSON list, got {value!r}")
    return {str(item).strip() for item in parsed if str(item).strip()}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row is not an object: {path}:{line_number}")
            rows.append(value)
    return rows


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV header is missing: {path}")
        return list(reader), list(reader.fieldnames)


def has_home_policy_conflict(row: dict[str, Any]) -> bool:
    """Return the eight known HOME-only STEP_BOX relation conflicts.

    The policy is applied to unresolved relationship candidates only.  A
    candidate must advertise HOME on both sides, compare equipment, and use
    STEP_BOX, which is outside the explicitly supported HOME equipment set.
    """

    if row.get("candidate_relation_code") != "REVIEW_REQUIRED":
        return False
    if "EQUIPMENT" not in str(row.get("comparison_dimensions", "")).split("|"):
        return False
    left_locations = parse_list(str(row.get("left_location_codes", "[]")))
    right_locations = parse_list(str(row.get("right_location_codes", "[]")))
    if "HOME" not in left_locations or "HOME" not in right_locations:
        return False
    equipment = parse_list(str(row.get("left_equipment_codes", "[]")))
    equipment |= parse_list(str(row.get("right_equipment_codes", "[]")))
    return "STEP_BOX" in equipment and bool(equipment - HOME_SUPPORTED_EQUIPMENT)


def build_human_review_reason(row: dict[str, Any]) -> str:
    reasons: list[str] = []
    dimensions = {
        dimension
        for dimension in str(row.get("comparison_dimensions", "")).split("|")
        if dimension and dimension != "NONE"
    }
    if row.get("movement_pattern_match") == "false":
        reasons.append("운동 패턴 코드가 달라 동일 운동인지 확인이 필요함")

    primary_match = row.get("primary_body_area_overlap") == "1.000"
    secondary_match = row.get("secondary_body_area_overlap") == "1.000"
    if not primary_match:
        reasons.append("primary 타겟 부위가 다르거나 일부만 겹침")
    if not secondary_match:
        reasons.append("secondary 타겟 부위가 다르거나 일부만 겹침")

    for dimension in sorted(dimensions):
        reason = DIMENSION_REASON_KO.get(dimension)
        if reason and reason not in reasons:
            reasons.append(reason)

    left_equipment = parse_list(str(row.get("left_equipment_codes", "[]")))
    right_equipment = parse_list(str(row.get("right_equipment_codes", "[]")))
    if not left_equipment or not right_equipment:
        reasons.append("장비 정보가 한쪽 이상 비어 있어 동일 수행인지 확인이 필요함")
    elif left_equipment != right_equipment and "EQUIPMENT" not in dimensions:
        reasons.append("사용 장비 정보가 달라 동일 수행인지 확인이 필요함")

    if not reasons:
        reasons.append("운동 방법과 타겟 근육의 동일 여부를 자동 확정할 근거가 부족함")
    return "; ".join(reasons) + ". 자동 중복 확정 대신 사람 확인이 필요함."


def route_row(row: dict[str, Any]) -> dict[str, str]:
    relation = str(row.get("candidate_relation_code", ""))
    if relation in {"PRIMARY_VARIANT", "SECONDARY_VARIANT"}:
        return {
            "queue_code": "VARIANT_CANDIDATE_QUEUE",
            "decision_code": "ROUTED_TO_VARIANT_CANDIDATE",
            "decision_source": "AUTO_RULE",
            "decision_reason_code": "RELATION_TYPE_VARIANT",
            "decision_note": (
                "기존 관계 유형이 PRIMARY_VARIANT 또는 SECONDARY_VARIANT인 후보다. "
                "실제 수행 형태 확인을 위해 Variant 후보 Queue로 분리했다."
            ),
            "human_review_required": "true",
        }

    if relation == "SEPARATE_EXERCISE":
        return {
            "queue_code": "SEPARATE_EXERCISE_QUEUE",
            "decision_code": "SEPARATE_EXERCISE",
            "decision_source": "AUTO_RULE",
            "decision_reason_code": "RELATION_TYPE_SEPARATE_EXERCISE",
            "decision_note": "기존 관계 유형이 SEPARATE_EXERCISE이므로 별도 운동으로 처리했다.",
            "human_review_required": "false",
        }

    if has_home_policy_conflict(row):
        return {
            "queue_code": "HOME_POLICY_EXCLUDED_QUEUE",
            "decision_code": "HOME_POLICY_EXCLUDED",
            "decision_source": "AUTO_RULE",
            "decision_reason_code": "HOME_UNSUPPORTED_STEP_BOX",
            "decision_note": (
                "양쪽 후보가 HOME을 포함하지만 STEP_BOX는 HOME 허용 장비가 아니므로 "
                "HOME 정책 대상에서 제외했다."
            ),
            "human_review_required": "false",
        }

    if (
        relation == "REVIEW_REQUIRED"
        and row.get("movement_pattern_match") == "false"
        and row.get("primary_body_area_overlap") == "0.000"
    ):
        return {
            "queue_code": "SEPARATE_EXERCISE_QUEUE",
            "decision_code": "SEPARATE_EXERCISE",
            "decision_source": "AUTO_RULE",
            "decision_reason_code": "NO_MOVEMENT_OR_PRIMARY_AREA_OVERLAP",
            "decision_note": (
                "movement_pattern_match=false이고 primary_body_area_overlap=0.000이므로 "
                "명백한 비관계 후보로 별도 운동 처리했다."
            ),
            "human_review_required": "false",
        }

    return {
        "queue_code": "HUMAN_REVIEW_QUEUE",
        "decision_code": "PENDING_HUMAN_REVIEW",
        "decision_source": "HUMAN_REVIEW",
        "decision_reason_code": "NO_DETERMINISTIC_QUEUE_RULE",
        "decision_note": "정책 기반 자동 분류 조건이 부족하여 최종 사람 검토가 필요하다.",
        "human_review_required": "true",
        HUMAN_REVIEW_REASON_FIELD: build_human_review_reason(row),
    }


def atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build(batch_dir: Path = DEFAULT_BATCH_DIR) -> dict[str, Any]:
    jsonl_path = batch_dir / "review_batch.jsonl"
    csv_path = batch_dir / "review_batch.csv"
    json_rows = read_jsonl(jsonl_path)
    csv_rows, csv_fields = read_csv(csv_path)
    json_ids = [str(row["candidate_pair_id"]) for row in json_rows]
    csv_by_id = {str(row["candidate_pair_id"]): row for row in csv_rows}
    if len(json_ids) != len(set(json_ids)):
        raise ValueError("candidate_pair_id must be unique in JSONL")
    if set(json_ids) != set(csv_by_id):
        raise ValueError("JSONL and CSV candidate IDs differ")

    routed_rows: list[dict[str, Any]] = []
    for json_row in json_rows:
        row = dict(json_row)
        routing = route_row(row)
        routing.setdefault(HUMAN_REVIEW_REASON_FIELD, "")
        row.update(routing)
        routed_rows.append(row)

    output_fields = [*csv_fields, *(field for field in ROUTING_FIELDS if field not in csv_fields)]
    routed_csv_rows = [
        {field: row.get(field, "") for field in output_fields} for row in routed_rows
    ]
    atomic_write_jsonl(jsonl_path, routed_rows)
    atomic_write_csv(csv_path, output_fields, routed_csv_rows)

    queues: dict[str, list[dict[str, Any]]] = {queue: [] for queue in QUEUE_FILES}
    for row in routed_rows:
        queues[row["queue_code"]].append(row)
    for queue_code, queue_rows in queues.items():
        stem = QUEUE_FILES[queue_code]
        atomic_write_jsonl(batch_dir / f"{stem}.jsonl", queue_rows)
        atomic_write_csv(
            batch_dir / f"{stem}.csv",
            output_fields,
            [{field: row.get(field, "") for field in output_fields} for row in queue_rows],
        )

    counts = Counter(row["queue_code"] for row in routed_rows)
    auto_count = sum(row["decision_source"] == "AUTO_RULE" for row in routed_rows)
    previous_queue_manifest: dict[str, Any] | None = None
    queue_manifest_path = batch_dir / "queue_manifest.json"
    if queue_manifest_path.exists():
        with queue_manifest_path.open(encoding="utf-8") as handle:
            previous_queue_manifest = json.load(handle)
    manifest = {
        "schema_version": "exercise-relationship-queue-routing-v0.1.0",
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "source_batch": {
            "path": str(jsonl_path.relative_to(ROOT.parent)),
            "record_count": len(routed_rows),
            "jsonl_sha256": sha256_file(jsonl_path),
            "csv_sha256": sha256_file(csv_path),
        },
        "policy": {
            "home_supported_equipment_codes": sorted(HOME_SUPPORTED_EQUIPMENT),
            "variant_candidate_codes": ["PRIMARY_VARIANT", "SECONDARY_VARIANT"],
            "obvious_separate_rule": {
                "candidate_relation_code": "REVIEW_REQUIRED",
                "movement_pattern_match": "false",
                "primary_body_area_overlap": "0.000",
                "decision_code": "SEPARATE_EXERCISE",
            },
            "home_exclusion_rule": {
                "both_locations_include": "HOME",
                "equipment_code": "STEP_BOX",
                "decision_code": "HOME_POLICY_EXCLUDED",
            },
        },
        "summary": {
            "source_record_count": len(routed_rows),
            "variant_candidate_queue_count": counts["VARIANT_CANDIDATE_QUEUE"],
            "separate_exercise_queue_count": counts["SEPARATE_EXERCISE_QUEUE"],
            "home_policy_excluded_queue_count": counts["HOME_POLICY_EXCLUDED_QUEUE"],
            "human_review_queue_count": counts["HUMAN_REVIEW_QUEUE"],
            "auto_rule_routed_count": auto_count,
            "human_review_required_count": sum(
                row["human_review_required"] == "true" for row in routed_rows
            ),
        },
        "queue_files": [
            {
                "queue_code": queue_code,
                "csv_path": f"{QUEUE_FILES[queue_code]}.csv",
                "jsonl_path": f"{QUEUE_FILES[queue_code]}.jsonl",
                "record_count": len(queues[queue_code]),
                "csv_sha256": sha256_file(batch_dir / f"{QUEUE_FILES[queue_code]}.csv"),
                "jsonl_sha256": sha256_file(batch_dir / f"{QUEUE_FILES[queue_code]}.jsonl"),
            }
            for queue_code in QUEUE_FILES
        ],
        "sample_candidate_pair_ids": {
            queue_code: [row["candidate_pair_id"] for row in queues[queue_code][:3]]
            for queue_code in QUEUE_FILES
        },
    }
    if previous_queue_manifest and "duplicate_deduplication" in previous_queue_manifest:
        manifest["duplicate_deduplication"] = previous_queue_manifest["duplicate_deduplication"]
    atomic_write_json(queue_manifest_path, manifest)

    review_manifest_path = batch_dir / "review_manifest.json"
    if review_manifest_path.exists():
        with review_manifest_path.open(encoding="utf-8") as handle:
            review_manifest = json.load(handle)
        review_manifest["files"] = [
            {
                "path": "review_batch.csv",
                "records": len(routed_csv_rows),
                "sha256": sha256_file(csv_path),
            },
            {
                "path": "review_batch.jsonl",
                "records": len(routed_rows),
                "sha256": sha256_file(jsonl_path),
            },
        ]
        review_manifest["queue_routing"] = {
            "manifest_path": "queue_manifest.json",
            "schema_version": manifest["schema_version"],
            "auto_rule_routed_count": auto_count,
            "human_review_queue_count": counts["HUMAN_REVIEW_QUEUE"],
        }
        atomic_write_json(review_manifest_path, review_manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(build(args.batch_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
