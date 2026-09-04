"""Build the v2.0.6 237-row backend projection from the normalized catalog.

The normalized CSV is the sole catalog input. This generator materializes the
backend catalog, exact local GIF bindings, reviewed goal/prescription defaults,
exercise-scoped safety rules, and the importer-required
STRETCH_STRAP -> BODYWEIGHT fallback relations. Household substitutions,
cautions, and replacement-exercise guides are excluded from this bundle.

The output remains a DRAFT and is never production-eligible merely because the
source rows are DOMAIN_APPROVED.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGET_VERSION = "exercise-catalog-v2.0.6-final"
CATALOG_VERSION = TARGET_VERSION
NORMALIZED_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
MEDIA_DIRECTORY = PROJECT_ROOT / "data/media/videos"
MEDIA_REVIEW = PROJECT_ROOT / "data/validation/review_results/gymvisual_media_reviewed.csv"
TAXONOMY_REGISTRY = PROJECT_ROOT / "data/normalized/exercise_taxonomy_codes.json"
SAFETY_POLICY = PROJECT_ROOT / "data/normalized/exercise_safety_rule_policy.json"
PRESCRIPTION_POLICY = PROJECT_ROOT / "data/normalized/goal_prescription_review_policy.json"
REPRESENTATIVE_DECISIONS = PROJECT_ROOT / "data/normalized/v2_representative_decisions.json"
FALLBACK_APPROVAL_MANIFEST = (
    PROJECT_ROOT / "data/reports/v2_0_6_catalog/stretch_strap_fallback_approval_manifest.json"
)
DEFAULT_TARGET = PROJECT_ROOT / "data/generated/exercise-catalog-v2.0.6-final/backend_bundle"

GENERATOR_VERSION = "v2-0-6-normalized-backend-projection-1.0.0"
BUNDLE_VERSION = "v2-0-6-backend-bundle-final-2026-09-04"
TECHNICAL_MEDIA_VERIFIED_AT = "2026-09-02T05:45:06.723100+00:00"
FORM_CUES_REVIEW_STATUS = "DOMAIN_APPROVED"
MEDIA_SET_VERSION = "media-set-v2.0.6"
ALTERNATIVE_SET_VERSION = "alternative-set-v2.0.6-stretch-strap-fallback"
RULE_SET_VERSION = "safety-rule-set-v2.0.6"
PRESCRIPTION_SET_VERSION = "prescription-set-v2.0.6"
ALTERNATIVE_RULE_VERSION = "alternative-rule-v2.0.6-stretch-strap-fallback"
SAFETY_RULE_VERSION = "v2.0.6-normalized-safety-1.0.0"
PRESCRIPTION_VERSION = "prescription-set-v2.0.6-normalized-1.0.0"
GENERATED_AT = "2026-09-04T00:00:00+09:00"

EXCLUDED_AUXILIARY_ARTIFACTS = [
    "data/normalized/home_equipment_substitution_guides_v1.jsonl",
    "data/normalized/dumbbell_bodyweight_variant_candidates_v1.jsonl",
    "data/normalized/foam_roller_bodyweight_variant_candidates_v1.jsonl",
    "data/normalized/resistance_band_bodyweight_variant_candidates_v1.jsonl",
    "data/normalized/stretch_strap_home_suitability_review_v1.jsonl",
    "data/reports/resistance_band_bodyweight_variant_gap_report_v1.json",
    "data/reports/home_equipment_substitution_guides_v1_validation.json",
]

BODY_AREA_MAP = {
    "ankle stabilizers": "ANKLE_FOOT",
    "ankles": "ANKLE_FOOT",
    "calves": "ANKLE_FOOT",
    "feet": "ANKLE_FOOT",
    "biceps": "ELBOW",
    "brachialis": "ELBOW",
    "forearms": "ELBOW",
    "triceps": "ELBOW",
    "hands": "WRIST_HAND",
    "wrists": "WRIST_HAND",
    "chest": "CHEST",
    "upper chest": "CHEST",
    "deltoids": "SHOULDER",
    "rear deltoids": "SHOULDER",
    "shoulders": "SHOULDER",
    "traps": "SHOULDER",
    "rhomboids": "UPPER_BACK",
    "upper back": "UPPER_BACK",
    "lower back": "LOWER_BACK",
    "glutes": "HIP",
    "groin": "HIP",
    "hip flexors": "HIP",
    "inner thighs": "HIP",
    "hamstrings": "KNEE",
    "quadriceps": "KNEE",
    "core": "ABDOMEN",
    "lower abs": "ABDOMEN",
    "obliques": "ABDOMEN",
    "sternocleidomastoid": "NECK",
}
BODY_AREA_CODES = set(BODY_AREA_MAP.values())
EQUIPMENT_MAP = {"ROPE": "STRETCH_STRAP"}
MEDIA_FILENAME_RE = re.compile(r"^(?P<identity>[0-9]{4})-[A-Za-z0-9]+\.gif$")

GOALS = ("FAT_LOSS", "GENERAL_FITNESS", "MUSCLE_GAIN")
MUSCLE_CORE_PATTERNS = {
    "HIP_DOMINANT",
    "KNEE_DOMINANT",
    "HORIZONTAL_PUSH",
    "HORIZONTAL_PULL",
    "VERTICAL_PUSH",
    "VERTICAL_PULL",
    "CORE_BRACE",
}
FAT_LOSS_CORE_PATTERNS = {
    "GAIT",
    "CYCLING",
    "ELLIPTICAL",
    "JUMP_PLYOMETRIC",
    "HIP_DOMINANT",
    "KNEE_DOMINANT",
    "HORIZONTAL_PUSH",
    "HORIZONTAL_PULL",
    "VERTICAL_PUSH",
    "VERTICAL_PULL",
}


class BundleBuildError(RuntimeError):
    """Raised when the normalized projection cannot be proven complete."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _int_or_none(value: str) -> int | None:
    return int(value) if value else None


