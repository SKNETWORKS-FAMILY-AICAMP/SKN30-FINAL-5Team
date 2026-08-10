"""Profile a verified KSPO Fitness100 snapshot and build a DRAFT review inventory."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from kspo_fitness100_pipeline import PipelineError, sha256_bytes, validate_snapshot


PROFILER_VERSION = "0.2.0"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "validation" / "profiles"
MAX_PROFILE_VALUES = 20

ALWAYS_REQUIRED_REVIEWS = (
    "ALTERNATIVE_RELATION_REVIEW_REQUIRED",
    "BEGINNER_SUITABILITY_REVIEW_REQUIRED",
    "DOMAIN_SAFETY_REVIEW_REQUIRED",
    "EXERCISE_TAXONOMY_MAPPING_REQUIRED",
    "EXECUTION_DOSAGE_REVIEW_REQUIRED",
    "INSTRUCTION_CONTENT_REVIEW_REQUIRED",
    "MEDIA_RIGHTS_REVIEW_REQUIRED",
)


def canonical_text(value: object) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def is_missing(value: object) -> bool:
    return canonical_text(value) == ""


def json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def count_key(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return canonical_text(value)


def load_snapshot(snapshot_dir: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    snapshot_dir = snapshot_dir.resolve()
    validate_snapshot(snapshot_dir)
    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, list):
        raise PipelineError("snapshot manifest의 files가 목록이 아닙니다.")

    items: list[dict[str, object]] = []
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise PipelineError("snapshot manifest의 파일 항목이 올바르지 않습니다.")
        page = json.loads((snapshot_dir / entry["path"]).read_text(encoding="utf-8-sig"))
        response = page.get("response", page)
        body = response.get("body", {}) if isinstance(response, dict) else {}
        container = body.get("items", {}) if isinstance(body, dict) else {}
        value = container.get("item", []) if isinstance(container, dict) else container
        if value in (None, ""):
            continue
        page_items = [value] if isinstance(value, dict) else value
        if not isinstance(page_items, list) or not all(
            isinstance(item, dict) for item in page_items
        ):
            raise PipelineError("snapshot 페이지의 item 목록이 올바르지 않습니다.")
        items.extend(page_items)
    return manifest, items


def unique_texts(items: Iterable[dict[str, object]], field: str) -> list[str]:
    values = {canonical_text(item.get(field)) for item in items}
    values.discard("")
    return sorted(values)


def field_profile(items: list[dict[str, object]]) -> list[dict[str, object]]:
    fields = sorted({field for item in items for field in item})
    profiles: list[dict[str, object]] = []
    for field in fields:
        values = [item.get(field) for item in items]
        missing_count = sum(is_missing(value) for value in values)
        non_missing = [value for value in values if not is_missing(value)]
        counts = Counter(count_key(value) for value in non_missing)
        types = Counter(json_type(value) for value in values)
        top_values = [
            {"value": value, "count": count}
            for value, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[
                :MAX_PROFILE_VALUES
            ]
        ]
        profiles.append(
            {
                "field": field,
                "missing_count": missing_count,
                "missing_rate": round(missing_count / len(items), 6) if items else 0,
                "unique_non_missing": len(counts),
                "json_types": dict(sorted(types.items())),
                "top_values": top_values,
            }
        )
    return profiles


def candidate_id(file_name: str, training_name: str) -> str:
    identity = f"kspo_fitness100_video\x1f{file_name}\x1f{training_name}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def scope_screen(age_groups: list[str], places: list[str]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    in_scope = True

    if not age_groups:
        in_scope = False
        reasons.append("AGE_UNSPECIFIED")
    elif set(age_groups) == {"유아기"}:
        in_scope = False
        reasons.append("AGE_CHILD_ONLY")
    else:
        reasons.append("AGE_GENERAL_REVIEWABLE")

    if not places:
        in_scope = False
        reasons.append("PLACE_UNSPECIFIED")
    elif set(places) == {"수영장"}:
        in_scope = False
        reasons.append("PLACE_POOL_ONLY")
    else:
        reasons.append("PLACE_MVP_REVIEWABLE")

    bucket = "MVP_SCOPE_REVIEW" if in_scope else "OUT_OF_SCOPE_REVIEW"
    return bucket, reasons


def build_candidates(
    items: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    unnamed_rows = 0
    for item in items:
        file_name = canonical_text(item.get("file_nm"))
        training_name = canonical_text(item.get("trng_nm"))
        if not training_name:
            unnamed_rows += 1
            continue
        if not file_name:
            raise PipelineError("운동명이 있는 원천 행에 file_nm이 없습니다.")
        groups[(file_name, training_name)].append(item)

    candidates: list[dict[str, object]] = []
    for (file_name, training_name), group in groups.items():
        age_groups = unique_texts(group, "aggrp_nm")
        places = unique_texts(group, "trng_plc_nm")
        tools = unique_texts(group, "tool_nm")
        muscle_parts = unique_texts(group, "trng_mscl_part")
        set_values = unique_texts(group, "set_cnt_nm")
        repetition_values = unique_texts(group, "rptt_tcnt_nm")
        time_values = unique_texts(group, "trng_hr_nm")
        cycle_values = unique_texts(group, "ecrg_cycl_nm")
        bucket, scope_reasons = scope_screen(age_groups, places)

        required_reviews = list(ALWAYS_REQUIRED_REVIEWS)
        if not muscle_parts:
            required_reviews.append("MUSCLE_METADATA_UNSPECIFIED")
        if not tools:
            required_reviews.append("TOOL_METADATA_UNSPECIFIED")
        if not any((set_values, repetition_values, time_values, cycle_values)):
            required_reviews.append("SOURCE_DOSAGE_UNSPECIFIED")

        candidates.append(
            {
                "source_candidate_id": candidate_id(file_name, training_name),
                "source_file_name": file_name,
                "source_training_name": training_name,
                "source_video_titles": unique_texts(group, "vdo_ttl_nm"),
                "source_descriptions": unique_texts(group, "vdo_desc"),
                "age_groups": age_groups,
                "places": places,
                "tools": tools,
                "muscle_names_ko": unique_texts(group, "trng_mscl_nm"),
                "muscle_parts": muscle_parts,
                "source_set_values": set_values,
                "source_repetition_values": repetition_values,
                "source_time_values": time_values,
                "source_cycle_values": cycle_values,
                "source_frame_rows": len(group),
                "review_bucket": bucket,
                "scope_reason_codes": scope_reasons,
                "required_review_codes": sorted(required_reviews),
                "review_status": "DRAFT",
                "production_eligible": False,
            }
        )

    candidates.sort(
        key=lambda candidate: (
            candidate["review_bucket"] != "MVP_SCOPE_REVIEW",
            str(candidate["source_training_name"]),
            str(candidate["source_file_name"]),
        )
    )
    summary = {
        "named_candidate_pairs": len(candidates),
        "unnamed_source_rows_excluded": unnamed_rows,
        "mvp_scope_review_candidates": sum(
            candidate["review_bucket"] == "MVP_SCOPE_REVIEW" for candidate in candidates
        ),
        "out_of_scope_review_candidates": sum(
            candidate["review_bucket"] == "OUT_OF_SCOPE_REVIEW" for candidate in candidates
        ),
    }
    return candidates, summary


def build_profile(
    manifest: dict[str, object], items: list[dict[str, object]]
) -> tuple[dict[str, object], list[dict[str, object]]]:
    candidates, candidate_summary = build_candidates(items)
    file_names = {canonical_text(item.get("file_nm")) for item in items}
    file_names.discard("")
    training_names = {canonical_text(item.get("trng_nm")) for item in items}
    training_names.discard("")
    video_groups = Counter(canonical_text(item.get("file_nm")) for item in items)
    video_groups.pop("", None)

    source = manifest.get("source", {})
    retrieval = manifest.get("retrieval", {})
    profile = {
        "schema_version": "1.0",
        "profiler_version": PROFILER_VERSION,
        "source": {
            "snapshot_id": manifest.get("snapshot_id"),
            "source_id": source.get("source_id") if isinstance(source, dict) else None,
            "dataset_id": source.get("dataset_id") if isinstance(source, dict) else None,
            "retrieved_at": retrieval.get("retrieved_at")
            if isinstance(retrieval, dict)
            else None,
        },
        "review": {"status": "DRAFT", "production_eligible": False},
        "unit_analysis": {
            "raw_frame_rows": len(items),
            "unique_video_files": len(file_names),
            "unique_training_names": len(training_names),
            "video_training_pairs_including_blank_names": len(
                {
                    (
                        canonical_text(item.get("file_nm")),
                        canonical_text(item.get("trng_nm")),
                    )
                    for item in items
                }
            ),
            "videos_with_multiple_training_names": sum(
                len(
                    {
                        canonical_text(item.get("trng_nm"))
                        for item in items
                        if canonical_text(item.get("file_nm")) == file_name
                    }
                )
                > 1
                for file_name in file_names
            ),
            "minimum_frame_rows_per_video": min(video_groups.values())
            if video_groups
            else 0,
            "maximum_frame_rows_per_video": max(video_groups.values())
            if video_groups
            else 0,
            **candidate_summary,
        },
        "field_profiles": field_profile(items),
        "interpretation_guards": [
            "ROW_IS_VIDEO_FRAME_METADATA_NOT_ONE_EXERCISE",
            "CANDIDATE_PAIR_IS_NOT_NORMALIZED_EXERCISE_ID",
            "VIDEO_LENGTH_IS_NOT_EXERCISE_DURATION",
            "MVP_SCOPE_REVIEW_IS_NOT_SAFETY_APPROVAL",
            "MEDIA_REFERENCE_IS_NOT_REDISTRIBUTION_PERMISSION",
        ],
    }
    return profile, candidates


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_inventory_jsonl(path: Path, candidates: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate, ensure_ascii=False, sort_keys=True) + "\n")


def joined(candidate: dict[str, object], field: str) -> str:
    value = candidate.get(field, [])
    return " | ".join(str(item) for item in value) if isinstance(value, list) else str(value)


def write_review_csv(path: Path, candidates: list[dict[str, object]]) -> None:
    fieldnames = [
        "source_candidate_id",
        "source_file_name",
        "source_training_name",
        "age_groups",
        "places",
        "tools",
        "muscle_parts",
        "source_frame_rows",
        "review_bucket",
        "scope_reason_codes",
        "required_review_codes",
        "review_status",
        "production_eligible",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "source_candidate_id": candidate["source_candidate_id"],
                    "source_file_name": candidate["source_file_name"],
                    "source_training_name": candidate["source_training_name"],
                    "age_groups": joined(candidate, "age_groups"),
                    "places": joined(candidate, "places"),
                    "tools": joined(candidate, "tools"),
                    "muscle_parts": joined(candidate, "muscle_parts"),
                    "source_frame_rows": candidate["source_frame_rows"],
                    "review_bucket": candidate["review_bucket"],
                    "scope_reason_codes": joined(candidate, "scope_reason_codes"),
                    "required_review_codes": joined(candidate, "required_review_codes"),
                    "review_status": candidate["review_status"],
                    "production_eligible": str(candidate["production_eligible"]).lower(),
                }
            )


def file_entry(path: Path, root: Path, *, records: int | None = None) -> dict[str, object]:
    raw = path.read_bytes()
    entry: dict[str, object] = {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
    }
    if records is not None:
        entry["records"] = records
    return entry


def create_profile(snapshot_dir: Path, output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    snapshot_dir = snapshot_dir.resolve()
    source_manifest_path = snapshot_dir / "manifest.json"
    manifest, items = load_snapshot(snapshot_dir)
    profile, candidates = build_profile(manifest, items)
    snapshot_id = canonical_text(manifest.get("snapshot_id"))
    if not snapshot_id:
        raise PipelineError("snapshot_id가 없습니다.")

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    directory_name = f"{snapshot_id}-profile-v{PROFILER_VERSION}"
    final_dir = output_root / directory_name
    partial_dir = output_root / f".{directory_name}.partial"
    if final_dir.exists():
        raise PipelineError(f"profile이 이미 존재합니다: {directory_name}")
    if partial_dir.exists():
        raise PipelineError(f"미완료 profile 디렉터리가 존재합니다: {partial_dir.name}")

    partial_dir.mkdir()
    try:
        profile_path = partial_dir / "profile.json"
        inventory_path = partial_dir / "candidate_inventory.jsonl"
        review_path = partial_dir / "candidate_review.csv"
        write_json(profile_path, profile)
        write_inventory_jsonl(inventory_path, candidates)
        write_review_csv(review_path, candidates)

        source_manifest_bytes = source_manifest_path.read_bytes()
        profile_manifest = {
            "schema_version": "1.0",
            "profiler_version": PROFILER_VERSION,
            "source": {
                "snapshot_id": snapshot_id,
                "manifest_sha256": sha256_bytes(source_manifest_bytes),
            },
            "review": {"status": "DRAFT", "production_eligible": False},
            "summary": profile["unit_analysis"],
            "files": [
                file_entry(profile_path, partial_dir),
                file_entry(inventory_path, partial_dir, records=len(candidates)),
                file_entry(review_path, partial_dir, records=len(candidates)),
            ],
        }
        write_json(partial_dir / "profile_manifest.json", profile_manifest)
        verify_profile(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def verify_profile(profile_dir: Path) -> dict[str, int | str]:
    profile_dir = profile_dir.resolve()
    manifest_path = profile_dir / "profile_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError("profile_manifest.json이 없습니다.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("profile_manifest.json이 유효한 JSON이 아닙니다.") from exc

    if manifest.get("schema_version") != "1.0":
        raise PipelineError("지원하지 않는 profile manifest schema입니다.")
    if manifest.get("profiler_version") != PROFILER_VERSION:
        raise PipelineError("profile manifest의 profiler version이 다릅니다.")
    review = manifest.get("review")
    if not isinstance(review, dict) or review != {
        "status": "DRAFT",
        "production_eligible": False,
    }:
        raise PipelineError("profile은 DRAFT/production_eligible=false여야 합니다.")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 3:
        raise PipelineError("profile manifest의 files가 올바르지 않습니다.")

    inventory_records: int | None = None
    csv_records: int | None = None
    profile_payload: dict[str, object] | None = None
    for entry in files:
        if not isinstance(entry, dict):
            raise PipelineError("profile manifest 파일 항목이 객체가 아닙니다.")
        relative = Path(str(entry.get("path", "")))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("profile manifest에 안전하지 않은 경로가 있습니다.")
        path = profile_dir / relative
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise PipelineError(f"profile 산출물이 없습니다: {relative.as_posix()}") from exc
        if sha256_bytes(raw) != entry.get("sha256"):
            raise PipelineError(f"profile 산출물 해시가 다릅니다: {relative.as_posix()}")
        if len(raw) != int(entry.get("bytes", -1)):
            raise PipelineError(f"profile 산출물 크기가 다릅니다: {relative.as_posix()}")
        if relative.name == "candidate_inventory.jsonl":
            lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
            if len(lines) != int(entry.get("records", -1)):
                raise PipelineError("candidate inventory 레코드 수가 다릅니다.")
            for line in lines:
                candidate = json.loads(line)
                if candidate.get("review_status") != "DRAFT" or candidate.get(
                    "production_eligible"
                ) is not False:
                    raise PipelineError("승인되지 않은 candidate 상태가 있습니다.")
                required = candidate.get("required_review_codes")
                if not isinstance(required, list) or "DOMAIN_SAFETY_REVIEW_REQUIRED" not in required:
                    raise PipelineError("candidate에 필수 안전 리뷰 코드가 없습니다.")
            inventory_records = len(lines)
        elif relative.name == "candidate_review.csv":
            rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
            if len(rows) != int(entry.get("records", -1)):
                raise PipelineError("candidate review CSV 레코드 수가 다릅니다.")
            for row in rows:
                if row.get("review_status") != "DRAFT" or row.get(
                    "production_eligible"
                ) != "false":
                    raise PipelineError("CSV에 승인되지 않은 candidate 상태가 있습니다.")
                if "DOMAIN_SAFETY_REVIEW_REQUIRED" not in row.get(
                    "required_review_codes", ""
                ):
                    raise PipelineError("CSV candidate에 필수 안전 리뷰 코드가 없습니다.")
            csv_records = len(rows)
        elif relative.name == "profile.json":
            loaded = json.loads(raw.decode("utf-8"))
            if not isinstance(loaded, dict):
                raise PipelineError("profile.json 최상위 값이 객체가 아닙니다.")
            loaded_review = loaded.get("review")
            if loaded_review != {"status": "DRAFT", "production_eligible": False}:
                raise PipelineError("profile.json은 DRAFT 상태여야 합니다.")
            profile_payload = loaded

    if inventory_records is None or csv_records is None or profile_payload is None:
        raise PipelineError("필수 profile 산출물이 없습니다.")
    if csv_records != inventory_records:
        raise PipelineError("JSONL과 CSV candidate 수가 다릅니다.")
    units = profile_payload.get("unit_analysis")
    if not isinstance(units, dict) or units.get("named_candidate_pairs") != inventory_records:
        raise PipelineError("profile 요약과 candidate 수가 다릅니다.")
    return {
        "profile": profile_dir.name,
        "candidates": inventory_records,
        "status": "valid",
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    profile = subparsers.add_parser("profile", help="검증된 snapshot profiling")
    profile.add_argument("snapshot", type=Path)
    profile.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    verify = subparsers.add_parser("verify", help="생성된 profile 재검증")
    verify.add_argument("profile", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "profile":
            profile_dir = create_profile(args.snapshot, args.output_root)
            result: dict[str, object] = {
                "status": "profiled",
                "profile": str(profile_dir),
            }
        else:
            result = verify_profile(args.profile)
    except (PipelineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"실패: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
