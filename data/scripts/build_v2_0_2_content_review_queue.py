"""Name the exercise content v2.0.2 still needs before it can be imported.

The final catalog cannot be packaged for the backend: `form_cues_ko` is empty on
every record, and the derived pain-area records carry no rest or transition
interval. Some of that is recoverable - the final canonical builder dropped cues
that its own audit artifacts still hold - and the rest has to be written.

This script separates the two. It recovers what the pipeline already reviewed,
keyed by stable code, and emits a review queue for what nobody has written yet.
It never fills a value in: a form cue is coaching text a person reads while
moving, and a rest interval is FITT dosage, so both sit behind explicit review
(data/AGENTS.md). Guessing either one would put invented instructions in front
of a beginner.

Two recovery sources, both keyed by the same stable code as the final catalog:

* ``audit/canonical_exercises_v2_0_2_refined.csv`` - the representatives, whose
  cues survived into the audit trail but not into the canonical payload.
* ``audit/alternatives/discomfort_safe_variants_v2_0_2.jsonl`` - the pain-area
  safe variants. These cues were written *for the replaced posture*, which is
  why the base exercise's cues must never be inherited in their place. Note the
  rows are ``REVIEW_REQUIRED``: recovering them does not make them approved.

Outputs `content_review_queue.csv`/`.jsonl` plus a manifest, under
`data/validation/review_batches/exercise-catalog-v2.0.2-content-review-v0.1.0/`.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FINAL = DATA_ROOT / "generated/exercise-catalog-v2.0.2-final"
DEFAULT_OUTPUT = (
    DATA_ROOT / "validation/review_batches/exercise-catalog-v2.0.2-content-review-v0.1.0"
)
QUEUE_VERSION = "exercise-catalog-v2.0.2-content-review-v0.1.0"

REPRESENTATIVE_SOURCE = "audit/canonical_exercises_v2_0_2_refined.csv"
SAFE_VARIANT_SOURCE = "audit/alternatives/discomfort_safe_variants_v2_0_2.jsonl"

# Ordered so the reviewer sees the fields a single record is missing together.
_REQUIRED_FIELDS = ("form_cues_ko", "default_rest_seconds", "default_transition_seconds")

_QUEUE_COLUMNS = (
    "stable_code",
    "name_ko",
    "record_type",
    "source_track",
    "missing_fields",
    "training_type_code",
    "primary_movement_pattern_code",
    "timing_mode_code",
    "difficulty_code",
    "general_pool_included",
    "instruction_summary_ko",
    "fixed_posture_code",
    "fixed_support_code",
    "alternative_source_base_stable_code",
    "representative_exercise_id",
    "recovered_form_cues_source",
    "form_cues_ko",
    "default_rest_seconds",
    "default_transition_seconds",
)


class QueueError(RuntimeError):
    """Raised when the queue cannot be built from the shipped artifacts."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise QueueError(f"artifact is missing: {path}") from exc
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise QueueError(f"artifact is missing: {path}") from exc


def _parse_cues(value: object) -> list[str] | None:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()] or None
    if isinstance(value, str) and value.strip() and value.strip() != "[]":
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return _parse_cues(parsed)
    return None


def recover_form_cues(final: Path) -> dict[str, tuple[list[str], str]]:
    """Return the cues the canonical builder dropped, keyed by stable code."""
    recovered: dict[str, tuple[list[str], str]] = {}
    for row in _read_csv(final / REPRESENTATIVE_SOURCE):
        cues = _parse_cues(row.get("form_cues_ko"))
        code = (row.get("stable_code") or "").strip()
        if cues and code:
            recovered.setdefault(code, (cues, REPRESENTATIVE_SOURCE))
    for row in _read_jsonl(final / SAFE_VARIANT_SOURCE):
        cues = _parse_cues(row.get("form_cues_ko"))
        code = str(row.get("stable_code") or "").strip()
        if cues and code:
            recovered.setdefault(code, (cues, SAFE_VARIANT_SOURCE))
    return recovered