def _bool(value: str) -> bool:
    if value not in {"True", "False", "true", "false"}:
        raise BundleBuildError(f"boolean field is invalid: {value}")
    return value.lower() == "true"


def _optional_bool(value: str) -> bool | None:
    return _bool(value) if value else None


def _recovery_policy() -> dict[str, bool]:
    try:
        payload = json.loads(REPRESENTATIVE_DECISIONS.read_text(encoding="utf-8"))
        policy = payload["runtime_materialization"]["recovery_eligible_by_training_type"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise BundleBuildError("approved recovery eligibility policy is invalid") from exc
    if set(policy) != {"STRENGTH", "CARDIO", "MOBILITY"} or not all(
        isinstance(value, bool) for value in policy.values()
    ):
        raise BundleBuildError("approved recovery eligibility policy is incomplete")
    return policy


def _codes(value: str) -> list[str]:
    return [item for item in value.split("|") if item]


def _mapped_body_areas(value: str) -> list[str]:
    mapped: list[str] = []
    for raw in _codes(value):
        area = BODY_AREA_MAP.get(raw.lower())
        if area is None:
            raise BundleBuildError(f"unmapped normalized body area: {raw}")
        if area not in mapped:
            mapped.append(area)
    return mapped


def _project_catalog(
    rows: list[dict[str, str]], recovery_policy: dict[str, bool]
) -> list[dict[str, Any]]:
    if len(rows) != 237:
        raise BundleBuildError(f"v2.0.6 normalized catalog must contain 237 rows: {len(rows)}")
    by_code = {row["stable_code"]: row for row in rows}
    if len(by_code) != len(rows) or any(not code for code in by_code):
        raise BundleBuildError("normalized stable_code values must be unique and non-empty")
    if len({row["source_identity"] for row in rows}) != len(rows):
        raise BundleBuildError("normalized source_identity values must be unique")

    projected: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: item["stable_code"]):
        if row["source_track"] != "gymvisual" or row["review_status_code"] != "DOMAIN_APPROVED":
            raise BundleBuildError(f"row is not approved Gymvisual input: {row['stable_code']}")
        primary = _mapped_body_areas(row["primary_body_area_codes"])
        secondary = [
            area
            for area in _mapped_body_areas(row["secondary_body_area_codes"])
            if area not in primary
        ]
        if not primary:
            safety_areas = _codes(row["safety_relevant_body_area_codes"])
            primary = [safety_areas[0]] if safety_areas else []
        if not primary or set(primary) & set(secondary):
            raise BundleBuildError(f"invalid projected body-area roles: {row['stable_code']}")
        equipment = [EQUIPMENT_MAP.get(code, code) for code in _codes(row["equipment_codes"])]
        if not equipment or len(equipment) != len(set(equipment)):
            raise BundleBuildError(f"invalid equipment codes: {row['stable_code']}")
        parent = row["representative_stable_code"] or None
        if row["record_type"] == "VARIANT" and parent not in by_code:
            raise BundleBuildError(f"variant parent is missing: {row['stable_code']}")
        if row["record_type"] != "VARIANT":
            parent = None
        recovery_value = (
            _bool(row["recovery_eligible"])
            if row["recovery_eligible"]
            else recovery_policy.get(row["training_type_code"])
        )
        if recovery_value is None:
            raise BundleBuildError(f"recovery eligibility is unavailable: {row['stable_code']}")
        projected.append(
            {
                "stable_code": row["stable_code"],
                "name_ko": row["name_ko"],
                "name_en": row["name_en"],
                "training_type_code": row["training_type_code"],
                "body_focus_code": row["body_focus_code"],
                "primary_movement_pattern_code": row["primary_movement_pattern_code"],
                "difficulty_code": row["difficulty_code"],
                "timing_mode_code": row["timing_mode_code"],
                "default_seconds_per_rep": _int_or_none(row["default_seconds_per_rep"]),
                "default_work_seconds": _int_or_none(row["default_work_seconds"]),
                "default_rest_seconds": int(row["default_rest_seconds"]),
                "default_transition_seconds": int(row["default_transition_seconds"]),
                "recovery_eligible": recovery_value,
                "primary_body_area_codes": primary,
                "secondary_body_area_codes": secondary,
                "equipment_codes": equipment,
                "location_codes": _codes(row["location_codes"]),
                "instruction_summary_ko": row["instruction_summary_ko"],
                "form_cues_ko": _codes(row["form_cues_ko"]),
                "instruction_content_version": row["instruction_content_version"],
                "review_status_code": row["review_status_code"],
                "source_track": row["source_track"],
                "source_identity": row["source_identity"],
                "record_type": row["record_type"],
                "family_code": row["family_code"],
                "representative_stable_code": parent,
                "general_pool_included": _optional_bool(row["general_pool_included"]),
                "form_cues_source": row["form_cues_source"],
                "form_cues_review_status": FORM_CUES_REVIEW_STATUS,
            }
        )
    return projected


