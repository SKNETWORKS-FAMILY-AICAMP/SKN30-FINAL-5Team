"""Profile a verified wger snapshot and build a DRAFT gym review inventory."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict

from manifest_values import require_int
from wger_exercise_pipeline import PipelineError, sha256_bytes, validate_snapshot

PROFILER_VERSION = "0.1.0"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "validation" / "profiles"
ENGLISH_LANGUAGE_CODE = "en"
KOREAN_LANGUAGE_CODE = "ko"

GYM_EQUIPMENT_NAMES = frozenset(
    {
        "Barbell",
        "Bench",
        "Cable machine",
        "Dumbbell",
        "Incline bench",
        "Kettlebell",
        "Pull-up bar",
        "SZ-Bar",
    }
)


class TargetMovement(TypedDict):
    """검색용 목표 운동군 정의. 정규화 taxonomy가 아니다."""

    code: str
    label_ko: str
    query_terms: list[str]
    pattern: re.Pattern[str]
    text_only_gym_evidence: bool


# These patterns screen source names and aliases only. They do not create a normalized
# exercise taxonomy or assert that two source records are equivalent.
TARGET_MOVEMENTS: tuple[TargetMovement, ...] = (
    {
        "code": "LAT_PULLDOWN",
        "label_ko": "랫풀다운 계열",
        "query_terms": ["lat pulldown", "lat pull-down", "pulldown"],
        "pattern": re.compile(r"\b(?:lat\s+)?pull[- ]?down\b", re.IGNORECASE),
        "text_only_gym_evidence": True,
    },
    {
        "code": "DUMBBELL_ROW",
        "label_ko": "덤벨로우 계열",
        "query_terms": ["dumbbell row", "row + dumbbell"],
        "pattern": re.compile(r"(?:\bdumbbell\b.*\brow\b|\brow\b.*\bdumbbell\b)", re.IGNORECASE),
        "text_only_gym_evidence": True,
    },
    {
        "code": "SEATED_OR_CABLE_ROW",
        "label_ko": "시티드·케이블로우 계열",
        "query_terms": ["seated row", "cable row"],
        "pattern": re.compile(r"\b(?:seated|cable)\b.*\brow\b", re.IGNORECASE),
        "text_only_gym_evidence": True,
    },
    {
        "code": "CHEST_OR_BENCH_PRESS",
        "label_ko": "체스트·벤치프레스 계열",
        "query_terms": ["chest press", "bench press"],
        "pattern": re.compile(r"\b(?:chest|bench)\s+press\b", re.IGNORECASE),
        "text_only_gym_evidence": True,
    },
    {
        "code": "SHOULDER_PRESS",
        "label_ko": "숄더·오버헤드프레스 계열",
        "query_terms": ["shoulder press", "overhead press", "military press"],
        "pattern": re.compile(r"\b(?:shoulder|overhead|military)\s+press\b", re.IGNORECASE),
        "text_only_gym_evidence": True,
    },
    {
        "code": "LEG_PRESS",
        "label_ko": "레그프레스 계열",
        "query_terms": ["leg press"],
        "pattern": re.compile(r"\bleg\s+press\b", re.IGNORECASE),
        "text_only_gym_evidence": True,
    },
    {
        "code": "LEG_EXTENSION",
        "label_ko": "레그익스텐션 계열",
        "query_terms": ["leg extension"],
        "pattern": re.compile(r"\bleg\s+extension\b", re.IGNORECASE),
        "text_only_gym_evidence": True,
    },
    {
        "code": "LEG_CURL",
        "label_ko": "레그컬 계열",
        "query_terms": ["leg curl"],
        "pattern": re.compile(r"\bleg\s+curl\b", re.IGNORECASE),
        "text_only_gym_evidence": True,
    },
    {
        "code": "SQUAT",
        "label_ko": "스쿼트 계열",
        "query_terms": ["squat"],
        "pattern": re.compile(r"\bsquat(?:s|ting)?\b", re.IGNORECASE),
        "text_only_gym_evidence": False,
    },
    {
        "code": "DEADLIFT",
        "label_ko": "데드리프트 계열",
        "query_terms": ["deadlift"],
        "pattern": re.compile(r"\bdeadlifts?\b", re.IGNORECASE),
        "text_only_gym_evidence": False,
    },
)

ALWAYS_REQUIRED_REVIEWS = (
    "BEGINNER_SUITABILITY_REVIEW_REQUIRED",
    "DOMAIN_SAFETY_REVIEW_REQUIRED",
    "EXERCISE_TAXONOMY_MAPPING_REQUIRED",
    "EXECUTION_DOSAGE_REVIEW_REQUIRED",
    "INSTRUCTION_CONTENT_REVIEW_REQUIRED",
    "KOREAN_LOCALIZATION_REVIEW_REQUIRED",
    "SOURCE_LICENSE_REVIEW_REQUIRED",
)


def canonical_text(value: object) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def source_exercise_id(candidate: dict[str, object]) -> int:
    return require_int(candidate["source_exercise_id"], "source_exercise_id")


def first_source_name(candidate: dict[str, object]) -> str:
    """Return the candidate's first English source name for deterministic ordering."""

    names = candidate.get("source_names_en")
    if isinstance(names, list) and names:
        return canonical_text(names[0])
    return ""


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PipelineError(f"{field_name} must be an object")
    return value


