"""Build a read-only consolidated catalog with exact duplicates removed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = DATA_ROOT / "generated" / "exercise-catalog-deduplicated-v0.4.0"
INPUTS = (
    DATA_ROOT / "generated" / "exercise-catalog-seed-kspo-mvp-v0.2.0",
    DATA_ROOT / "generated" / "exercise-catalog-seed-wger-mvp-v0.2.0",
    DATA_ROOT / "generated" / "exercise-catalog-seed-kspo-tranche3-v0.1.0",
    DATA_ROOT / "generated" / "exercise-catalog-seed-wger-tranche3-v0.1.0",
)
VERSION = "exercise-catalog-deduplicated-v0.4.0"
GYMVISUAL_RAW = DATA_ROOT / "raw" / "gym_visual" / "exercises.json"
GYMVISUAL_REVIEW_INPUTS = (
    DATA_ROOT / "validation" / "review_batches" / "gymvisual_strength_representative_review.csv",
    DATA_ROOT / "validation" / "review_batches" / "gymvisual_mobility_review.csv",
    DATA_ROOT / "validation" / "review_batches" / "gymvisual_cardio_review.csv",
)

SEMANTIC_DUPLICATE_GROUPS = (
    {
        "kept": "outdoor_walking",
        "removed": "treadmill_walking",
        "reason": "두 설명 모두 일정한 속도로 걷는 연속 보행 유산소이며 장소·장비만 다름",
    },
    {
        "kept": "standing_weighted_hip_hinge",
        "removed": "stability_ball_hip_hinge_lift",
        "reason": (
            "두 설명 모두 엉덩이를 뒤로 보내 상체를 기울였다가 엉덩관절을 펴는 "
            "힙힌지이며 도구만 다름"
        ),
    },
    {
        "kept": "seated_leg_extension",
        "removed": "leg_extension",
        "reason": (
            "두 설명 모두 앉은 자세에서 무릎을 펴 하퇴를 들어 올렸다가 통제하며 "
            "내리는 동작이며 장비만 다름"
        ),
    },
    {
        "kept": "standing_calf_raise",
        "removed": "machine_calf_press",
        "reason": (
            "두 설명 모두 앞꿈치를 지지해 뒤꿈치를 올리고 천천히 내리는 종아리 "
            "발목 폄 동작이며 지지 장비만 다름"
        ),
    },
)

GYMVISUAL_DUPLICATE_GROUPS = (
    {
        "removed": "inverted_row",
        "reference_id": "0499",
        "reference_name": "inverted row",
        "reason": (
            "두 설명 모두 고정된 바 아래에서 몸을 곧게 유지하고 가슴을 바 쪽으로 "
            "당기는 인버티드 로우"
        ),
    },
    {
        "removed": "seated_cable_row",
        "reference_id": "0861",
        "reference_name": "cable seated row",
        "reason": "두 설명 모두 앉아서 손잡이를 몸쪽으로 당기는 케이블 시티드 로우",
    },
    {
        "removed": "push_up",
        "reference_id": "0662",
        "reference_name": "push-up",
        "reason": (
            "두 설명 모두 플랭크 정렬에서 팔꿈치를 굽혀 가슴을 낮췄다가 밀어 올리는 팔굽혀펴기"
        ),
    },
    {
        "removed": "seated_leg_extension",
        "reference_id": "0585",
        "reference_name": "lever leg extension",
        "reason": "두 설명 모두 앉은 자세에서 무릎을 펴 하퇴를 들어 올리는 레그 익스텐션",
    },
    {
        "removed": "supine_hip_bridge",
        "reference_id": "3013",
        "reference_name": "low glute bridge on floor",
        "reason": "두 설명 모두 누워 무릎을 세우고 엉덩이를 들어 올리는 바닥 글루트 브리지",
    },
    {
        "removed": "standing_lateral_raise",
        "reference_id": "0334",
        "reference_name": "dumbbell lateral raise",
        "reason": "두 설명 모두 서서 팔을 양옆으로 어깨 높이까지 들어 올리는 레터럴 레이즈",
    },
    {
        "removed": "household_biceps_curl",
        "reference_id": "0416",
        "reference_name": "dumbbell standing biceps curl",
        "reason": (
            "두 설명 모두 팔꿈치를 몸 옆에 고정하고 저항을 어깨 쪽으로 올리는 스탠딩 바이셉스 컬"
        ),
    },
    {
        "removed": "standing_calf_raise",
        "reference_id": "1373",
        "reference_name": "bodyweight standing calf raise",
        "reason": (
            "두 설명 모두 지지물을 잡고 선 자세에서 뒤꿈치를 들어 올렸다가 천천히 "
            "내리는 스탠딩 카프 레이즈"
        ),
    },
    {
        "removed": "leg_curl",
        "reference_id": "0599",
        "reference_name": "lever seated leg curl",
        "reason": "두 설명 모두 장비 패드에 다리를 고정하고 무릎을 굽혀 뒤꿈치를 당기는 레그 컬",
    },
    {
        "removed": "dumbbell_goblet_squat",
        "reference_id": "1760",
        "reference_name": "dumbbell goblet squat",
        "reason": (
            "두 설명 모두 덤벨을 가슴 앞에 들고 엉덩이와 무릎을 굽혔다가 일어나는 고블릿 스쿼트"
        ),
    },
    {
        "removed": "romanian_deadlift",
        "reference_id": "0116",
        "reference_name": "barbell straight leg deadlift",
        "reason": (
            "두 설명 모두 무릎을 약간 굽힌 채 엉덩이를 뒤로 보내 바벨을 다리 가까이 내리는 RDL 계열"
        ),
    },
    {
        "removed": "dumbbell_romanian_deadlift",
        "reference_id": "0116",
        "reference_name": "barbell straight leg deadlift",
        "reason": (
            "두 설명 모두 무릎 각도를 크게 바꾸지 않고 엉덩이를 뒤로 보내 다리를 따라 "
            "중량을 내리는 RDL 계열"
        ),
    },
    {
        "removed": "dumbbell_shoulder_press",
        "reference_id": "0405",
        "reference_name": "dumbbell seated shoulder press",
        "reason": "두 설명 모두 덤벨을 어깨 높이에서 머리 위로 밀어 올리는 덤벨 숄더 프레스",
    },
    {
        "removed": "dumbbell_overhead_triceps_extension",
        "reference_id": "0109",
        "reference_name": "barbell standing overhead triceps extension",
        "reason": (
            "두 설명 모두 머리 위 중량을 팔꿈치 굽힘으로 뒤로 내렸다가 위팔을 고정해 "
            "펴는 오버헤드 트라이셉스 익스텐션"
        ),
    },
    {
        "removed": "cable_triceps_pushdown",
        "reference_id": "0201",
        "reference_name": "cable pushdown",
        "reason": (
            "두 설명 모두 상단 케이블에서 위팔을 몸통 옆에 고정하고 팔꿈치를 펴는 케이블 푸시다운"
        ),
    },
    {
        "removed": "standing_side_stretch",
        "reference_id": "0794",
        "reference_name": "standing lateral stretch",
        "reason": (
            "두 설명 모두 서서 몸통을 한쪽으로 기울여 옆구리·광배근을 늘리는 스탠딩 사이드 스트레치"
        ),
    },
    {
        "removed": "outdoor_walking",
        "reference_id": "3666",
        "reference_name": "walking on incline treadmill",
        "reason": (
            "두 설명 모두 일정한 속도로 걷는 보행 유산소이며 Gym Visual 쪽은 경사·기구만 "
            "추가된 변형"
        ),
    },
)


class CatalogError(RuntimeError):
    """Raised when a source catalog cannot be safely consolidated."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CatalogError(f"JSON root is not an object: {path}")
    return value


