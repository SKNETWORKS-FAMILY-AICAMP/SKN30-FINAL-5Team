"""Build a fail-closed review queue for cross-source Gymvisual media candidates.

This artifact is advisory only. A name match does not transfer source provenance,
so every row remains ineligible for production until a reviewer confirms that
the source exercise and the Gymvisual demonstration are the same movement.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = (
    PROJECT_ROOT
    / "data/generated/exercise-catalog-v2.0.4-final/backend_bundle/catalog/exercises.jsonl"
)
REGISTRY_PATH = (
    PROJECT_ROOT
    / "data/generated/exercise-catalog-v2.0.4-final"
    / "backend_bundle/catalog/input/representative_exercises.csv"
)
GYMVISUAL_PATH = PROJECT_ROOT / "data/raw/gym_visual/exercises.json"
OUTPUT_DIR = PROJECT_ROOT / "data/validation/review_batches/gymvisual-cross-source-media-v0.1.0"

FIELDNAMES = (
    "representative_exercise_id",
    "stable_code",
    "catalog_name_en",
    "catalog_name_ko",
    "catalog_source_track",
    "catalog_source_identity",
    "catalog_equipment_codes",
    "catalog_movement_pattern_code",
    "gymvisual_source_identity",
    "gymvisual_name",
    "gymvisual_equipment",
    "gymvisual_body_part",
    "gymvisual_target",
    "gymvisual_gif_url",
    "candidate_classification",
    "review_reason",
    "review_status",
    "automatic_binding",
    "production_eligible",
)

# Deliberately small, evidence-backed candidate set. These values identify
# review work; they do not authorize media reuse for another source record.
CANDIDATES = (
    {
        "representative_exercise_id": "REX-000061",
        "gymvisual_source_identity": "0549",
        "candidate_classification": "EXACT_NAME_EQUIPMENT_MOVEMENT_CANDIDATE",
        "review_reason": (
            "Kettlebell swing name and kettlebell/hip-dominant movement align; "
            "review execution details before changing Wger provenance."
        ),
    },
    {
        "representative_exercise_id": "REX-000093",
        "gymvisual_source_identity": "0043",
        "candidate_classification": "EXACT_NAME_EQUIPMENT_MOVEMENT_CANDIDATE",
        "review_reason": (
            "Barbell full squat name and barbell/knee-dominant movement align; "
            "review bar position, depth, and execution before binding."
        ),
    },
    {
        "representative_exercise_id": "REX-000049",
        "gymvisual_source_identity": "0576",
        "candidate_classification": "AMBIGUOUS_DUPLICATE_MEDIA_CANDIDATE",
        "review_reason": (
            "Lever chest press matches the broad catalog label, but Gymvisual has "
            "two same-name demonstrations and the Wger aggregate has three sources."
        ),
    },
    {
        "representative_exercise_id": "REX-000049",
        "gymvisual_source_identity": "0577",
        "candidate_classification": "AMBIGUOUS_DUPLICATE_MEDIA_CANDIDATE",
        "review_reason": (
            "Lever chest press matches the broad catalog label, but Gymvisual has "
            "two same-name demonstrations and the Wger aggregate has three sources."
        ),
    },
    {
        "representative_exercise_id": "REX-000041",
        "gymvisual_source_identity": "0739",
        "candidate_classification": "EQUIPMENT_AND_VIEWPOINT_REVIEW_REQUIRED",
        "review_reason": (
            "Leg press is a broad label; confirm machine geometry, stance, and target "
            "against Wger 371 before selecting any demonstration."
        ),
    },
    {
        "representative_exercise_id": "REX-000041",
        "gymvisual_source_identity": "1463",
        "candidate_classification": "EQUIPMENT_AND_VIEWPOINT_REVIEW_REQUIRED",
        "review_reason": (
            "Side-view sled leg press is plausible, but source equipment and execution "
            "must be compared with Wger 371."
        ),
    },
    {
        "representative_exercise_id": "REX-000041",
        "gymvisual_source_identity": "1464",
        "candidate_classification": "EQUIPMENT_AND_VIEWPOINT_REVIEW_REQUIRED",
        "review_reason": (
            "Back-view sled leg press is plausible, but its viewpoint may not show the "
            "form cues required for this catalog exercise."
        ),
    },
    {
        "representative_exercise_id": "REX-000041",
        "gymvisual_source_identity": "2287",
        "candidate_classification": "MOVEMENT_VARIANT_REVIEW_REQUIRED",
        "review_reason": (
            "Alternate leg press is unilateral/alternating and must not be treated as "
            "the generic bilateral leg press without domain review."
        ),
    },
)


class ReviewBuildError(RuntimeError):
    """Raised when a declared candidate cannot be proven from source artifacts."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _read_registry(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {row["representative_exercise_id"]: row["stable_code"] for row in rows}