def _media_review_metadata() -> dict[str, str]:
    approved = [
        row for row in _read_csv(MEDIA_REVIEW) if row.get("rights_review_status") == "APPROVED"
    ]
    if not approved:
        raise BundleBuildError("no approved Gymvisual media rights evidence exists")
    first = approved[0]
    for field in ("rights_reviewer", "rights_reviewed_at", "rights_evidence_reference"):
        if not first.get(field):
            raise BundleBuildError(f"media rights evidence is incomplete: {field}")
    return {
        field: first[field]
        for field in ("rights_reviewer", "rights_reviewed_at", "rights_evidence_reference")
    }


def _project_media(
    catalog: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    files: dict[str, str] = {}
    for path in MEDIA_DIRECTORY.iterdir():
        match = MEDIA_FILENAME_RE.fullmatch(path.name)
        if match:
            identity = match.group("identity")
            if identity in files:
                raise BundleBuildError(f"duplicate local GIF identity: {identity}")
            files[identity] = path.name
    if len(files) != 237:
        raise BundleBuildError(f"local GIF directory must contain 237 files: {len(files)}")
    rights = _media_review_metadata()
    media: list[dict[str, Any]] = []
    registry: list[dict[str, str]] = []
    for index, row in enumerate(catalog, start=1):
        filename = files.get(row["source_identity"])
        if filename is None:
            raise BundleBuildError(
                f"catalog source identity has no local GIF: {row['source_identity']}"
            )
        representative_id = f"REX-{index:06d}"
        registry.append(
            {"representative_exercise_id": representative_id, "stable_code": row["stable_code"]}
        )
        media.append(
            {
                "representative_exercise_id": representative_id,
                "s3_key": f"catalog-media/gymvisual/{row['stable_code']}/demo.gif",
                "media_status": "AVAILABLE",
                "rights_review_status": "APPROVED",
                "rights_reviewer": rights["rights_reviewer"],
                "rights_reviewed_at": rights["rights_reviewed_at"],
                "rights_evidence_reference": rights["rights_evidence_reference"],
                "source_metadata": {
                    "source_object_content_type": "image/gif",
                    "source_object_key": f"videos/{filename}",
                    "source_object_verified_at": TECHNICAL_MEDIA_VERIFIED_AT,
                },
            }
        )
    return media, registry


def _role(pattern: str, goal: str) -> str:
    if goal == "MUSCLE_GAIN":
        return "CORE" if pattern in MUSCLE_CORE_PATTERNS else "SUPPORT"
    if goal == "FAT_LOSS":
        return "CORE" if pattern in FAT_LOSS_CORE_PATTERNS else "SUPPORT"
    return "CORE" if pattern in MUSCLE_CORE_PATTERNS | FAT_LOSS_CORE_PATTERNS else "SUPPORT"


def _profile(
    row: dict[str, Any],
    goal: str,
    level: str,
    phase: str,
    sets: int,
    reps: int | None,
    work: int | None,
    rest: int,
    intensity: str,
) -> dict[str, Any]:
    return {
        "catalog_version_code": CATALOG_VERSION,
        "exercise_stable_code": row["stable_code"],
        "goal_code": goal,
        "experience_level_code": level,
        "phase_code": phase,
        "sets": sets,
        "reps": reps if row["timing_mode_code"] == "REPS" else None,
        "work_seconds_per_set": work if row["timing_mode_code"] == "DURATION" else None,
        "rest_seconds_per_set": rest,
        "intensity_code": intensity,
        "prescription_version": PRESCRIPTION_VERSION,
        "review_status_code": "DOMAIN_APPROVED",
    }


def _goal_and_prescriptions(
    catalog: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    links: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    for row in catalog:
        for goal in GOALS:
            links.append(
                {
                    "catalog_version_code": CATALOG_VERSION,
                    "exercise_stable_code": row["stable_code"],
                    "goal_code": goal,
                    "role_eligibility_code": _role(row["primary_movement_pattern_code"], goal),
                    "review_status_code": "DOMAIN_APPROVED",
                }
            )
            levels = (
                ["BEGINNER", "INTERMEDIATE"]
                if row["difficulty_code"] == "BEGINNER"
                else ["INTERMEDIATE"]
            )
            for level in levels:
                if row["training_type_code"] == "MOBILITY":
                    for phase, work in (("WARMUP", 60), ("COOLDOWN", 45)):
                        profiles.append(_profile(row, goal, level, phase, 1, None, work, 0, "LOW"))
                    continue
                beginner = level == "BEGINNER"
                if goal == "FAT_LOSS":
                    sets, reps, work, rest = (2, 12, None, 40) if beginner else (3, 12, None, 30)
                else:
                    sets, reps, work, rest = (2, 10, None, 60) if beginner else (3, 10, None, 75)
                if row["timing_mode_code"] == "DURATION":
                    work, reps = (60 if goal == "FAT_LOSS" else 45), None
                profiles.append(
                    _profile(row, goal, level, "MAIN", sets, reps, work, rest, "MODERATE")
                )
    links.sort(key=lambda item: (item["exercise_stable_code"], item["goal_code"]))
    profiles.sort(
        key=lambda item: (
            item["exercise_stable_code"],
            item["goal_code"],
            item["experience_level_code"],
            item["phase_code"],
        )
    )
    return links, profiles


def _safety_record(
    code: str,
    area: str,
    role: str,
    minimum: str,
    maximum: str,
    effect: str,
    reason: str,
    source_hash: str,
) -> dict[str, Any]:
    return {
        "body_area_code": area,
        "body_part_role_code": role,
        "catalog_version_code": CATALOG_VERSION,
        "effect_code": effect,
        "exercise_stable_code": code,
        "maximum_severity_code": maximum,
        "minimum_severity_code": minimum,
        "movement_pattern_code": None,
        "reason_code": reason,
        "review_status_code": "DOMAIN_APPROVED",
        "rule_scope": "EXERCISE",
        "rule_version": SAFETY_RULE_VERSION,
        "rule_set_version_code": RULE_SET_VERSION,
        "production_eligible": False,
        "source_manifest_hash": source_hash,
        "source_metadata": {
            "basis": "approved exercise safety rule policy and normalized safety-relevant areas",
            "reviewer_code": "PM_DIRECT_REVIEW",
        },
        "created_at": GENERATED_AT,
        "updated_at": GENERATED_AT,
    }


def _safety_rules(
    catalog: list[dict[str, Any]], raw_by_code: dict[str, dict[str, str]], source_hash: str
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for row in catalog:
        loaded = set(row["primary_body_area_codes"]) | set(row["secondary_body_area_codes"])
        loaded |= set(_codes(raw_by_code[row["stable_code"]]["safety_relevant_body_area_codes"]))
        primary = set(row["primary_body_area_codes"])
        for area in sorted(primary):
            rules.append(
                _safety_record(
                    row["stable_code"],
                    area,
                    "PRIMARY",
                    "MILD",
                    "SEVERE",
                    "EXCLUDE",
                    "DIRECT_JOINT_LOAD",
                    source_hash,
                )
            )
        for area in sorted(loaded - primary):
            rules.append(
                _safety_record(
                    row["stable_code"],
                    area,
                    "SECONDARY",
                    "MILD",
                    "MILD",
                    "CAUTION",
                    "STABILIZER_LOAD",
                    source_hash,
                )
            )
            rules.append(
                _safety_record(
                    row["stable_code"],
                    area,
                    "SECONDARY",
                    "MODERATE",
                    "SEVERE",
                    "EXCLUDE",
                    "STABILIZER_LOAD",
                    source_hash,
                )
            )
    rules.sort(
        key=lambda item: (
            item["exercise_stable_code"],
            item["body_area_code"],
            item["body_part_role_code"],
            item["minimum_severity_code"],
        )
    )
    return rules


def _fallbacks(source_hash: str) -> list[dict[str, Any]]:
    try:
        approval = json.loads(FALLBACK_APPROVAL_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleBuildError("stretch-strap fallback approval manifest is invalid") from exc
    if (
        approval.get("status") != "DOMAIN_APPROVED"
        or approval.get("production_eligible") is not False
        or approval.get("source_catalog_sha256") != source_hash
        or approval.get("alternative_policy") != "STRETCH_STRAP_TO_BODYWEIGHT_ONLY"
    ):
        raise BundleBuildError("stretch-strap fallback approval does not match the catalog")
    pairs = tuple(
        (record.get("source_exercise_stable_code"), record.get("alternative_exercise_stable_code"))
        for record in approval.get("records", [])
        if record.get("reason_code") == "EQUIPMENT"
        and record.get("goal_preservation_code") == "SAME_GOAL"
    )
    if len(pairs) != 1 or any(not source or not target for source, target in pairs):
        raise BundleBuildError("exactly one approved stretch-strap fallback is required")
    return [
        {
            "alternative_catalog_version_code": CATALOG_VERSION,
            "alternative_exercise_stable_code": target,
            "created_at": GENERATED_AT,
            "difficulty_delta": 0,
            "goal_preservation_code": "SAME_GOAL",
            "reason_code": "EQUIPMENT",
            "review_method_code": "DOMAIN_REVIEWER",
            "review_status_code": "DOMAIN_APPROVED",
            "rule_version": ALTERNATIVE_RULE_VERSION,
            "source_catalog_version_code": CATALOG_VERSION,
            "source_exercise_stable_code": source,
            "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
            "alternative_set_version_code": ALTERNATIVE_SET_VERSION,
            "production_eligible": False,
            "source_manifest_hash": source_hash,
            "source_metadata": {
                "basis": "approved importer fallback gate",
                "reviewer_code": "PM_DIRECT_REVIEW",
                "policy": "STRETCH_STRAP_TO_BODYWEIGHT_ONLY",
            },
            "updated_at": GENERATED_AT,
        }
        for source, target in pairs
    ]


def _manifest_file(path: Path, root: Path, records: int) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "records": records,
    }


def _review() -> dict[str, Any]:
    return {
        "status": "DOMAIN_APPROVED",
        "review_method_code": "DOMAIN_REVIEWER",
        "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
        "production_eligible": False,
    }


def _write_registry(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("representative_exercise_id", "stable_code"), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def build(*, target: Path = DEFAULT_TARGET) -> dict[str, Any]:
    raw_rows = _read_csv(NORMALIZED_CATALOG)
    raw_by_code = {row["stable_code"]: row for row in raw_rows}
    recovery_policy = _recovery_policy()
    catalog = _project_catalog(raw_rows, recovery_policy)
    media, registry = _project_media(catalog)
    source_hash = _sha256(NORMALIZED_CATALOG)
    links, profiles = _goal_and_prescriptions(catalog)
    safety = _safety_rules(catalog, raw_by_code, source_hash)
    alternatives = _fallbacks(source_hash)
    codes = {row["stable_code"] for row in catalog}
    if any(
        record["source_exercise_stable_code"] not in codes
        or record["alternative_exercise_stable_code"] not in codes
        for record in alternatives
    ):
        raise BundleBuildError("fallback relation references a missing catalog code")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    catalog_root = target / "catalog"
    _write_jsonl(catalog_root / "exercises.jsonl", catalog)
    registry_path = catalog_root / "input/representative_exercises.csv"
    _write_registry(registry_path, registry)
    _write_json(
        catalog_root / "seed_manifest.json",
        {
            "schema_version": "1.1",
            "generator_version": GENERATOR_VERSION,
            "catalog_version": {"version_code": CATALOG_VERSION, "status_code": "DRAFT"},
            "source": {
                "track": "gymvisual",
                "review_batch_directory": "data/reports",
                "taxonomy_registry_sha256": _sha256(TAXONOMY_REGISTRY),
                "input_artifacts": [
                    {
                        "role": "representative_catalog_csv",
                        "path": "input/representative_exercises.csv",
                        "sha256": _sha256(registry_path),
                        "bytes": registry_path.stat().st_size,
                    },
                    {
                        "role": "recovery_eligibility_policy",
                        "path": str(REPRESENTATIVE_DECISIONS.relative_to(PROJECT_ROOT)),
                        "sha256": _sha256(REPRESENTATIVE_DECISIONS),
                        "bytes": REPRESENTATIVE_DECISIONS.stat().st_size,
                    },
                ],
            },
            "review": _review(),
            "summary": {"exercise_records": len(catalog)},
            "files": [_manifest_file(catalog_root / "exercises.jsonl", catalog_root, len(catalog))],
        },
    )

    safety_root = target / "safety"
    _write_jsonl(safety_root / "safety_rules.jsonl", safety)
    _write_json(
        safety_root / "rules_manifest.json",
        {
            "schema_version": "1.0",
            "generator_version": GENERATOR_VERSION,
            "rule_set_version": {"version_code": RULE_SET_VERSION, "status_code": "DRAFT"},
            "source": {
                "catalog_version_code": CATALOG_VERSION,
                "catalog_sha256": source_hash,
                "policy_path": str(SAFETY_POLICY.relative_to(PROJECT_ROOT)),
                "policy_sha256": _sha256(SAFETY_POLICY),
            },
            "review": _review(),
            "summary": {
                "rule_records": len(safety),
                "exercise_records": len(catalog),
                "pattern_scope_rules": 0,
                "exercise_scope_rules": len(safety),
            },
            "files": [_manifest_file(safety_root / "safety_rules.jsonl", safety_root, len(safety))],
        },
    )

    alternative_root = target / "alternatives"
    _write_jsonl(alternative_root / "alternatives.jsonl", alternatives)
    conflict_report = alternative_root / "input/alternative_projection_conflicts.json"
    _write_json(
        conflict_report,
        {
            "conflict_count": 0,
            "conflicts": [],
            "importer_record_count": len(alternatives),
            "production_eligible": False,
            "projection_status": "DIRECT",
            "runtime_record_count": len(alternatives),
            "status": "DRAFT",
        },
    )
    _write_json(
        alternative_root / "alternatives_manifest.json",
        {
            "schema_version": "1.0",
            "generator_version": GENERATOR_VERSION,
            "alternative_set_version": {
                "version_code": ALTERNATIVE_SET_VERSION,
                "status_code": "DRAFT",
            },
            "source": {
                "catalog_version_code": CATALOG_VERSION,
                "catalog_sha256": source_hash,
                "fallback_policy": "STRETCH_STRAP_TO_BODYWEIGHT_ONLY",
                "input_artifacts": [
                    {
                        "role": "fallback_approval_manifest",
                        "path": str(FALLBACK_APPROVAL_MANIFEST.relative_to(PROJECT_ROOT)),
                        "sha256": _sha256(FALLBACK_APPROVAL_MANIFEST),
                        "bytes": FALLBACK_APPROVAL_MANIFEST.stat().st_size,
                    }
                ],
            },
            "review": _review(),
            "summary": {"alternative_records": len(alternatives)},
            "files": [
                _manifest_file(
                    alternative_root / "alternatives.jsonl", alternative_root, len(alternatives)
                )
            ],
        },
    )

    prescription_root = target / "prescriptions"
    _write_jsonl(prescription_root / "goal_tag_links.jsonl", links)
    _write_jsonl(prescription_root / "prescription_profiles.jsonl", profiles)
    _write_json(
        prescription_root / "prescription_manifest.json",
        {
            "schema_version": "1.0",
            "generator_version": GENERATOR_VERSION,
            "prescription_set_version": {
                "version_code": PRESCRIPTION_SET_VERSION,
                "status_code": "DRAFT",
            },
            "source": {
                "catalog_version_code": CATALOG_VERSION,
                "catalog_sha256": source_hash,
                "policy_path": str(PRESCRIPTION_POLICY.relative_to(PROJECT_ROOT)),
                "policy_sha256": _sha256(PRESCRIPTION_POLICY),
                "input_artifacts": [],
            },
            "review": _review(),
            "summary": {
                "exercise_records": len(catalog),
                "goal_tag_records": len(links),
                "prescription_records": len(profiles),
            },
            "files": [
                _manifest_file(
                    prescription_root / "goal_tag_links.jsonl", prescription_root, len(links)
                ),
                _manifest_file(
                    prescription_root / "prescription_profiles.jsonl",
                    prescription_root,
                    len(profiles),
                ),
            ],
        },
    )

    media_root = target / "media"
    _write_jsonl(media_root / "media_assets.jsonl", media)
    _write_json(
        media_root / "media_manifest.json",
        {
            "schema_version": "1.0",
            "generator_version": GENERATOR_VERSION,
            "media_set_version": {"version_code": MEDIA_SET_VERSION, "status_code": "DRAFT"},
            "catalog_version_code": CATALOG_VERSION,
            "source": {
                "catalog_version_code": CATALOG_VERSION,
                "matching_rule": "exact normalized source_identity to data/media/videos filename",
                "source_catalog_sha256": source_hash,
                "input_artifacts": [
                    {
                        "role": "GYMVISUAL_MEDIA_REVIEW",
                        "path": "data/validation/review_results/gymvisual_media_reviewed.csv",
                        "sha256": _sha256(MEDIA_REVIEW),
                        "bytes": MEDIA_REVIEW.stat().st_size,
                    }
                ],
            },
            "review": _review(),
            "summary": {"media_asset_records": len(media)},
            "files": [_manifest_file(media_root / "media_assets.jsonl", media_root, len(media))],
        },
    )

    audit_rows = [
        {
            "stable_code": row["stable_code"],
            "source_identity": row["source_identity"],
            "source_track": row["source_track"],
            "projection": "NORMALIZED_TO_V2_BACKEND",
            "review_status_code": row["review_status_code"],
            "production_eligible": False,
        }
        for row in catalog
    ]
    _write_jsonl(target / "audit/projection_audit.jsonl", audit_rows)

    bundle_path = target / "bundle_manifest.json"
    bundle = {
        "schema_version": "1.0",
        "bundle_version": BUNDLE_VERSION,
        "catalog_version_code": CATALOG_VERSION,
        "derived_set_versions": {
            "alternative_set_version_code": ALTERNATIVE_SET_VERSION,
            "prescription_set_version_code": PRESCRIPTION_SET_VERSION,
            "rule_set_version_code": RULE_SET_VERSION,
        },
        "derived_from": {
            "catalog_source_path": str(NORMALIZED_CATALOG.relative_to(PROJECT_ROOT)),
            "catalog_source_sha256": source_hash,
            "catalog_source_records": len(catalog),
            "generator_version": GENERATOR_VERSION,
            "change_summary": (
                "Direct 237-row normalized v2.0.6 backend projection with importer-required "
                "stretch-strap fallbacks."
            ),
        },
        "importer_paths": {
            "alternatives": "alternatives/alternatives_manifest.json",
            "catalog": "catalog/seed_manifest.json",
            "media": "media/media_manifest.json",
            "prescriptions": "prescriptions/prescription_manifest.json",
            "safety": "safety/rules_manifest.json",
        },
        "production_eligible": False,
        "status_code": "DRAFT",
        "summary": {
            "alternative_records": len(alternatives),
            "catalog_records": len(catalog),
            "goal_tag_records": len(links),
            "media_asset_records": len(media),
            "prescription_records": len(profiles),
            "safety_rule_records": len(safety),
        },
        "projection": {
            "status": "DIRECT",
            "media_coverage": "EXACT_ALL_CATALOG_RECORDS",
            "runtime_alternative_records": len(alternatives),
            "importer_alternative_records": len(alternatives),
            "alternative_conflict_count": 0,
            "conflict_report_path": "alternatives/input/alternative_projection_conflicts.json",
            "fallback_policy": "STRETCH_STRAP_TO_BODYWEIGHT_ONLY",
        },
        "input_policy": {
            "canonical_catalog_source": "data/normalized/v2_0_6_exercise_catalog.csv",
            "excluded_auxiliary_artifacts": EXCLUDED_AUXILIARY_ARTIFACTS,
            "excluded_reason": (
                "household substitutions, cautions, and replacement exercises are not "
                "stored in equipment descriptions or alternatives"
            ),
        },
    }
    _write_json(bundle_path, bundle)
    files: list[dict[str, Any]] = []
    for path in sorted(target.rglob("*")):
        if not path.is_file() or path == bundle_path:
            continue
        entry: dict[str, Any] = {
            "path": path.relative_to(target).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        if path.suffix == ".jsonl":
            entry["records"] = sum(
                1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
            )
        files.append(entry)
    bundle["files"] = files
    _write_json(bundle_path, bundle)
    return {
        "catalog_version_code": CATALOG_VERSION,
        "catalog_records": len(catalog),
        "media_asset_records": len(media),
        "alternative_records": len(alternatives),
        "goal_tag_records": len(links),
        "prescription_records": len(profiles),
        "safety_rule_records": len(safety),
        "bundle_manifest_sha256": _sha256(bundle_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    print(json.dumps(build(target=args.target), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
