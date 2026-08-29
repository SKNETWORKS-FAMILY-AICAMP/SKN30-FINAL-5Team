"""Remove reviewed duplicate relationship pairs from the v2.0.2 queues.

The decisions in ``DUPLICATE_DECISIONS`` are deliberately explicit.  A pair is
removed only when its two sides have the same stable code, movement pattern,
primary/secondary body-area targets, and the remaining name difference is a
translation or explanatory wording difference.  Equipment, posture, grip,
stance, range-of-motion, and other execution differences remain in the queue.
"""

from __future__ import annotations

import argparse
import csv
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

# The right side is the canonical EXERCISE record for every selected pair.  It
# is retained because its body-area metadata is equally specific, its
# equipment metadata is filled more often, and its Korean name is at least as
# suitable for the catalog user.
DUPLICATE_DECISIONS = {
    "ERP-20260827-00138": "right",
    "ERP-20260827-00400": "right",
    "ERP-20260827-00464": "right",
    "ERP-20260827-00465": "right",
    "ERP-20260827-00467": "right",
    "ERP-20260827-00474": "right",
    "ERP-20260827-00493": "right",
    "ERP-20260827-00502": "right",
    "ERP-20260827-00592": "right",
    "ERP-20260827-00603": "right",
}

QUEUE_FILES = {
    "VARIANT_CANDIDATE_QUEUE": "variant_candidate_queue",
    "SEPARATE_EXERCISE_QUEUE": "separate_exercise_queue",
    "HOME_POLICY_EXCLUDED_QUEUE": "home_policy_excluded_queue",
    "HUMAN_REVIEW_QUEUE": "human_review_queue",
}


def parse_json_list(value: str) -> tuple[str, ...]:
    parsed = json.loads(value or "[]")
    if not isinstance(parsed, list):
        raise ValueError(f"expected JSON list, got {value!r}")
    return tuple(sorted(str(item).strip() for item in parsed if str(item).strip()))


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


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def is_same_method_and_target(row: dict[str, Any]) -> bool:
    return (
        row.get("left_record_type") == "V1_ALIAS"
        and row.get("right_record_type") == "EXERCISE"
        and row.get("left_stable_code") == row.get("right_stable_code")
        and row.get("movement_pattern_match") == "true"
        and parse_json_list(str(row.get("left_primary_body_area_codes", "[]")))
        == parse_json_list(str(row.get("right_primary_body_area_codes", "[]")))
        and parse_json_list(str(row.get("left_secondary_body_area_codes", "[]")))
        == parse_json_list(str(row.get("right_secondary_body_area_codes", "[]")))
    )


def update_manifests(batch_dir: Path, batch_rows: list[dict[str, Any]]) -> None:
    counts = Counter(row["queue_code"] for row in batch_rows)
    removed = [
        {
            "candidate_pair_id": pair_id,
            "removed_side": "left",
            "kept_side": keep_side,
            "reason_code": "SAME_METHOD_AND_PRIMARY_SECONDARY_TARGET",
        }
        for pair_id, keep_side in DUPLICATE_DECISIONS.items()
    ]

    queue_manifest_path = batch_dir / "queue_manifest.json"
    if queue_manifest_path.exists():
        with queue_manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        manifest["source_batch"]["record_count"] = len(batch_rows)
        manifest["source_batch"]["jsonl_sha256"] = sha256_file(batch_dir / "review_batch.jsonl")
        manifest["source_batch"]["csv_sha256"] = sha256_file(batch_dir / "review_batch.csv")
        manifest["summary"].update(
            {
                "source_record_count": len(batch_rows),
                "variant_candidate_queue_count": counts["VARIANT_CANDIDATE_QUEUE"],
                "separate_exercise_queue_count": counts["SEPARATE_EXERCISE_QUEUE"],
                "home_policy_excluded_queue_count": counts["HOME_POLICY_EXCLUDED_QUEUE"],
                "human_review_queue_count": counts["HUMAN_REVIEW_QUEUE"],
                "human_review_required_count": sum(
                    row["human_review_required"] == "true" for row in batch_rows
                ),
            }
        )
        for queue_file in manifest["queue_files"]:
            stem = QUEUE_FILES[queue_file["queue_code"]]
            queue_file["record_count"] = counts[queue_file["queue_code"]]
            queue_file["csv_sha256"] = sha256_file(batch_dir / f"{stem}.csv")
            queue_file["jsonl_sha256"] = sha256_file(batch_dir / f"{stem}.jsonl")
        manifest["duplicate_deduplication"] = {
            "removed_pair_count": len(removed),
            "rule": (
                "same stable code, movement pattern, primary body area, and secondary body area; "
                "name-only or explanatory translation difference"
            ),
            "decisions": removed,
        }
        atomic_write_json(queue_manifest_path, manifest)

    review_manifest_path = batch_dir / "review_manifest.json"
    if review_manifest_path.exists():
        with review_manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        manifest["files"] = [
            {
                "path": "review_batch.csv",
                "records": len(batch_rows),
                "sha256": sha256_file(batch_dir / "review_batch.csv"),
            },
            {
                "path": "review_batch.jsonl",
                "records": len(batch_rows),
                "sha256": sha256_file(batch_dir / "review_batch.jsonl"),
            },
        ]
        summary = manifest["summary"]
        relation_counts = Counter(row["candidate_relation_code"] for row in batch_rows)
        summary.update(
            {
                "candidate_pair_count": len(batch_rows),
                "same_exercise_candidate_count": relation_counts["SAME_EXERCISE"],
                "variant_candidate_count": relation_counts["PRIMARY_VARIANT"]
                + relation_counts["SECONDARY_VARIANT"],
                "primary_variant_candidate_count": relation_counts["PRIMARY_VARIANT"],
                "secondary_variant_candidate_count": relation_counts["SECONDARY_VARIANT"],
                "separate_exercise_candidate_count": relation_counts["SEPARATE_EXERCISE"],
                "excluded_candidate_count": relation_counts["EXCLUDED"],
                "review_required_candidate_count": relation_counts["REVIEW_REQUIRED"],
                "pending_human_review_count": len(batch_rows),
            }
        )
        manifest["duplicate_deduplication"] = {
            "removed_pair_count": len(removed),
            "decisions": removed,
        }
        atomic_write_json(review_manifest_path, manifest)


