"""Build a reproducible DRAFT review batch from a verified KSPO profile."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from kspo_fitness100_pipeline import PipelineError, sha256_bytes
from profile_kspo_fitness100 import canonical_text, verify_profile


REVIEW_BATCH_VERSION = "0.1.0"
DEFAULT_BATCH_SIZE = 50
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "validation" / "review_batches"
MISSING_METADATA_CODES = {
    "MUSCLE_METADATA_UNSPECIFIED",
    "SOURCE_DOSAGE_UNSPECIFIED",
    "TOOL_METADATA_UNSPECIFIED",
}
SELECTION_BASIS_CODES = (
    "MVP_SCOPE_REVIEW_ONLY",
    "UNIQUE_SOURCE_TRAINING_NAME_REPRESENTATIVE",
    "LOWEST_MISSING_SOURCE_METADATA_COUNT",
    "RAW_PLACE_TOOL_GROUP_ROUND_ROBIN",
)
INTERPRETATION_GUARDS = (
    "REVIEW_BATCH_IS_NOT_FINAL_SHORTLIST",
    "REVIEW_BATCH_IS_NOT_TAXONOMY_MAPPING",
    "REVIEW_BATCH_IS_NOT_BEGINNER_SUITABILITY_APPROVAL",
    "REVIEW_BATCH_IS_NOT_DOMAIN_SAFETY_APPROVAL",
    "BLANK_SOURCE_TOOL_IS_UNSPECIFIED_NOT_BODYWEIGHT",
    "SOURCE_VIDEO_LENGTH_IS_NOT_EXERCISE_DOSAGE",
    "MEDIA_REFERENCE_IS_NOT_REDISTRIBUTION_PERMISSION",
)


def load_candidates(profile_dir: Path) -> list[dict[str, object]]:
    profile_dir = profile_dir.resolve()
    verify_profile(profile_dir)
    inventory_path = profile_dir / "candidate_inventory.jsonl"
    candidates: list[dict[str, object]] = []
    for line_number, line in enumerate(
        inventory_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        candidate = json.loads(line)
        if not isinstance(candidate, dict):
            raise PipelineError(f"candidate inventory line {line_number} is not an object")
        candidates.append(candidate)
    return candidates


def list_value(candidate: dict[str, object], field: str) -> list[str]:
    value = candidate.get(field, [])
    if not isinstance(value, list):
        raise PipelineError(f"candidate field {field} must be a list")
    return sorted({canonical_text(item) for item in value if canonical_text(item)})


def missing_source_metadata_count(candidate: dict[str, object]) -> int:
    required = list_value(candidate, "required_review_codes")
    return sum(code in MISSING_METADATA_CODES for code in required)


def representative_rank(candidate: dict[str, object]) -> tuple[object, ...]:
    """Prefer source-complete evidence without inferring exercise quality or safety."""

    descriptions = list_value(candidate, "source_descriptions")
    muscle_parts = list_value(candidate, "muscle_parts")
    tools = list_value(candidate, "tools")
    frame_rows = candidate.get("source_frame_rows", 0)
    if not isinstance(frame_rows, int) or frame_rows < 1:
        raise PipelineError("source_frame_rows must be a positive integer")
    return (
        missing_source_metadata_count(candidate),
        -int(bool(descriptions)),
        -int(bool(muscle_parts)),
        -int(bool(tools)),
        -frame_rows,
        canonical_text(candidate.get("source_file_name")),
        canonical_text(candidate.get("source_candidate_id")),
    )


def raw_signature(candidate: dict[str, object], field: str) -> str:
    values = list_value(candidate, field)
    return " | ".join(values) if values else "SOURCE_UNSPECIFIED"


def select_review_batch(
    candidates: Iterable[dict[str, object]], size: int = DEFAULT_BATCH_SIZE
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if size < 1:
        raise PipelineError("review batch size must be at least 1")

    eligible = [
        candidate
        for candidate in candidates
        if candidate.get("review_bucket") == "MVP_SCOPE_REVIEW"
    ]
    if not eligible:
        raise PipelineError("profile contains no MVP_SCOPE_REVIEW candidates")

    by_name: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen_ids: set[str] = set()
    for candidate in eligible:
        candidate_id = canonical_text(candidate.get("source_candidate_id"))
        training_name = canonical_text(candidate.get("source_training_name"))
        if not candidate_id or not training_name:
            raise PipelineError("eligible candidate is missing its source ID or training name")
        if candidate_id in seen_ids:
            raise PipelineError(f"duplicate source_candidate_id: {candidate_id}")
        seen_ids.add(candidate_id)
        by_name[training_name].append(candidate)

    representatives: list[dict[str, object]] = []
    duplicate_name_groups = 0
    for training_name, group in sorted(by_name.items()):
        if len(group) > 1:
            duplicate_name_groups += 1
        representative = min(group, key=representative_rank)
        prepared = dict(representative)
        prepared["duplicate_name_candidate_count"] = len(group)
        prepared["source_training_name"] = training_name
        representatives.append(prepared)

    if size > len(representatives):
        raise PipelineError(
            f"requested {size} rows but only {len(representatives)} unique names are available"
        )

    diversity_groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for candidate in representatives:
        group_key = (
            raw_signature(candidate, "places"),
            raw_signature(candidate, "tools"),
        )
        diversity_groups[group_key].append(candidate)
    for group in diversity_groups.values():
        group.sort(
            key=lambda candidate: (
                canonical_text(candidate.get("source_training_name")),
                canonical_text(candidate.get("source_file_name")),
            )
        )

    selected: list[dict[str, object]] = []
    group_keys = sorted(diversity_groups)
    while len(selected) < size:
        progressed = False
        for group_key in group_keys:
            group = diversity_groups[group_key]
            if not group:
                continue
            candidate = group.pop(0)
            selected.append(candidate)
            progressed = True
            if len(selected) == size:
                break
        if not progressed:
            raise PipelineError("review batch selection stopped before reaching requested size")

    prepared_rows: list[dict[str, object]] = []
    for position, candidate in enumerate(selected, start=1):
        row = dict(candidate)
        row.update(
            {
                "batch_position": position,
                "batch_status": "DRAFT_REVIEW_QUEUE",
                "selection_basis_codes": list(SELECTION_BASIS_CODES),
                "review_status": "DRAFT",
                "production_eligible": False,
            }
        )
        prepared_rows.append(row)

    summary: dict[str, object] = {
        "mvp_scope_candidate_pairs": len(eligible),
        "unique_source_training_names": len(representatives),
        "duplicate_source_training_name_groups": duplicate_name_groups,
        "raw_place_tool_groups": len(diversity_groups),
        "requested_batch_size": size,
        "selected_batch_size": len(prepared_rows),
    }
    return prepared_rows, summary


def joined(candidate: dict[str, object], field: str) -> str:
    return " | ".join(list_value(candidate, field))


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "batch_position",
        "source_candidate_id",
        "source_file_name",
        "source_training_name",
        "duplicate_name_candidate_count",
        "age_groups",
        "places",
        "tools",
        "muscle_parts",
        "source_frame_rows",
        "required_review_codes",
        "batch_status",
        "review_status",
        "production_eligible",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "batch_position": row["batch_position"],
                    "source_candidate_id": row["source_candidate_id"],
                    "source_file_name": row["source_file_name"],
                    "source_training_name": row["source_training_name"],
                    "duplicate_name_candidate_count": row[
                        "duplicate_name_candidate_count"
                    ],
                    "age_groups": joined(row, "age_groups"),
                    "places": joined(row, "places"),
                    "tools": joined(row, "tools"),
                    "muscle_parts": joined(row, "muscle_parts"),
                    "source_frame_rows": row["source_frame_rows"],
                    "required_review_codes": joined(row, "required_review_codes"),
                    "batch_status": row["batch_status"],
                    "review_status": row["review_status"],
                    "production_eligible": "false",
                }
            )


def file_entry(path: Path, root: Path, records: int) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "records": records,
    }


def create_review_batch(
    profile_dir: Path,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    size: int = DEFAULT_BATCH_SIZE,
) -> Path:
    profile_dir = profile_dir.resolve()
    candidates = load_candidates(profile_dir)
    rows, summary = select_review_batch(candidates, size=size)
    profile_manifest_path = profile_dir / "profile_manifest.json"

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    directory_name = f"{profile_dir.name}-review-batch-v{REVIEW_BATCH_VERSION}"
    final_dir = output_root / directory_name
    partial_dir = output_root / f".{directory_name}.partial"
    if final_dir.exists():
        raise PipelineError(f"review batch already exists: {directory_name}")
    if partial_dir.exists():
        raise PipelineError(f"partial review batch already exists: {partial_dir.name}")

    partial_dir.mkdir()
    try:
        jsonl_path = partial_dir / "review_batch.jsonl"
        csv_path = partial_dir / "review_batch.csv"
        write_jsonl(jsonl_path, rows)
        write_csv(csv_path, rows)
        manifest = {
            "schema_version": "1.0",
            "review_batch_version": REVIEW_BATCH_VERSION,
            "source": {
                "profile_directory": profile_dir.name,
                "profile_manifest_sha256": sha256_bytes(
                    profile_manifest_path.read_bytes()
                ),
            },
            "selection": {
                "status": "DRAFT_REVIEW_QUEUE",
                "method_codes": list(SELECTION_BASIS_CODES),
                "interpretation_guards": list(INTERPRETATION_GUARDS),
            },
            "review": {"status": "DRAFT", "production_eligible": False},
            "summary": summary,
            "files": [
                file_entry(jsonl_path, partial_dir, len(rows)),
                file_entry(csv_path, partial_dir, len(rows)),
            ],
        }
        write_json(partial_dir / "review_manifest.json", manifest)
        verify_review_batch(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def verify_review_batch(batch_dir: Path) -> dict[str, int | str]:
    batch_dir = batch_dir.resolve()
    manifest_path = batch_dir / "review_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError("review_manifest.json is missing") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("review_manifest.json is not valid JSON") from exc

    if manifest.get("schema_version") != "1.0":
        raise PipelineError("unsupported review manifest schema")
    if manifest.get("review_batch_version") != REVIEW_BATCH_VERSION:
        raise PipelineError("review batch version does not match this verifier")
    if manifest.get("review") != {"status": "DRAFT", "production_eligible": False}:
        raise PipelineError("review batch must remain DRAFT and production-ineligible")
    source = manifest.get("source")
    if not isinstance(source, dict) or not canonical_text(source.get("profile_directory")):
        raise PipelineError("review batch source profile is missing")
    profile_manifest_hash = canonical_text(source.get("profile_manifest_sha256"))
    if not re.fullmatch(r"[0-9a-f]{64}", profile_manifest_hash):
        raise PipelineError("review batch source profile hash is invalid")
    selection = manifest.get("selection")
    if not isinstance(selection, dict) or selection.get("status") != "DRAFT_REVIEW_QUEUE":
        raise PipelineError("review batch selection status is invalid")
    if selection.get("method_codes") != list(SELECTION_BASIS_CODES):
        raise PipelineError("review batch selection method codes are invalid")
    guards = selection.get("interpretation_guards")
    if not isinstance(guards, list) or "REVIEW_BATCH_IS_NOT_DOMAIN_SAFETY_APPROVAL" not in guards:
        raise PipelineError("review batch is missing its safety interpretation guard")

    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 2:
        raise PipelineError("review manifest must list JSONL and CSV files")

    jsonl_rows: list[dict[str, object]] | None = None
    csv_rows: list[dict[str, str]] | None = None
    for entry in files:
        if not isinstance(entry, dict):
            raise PipelineError("review manifest file entry is invalid")
        relative = Path(str(entry.get("path", "")))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("review manifest contains an unsafe file path")
        path = batch_dir / relative
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise PipelineError(f"review batch file is missing: {relative.as_posix()}") from exc
        if sha256_bytes(raw) != entry.get("sha256"):
            raise PipelineError(f"review batch hash mismatch: {relative.as_posix()}")
        if len(raw) != int(entry.get("bytes", -1)):
            raise PipelineError(f"review batch size mismatch: {relative.as_posix()}")

        expected_records = int(entry.get("records", -1))
        if relative.name == "review_batch.jsonl":
            jsonl_rows = [
                json.loads(line)
                for line in raw.decode("utf-8").splitlines()
                if line.strip()
            ]
            if len(jsonl_rows) != expected_records:
                raise PipelineError("review batch JSONL record count mismatch")
        elif relative.name == "review_batch.csv":
            csv_rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
            if len(csv_rows) != expected_records:
                raise PipelineError("review batch CSV record count mismatch")

    if jsonl_rows is None or csv_rows is None:
        raise PipelineError("review batch is missing JSONL or CSV content")
    if len(jsonl_rows) != len(csv_rows):
        raise PipelineError("review batch JSONL and CSV counts differ")

    expected_positions = list(range(1, len(jsonl_rows) + 1))
    actual_positions: list[int] = []
    training_names: set[str] = set()
    for row in jsonl_rows:
        if not isinstance(row, dict):
            raise PipelineError("review batch JSONL row is invalid")
        if row.get("batch_status") != "DRAFT_REVIEW_QUEUE":
            raise PipelineError("review batch row status is invalid")
        if row.get("review_status") != "DRAFT" or row.get("production_eligible") is not False:
            raise PipelineError("review batch row was promoted without approval")
        required = row.get("required_review_codes")
        if not isinstance(required, list) or "DOMAIN_SAFETY_REVIEW_REQUIRED" not in required:
            raise PipelineError("review batch row is missing domain safety review")
        actual_positions.append(int(row.get("batch_position", 0)))
        training_name = canonical_text(row.get("source_training_name"))
        if not training_name or training_name in training_names:
            raise PipelineError("review batch training names must be non-empty and unique")
        training_names.add(training_name)
    if actual_positions != expected_positions:
        raise PipelineError("review batch positions are not contiguous")

    for jsonl_row, csv_row in zip(jsonl_rows, csv_rows, strict=True):
        if (
            csv_row.get("batch_status") != "DRAFT_REVIEW_QUEUE"
            or csv_row.get("review_status") != "DRAFT"
            or csv_row.get("production_eligible") != "false"
        ):
            raise PipelineError("review batch CSV contains an invalid state")
        identity = (
            str(jsonl_row["batch_position"]),
            canonical_text(jsonl_row.get("source_candidate_id")),
            canonical_text(jsonl_row.get("source_training_name")),
        )
        csv_identity = (
            csv_row.get("batch_position", ""),
            csv_row.get("source_candidate_id", ""),
            csv_row.get("source_training_name", ""),
        )
        if csv_identity != identity:
            raise PipelineError("review batch JSONL and CSV identity mismatch")

    summary = manifest.get("summary")
    if not isinstance(summary, dict) or summary.get("selected_batch_size") != len(jsonl_rows):
        raise PipelineError("review manifest summary does not match batch size")
    if summary.get("requested_batch_size") != len(jsonl_rows):
        raise PipelineError("review manifest requested size does not match batch size")
    return {"batch": batch_dir.name, "records": len(jsonl_rows), "status": "valid"}


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a DRAFT review batch")
    build.add_argument("profile", type=Path)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--size", type=int, default=DEFAULT_BATCH_SIZE)
    verify = subparsers.add_parser("verify", help="verify a generated review batch")
    verify.add_argument("batch", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "build":
            batch_dir = create_review_batch(args.profile, args.output_root, args.size)
            result: dict[str, object] = {"status": "built", "batch": str(batch_dir)}
        else:
            result = verify_review_batch(args.batch)
    except (PipelineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