def text_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " | ".join(text_value(item) for item in value)
    if isinstance(value, dict):
        return " | ".join(f"{key}:{text_value(item)}" for key, item in value.items())
    return str(value)


def load_gymvisual_references() -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    try:
        raw_value = json.loads(GYMVISUAL_RAW.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"invalid Gym Visual raw JSON: {GYMVISUAL_RAW}") from exc
    if not isinstance(raw_value, list):
        raise CatalogError("Gym Visual raw JSON must be a list")
    raw_by_id: dict[str, dict[str, Any]] = {}
    for value in raw_value:
        if not isinstance(value, dict) or not str(value.get("id", "")):
            raise CatalogError("Gym Visual raw record has no id")
        raw_by_id[str(value["id"])] = value

    selected: dict[str, dict[str, str]] = {}
    review_inputs: list[dict[str, Any]] = []
    for path in GYMVISUAL_REVIEW_INPUTS:
        review_inputs.append(
            {
                "path": path.relative_to(DATA_ROOT.parent).as_posix(),
                "sha256": sha256_bytes(path.read_bytes()),
                "bytes": path.stat().st_size,
            }
        )
    for group in GYMVISUAL_DUPLICATE_GROUPS:
        reference_id = str(group["reference_id"])
        raw = raw_by_id.get(reference_id)
        if raw is None:
            raise CatalogError(f"Gym Visual reference is missing: {reference_id}")
        if text_value(raw.get("name", "")) != str(group["reference_name"]):
            raise CatalogError(f"Gym Visual reference name does not match: {reference_id}")
        selected[reference_id] = {
            "source_name": text_value(raw.get("name", "")),
            "source_equipment": text_value(raw.get("equipment", "")),
            "instructions": text_value(raw.get("instructions") or raw.get("instruction_steps", "")),
            "source_media_id": text_value(raw.get("media_id", "")),
        }
    return selected, review_inputs