def build(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    catalog = {row["stable_code"]: row for row in _read_jsonl(CATALOG_PATH)}
    registry = _read_registry(REGISTRY_PATH)
    gymvisual = {
        str(row["id"]).zfill(4): row
        for row in json.loads(GYMVISUAL_PATH.read_text(encoding="utf-8"))
    }

    output_rows: list[dict[str, str]] = []
    for declared in CANDIDATES:
        exercise_id = declared["representative_exercise_id"]
        stable_code = registry.get(exercise_id)
        exercise = catalog.get(stable_code or "")
        source_identity = declared["gymvisual_source_identity"]
        candidate = gymvisual.get(source_identity)
        if exercise is None or candidate is None:
            raise ReviewBuildError(f"candidate source is missing: {exercise_id}/{source_identity}")
        if exercise.get("source_track") == "gymvisual":
            raise ReviewBuildError(
                f"cross-source queue contains Gymvisual catalog row: {exercise_id}"
            )

        output_rows.append(
            {
                "representative_exercise_id": exercise_id,
                "stable_code": stable_code or "",
                "catalog_name_en": str(exercise.get("name_en", "")),
                "catalog_name_ko": str(exercise.get("name_ko", "")),
                "catalog_source_track": str(exercise.get("source_track", "")),
                "catalog_source_identity": str(exercise.get("source_identity", "")),
                "catalog_equipment_codes": "|".join(exercise.get("equipment_codes", [])),
                "catalog_movement_pattern_code": str(
                    exercise.get("primary_movement_pattern_code", "")
                ),
                "gymvisual_source_identity": source_identity,
                "gymvisual_name": str(candidate.get("name", "")),
                "gymvisual_equipment": str(candidate.get("equipment", "")),
                "gymvisual_body_part": str(candidate.get("body_part", "")),
                "gymvisual_target": str(candidate.get("target", "")),
                "gymvisual_gif_url": str(candidate.get("gif_url", "")),
                "candidate_classification": declared["candidate_classification"],
                "review_reason": declared["review_reason"],
                "review_status": "REVIEW_REQUIRED",
                "automatic_binding": "false",
                "production_eligible": "false",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "cross_source_media_candidates.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    exact_count = sum(
        row["candidate_classification"] == "EXACT_NAME_EQUIPMENT_MOVEMENT_CANDIDATE"
        for row in output_rows
    )
    manifest = {
        "artifact_version": "gymvisual-cross-source-media-v0.1.0",
        "decision": "REVIEW_ONLY_NO_AUTOMATIC_BINDING",
        "inputs": [
            {
                "path": str(CATALOG_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": _sha256(CATALOG_PATH),
            },
            {
                "path": str(REGISTRY_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": _sha256(REGISTRY_PATH),
            },
            {
                "path": str(GYMVISUAL_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": _sha256(GYMVISUAL_PATH),
            },
        ],
        "output": {
            "candidate_rows": len(output_rows),
            "catalog_exercises": len({row["representative_exercise_id"] for row in output_rows}),
            "exact_match_candidates": exact_count,
            "review_required_candidates": len(output_rows) - exact_count,
            "path": str(csv_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "sha256": _sha256(csv_path),
        },
        "production_eligible": False,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