def _list_of_mappings(value: object, field_name: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PipelineError(f"{field_name} must be a list of objects")
    return value


def load_resources(
    snapshot_dir: Path,
) -> tuple[dict[str, object], dict[str, list[dict[str, object]]]]:
    snapshot_dir = snapshot_dir.resolve()
    validate_snapshot(snapshot_dir)
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, list):
        raise PipelineError("snapshot manifest.files must be a list")

    resources: dict[str, list[dict[str, object]]] = {}
    for entry_value in files:
        entry = _mapping(entry_value, "manifest.files entry")
        resource = canonical_text(entry.get("resource"))
        relative_path = entry.get("path")
        if not resource or not isinstance(relative_path, str):
            raise PipelineError("snapshot manifest file entry is invalid")
        payload = json.loads((snapshot_dir / relative_path).read_text(encoding="utf-8-sig"))
        page_results = _list_of_mappings(payload.get("results"), f"{resource}.results")
        resources.setdefault(resource, []).extend(page_results)
    return manifest, resources


def language_ids(resources: dict[str, list[dict[str, object]]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for language in resources.get("language", []):
        code = canonical_text(language.get("short_name"))
        language_id = language.get("id")
        if code and isinstance(language_id, int):
            result[code] = language_id
    for required in (ENGLISH_LANGUAGE_CODE, KOREAN_LANGUAGE_CODE):
        if required not in result:
            raise PipelineError(f"required language reference is missing: {required}")
    return result


def license_lookup(
    resources: dict[str, list[dict[str, object]]],
) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for license_item in resources.get("license", []):
        license_id = license_item.get("id")
        if isinstance(license_id, int):
            result[license_id] = {
                "id": license_id,
                "short_name": canonical_text(license_item.get("short_name")),
                "url": canonical_text(license_item.get("url")),
            }
    if not result:
        raise PipelineError("license reference resource is empty")
    return result


def translation_names(translations: Iterable[dict[str, object]], language_id: int) -> list[str]:
    values = {
        canonical_text(translation.get("name"))
        for translation in translations
        if translation.get("language") == language_id
    }
    values.discard("")
    return sorted(values, key=str.casefold)


def translation_aliases(translations: Iterable[dict[str, object]], language_id: int) -> list[str]:
    values: set[str] = set()
    for translation in translations:
        if translation.get("language") != language_id:
            continue
        for alias in _list_of_mappings(translation.get("aliases", []), "translation.aliases"):
            value = canonical_text(alias.get("alias"))
            if value:
                values.add(value)
    return sorted(values, key=str.casefold)


def target_match_codes(names_and_aliases: Iterable[str]) -> list[str]:
    searchable = " | ".join(names_and_aliases)
    return [target["code"] for target in TARGET_MOVEMENTS if target["pattern"].search(searchable)]


def compact_named_items(items: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    compacted: list[dict[str, object]] = []
    for item in items:
        item_id = item.get("id")
        name = canonical_text(item.get("name"))
        if isinstance(item_id, int) and name:
            compacted.append({"id": item_id, "name": name})
    return sorted(compacted, key=lambda item: (str(item["name"]).casefold(), item["id"]))


def build_inventory(
    resources: dict[str, list[dict[str, object]]],
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    languages = language_ids(resources)
    licenses = license_lookup(resources)
    exercises = resources.get("exerciseinfo", [])
    candidates: list[dict[str, object]] = []
    all_target_matches: dict[str, list[dict[str, object]]] = {
        str(target["code"]): [] for target in TARGET_MOVEMENTS
    }
    equipment_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    license_counter: Counter[str] = Counter()
    translation_language_counter: Counter[str] = Counter()
    exercises_with_english = 0
    exercises_with_korean = 0
    exercises_with_images = 0
    exercises_with_videos = 0
    equipment_evidence_count = 0
    target_name_evidence_count = 0

    for item in exercises:
        exercise_id = item.get("id")
        exercise_uuid = canonical_text(item.get("uuid"))
        if not isinstance(exercise_id, int) or not exercise_uuid:
            raise PipelineError("exerciseinfo identity is invalid")
        translations = _list_of_mappings(item.get("translations"), "translations")
        equipment = compact_named_items(_list_of_mappings(item.get("equipment"), "equipment"))
        primary_muscles = compact_named_items(_list_of_mappings(item.get("muscles"), "muscles"))
        secondary_muscles = compact_named_items(
            _list_of_mappings(item.get("muscles_secondary"), "muscles_secondary")
        )
        images = _list_of_mappings(item.get("images"), "images")
        videos = _list_of_mappings(item.get("videos"), "videos")
        category = _mapping(item.get("category"), "category")
        base_license = _mapping(item.get("license"), "license")

        english_names = translation_names(translations, languages[ENGLISH_LANGUAGE_CODE])
        english_aliases = translation_aliases(translations, languages[ENGLISH_LANGUAGE_CODE])
        korean_names = translation_names(translations, languages[KOREAN_LANGUAGE_CODE])
        matches = target_match_codes([*english_names, *english_aliases])
        equipment_names = {str(value["name"]) for value in equipment}
        equipment_evidence = bool(equipment_names & GYM_EQUIPMENT_NAMES)
        target_name_evidence = any(
            target["code"] in matches and target["text_only_gym_evidence"]
            for target in TARGET_MOVEMENTS
        )
        gym_candidate = equipment_evidence or target_name_evidence

        for value in equipment_names:
            equipment_counter[value] += 1
        category_name = canonical_text(category.get("name")) or "UNSPECIFIED"
        category_counter[category_name] += 1
        license_name = canonical_text(base_license.get("short_name")) or "UNSPECIFIED"
        license_counter[license_name] += 1
        for translation in translations:
            translation_language_counter[str(translation.get("language"))] += 1
        exercises_with_english += bool(english_names)
        exercises_with_korean += bool(korean_names)
        exercises_with_images += bool(images)
        exercises_with_videos += bool(videos)

        sample = {
            "source_exercise_id": exercise_id,
            "source_exercise_uuid": exercise_uuid,
            "source_names_en": english_names,
            "source_equipment_names": sorted(equipment_names, key=str.casefold),
        }
        for code in matches:
            all_target_matches[code].append(sample)

        if not gym_candidate:
            continue
        equipment_evidence_count += equipment_evidence
        target_name_evidence_count += target_name_evidence
        required_reviews = list(ALWAYS_REQUIRED_REVIEWS)
        if not english_names:
            required_reviews.append("SOURCE_ENGLISH_TRANSLATION_MISSING")
        if not equipment:
            required_reviews.append("SOURCE_EQUIPMENT_UNSPECIFIED")
        if images or videos:
            required_reviews.append("MEDIA_RIGHTS_REVIEW_REQUIRED")

        translation_licenses: list[dict[str, object]] = []
        for translation in translations:
            translation_id = translation.get("id")
            translation_license_id = translation.get("license")
            if not isinstance(translation_id, int) or not isinstance(translation_license_id, int):
                raise PipelineError("translation license identity is invalid")
            license_reference = licenses.get(translation_license_id)
            if license_reference is None:
                raise PipelineError(
                    f"translation license reference is missing: {translation_license_id}"
                )
            translation_licenses.append(
                {
                    "translation_id": translation_id,
                    "language_id": translation.get("language"),
                    "license": license_reference,
                    "license_author": canonical_text(translation.get("license_author")),
                }
            )

        candidates.append(
            {
                "source_exercise_id": exercise_id,
                "source_exercise_uuid": exercise_uuid,
                "source_names_en": english_names,
                "source_aliases_en": english_aliases,
                "source_names_ko": korean_names,
                "source_category": {
                    "id": category.get("id"),
                    "name": category_name,
                },
                "source_equipment": equipment,
                "source_primary_muscles": primary_muscles,
                "source_secondary_muscles": secondary_muscles,
                "source_base_license": {
                    "id": base_license.get("id"),
                    "short_name": license_name,
                    "url": canonical_text(base_license.get("url")),
                    "license_author": canonical_text(item.get("license_author")),
                },
                "source_translation_licenses": translation_licenses,
                "source_image_reference_count": len(images),
                "source_video_reference_count": len(videos),
                "target_name_match_codes": matches,
                "gym_candidate_reason_codes": sorted(
                    [
                        code
                        for code, present in (
                            ("GYM_EQUIPMENT_SOURCE_EVIDENCE", equipment_evidence),
                            ("TARGET_NAME_SOURCE_EVIDENCE", target_name_evidence),
                        )
                        if present
                    ]
                ),
                "required_review_codes": sorted(required_reviews),
                "review_status": "DRAFT",
                "production_eligible": False,
            }
        )

    candidates.sort(
        key=lambda candidate: (
            not bool(candidate["target_name_match_codes"]),
            first_source_name(candidate).casefold(),
            source_exercise_id(candidate),
        )
    )

    target_coverage_items: list[dict[str, object]] = []
    for target in TARGET_MOVEMENTS:
        code = target["code"]
        target_samples = sorted(all_target_matches[code], key=source_exercise_id)
        target_coverage_items.append(
            {
                "code": code,
                "label_ko": target["label_ko"],
                "query_terms": target["query_terms"],
                "source_name_match_count": len(target_samples),
                "samples": target_samples[:10],
            }
        )

    coverage = {
        "total_exercises": len(exercises),
        "total_translations": sum(
            len(_list_of_mappings(item.get("translations", []), "exerciseinfo.translations"))
            for item in exercises
        ),
        "exercises_with_english_translation": exercises_with_english,
        "exercises_with_korean_translation": exercises_with_korean,
        "gym_review_candidates": len(candidates),
        "gym_candidates_with_equipment_evidence": equipment_evidence_count,
        "gym_candidates_with_target_name_evidence": target_name_evidence_count,
        "exercises_with_image_references": exercises_with_images,
        "exercises_with_video_references": exercises_with_videos,
        "equipment_counts": dict(sorted(equipment_counter.items())),
        "category_counts": dict(sorted(category_counter.items())),
        "base_license_counts": dict(sorted(license_counter.items())),
        "translation_language_id_counts": dict(sorted(translation_language_counter.items())),
    }
    target_coverage: dict[str, object] = {
        "schema_version": "1.0",
        "profiler_version": PROFILER_VERSION,
        "review": {"status": "DRAFT", "production_eligible": False},
        "matching_policy": {
            "evidence_type": "SOURCE_ENGLISH_NAME_OR_ALIAS_TEXT_MATCH",
            "normalized_taxonomy_created": False,
            "equivalence_asserted": False,
        },
        "targets": target_coverage_items,
    }
    return candidates, coverage, target_coverage


def build_profile(
    manifest: dict[str, object], resources: dict[str, list[dict[str, object]]]
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    candidates, coverage, target_coverage = build_inventory(resources)
    source = _mapping(manifest.get("source"), "manifest.source")
    retrieval = _mapping(manifest.get("retrieval"), "manifest.retrieval")
    profile: dict[str, object] = {
        "schema_version": "1.0",
        "profiler_version": PROFILER_VERSION,
        "source": {
            "snapshot_id": manifest.get("snapshot_id"),
            "source_id": source.get("source_id"),
            "retrieved_at": retrieval.get("retrieved_at"),
            "data_license_mode": _mapping(
                source.get("data_license"), "manifest.source.data_license"
            ).get("mode"),
        },
        "review": {"status": "DRAFT", "production_eligible": False},
        "coverage": coverage,
        "interpretation_guards": [
            "SOURCE_NAME_MATCH_IS_NOT_NORMALIZED_EXERCISE_MAPPING",
            "COMMUNITY_INSTRUCTION_IS_NOT_APPROVED_EXECUTION_GUIDANCE",
            "SOURCE_MUSCLE_METADATA_IS_NOT_SAFETY_OR_CONTRAINDICATION_DATA",
            "KOREAN_LOCALIZATION_REQUIRES_HUMAN_REVIEW",
            "MEDIA_REFERENCE_IS_NOT_REDISTRIBUTION_PERMISSION",
            "EACH_SOURCE_AND_TRANSLATION_LICENSE_MUST_BE_REVIEWED",
        ],
    }
    target_coverage["source"] = profile["source"]
    return profile, candidates, target_coverage


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_inventory_jsonl(path: Path, candidates: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate, ensure_ascii=False, sort_keys=True) + "\n")


def _joined(candidate: dict[str, object], field: str) -> str:
    value = candidate.get(field, [])
    return " | ".join(str(item) for item in value) if isinstance(value, list) else str(value)


def write_review_csv(path: Path, candidates: list[dict[str, object]]) -> None:
    fieldnames = [
        "source_exercise_id",
        "source_exercise_uuid",
        "source_names_en",
        "source_names_ko",
        "source_category",
        "source_equipment_names",
        "target_name_match_codes",
        "gym_candidate_reason_codes",
        "source_base_license",
        "required_review_codes",
        "review_status",
        "production_eligible",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            category = _mapping(candidate["source_category"], "candidate.category")
            base_license = _mapping(
                candidate["source_base_license"], "candidate.source_base_license"
            )
            equipment = _list_of_mappings(
                candidate["source_equipment"], "candidate.source_equipment"
            )
            writer.writerow(
                {
                    "source_exercise_id": candidate["source_exercise_id"],
                    "source_exercise_uuid": candidate["source_exercise_uuid"],
                    "source_names_en": _joined(candidate, "source_names_en"),
                    "source_names_ko": _joined(candidate, "source_names_ko"),
                    "source_category": category.get("name", ""),
                    "source_equipment_names": " | ".join(str(item["name"]) for item in equipment),
                    "target_name_match_codes": _joined(candidate, "target_name_match_codes"),
                    "gym_candidate_reason_codes": _joined(candidate, "gym_candidate_reason_codes"),
                    "source_base_license": base_license.get("short_name", ""),
                    "required_review_codes": _joined(candidate, "required_review_codes"),
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
    manifest, resources = load_resources(snapshot_dir)
    profile, candidates, target_coverage = build_profile(manifest, resources)
    snapshot_id = canonical_text(manifest.get("snapshot_id"))
    if not snapshot_id:
        raise PipelineError("snapshot_id is missing")

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    directory_name = f"{snapshot_id}-profile-v{PROFILER_VERSION}"
    final_dir = output_root / directory_name
    partial_dir = output_root / f".{directory_name}.partial"
    if final_dir.exists():
        raise PipelineError(f"profile already exists: {directory_name}")
    if partial_dir.exists():
        raise PipelineError(f"partial profile already exists: {partial_dir.name}")

    partial_dir.mkdir()
    try:
        profile_path = partial_dir / "profile.json"
        inventory_path = partial_dir / "gym_candidate_inventory.jsonl"
        review_path = partial_dir / "gym_candidate_review.csv"
        target_path = partial_dir / "target_movement_coverage.json"
        write_json(profile_path, profile)
        write_inventory_jsonl(inventory_path, candidates)
        write_review_csv(review_path, candidates)
        write_json(target_path, target_coverage)

        profile_manifest = {
            "schema_version": "1.0",
            "profiler_version": PROFILER_VERSION,
            "source": {
                "snapshot_id": snapshot_id,
                "manifest_sha256": sha256_bytes(source_manifest_path.read_bytes()),
            },
            "review": {"status": "DRAFT", "production_eligible": False},
            "summary": profile["coverage"],
            "files": [
                file_entry(profile_path, partial_dir),
                file_entry(inventory_path, partial_dir, records=len(candidates)),
                file_entry(review_path, partial_dir, records=len(candidates)),
                file_entry(target_path, partial_dir, records=len(TARGET_MOVEMENTS)),
            ],
        }
        write_json(partial_dir / "profile_manifest.json", profile_manifest)
        verify_profile(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def verify_profile(profile_dir: Path) -> dict[str, object]:
    profile_dir = profile_dir.resolve()
    manifest_path = profile_dir / "profile_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError("profile_manifest.json is missing") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("profile_manifest.json is not valid UTF-8 JSON") from exc

    if manifest.get("schema_version") != "1.0":
        raise PipelineError("unsupported profile manifest schema")
    if manifest.get("profiler_version") != PROFILER_VERSION:
        raise PipelineError("profile manifest profiler version does not match verifier")
    if manifest.get("review") != {"status": "DRAFT", "production_eligible": False}:
        raise PipelineError("wger profile must remain DRAFT and production-ineligible")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 4:
        raise PipelineError("profile manifest files are invalid")

    inventory_records: int | None = None
    csv_records: int | None = None
    profile_payload: dict[str, object] | None = None
    targets_payload: dict[str, object] | None = None
    for entry_value in files:
        entry = _mapping(entry_value, "profile manifest file entry")
        relative = Path(str(entry.get("path", "")))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("profile manifest contains an unsafe path")
        path = profile_dir / relative
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise PipelineError(f"profile output is missing: {relative.as_posix()}") from exc
        if sha256_bytes(raw) != entry.get("sha256"):
            raise PipelineError(f"profile output hash mismatch: {relative.as_posix()}")
        if len(raw) != require_int(entry.get("bytes", -1), "manifest bytes"):
            raise PipelineError(f"profile output size mismatch: {relative.as_posix()}")

        if relative.name == "gym_candidate_inventory.jsonl":
            lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
            if len(lines) != require_int(entry.get("records", -1), "manifest records"):
                raise PipelineError("gym inventory record count mismatch")
            for line in lines:
                candidate = json.loads(line)
                if (
                    candidate.get("review_status") != "DRAFT"
                    or candidate.get("production_eligible") is not False
                ):
                    raise PipelineError("gym candidate has an unapproved state")
                required = candidate.get("required_review_codes")
                if not isinstance(required, list) or not {
                    "DOMAIN_SAFETY_REVIEW_REQUIRED",
                    "SOURCE_LICENSE_REVIEW_REQUIRED",
                }.issubset(required):
                    raise PipelineError("gym candidate is missing required reviews")
            inventory_records = len(lines)
        elif relative.name == "gym_candidate_review.csv":
            rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
            if len(rows) != require_int(entry.get("records", -1), "manifest records"):
                raise PipelineError("gym review CSV record count mismatch")
            for row in rows:
                if row.get("review_status") != "DRAFT" or row.get("production_eligible") != "false":
                    raise PipelineError("gym review CSV has an unapproved state")
                if "DOMAIN_SAFETY_REVIEW_REQUIRED" not in row.get("required_review_codes", ""):
                    raise PipelineError("gym review CSV is missing safety review")
            csv_records = len(rows)
        elif relative.name == "profile.json":
            loaded = json.loads(raw.decode("utf-8"))
            if not isinstance(loaded, dict):
                raise PipelineError("profile.json root must be an object")
            profile_payload = loaded
        elif relative.name == "target_movement_coverage.json":
            loaded = json.loads(raw.decode("utf-8"))
            if not isinstance(loaded, dict):
                raise PipelineError("target movement coverage root must be an object")
            targets = loaded.get("targets")
            if not isinstance(targets, list) or len(targets) != require_int(
                entry.get("records", -1), "manifest records"
            ):
                raise PipelineError("target movement coverage count mismatch")
            targets_payload = loaded

    if (
        None in (inventory_records, csv_records)
        or profile_payload is None
        or targets_payload is None
    ):
        raise PipelineError("required wger profile output is missing")
    if inventory_records != csv_records:
        raise PipelineError("JSONL and CSV gym candidate counts differ")
    if profile_payload.get("review") != {
        "status": "DRAFT",
        "production_eligible": False,
    }:
        raise PipelineError("profile.json must remain DRAFT")
    coverage = profile_payload.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("gym_review_candidates") != inventory_records:
        raise PipelineError("profile coverage and gym candidate count differ")
    if targets_payload.get("review") != {
        "status": "DRAFT",
        "production_eligible": False,
    }:
        raise PipelineError("target movement coverage must remain DRAFT")
    return {
        "profile": profile_dir.name,
        "gym_candidates": inventory_records,
        "status": "valid",
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    profile = subparsers.add_parser("profile", help="profile a verified wger snapshot")
    profile.add_argument("snapshot", type=Path)
    profile.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    verify = subparsers.add_parser("verify", help="verify a generated wger profile")
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
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