def load_records(directory: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest_path = directory / "seed_manifest.json"
    exercises_path = directory / "exercises.jsonl"
    manifest = load_json(manifest_path)
    try:
        raw = exercises_path.read_bytes()
    except OSError as exc:
        raise CatalogError(f"missing catalog file: {exercises_path}") from exc
    files = manifest.get("files")
    if not isinstance(files, list) or not files or not isinstance(files[0], dict):
        raise CatalogError(f"manifest has no file entry: {manifest_path}")
    entry = files[0]
    if entry.get("path") != "exercises.jsonl" or entry.get("sha256") != sha256_bytes(raw):
        raise CatalogError(f"catalog hash does not match manifest: {directory}")

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CatalogError(f"invalid JSONL at {exercises_path}:{line_number}") from exc
        if not isinstance(record, dict):
            raise CatalogError(f"JSONL record is not an object: {exercises_path}:{line_number}")
        records.append(record)
    if entry.get("records") != len(records):
        raise CatalogError(f"record count does not match manifest: {directory}")
    return records, manifest


def normalized_name(value: object) -> str:
    return "".join(str(value).casefold().split())


def duplicate_keys(record: dict[str, Any]) -> list[tuple[str, str]]:
    stable_code = str(record.get("stable_code", "")).strip()
    name_ko = normalized_name(record.get("name_ko", ""))
    source_track = str(record.get("source_track", "")).strip()
    source_identity = str(record.get("source_identity", "")).strip()
    if not stable_code or not name_ko or not source_track or not source_identity:
        raise CatalogError(
            "all catalog records need stable_code, name_ko, source_track, source_identity"
        )
    return [
        ("stable_code", stable_code),
        ("display_name_ko", name_ko),
        ("source_identity", f"{source_track}:{source_identity}"),
    ]


def semantic_duplicate_entry(
    kept: dict[str, Any], removed: dict[str, Any], reason: str
) -> dict[str, Any]:
    return {
        "removed_source_track": removed["source_track"],
        "removed_source_identity": removed["source_identity"],
        "removed_stable_code": removed["stable_code"],
        "removed_name_ko": removed["name_ko"],
        "removed_instruction_summary_ko": removed["instruction_summary_ko"],
        "removed_form_cues_ko": removed["form_cues_ko"],
        "kept_source_track": kept["source_track"],
        "kept_source_identity": kept["source_identity"],
        "kept_stable_code": kept["stable_code"],
        "kept_name_ko": kept["name_ko"],
        "kept_instruction_summary_ko": kept["instruction_summary_ko"],
        "kept_form_cues_ko": kept["form_cues_ko"],
        "duplicate_key_type": "SEMANTIC_DESCRIPTION_DUPLICATE",
        "reason": reason,
    }


def gymvisual_duplicate_entry(
    removed: dict[str, Any], reference: dict[str, str], group: dict[str, Any]
) -> dict[str, Any]:
    return {
        "removed_source_track": removed["source_track"],
        "removed_source_identity": removed["source_identity"],
        "removed_stable_code": removed["stable_code"],
        "removed_name_ko": removed["name_ko"],
        "removed_instruction_summary_ko": removed["instruction_summary_ko"],
        "removed_form_cues_ko": removed["form_cues_ko"],
        "kept_source_track": "gymvisual",
        "kept_source_identity": group["reference_id"],
        "kept_name_en": reference["source_name"],
        "kept_instruction_en": reference["instructions"],
        "kept_equipment": reference["source_equipment"],
        "kept_media_id": reference["source_media_id"],
        "duplicate_key_type": "GYMVISUAL_SEMANTIC_DESCRIPTION_DUPLICATE",
        "reason": group["reason"],
    }


def consolidate() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]
]:
    all_records: list[dict[str, Any]] = []
    input_manifests: list[dict[str, Any]] = []
    for directory in INPUTS:
        records, manifest = load_records(directory)
        all_records.extend(records)
        input_manifests.append(
            {
                "directory": directory.name,
                "manifest_sha256": sha256_bytes((directory / "seed_manifest.json").read_bytes()),
                "exercises_sha256": sha256_bytes((directory / "exercises.jsonl").read_bytes()),
                "records": len(records),
            }
        )

    by_stable_code = {str(record["stable_code"]): record for record in all_records}
    semantic_removed: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for group in SEMANTIC_DUPLICATE_GROUPS:
        kept_code = str(group["kept"])
        removed_code = str(group["removed"])
        if kept_code not in by_stable_code or removed_code not in by_stable_code:
            raise CatalogError(f"semantic duplicate group is missing a stable code: {group}")
        if removed_code in semantic_removed:
            raise CatalogError(
                f"stable code is removed by multiple semantic groups: {removed_code}"
            )
        semantic_removed[removed_code] = group
        duplicates.append(
            semantic_duplicate_entry(
                by_stable_code[kept_code], by_stable_code[removed_code], str(group["reason"])
            )
        )

    gymvisual_references, review_inputs = load_gymvisual_references()
    gymvisual_removed: dict[str, dict[str, Any]] = {}
    for group in GYMVISUAL_DUPLICATE_GROUPS:
        removed_code = str(group["removed"])
        if removed_code not in by_stable_code:
            raise CatalogError(
                f"Gym Visual duplicate group is missing a stable code: {removed_code}"
            )
        if removed_code in semantic_removed:
            raise CatalogError(
                f"stable code is removed by internal and Gym Visual groups: {removed_code}"
            )
        if removed_code in gymvisual_removed:
            raise CatalogError(
                f"stable code is removed by multiple Gym Visual groups: {removed_code}"
            )
        reference = gymvisual_references[str(group["reference_id"])]
        gymvisual_removed[removed_code] = group
        duplicates.append(gymvisual_duplicate_entry(by_stable_code[removed_code], reference, group))

    kept: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for record in all_records:
        stable_code = str(record["stable_code"])
        if stable_code in semantic_removed or stable_code in gymvisual_removed:
            continue
        matching_key: tuple[str, str] | None = None
        original: dict[str, Any] | None = None
        for key in duplicate_keys(record):
            if key in seen:
                matching_key = key
                original = seen[key]
                break
        if matching_key is None or original is None:
            kept.append(record)
            for key in duplicate_keys(record):
                seen[key] = record
            continue
        duplicates.append(
            {
                "removed_source_track": record["source_track"],
                "removed_source_identity": record["source_identity"],
                "removed_stable_code": record["stable_code"],
                "removed_name_ko": record["name_ko"],
                "kept_source_track": original["source_track"],
                "kept_source_identity": original["source_identity"],
                "kept_stable_code": original["stable_code"],
                "kept_name_ko": original["name_ko"],
                "duplicate_key_type": matching_key[0],
            }
        )
    return kept, duplicates, input_manifests, review_inputs


