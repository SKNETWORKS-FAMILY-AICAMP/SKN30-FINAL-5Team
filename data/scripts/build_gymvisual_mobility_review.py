"""Build CSV review batches from the Gym Visual mobility profile."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = REPO_ROOT / "data/validation/profiles/gymvisual_mobility_profile.json"
DEFAULT_BATCH = REPO_ROOT / "data/validation/review_batches/gymvisual_mobility_review.csv"
DEFAULT_RESULTS = REPO_ROOT / "data/validation/review_results/gymvisual_mobility_reviewed.csv"
DEFAULT_MANIFEST = (
    REPO_ROOT / "data/validation/review_batches/gymvisual_mobility_review_manifest.json"
)
REVIEW_BATCH_VERSION = "gymvisual-mobility-review-v0.1.0"

REVIEW_COLUMNS = [
    "candidate_id",
    "source_name",
    "source_body_part",
    "source_target",
    "source_equipment",
    "mobility_goal_code",
    "body_area_codes_candidate",
    "training_type_code_candidate",
    "movement_pattern_code_candidate",
    "exercise_family_candidate",
    "variant_group_candidate",
    "selection_rank",
    "difficulty_code_candidate",
    "beginner_suitability_candidate",
    "equipment_code_candidate",
    "location_code_candidates",
    "load_profile_candidate",
    "selection_screening_decision",
    "review_required_codes",
    "alternative_relation_status",
    "source_media_id",
    "source_image",
    "source_gif_url",
    "review_decision",
    "review_family_code",
    "review_variant_group",
    "review_reason_code",
    "review_note",
    "reviewer",
    "reviewed_at",
]


class ReviewBatchError(ValueError):
    """Fail-closed review batch error."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewBatchError(f"invalid JSON: {path}") from exc


def relative_path(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def load_profile(path: Path) -> dict[str, Any]:
    profile = load_json(path)
    if not isinstance(profile, dict) or profile.get("status") != "DRAFT_REVIEW_QUEUE":
        raise ReviewBatchError("mobility profile is not a DRAFT_REVIEW_QUEUE")
    if profile.get("production_eligible") is not False:
        raise ReviewBatchError("mobility profile must be production-ineligible")
    candidates = profile.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ReviewBatchError("mobility profile has no candidates")
    return profile


def row_from_candidate(candidate: dict[str, Any], *, pending: bool) -> dict[str, str]:
    def joined(value: Any) -> str:
        if isinstance(value, list):
            return "|".join(str(item) for item in value)
        return str(value or "")

    row = {
        "candidate_id": str(candidate["candidate_id"]),
        "source_name": str(candidate["source_name"]),
        "source_body_part": str(candidate["source_body_part"]),
        "source_target": str(candidate["source_target"]),
        "source_equipment": str(candidate["source_equipment"]),
        "mobility_goal_code": str(candidate["mobility_goal_code"]),
        "body_area_codes_candidate": joined(candidate["body_area_codes_candidate"]),
        "training_type_code_candidate": str(candidate["training_type_code_candidate"]),
        "movement_pattern_code_candidate": str(candidate["movement_pattern_code_candidate"]),
        "exercise_family_candidate": str(candidate["exercise_family_candidate"]),
        "variant_group_candidate": str(candidate["variant_group_candidate"]),
        "selection_rank": str(candidate["selection_rank"]),
        "difficulty_code_candidate": str(candidate["difficulty_code_candidate"]),
        "beginner_suitability_candidate": str(candidate["beginner_suitability_candidate"]),
        "equipment_code_candidate": str(candidate["equipment_code_candidate"]),
        "location_code_candidates": joined(candidate["location_code_candidates"]),
        "load_profile_candidate": str(candidate["load_profile_candidate"]),
        "selection_screening_decision": str(candidate["screening_decision"]),
        "review_required_codes": joined(candidate["review_required_codes"]),
        "alternative_relation_status": str(candidate["alternative_relation_status"]),
        "source_media_id": str(candidate.get("source_media_id", "")),
        "source_image": str(candidate.get("source_image", "")),
        "source_gif_url": str(candidate.get("source_gif_url", "")),
        "review_decision": "PENDING" if pending else "",
        "review_family_code": "",
        "review_variant_group": "",
        "review_reason_code": "",
        "review_note": "",
        "reviewer": "",
        "reviewed_at": "",
    }
    return row


def build_rows(profile: dict[str, Any], *, pending: bool = False) -> list[dict[str, str]]:
    rows = [row_from_candidate(candidate, pending=pending) for candidate in profile["candidates"]]
    if len({row["candidate_id"] for row in rows}) != len(rows):
        raise ReviewBatchError("review batch contains duplicate candidate IDs")
    if any(row["alternative_relation_status"] != "NOT_CREATED_BY_DESIGN" for row in rows):
        raise ReviewBatchError("mobility review batch must not contain alternative relations")
    return sorted(
        rows,
        key=lambda row: (
            row["mobility_goal_code"],
            int(row["selection_rank"]),
            row["candidate_id"],
        ),
    )


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def build_manifest(
    profile_path: Path, batch_path: Path, results_path: Path, rows: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "review_batch_version": REVIEW_BATCH_VERSION,
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "purpose": (
            "mobility/stretch candidate, family and variant review; "
            "not a catalog seed or alternative set"
        ),
        "source": {
            "profile": relative_path(profile_path),
            "profile_sha256": sha256_file(profile_path),
        },
        "artifacts": {
            "review_batch": {
                "path": relative_path(batch_path),
                "sha256": sha256_file(batch_path),
                "records": len(rows),
            },
            "review_results_template": {
                "path": relative_path(results_path),
                "sha256": sha256_file(results_path),
                "records": len(rows),
            },
        },
        "review_guards": [
            "FAMILY_VARIANT_IS_NOT_ALTERNATIVE",
            "DO_NOT_CREATE_SQUAT_TO_QUADRICEPS_STRETCH_ALTERNATIVE",
            "REQUIRE_DOMAIN_SAFETY_REVIEW_BEFORE_GENERATED_OUTPUT",
            "REQUIRE_LOAD_PROFILE_REVIEW",
        ],
        "review_columns": REVIEW_COLUMNS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--review-batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--review-results-template", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        profile = load_profile(args.profile)
        rows = build_rows(profile)
        pending_rows = build_rows(profile, pending=True)
        write_csv(args.review_batch, rows)
        write_csv(args.review_results_template, pending_rows)
        manifest = build_manifest(
            args.profile, args.review_batch, args.review_results_template, rows
        )
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except (OSError, ReviewBatchError, KeyError, TypeError, ValueError) as exc:
        print(f"failed: {exc}")
        return 1
    print(
        json.dumps(
            {"status": "built", "review_batch": str(args.review_batch), "records": len(rows)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