def build_queue(final: Path = DEFAULT_FINAL) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    catalog = _read_jsonl(final / "catalog/exercises.jsonl")
    recovered = recover_form_cues(final)

    rows: list[dict[str, Any]] = []
    complete = 0
    recovered_only = 0
    for record in catalog:
        code = str(record.get("stable_code"))
        cues = _parse_cues(record.get("form_cues_ko"))
        recovered_entry = recovered.get(code)
        if cues is None and recovered_entry is not None:
            cues, cue_source = recovered_entry
        else:
            cue_source = "" if cues is None else "catalog"

        missing = []
        if cues is None:
            missing.append("form_cues_ko")
        if record.get("default_rest_seconds") is None:
            missing.append("default_rest_seconds")
        if record.get("default_transition_seconds") is None:
            missing.append("default_transition_seconds")
        if not missing:
            complete += 1
            if cue_source not in ("", "catalog"):
                recovered_only += 1
            continue

        rows.append(
            {
                "stable_code": code,
                "name_ko": record.get("name_ko"),
                "record_type": record.get("record_type"),
                "source_track": record.get("source_track"),
                "missing_fields": "|".join(missing),
                "training_type_code": record.get("training_type_code"),
                "primary_movement_pattern_code": record.get("primary_movement_pattern_code"),
                "timing_mode_code": record.get("timing_mode_code"),
                "difficulty_code": record.get("difficulty_code"),
                "general_pool_included": record.get("general_pool_included"),
                "instruction_summary_ko": record.get("instruction_summary_ko"),
                "fixed_posture_code": record.get("fixed_posture_code"),
                "fixed_support_code": record.get("fixed_support_code"),
                "alternative_source_base_stable_code": record.get(
                    "alternative_source_base_stable_code"
                ),
                "representative_exercise_id": record.get("representative_exercise_id"),
                "recovered_form_cues_source": cue_source,
                # Pre-filled when recovery found it, blank when a reviewer must write it.
                "form_cues_ko": json.dumps(cues, ensure_ascii=False) if cues else "",
                "default_rest_seconds": record.get("default_rest_seconds") or "",
                "default_transition_seconds": record.get("default_transition_seconds") or "",
            }
        )

    rows.sort(key=lambda row: (str(row["missing_fields"]), str(row["stable_code"])))
    by_missing: dict[str, int] = {}
    for row in rows:
        by_missing[str(row["missing_fields"])] = by_missing.get(str(row["missing_fields"]), 0) + 1
    summary = {
        "schema_version": "v2.0.2-content-review-v0.1.0",
        "queue_version": QUEUE_VERSION,
        "catalog_version_code": "exercise-catalog-v2.0.2-final",
        "status": "CONTENT_REVIEW_REQUIRED",
        "production_eligible": False,
        "catalog_records": len(catalog),
        "importable_records": complete,
        "queued_records": len(rows),
        "form_cues_recovered_records": recovered_only,
        "queued_by_missing_fields": dict(sorted(by_missing.items())),
        "recovery_sources": [REPRESENTATIVE_SOURCE, SAFE_VARIANT_SOURCE],
        "note": (
            "Recovered cues keep the review status of their source artifact; the "
            "safe-variant rows are REVIEW_REQUIRED. Recovery is not approval."
        ),
    }
    return rows, summary


def write_queue(
    rows: list[dict[str, Any]], summary: dict[str, Any], output: Path = DEFAULT_OUTPUT
) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "content_review_queue.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_QUEUE_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in _QUEUE_COLUMNS})
    jsonl_path = output / "content_review_queue.jsonl"
    jsonl_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    manifest = dict(summary)
    manifest["files"] = [
        {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "records": len(rows),
        }
        for path in (csv_path, jsonl_path)
    ]
    (output / "queue_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", type=Path, default=DEFAULT_FINAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--report-only", action="store_true", help="print the summary without writing the queue"
    )
    args = parser.parse_args(argv)
    rows, summary = build_queue(args.final)
    if not args.report_only:
        write_queue(rows, summary, args.output)
        summary["output"] = str(args.output)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