def write_output(output: Path) -> None:
    if output.exists():
        raise CatalogError(f"refusing to overwrite existing output: {output}")
    records, duplicates, input_manifests, review_inputs = consolidate()
    if len(records) != 56 - len(duplicates):
        raise CatalogError("consolidated record count is inconsistent")
    output.mkdir(parents=True)
    try:
        exercises_path = output / "exercises.jsonl"
        with exercises_path.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

        report = {
            "schema_version": "1.0",
            "version_code": VERSION,
            "deduplication_policy": {
                "duplicate_keys": [
                    "stable_code",
                    "display_name_ko",
                    "source_track:source_identity",
                ],
                "variants_retained": True,
                "note": (
                    "Equipment, posture, grip, unilateral, and location variants are retained "
                    "unless an exact duplicate key matches."
                ),
            },
            "input_catalogs": input_manifests,
            "gymvisual_reference_inputs": review_inputs,
            "gymvisual_raw_sha256": sha256_bytes(GYMVISUAL_RAW.read_bytes()),
            "summary": {
                "input_records": 56,
                "duplicate_records_removed": len(duplicates),
                "output_records": len(records),
            },
            "removed_duplicates": duplicates,
        }
        report_path = output / "deduplication_report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        manifest = {
            "schema_version": "1.0",
            "generator_version": "0.1.0",
            "catalog_version": {"version_code": VERSION, "status_code": "DRAFT"},
            "source": {
                "input_catalogs": input_manifests,
                "gymvisual_reference_inputs": review_inputs,
                "gymvisual_raw_sha256": sha256_bytes(GYMVISUAL_RAW.read_bytes()),
            },
            "review": {
                "status": "DOMAIN_APPROVED",
                "review_method_code": "AGENT_ONLY",
                "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
                "production_eligible": False,
            },
            "summary": {
                "input_records": 56,
                "duplicate_records_removed": len(duplicates),
                "exercise_records": len(records),
            },
            "files": [
                {
                    "path": "exercises.jsonl",
                    "sha256": sha256_bytes(exercises_path.read_bytes()),
                    "bytes": exercises_path.stat().st_size,
                    "records": len(records),
                },
                {
                    "path": "deduplication_report.json",
                    "sha256": sha256_bytes(report_path.read_bytes()),
                    "bytes": report_path.stat().st_size,
                    "records": 1,
                },
            ],
        }
        (output / "seed_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception:
        for path in output.iterdir():
            path.unlink()
        output.rmdir()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    write_output(args.output_dir.resolve())
    print(args.output_dir.resolve())


if __name__ == "__main__":
    main()