def dedupe(batch_dir: Path = DEFAULT_BATCH_DIR) -> dict[str, Any]:
    batch_json_path = batch_dir / "review_batch.jsonl"
    batch_csv_path = batch_dir / "review_batch.csv"
    human_json_path = batch_dir / "human_review_queue.jsonl"
    human_csv_path = batch_dir / "human_review_queue.csv"

    batch_rows = read_jsonl(batch_json_path)
    batch_csv_rows, batch_csv_fields = read_csv(batch_csv_path)
    human_rows = read_jsonl(human_json_path)
    human_csv_rows, human_csv_fields = read_csv(human_csv_path)
    batch_ids = {str(row["candidate_pair_id"]) for row in batch_rows}
    batch_csv_ids = {str(row["candidate_pair_id"]) for row in batch_csv_rows}
    human_ids = {str(row["candidate_pair_id"]) for row in human_rows}
    human_csv_ids = {str(row["candidate_pair_id"]) for row in human_csv_rows}
    if batch_ids != batch_csv_ids or human_ids != human_csv_ids or not human_ids <= batch_ids:
        raise ValueError("review batch and human queue IDs are inconsistent")

    rows_by_id = {str(row["candidate_pair_id"]): row for row in human_rows}
    for pair_id in DUPLICATE_DECISIONS:
        row = rows_by_id.get(pair_id)
        if row is None:
            raise ValueError(f"duplicate decision is missing from human queue: {pair_id}")
        if not is_same_method_and_target(row):
            raise ValueError(f"duplicate decision failed method/target validation: {pair_id}")

    batch_rows = [
        row for row in batch_rows if str(row["candidate_pair_id"]) not in DUPLICATE_DECISIONS
    ]
    human_rows = [
        row for row in human_rows if str(row["candidate_pair_id"]) not in DUPLICATE_DECISIONS
    ]
    batch_csv_rows = [
        row for row in batch_csv_rows if str(row["candidate_pair_id"]) not in DUPLICATE_DECISIONS
    ]
    human_csv_rows = [
        row for row in human_csv_rows if str(row["candidate_pair_id"]) not in DUPLICATE_DECISIONS
    ]

    atomic_write_jsonl(batch_json_path, batch_rows)
    atomic_write_csv(batch_csv_path, batch_csv_fields, batch_csv_rows)
    atomic_write_jsonl(human_json_path, human_rows)
    atomic_write_csv(human_csv_path, human_csv_fields, human_csv_rows)
    update_manifests(batch_dir, batch_rows)
    return {
        "removed_pair_count": len(DUPLICATE_DECISIONS),
        "review_batch_count": len(batch_rows),
        "human_review_queue_count": len(human_rows),
        "remaining_queue_counts": dict(Counter(row["queue_code"] for row in batch_rows)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(dedupe(args.batch_dir), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
