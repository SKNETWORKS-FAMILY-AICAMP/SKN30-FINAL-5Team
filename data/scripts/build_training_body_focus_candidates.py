"""Build review-only training type and body focus candidates.

The output is an audit queue.  It never mutates the merged catalog and never
promotes a candidate to a domain-approved value.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / (
    "data/generated/exercise-catalog-v2.0.6-draft/review_catalog/exercise_catalog_merged_draft.json"
)
DEFAULT_ADDITIONS = DEFAULT_CATALOG.parent / "exercise_catalog_additions.json"
DEFAULT_RAW_GYMVISUAL = PROJECT_ROOT / "data/raw/gym_visual/exercises.json"
DEFAULT_OUTPUT = DEFAULT_CATALOG.parent / "training_body_focus_candidates.jsonl"

ALLOWED_TRAINING_TYPES = {"STRENGTH", "CARDIO", "MOBILITY"}
ALLOWED_BODY_FOCUS = {
    "ADDUCTORS",
    "CHEST",
    "BACK",
    "SHOULDERS",
    "BICEPS",
    "TRICEPS",
    "FOREARMS",
    "GLUTES",
    "QUADRICEPS",
    "HAMSTRINGS",
    "CALVES",
    "CORE",
    "FULL_BODY",
    "CARDIO",
    "MOBILITY",
}

REQUIRED_OUTPUT_FIELDS = (
    "stable_code",
    "source_track",
    "source_identity",
    "name_ko",
    "name_en",
    "source_category",
    "source_target",
    "source_muscle_group",
    "source_secondary_muscles",
    "source_instruction",
    "current_training_type_code",
    "training_type_code_candidate",
    "training_type_review_status",
    "training_type_reason_codes",
    "current_body_focus_code",
    "body_focus_code_candidate",
    "body_focus_review_status",
    "body_focus_reason_codes",
    "evidence_fields",
    "conflict_codes",
)

RESISTANCE_EQUIPMENT = {
    "assisted",
    "band",
    "barbell",
    "cable",
    "dumbbell",
    "kettlebell",
    "leverage machine",
    "resistance band",
    "roller",
    "rope",
    "sled machine",
    "smith machine",
    "weighted",
}

STRENGTH_NAME_RE = re.compile(
    r"\b(?:bench|row|pull[- ]?up|push[- ]?up|squat|squats|deadlift|curl|curls|"
    r"raise|raises|press|presses|dip|dips|lunge|lunges|fly|flies|pullover|shrug|"
    r"plank|planks|crunch|crunches|sit[- ]?up|bridge|bridges|hip thrust|kickback|"
    r"extension|extensions|calf|leg press|good morning|pulldown|pull down|push|pull|"
    r"squeeze)\b",
    re.IGNORECASE,
)
MOBILITY_RE = re.compile(
    r"\b(?:stretch(?:ing)?|mobility|flexibility|yoga|circle(?:s)?|rotation(?:s)?|rotate(?:d|s|ing)?|"
    r"range of motion)\b",
    re.IGNORECASE,
)

TARGET_TO_BODY = {
    "pectorals": "CHEST",
    "chest": "CHEST",
    "lats": "BACK",
    "upper back": "BACK",
    "back": "BACK",
    "traps": "BACK",
    "trapezius": "BACK",
    "delts": "SHOULDERS",
    "deltoids": "SHOULDERS",
    "shoulders": "SHOULDERS",
    "biceps": "BICEPS",
    "triceps": "TRICEPS",
    "forearms": "FOREARMS",
    "glutes": "GLUTES",
    "quads": "QUADRICEPS",
    "quadriceps": "QUADRICEPS",
    "hamstrings": "HAMSTRINGS",
    "calves": "CALVES",
    "abs": "CORE",
    "abdominals": "CORE",
    "abdominal": "CORE",
}
MUSCLE_TO_BODY = {
    "chest": "CHEST",
    "shoulders": "SHOULDERS",
    "deltoids": "SHOULDERS",
    "biceps": "BICEPS",
    "triceps": "TRICEPS",
    "forearms": "FOREARMS",
    "glutes": "GLUTES",
    "quadriceps": "QUADRICEPS",
    "hamstrings": "HAMSTRINGS",
    "calves": "CALVES",
    "traps": "BACK",
    "trapezius": "BACK",
    "core": "CORE",
}
CATEGORY_BODY = {
    "chest": {"CHEST"},
    "back": {"BACK"},
    "shoulders": {"SHOULDERS"},
    "upper arms": {"BICEPS", "TRICEPS"},
    "lower legs": {"CALVES"},
    "waist": {"CORE"},
    "upper legs": {"GLUTES", "QUADRICEPS", "HAMSTRINGS"},
}


class CandidateBuildError(ValueError):
    """Raised when an input violates the candidate artifact contract."""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateBuildError(f"cannot read JSON: {path}") from exc


def _rows(value: Any, path: Path) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise CandidateBuildError(f"expected an array of objects: {path}")
    return value


def _source_instruction(source: dict[str, Any]) -> str | None:
    value = source.get("instructions_ko")
    if isinstance(value, str) and value.strip():
        return value.strip()
    instructions = source.get("instructions")
    if isinstance(instructions, dict):
        value = instructions.get("ko")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _source_record(
    row: dict[str, Any],
    additions: dict[str, dict[str, Any]],
    raw_gymvisual: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    identity = row.get("source_identity")
    if not isinstance(identity, str) or not identity:
        return None
    # Additions are authoritative for their exact IDs.  Existing Gymvisual
    # rows are resolved by exact ID as well; names are never used as a key.
    return additions.get(identity) or raw_gymvisual.get(identity)


def _text_evidence(
    source: dict[str, Any] | None, row: dict[str, Any]
) -> tuple[str, str, list[str]]:
    if source is not None:
        instruction = _source_instruction(source) or ""
        name = str(source.get("name") or row.get("name_en") or "")
        target = str(source.get("target") or "").strip().lower()
        muscle = str(source.get("muscle_group") or "").strip().lower()
        category = str(source.get("category") or "").strip().lower()
        evidence = []
        if instruction:
            evidence.append("source_instruction")
        if name:
            evidence.append("name_en")
        if target:
            evidence.append("source_target")
        if muscle:
            evidence.append("source_muscle_group")
        if category:
            evidence.append("source_category")
        return f"{instruction} {name}".strip(), target, evidence
    return (
        " ".join(str(row.get(key) or "") for key in ("instruction_summary_ko", "name_en")),
        "",
        [],
    )


def _classify_training(
    source: dict[str, Any] | None, row: dict[str, Any]
) -> tuple[str | None, str, list[str], list[str]]:
    text, target, evidence = _text_evidence(source, row)
    category = str(source.get("category") or "").strip().lower() if source else ""
    equipment = str(source.get("equipment") or "").strip().lower() if source else ""
    equipment_strength_signal = (
        bool(RESISTANCE_EQUIPMENT.intersection({equipment})) and category != "cardio"
    )
    strength_signal = equipment_strength_signal or bool(STRENGTH_NAME_RE.search(text))
    cardio_signal = category == "cardio" or target == "cardiovascular system"
    mobility_signal = bool(MOBILITY_RE.search(text))
    reasons: list[str] = []
    conflicts: list[str] = []

    if cardio_signal and strength_signal:
        conflicts.append("MIXED_CARDIO_STRENGTH")
    if cardio_signal and mobility_signal:
        conflicts.append("MIXED_CARDIO_MOBILITY")
    if mobility_signal and strength_signal:
        conflicts.append("MIXED_MOBILITY_STRENGTH")
    if conflicts:
        return None, "REVIEW_REQUIRED", ["AMBIGUOUS_COMPOSITE_MOVEMENT"], conflicts
    if cardio_signal:
        return "CARDIO", "REVIEW_REQUIRED", ["CARDIO_REVIEW_REQUIRED"], conflicts
    if mobility_signal:
        return "MOBILITY", "REVIEW_REQUIRED", ["MOBILITY_REVIEW_REQUIRED"], conflicts
    if strength_signal:
        reasons.append("RESISTANCE_OR_RESISTED_MOVEMENT")
        if equipment in RESISTANCE_EQUIPMENT:
            reasons.append("RESISTANCE_EQUIPMENT_PRESENT")
        return "STRENGTH", "CANDIDATE_READY", reasons, conflicts
    if not evidence:
        reasons.append("SOURCE_EVIDENCE_MISSING")
    else:
        reasons.append("TRAINING_TYPE_NOT_DETERMINED")
    return None, "REVIEW_REQUIRED", reasons, conflicts


def _classify_body(
    source: dict[str, Any] | None,
    row: dict[str, Any],
    training_candidate: str | None,
) -> tuple[str | None, str, list[str], list[str]]:
    if training_candidate == "CARDIO":
        return "CARDIO", "REVIEW_REQUIRED", ["CARDIO_BODY_FOCUS_REVIEW_REQUIRED"], []
    if training_candidate == "MOBILITY":
        return "MOBILITY", "REVIEW_REQUIRED", ["MOBILITY_BODY_FOCUS_REVIEW_REQUIRED"], []

    target = str(source.get("target") or "").strip().lower() if source else ""
    muscle = str(source.get("muscle_group") or "").strip().lower() if source else ""
    category = str(source.get("category") or "").strip().lower() if source else ""
    candidate = TARGET_TO_BODY.get(target)
    reasons: list[str] = []
    conflicts: list[str] = []

    if category == "waist" or target in {"obliques", "waist"} or muscle == "obliques":
        reasons.append("AMBIGUOUS_WAIST_OR_OBLIQUES_MAPPING")
    if target in {
        "hips",
        "legs",
        "upper body",
        "lower body",
        "multiple target",
        "adductors",
        "abductors",
        "spine",
        "serratus anterior",
        "levator scapulae",
    }:
        reasons.append("AMBIGUOUS_PRIMARY_TARGET_MAPPING")
    if target in {"traps", "trapezius"}:
        reasons.append("TRAPS_TO_BACK_REVIEW_REQUIRED")
    muscle_body = MUSCLE_TO_BODY.get(muscle)
    if candidate is not None and muscle_body is not None and candidate != muscle_body:
        conflicts.append("TARGET_MUSCLE_GROUP_CONFLICT")
    if (
        candidate is not None
        and category in CATEGORY_BODY
        and candidate not in CATEGORY_BODY[category]
    ):
        conflicts.append("CATEGORY_TARGET_CONFLICT")
    if candidate is None and muscle_body is not None and target in {"", "unknown", "unspecified"}:
        candidate = muscle_body
        reasons.append("PRIMARY_TARGET_MISSING_USED_MUSCLE_GROUP")
    if candidate is None and not source:
        reasons.append("SOURCE_EVIDENCE_MISSING")
    elif candidate is None and not reasons:
        reasons.append("BODY_FOCUS_NOT_DETERMINED")
    if conflicts:
        reasons.append("SOURCE_FIELDS_CONFLICT")
    status = "REVIEW_REQUIRED" if reasons or conflicts or candidate is None else "CANDIDATE_READY"
    return candidate, status, reasons, conflicts


def _apply_current(
    candidate: str | None,
    base_status: str,
    reasons: list[str],
    conflicts: list[str],
    current: Any,
) -> tuple[str | None, str, list[str], list[str]]:
    current_value = (
        current if current in (None, *ALLOWED_TRAINING_TYPES, *ALLOWED_BODY_FOCUS) else current
    )
    if conflicts:
        if current_value is not None and current_value == candidate:
            reasons = [*reasons, "CURRENT_VALUE_CONSISTENT", "CURRENT_VALUE_PRESERVED"]
        elif current_value is not None:
            reasons = [*reasons, "CURRENT_VALUE_PRESERVED"]
        return candidate, "REVIEW_REQUIRED", reasons, conflicts
    if candidate is not None and current_value == candidate:
        reasons = [*reasons, "CURRENT_VALUE_CONSISTENT"]
        return candidate, "CONSISTENT", reasons, conflicts
    if current_value is not None and candidate is not None and current_value != candidate:
        conflicts = [*conflicts, "CURRENT_VALUE_CONFLICT"]
        reasons = [*reasons, "CURRENT_VALUE_PRESERVED"]
        return candidate, "REVIEW_REQUIRED", reasons, conflicts
    if current_value is not None:
        reasons = [*reasons, "CURRENT_VALUE_PRESERVED"]
        return candidate, "REVIEW_REQUIRED", reasons, conflicts
    return candidate, base_status, reasons, conflicts


def build_candidates(
    catalog: list[dict[str, Any]],
    additions: list[dict[str, Any]],
    raw_gymvisual: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    addition_by_id: dict[str, dict[str, Any]] = {}
    for item in additions:
        identity = item.get("id")
        if not isinstance(identity, str) or not identity:
            raise CandidateBuildError("every addition must have a non-empty string id")
        if identity in addition_by_id:
            raise CandidateBuildError(f"duplicate additions id: {identity}")
        addition_by_id[identity] = item
    raw_by_id: dict[str, dict[str, Any]] = {}
    for item in raw_gymvisual:
        identity = item.get("id")
        if isinstance(identity, str):
            raw_by_id[identity] = item

    output: list[dict[str, Any]] = []
    for row in catalog:
        source = _source_record(row, addition_by_id, raw_by_id)
        training, training_status, training_reasons, training_conflicts = _classify_training(
            source, row
        )
        body, body_status, body_reasons, body_conflicts = _classify_body(source, row, training)
        evidence = _text_evidence(source, row)[2]
        if source is None:
            evidence = (
                ["instruction_summary_ko", "name_en"]
                if any(row.get(key) for key in ("instruction_summary_ko", "name_en"))
                else []
            )
        training, training_status, training_reasons, training_conflicts = _apply_current(
            training,
            training_status,
            training_reasons,
            training_conflicts,
            row.get("training_type_code"),
        )
        body, body_status, body_reasons, body_conflicts = _apply_current(
            body,
            body_status,
            body_reasons,
            body_conflicts,
            row.get("body_focus_code"),
        )
        all_conflicts = sorted(set(training_conflicts + body_conflicts))
        output.append(
            {
                "stable_code": row.get("stable_code"),
                "source_track": row.get("source_track"),
                "source_identity": row.get("source_identity"),
                "name_ko": row.get("name_ko"),
                "name_en": row.get("name_en"),
                "source_category": source.get("category") if source else None,
                "source_target": source.get("target") if source else None,
                "source_muscle_group": source.get("muscle_group") if source else None,
                "source_secondary_muscles": source.get("secondary_muscles") if source else None,
                "source_instruction": _source_instruction(source) if source else None,
                "current_training_type_code": row.get("training_type_code"),
                "training_type_code_candidate": training,
                "training_type_review_status": training_status,
                "training_type_reason_codes": sorted(set(training_reasons)),
                "current_body_focus_code": row.get("body_focus_code"),
                "body_focus_code_candidate": body,
                "body_focus_review_status": body_status,
                "body_focus_reason_codes": sorted(set(body_reasons)),
                "evidence_fields": evidence,
                "conflict_codes": all_conflicts,
            }
        )
    return output


def validate_candidates(rows: list[dict[str, Any]], catalog: list[dict[str, Any]]) -> None:
    if len(rows) != len(catalog):
        raise CandidateBuildError("candidate count must equal catalog count")
    if len({row.get("source_identity") for row in rows}) != len(rows):
        raise CandidateBuildError("source_identity must be unique")
    for row in rows:
        missing = [field for field in REQUIRED_OUTPUT_FIELDS if field not in row]
        if missing:
            raise CandidateBuildError(f"candidate is missing fields: {', '.join(missing)}")
        if row["training_type_code_candidate"] not in (None, *ALLOWED_TRAINING_TYPES):
            raise CandidateBuildError("invalid training type candidate")
        if row["body_focus_code_candidate"] not in (None, *ALLOWED_BODY_FOCUS):
            raise CandidateBuildError("invalid body focus candidate")
        if row["training_type_review_status"] not in {
            "CANDIDATE_READY",
            "REVIEW_REQUIRED",
            "CONSISTENT",
        }:
            raise CandidateBuildError("invalid training review status")
        if row["body_focus_review_status"] not in {
            "CANDIDATE_READY",
            "REVIEW_REQUIRED",
            "CONSISTENT",
        }:
            raise CandidateBuildError("invalid body focus review status")
        if (
            row["training_type_code_candidate"] in {"CARDIO", "MOBILITY"}
            and row["current_training_type_code"] is None
        ):
            if row["training_type_review_status"] != "REVIEW_REQUIRED":
                raise CandidateBuildError(
                    "CARDIO/MOBILITY must remain review-required without a current value"
                )
        if (
            row["body_focus_code_candidate"] in {"CARDIO", "MOBILITY"}
            and row["current_body_focus_code"] is None
        ):
            if row["body_focus_review_status"] != "REVIEW_REQUIRED":
                raise CandidateBuildError(
                    "CARDIO/MOBILITY body focus must remain review-required without a current value"
                )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--additions", type=Path, default=DEFAULT_ADDITIONS)
    parser.add_argument("--raw-gymvisual", type=Path, default=DEFAULT_RAW_GYMVISUAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    catalog = _rows(_read_json(args.catalog), args.catalog)
    additions = _rows(_read_json(args.additions), args.additions)
    raw_gymvisual = _rows(_read_json(args.raw_gymvisual), args.raw_gymvisual)
    rows = build_candidates(catalog, additions, raw_gymvisual)
    validate_candidates(rows, catalog)
    write_jsonl(args.output, rows)
    print(f"wrote {len(rows)} candidates to {args.output}")


if __name__ == "__main__":
    main()
