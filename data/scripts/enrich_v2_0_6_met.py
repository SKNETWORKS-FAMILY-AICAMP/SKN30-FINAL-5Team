#!/usr/bin/env python3
"""Enrich v2.0.6 with source-backed MET values and auditable provenance.

The normalized CSV remains the only editable catalog source. This script reads
it plus the designated Adult Compendium JSONL subset and writes the six MET
columns back to the normalized CSV. DIRECT mappings require a directly named
activity or the same activity type. SIMILAR_ACTIVITY mappings are limited to
an activity whose equipment, posture, movement form, and execution mode are
materially aligned. No MET value is calculated, averaged, interpolated, or
copied from another catalog exercise.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_COMPENDIUM = (
    PROJECT_ROOT
    / "data/raw/physical_activity_guidelines/adult_compendium_mvp_reference_subset.jsonl"
)
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data/reports/v2_0_6_met"
DEFAULT_APPROVAL_MANIFEST = DEFAULT_REPORT_DIR / "met_review_approval_manifest.json"
SOURCE_RELATIVE_PATH = (
    "data/raw/physical_activity_guidelines/adult_compendium_mvp_reference_subset.jsonl"
)
POLICY_VERSION = "v2.0.6-met-compendium-direct-similar-1.0.0"
MET_FIELDS = (
    "met_value",
    "met_source_code",
    "met_source_activity_code",
    "met_mapping_method_code",
    "met_review_status_code",
    "met_policy_version",
)
FORBIDDEN_RANK_FIELDS = {"rank", "variant_difficulty_rank"}
MET_REVIEW_STATUS_CODES = {"REVIEW_REQUIRED", "DOMAIN_APPROVED"}

DIRECT_KETTLEBELL_SWING = re.compile(r"\b(?:kettle\s*bell|kettlebell)\s+swing\b")
STRETCH_TERMS = ("stretch", "pose", "mobility")
CORE_LIGHT_TERMS = (
    "crunch",
    "curl up",
    "curl-up",
    "sit up",
    "plank",
    "dead bug",
    "bridge",
    "pelvic tilt",
    "side bridge",
)
LOWER_BODY_WEIGHTED_TERMS = ("squat", "deadlift", "good morning", "rack pull")
HIGH_EFFORT_TERMS = (
    "jump",
    "plyo",
    "mountain climber",
    "high knee",
    "quick feet",
    "ski step",
)
WALKING_ACTIVITY_CODES = (
    "17170",
    "17190",
    "17200",
    "17349",
    "17352",
    "17355",
    "17358",
)

# These two rows were checked against their local GIFs because their names do
# not identify a sufficiently specific Compendium activity on their own.
# The selected activities are still copied verbatim from the designated
# Compendium subset; the GIF only confirms the exercise form.
GIF_REVIEW_SIMILAR_MAPPINGS = {
    "3672": {
        "activity_code": "02064",
        "reason_code": "GIF_REVIEW_IN_PLACE_STEP_HOME_EXERCISE",
        "rationale": (
            "GIF에서 장비 없이 제자리에서 앞뒤로 반복 스텝을 수행하는 형태가 확인되어 "
            "원천의 일반 홈트레이닝 activity와 수행 방식이 대응합니다."
        ),
    },
    "3221": {
        "activity_code": "02056",
        "reason_code": "GIF_REVIEW_HALF_SQUAT_BODYWEIGHT_RESISTANCE",
        "rationale": (
            "GIF에서 장비 없이 무릎을 굽혔다 펴는 반스쿼트 반복 동작이 확인되어 "
            "스쿼트를 예시로 든 원천의 일반 맨몸 저항운동과 수행 형태가 대응합니다."
        ),
    },
    "3666": {
        "activity_code": "12255",
        "reason_code": "GIF_REVIEW_INCLINE_TREADMILL_RUNNING",
        "rationale": (
            "GIF와 원천 지시문에서 경사 트레드밀 위를 달리는 형태가 확인되어 "
            "원천의 4.5mph 5% 경사 오르막 달리기 activity와 수행 환경과 방식이 대응합니다."
        ),
    },
    "0684": {
        "activity_code": "12150",
        "reason_code": "GIF_REVIEW_TREADMILL_RUNNING",
        "rationale": (
            "GIF에서 트레드밀 위 달리기가 확인되어 원천의 일반 달리기 activity와 "
            "수행 방식이 대응합니다."
        ),
    },
    "3656": {
        "activity_code": "12020",
        "reason_code": "GIF_REVIEW_SHORT_STRIDE_JOGGING",
        "rationale": (
            "GIF에서 제자리와 짧은 보폭으로 가볍게 뛰는 형태가 확인되어 원천의 "
            "자기 선택 속도 일반 조깅 activity와 수행 방식이 대응합니다."
        ),
    },
    "2311": {
        "activity_code": "02065",
        "reason_code": "DIRECT_STAIR_TREADMILL_ACTIVITY",
        "method": "DIRECT",
        "rationale": (
            "GIF와 운동명이 계단형 트레드밀 수행을 직접 나타내며 원천 activity와 대응합니다."
        ),
    },
    "0798": {
        "activity_code": "01200",
        "reason_code": "DIRECT_STATIONARY_BICYCLE_ACTIVITY",
        "method": "DIRECT",
        "rationale": (
            "GIF와 운동명이 고정식 자전거 페달링을 직접 나타내며 원천 activity와 대응합니다."
        ),
    },
    "2141": {
        "activity_code": "02048",
        "reason_code": "DIRECT_ELLIPTICAL_TRAINER_ACTIVITY",
        "method": "DIRECT",
        "rationale": (
            "GIF와 운동명이 일립티컬 트레이너 수행을 직접 나타내며 원천 activity와 대응합니다."
        ),
    },
    "2271": {
        "activity_code": "15110",
        "reason_code": "SIMILAR_BOXING_PUNCHING_BAG_ACTIVITY",
        "method": "SIMILAR_ACTIVITY",
        "rationale": (
            "GIF에서 반복적인 복싱 펀치 동작이 확인되어 원천의 punching bag "
            "복싱 activity와 수행 방식이 대응합니다."
        ),
    },
    "2133": {
        "activity_code": "17018",
        "reason_code": "SIMILAR_LOADED_CARRYING_ACTIVITY",
        "method": "SIMILAR_ACTIVITY",
        "rationale": (
            "GIF에서 양손 중량을 들고 평지에서 걷는 형태가 확인되어 원천의 "
            "15–155lb 하중 운반 activity와 수행 방식이 대응합니다."
        ),
    },
}


class MetEnrichmentError(ValueError):
    """Raised when source-only MET enrichment cannot be proven safe."""


def _normalize_text(value: str) -> str:
    value = value.lower().replace("–", "-").replace("—", "-")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _read_catalog(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    except OSError as exc:
        raise MetEnrichmentError(f"cannot read normalized catalog: {path}") from exc
    if not fields or not rows:
        raise MetEnrichmentError("normalized catalog must have a header and at least one row")
    if None in fields or any(None in row for row in rows):
        raise MetEnrichmentError("normalized catalog rows do not match the header")
    forbidden = sorted(FORBIDDEN_RANK_FIELDS.intersection(fields))
    if forbidden:
        raise MetEnrichmentError(
            "rank fields must not be generated in v2.0.6 normalized catalog: "
            + ", ".join(forbidden)
        )
    identities = [row.get("source_identity", "") for row in rows]
    stable_codes = [row.get("stable_code", "") for row in rows]
    if any(not value for value in identities) or len(set(identities)) != len(identities):
        raise MetEnrichmentError("source_identity must be non-empty and unique")
    if any(not value for value in stable_codes) or len(set(stable_codes)) != len(stable_codes):
        raise MetEnrichmentError("stable_code must be non-empty and unique")
    return rows, fields


def _read_compendium(path: Path) -> dict[str, dict[str, Any]]:
    try:
        raw_rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise MetEnrichmentError(f"cannot read designated Compendium subset: {path}") from exc
    activities: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            raise MetEnrichmentError("Compendium JSONL contains a non-object row")
        code = str(row.get("activity_code", "")).strip()
        description = str(row.get("activity_description", "")).strip()
        if not code or not description or code in activities:
            raise MetEnrichmentError("Compendium activity codes must be unique and complete")
        if "met_value" not in row or not isinstance(row["met_value"], (int, float)):
            raise MetEnrichmentError(f"Compendium MET value is missing or invalid: {code}")
        if not math.isfinite(float(row["met_value"])):
            raise MetEnrichmentError(f"Compendium MET value is not finite: {code}")
        activities[code] = row
    if not activities:
        raise MetEnrichmentError("Compendium JSONL is empty")
    return activities


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _write_catalog(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {field: _csv_value(row.get(field, "")) for field in fields} for row in rows
        )


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {field: _csv_value(row.get(field, "")) for field in fields} for row in rows
        )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _equipment_codes(row: dict[str, str]) -> set[str]:
    return {item for item in row.get("equipment_codes", "").split("|") if item}


def _has_term(text: str, terms: tuple[str, ...]) -> bool:
    normalized = _normalize_text(text)
    return any(_normalize_text(term) in normalized for term in terms)


def _candidate_codes(row: dict[str, str]) -> tuple[list[str], str]:
    """Return the source activities considered for the audit trail."""

    name = row.get("name_en", "")
    equipment = _equipment_codes(row)
    if _has_term(name, STRETCH_TERMS) or row.get("primary_movement_pattern_code") == (
        "MOBILITY_STRETCH"
    ):
        return ["02101"], "STRETCHING_ACTIVITY"
    if "kettlebell" in _normalize_text(name):
        return ["02054", "02058"], "KETTLEBELL_ACTIVITY_VARIANCE"
    if _has_term(name, ("walk", "walking")):
        return list(WALKING_ACTIVITY_CODES), "WALKING_SPEED_OR_GRADE_MISSING"
    if "elliptical" in _normalize_text(name):
        return [], "NO_ELLIPTICAL_ACTIVITY_IN_DESIGNATED_SUBSET"
    if "bike" in _normalize_text(name) or "cycling" in _normalize_text(name):
        return [], "NO_CYCLING_ACTIVITY_IN_DESIGNATED_SUBSET"
    if "run" in _normalize_text(name):
        return [], "NO_RUNNING_ACTIVITY_IN_DESIGNATED_SUBSET"
    if row.get("training_type_code") == "MOBILITY":
        return ["02101"], "MOBILITY_ACTIVITY_CONDITION_UNCLEAR"
    if row.get("training_type_code") == "STRENGTH":
        if "STABILITY_BALL" in equipment:
            return ["02054", "02112"], "STABILITY_BALL_ACTIVITY"
        if "BODYWEIGHT" in equipment:
            return ["02020", "02022", "02024", "02056", "02057"], "BODYWEIGHT_ACTIVITY"
        return ["02050", "02052", "02054"], "RESISTANCE_ACTIVITY"
    if row.get("training_type_code") == "CARDIO":
        return ["02020", "02064"], "CONDITIONING_ACTIVITY"
    return [], "NO_SUPPORTING_ACTIVITY"


def _mapped(
    activity: dict[str, Any],
    code: str,
    method: str,
    rationale: str,
    candidates: list[str],
    reason_code: str,
    review_status_code: str,
) -> dict[str, Any]:
    audit_candidates = list(dict.fromkeys([*candidates, code]))
    return {
        "mapping_status": "MAPPED_DIRECT" if method == "DIRECT" else "MAPPED_SIMILAR_ACTIVITY",
        "met_value": _csv_value(activity["met_value"]),
        "met_source_code": str(activity["source_id"]),
        "met_source_activity_code": code,
        "met_mapping_method_code": method,
        "met_review_status_code": review_status_code,
        "met_policy_version": POLICY_VERSION,
        "candidate_activity_codes": audit_candidates,
        "candidate_activity_descriptions": [
            str(activity["activity_description"]) if candidate == code else ""
            for candidate in audit_candidates
        ],
        "source_activity": activity,
        "reason_code": reason_code,
        "mapping_rationale": rationale,
    }


def _map_row(
    row: dict[str, str], activities: dict[str, dict[str, Any]], review_status_code: str
) -> dict[str, Any]:
    name = row.get("name_en", "")
    normalized_name = _normalize_text(name)
    equipment = _equipment_codes(row)
    pattern = row.get("primary_movement_pattern_code", "")

    # DIRECT: body-part and low-intensity tool variations do not change the
    # stretching activity type; kettlebell swing is named by the source.
    if _has_term(name, STRETCH_TERMS) or pattern == "MOBILITY_STRETCH":
        code = "02101"
        return _mapped(
            activities[code],
            code,
            "DIRECT",
            "정적 또는 저강도 가동성 스트레칭이며 신체 부위와 보조 도구가 달라도 "
            "원천의 stretching 활동 유형과 직접 대응합니다.",
            [code],
            "DIRECT_STRETCHING_ACTIVITY",
            review_status_code,
        )
    if DIRECT_KETTLEBELL_SWING.search(normalized_name):
        code = "02058"
        return _mapped(
            activities[code],
            code,
            "DIRECT",
            "운동명이 케틀벨 스윙과 직접 대응하고 원천 activity가 같은 수행 방식을 명시합니다.",
            [code],
            "DIRECT_KETTLEBELL_SWING_ACTIVITY",
            review_status_code,
        )

    gif_review_mapping = GIF_REVIEW_SIMILAR_MAPPINGS.get(row.get("source_identity", ""))
    if gif_review_mapping:
        code = gif_review_mapping["activity_code"]
        return _mapped(
            activities[code],
            code,
            gif_review_mapping.get("method", "SIMILAR_ACTIVITY"),
            gif_review_mapping["rationale"],
            [code],
            gif_review_mapping["reason_code"],
            review_status_code,
        )

    candidates, candidate_reason = _candidate_codes(row)
    selected_code = ""
    rationale = ""
    reason_code = ""
    if row.get("training_type_code") == "STRENGTH" and row.get("timing_mode_code") == "REPS":
        if "STABILITY_BALL" in equipment and _has_term(name, CORE_LIGHT_TERMS):
            selected_code = "02112"
            rationale = (
                "짐볼을 사용하는 반복형 코어 운동으로 원천의 Fitball exercise와 "
                "장비와 수행 형태가 대응합니다."
            )
            reason_code = "SIMILAR_STABILITY_BALL_EXERCISE"
        elif "BODYWEIGHT" in equipment:
            if _has_term(name, HIGH_EFFORT_TERMS) or pattern == "JUMP_PLYOMETRIC":
                selected_code = "02057" if _has_term(name, ("squat",)) else "02020"
                rationale = (
                    "맨몸 기반의 빠르거나 폭발적인 동작으로 원천의 고강도 맨몸 "
                    "저항운동 또는 격한 calisthenics와 수행 형태가 대응합니다."
                )
                reason_code = "SIMILAR_DYNAMIC_BODYWEIGHT_ACTIVITY"
            elif _has_term(name, CORE_LIGHT_TERMS):
                selected_code = "02024"
                rationale = (
                    "반복형 맨몸 코어 운동이며 crunch curl-up plank 계열을 명시한 "
                    "원천 활동과 수행 형태가 대응합니다."
                )
                reason_code = "SIMILAR_BODYWEIGHT_CORE_ACTIVITY"
            else:
                selected_code = "02056"
                rationale = (
                    "반복형 맨몸 저항운동으로 원천의 일반 맨몸 저항운동과 "
                    "장비와 수행 형태가 대응합니다."
                )
                reason_code = "SIMILAR_BODYWEIGHT_RESISTANCE_ACTIVITY"
        elif "KETTLEBELL" in equipment:
            selected_code = "02054"
            rationale = (
                "케틀벨을 사용하는 반복형 저항운동이며 원천의 다양한 저항운동 "
                "activity와 장비와 수행 형태가 대응합니다."
            )
            reason_code = "SIMILAR_KETTLEBELL_RESISTANCE_ACTIVITY"
        elif _has_term(name, LOWER_BODY_WEIGHTED_TERMS) or pattern in {
            "KNEE_DOMINANT",
            "HIP_DOMINANT",
        }:
            selected_code = "02052"
            rationale = (
                "중량을 사용하는 스쿼트·데드리프트 또는 유사한 하체 저항운동으로 "
                "원천의 weight training activity와 동작 형태가 대응합니다."
            )
            reason_code = "SIMILAR_WEIGHTED_LOWER_BODY_ACTIVITY"
        else:
            selected_code = "02054"
            rationale = (
                "중량 장비를 사용하는 반복형 저항운동으로 원천의 varied resistance "
                "training activity와 장비와 수행 형태가 대응합니다."
            )
            reason_code = "SIMILAR_WEIGHTED_RESISTANCE_ACTIVITY"
    elif row.get("training_type_code") == "STRENGTH" and _has_term(
        name, ("pelvic tilt", "quick feet")
    ):
        if _has_term(name, HIGH_EFFORT_TERMS):
            selected_code = "02020"
            rationale = (
                "빠른 반복 동작을 수행하는 맨몸 컨디셔닝으로 원천의 vigorous "
                "calisthenics와 수행 방식이 대응합니다."
            )
            reason_code = "SIMILAR_DYNAMIC_BODYWEIGHT_ACTIVITY"
        else:
            selected_code = "02024"
            rationale = (
                "저강도 정적 코어 동작으로 원천의 light calisthenics core activity와 "
                "수행 형태가 대응합니다."
            )
            reason_code = "SIMILAR_BODYWEIGHT_CORE_ACTIVITY"
    elif row.get("training_type_code") == "CARDIO" and _has_term(name, HIGH_EFFORT_TERMS):
        selected_code = "02020"
        rationale = (
            "빠르거나 점프를 포함하는 맨몸 컨디셔닝으로 원천의 vigorous "
            "calisthenics와 동적 수행 형태가 대응합니다."
        )
        reason_code = "SIMILAR_DYNAMIC_CONDITIONING_ACTIVITY"

    if selected_code and selected_code in activities:
        return _mapped(
            activities[selected_code],
            selected_code,
            "SIMILAR_ACTIVITY",
            rationale,
            candidates or [selected_code],
            reason_code,
            review_status_code,
        )

    if not candidates:
        reason_code = candidate_reason
    else:
        reason_code = f"{candidate_reason}_NOT_SUFFICIENTLY_ALIGNED"
    return {
        "mapping_status": "UNMAPPED",
        "met_value": "",
        "met_source_code": "",
        "met_source_activity_code": "",
        "met_mapping_method_code": "",
        "met_review_status_code": review_status_code,
        "met_policy_version": POLICY_VERSION,
        "candidate_activity_codes": candidates,
        "candidate_activity_descriptions": [
            activities[code]["activity_description"] for code in candidates if code in activities
        ],
        "source_activity": None,
        "reason_code": reason_code,
        "mapping_rationale": (
            "지정된 Compendium subset에서 수행 방식과 강도 조건이 충분히 대응하는 "
            "단일 activity를 확인하지 못했습니다."
        ),
    }


def enrich(
    catalog_path: Path = DEFAULT_CATALOG,
    compendium_path: Path = DEFAULT_COMPENDIUM,
    report_dir: Path = DEFAULT_REPORT_DIR,
    force: bool = False,
    review_status_code: str | None = None,
    approval_manifest: Path | None = None,
) -> dict[str, Any]:
    rows, original_fields = _read_catalog(catalog_path)
    activities = _read_compendium(compendium_path)
    if catalog_path.resolve() == DEFAULT_CATALOG.resolve() and not force:
        raise MetEnrichmentError(
            "the canonical normalized catalog already exists; use --force to "
            "enrich it intentionally"
        )

    existing_statuses = {
        str(row.get("met_review_status_code") or "").strip()
        for row in rows
        if str(row.get("met_review_status_code") or "").strip()
    }
    resolved_review_status = review_status_code or (
        existing_statuses.pop() if len(existing_statuses) == 1 else "REVIEW_REQUIRED"
    )
    if resolved_review_status not in MET_REVIEW_STATUS_CODES:
        raise MetEnrichmentError(
            f"invalid met review status: {resolved_review_status}; "
            f"expected one of {sorted(MET_REVIEW_STATUS_CODES)}"
        )
    if resolved_review_status == "DOMAIN_APPROVED":
        if approval_manifest is None or not approval_manifest.is_file():
            raise MetEnrichmentError("DOMAIN_APPROVED MET output requires an approval manifest")
        try:
            approval = json.loads(approval_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MetEnrichmentError("MET approval manifest is invalid") from exc
        if approval.get("review_status_code") != "DOMAIN_APPROVED":
            raise MetEnrichmentError("MET approval manifest is not DOMAIN_APPROVED")

    fields = list(original_fields)
    for field in MET_FIELDS:
        if field not in fields:
            fields.append(field)

    detail_rows: list[dict[str, Any]] = []
    enriched_rows: list[dict[str, str]] = []
    for row in rows:
        mapping = _map_row(row, activities, resolved_review_status)
        enriched = dict(row)
        for field in MET_FIELDS:
            enriched[field] = str(mapping[field])
        enriched_rows.append(enriched)
        detail_rows.append(
            {
                "stable_code": row["stable_code"],
                "source_identity": row["source_identity"],
                "name_en": row.get("name_en", ""),
                "name_ko": row.get("name_ko", ""),
                "mapping_status": mapping["mapping_status"],
                "reason_code": mapping["reason_code"],
                "met_value": mapping["met_value"],
                "met_source_code": mapping["met_source_code"],
                "met_source_activity_code": mapping["met_source_activity_code"],
                "met_source_activity_description": (
                    mapping["source_activity"]["activity_description"]
                    if mapping["source_activity"]
                    else ""
                ),
                "met_mapping_method_code": mapping["met_mapping_method_code"],
                "met_review_status_code": mapping["met_review_status_code"],
                "met_policy_version": mapping["met_policy_version"],
                "mapping_rationale": mapping["mapping_rationale"],
                "candidate_activity_codes": "|".join(mapping["candidate_activity_codes"]),
                "candidate_activity_descriptions": "|".join(
                    mapping["candidate_activity_descriptions"]
                ),
                "source_file_path": SOURCE_RELATIVE_PATH,
            }
        )

    _write_catalog(catalog_path, enriched_rows, fields)
    mapped = [row for row in detail_rows if row["mapping_status"].startswith("MAPPED_")]
    direct = [row for row in detail_rows if row["met_mapping_method_code"] == "DIRECT"]
    similar = [row for row in detail_rows if row["met_mapping_method_code"] == "SIMILAR_ACTIVITY"]
    unmapped = [row for row in detail_rows if row["mapping_status"] == "UNMAPPED"]
    review_needed = [
        row for row in detail_rows if row["met_review_status_code"] == "REVIEW_REQUIRED"
    ]
    approved = [row for row in detail_rows if row["met_review_status_code"] == "DOMAIN_APPROVED"]
    if resolved_review_status == "DOMAIN_APPROVED" and unmapped:
        raise MetEnrichmentError("DOMAIN_APPROVED MET output cannot contain unmapped rows")

    _write_csv(
        report_dir / "met_mapping_results.csv",
        (
            "stable_code",
            "source_identity",
            "name_en",
            "name_ko",
            "mapping_status",
            "reason_code",
            "met_value",
            "met_source_code",
            "met_source_activity_code",
            "met_source_activity_description",
            "met_mapping_method_code",
            "met_review_status_code",
            "met_policy_version",
            "mapping_rationale",
            "candidate_activity_codes",
            "candidate_activity_descriptions",
            "source_file_path",
        ),
        detail_rows,
    )
    _write_csv(
        report_dir / "met_unmapped_exercises.csv",
        (
            "stable_code",
            "source_identity",
            "name_en",
            "name_ko",
            "mapping_status",
            "reason_code",
            "mapping_rationale",
            "candidate_activity_codes",
            "candidate_activity_descriptions",
            "source_file_path",
        ),
        unmapped,
    )
    evidence_fields = (
        "stable_code",
        "source_identity",
        "name_en",
        "name_ko",
        "met_source_activity_description",
        "met_source_activity_code",
        "met_value",
        "met_mapping_method_code",
        "met_review_status_code",
        "met_policy_version",
        "mapping_rationale",
        "source_file_path",
    )
    _write_csv(report_dir / "met_mapping_evidence.csv", evidence_fields, mapped)
    _write_csv(report_dir / "met_direct_mappings.csv", evidence_fields, direct)
    _write_csv(report_dir / "met_similar_activity_mappings.csv", evidence_fields, similar)
    _write_csv(
        report_dir / "met_provenance.csv",
        (
            "stable_code",
            "source_identity",
            "name_en",
            "name_ko",
            "met_value",
            "met_source_code",
            "met_source_activity_code",
            "met_source_activity_description",
            "met_mapping_method_code",
            "met_review_status_code",
            "met_policy_version",
            "mapping_rationale",
            "source_file_path",
        ),
        detail_rows,
    )

    column_rows = []
    for field in fields:
        if field in MET_FIELDS:
            source = (
                f"{SOURCE_RELATIVE_PATH}#activity_code,activity_description,"
                "met_value,source_id,source_locator"
            )
            rule = (
                "designated Adult Compendium JSONL; selected DIRECT or SIMILAR_ACTIVITY source row"
            )
        else:
            source = f"data/normalized/v2_0_6_exercise_catalog.csv#{field}"
            rule = "canonical normalized catalog value; preserved without inference"
        column_rows.append({"column_name": field, "source": source, "mapping_rule": rule})
    _write_csv(
        report_dir / "catalog_column_source_report.csv",
        ("column_name", "source", "mapping_rule"),
        column_rows,
    )

    rank_report = {
        "status": "PASS",
        "rank_fields_checked": sorted(FORBIDDEN_RANK_FIELDS),
        "rank_fields_in_normalized_catalog": sorted(FORBIDDEN_RANK_FIELDS.intersection(fields)),
        "rank_fields_generated": [],
        "rank_fields_used_for_mapping": [],
        "variant_difficulty_rank_generated": False,
        "policy": (
            "rank and variant_difficulty_rank are excluded from v2.0.6 "
            "normalized and generated outputs"
        ),
        "source_catalog_sha256": _sha256(catalog_path),
    }
    _write_json(report_dir / "rank_usage_report.json", rank_report)

    report = {
        "status": "DRAFT",
        "production_eligible": False,
        "policy_version": POLICY_VERSION,
        "policy": {
            "source_file": SOURCE_RELATIVE_PATH,
            "direct_activity_description_only": False,
            "direct_mapping_allowed": True,
            "similar_activity_mapping_allowed": True,
            "no_estimation_or_calculation": True,
            "no_met_category_average_or_interpolation": True,
            "no_unmatched_exercise_value_copy": True,
            "unresolved_or_condition_mismatch_remain_blank": True,
            "met_review_status_requires_explicit_approval": True,
            "met_review_status_code": resolved_review_status,
            "met_approval_manifest": str(approval_manifest) if approval_manifest else None,
            "rank_not_generated_or_used": True,
        },
        "inputs": {
            "normalized_catalog": {
                "path": str(catalog_path),
                "sha256": _sha256(catalog_path),
                "records": len(rows),
            },
            "compendium_subset": {
                "path": SOURCE_RELATIVE_PATH,
                "sha256": _sha256(compendium_path),
                "activity_records": len(activities),
            },
        },
        "counts": {
            "catalog_records": len(detail_rows),
            "mapping_success": len(mapped),
            "unmapped": len(unmapped),
            "direct_mappings": len(direct),
            "similar_activity_mappings": len(similar),
            "review_needed": len(review_needed),
            "approved": len(approved),
            "met_values_non_empty": sum(bool(row["met_value"]) for row in detail_rows),
        },
        "mapped_activity_codes": sorted({row["met_source_activity_code"] for row in mapped}),
        "outputs": {
            "normalized_catalog": str(catalog_path),
            "mapping_results": str(report_dir / "met_mapping_results.csv"),
            "mapping_evidence": str(report_dir / "met_mapping_evidence.csv"),
            "direct_mappings": str(report_dir / "met_direct_mappings.csv"),
            "similar_activity_mappings": str(report_dir / "met_similar_activity_mappings.csv"),
            "unmapped_exercises": str(report_dir / "met_unmapped_exercises.csv"),
            "provenance": str(report_dir / "met_provenance.csv"),
            "column_source": str(report_dir / "catalog_column_source_report.csv"),
            "rank_usage": str(report_dir / "rank_usage_report.json"),
        },
    }
    report["inputs"]["normalized_catalog"]["sha256_after_enrichment"] = _sha256(catalog_path)
    _write_json(report_dir / "met_mapping_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--compendium", type=Path, default=DEFAULT_COMPENDIUM)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--review-status-code",
        choices=sorted(MET_REVIEW_STATUS_CODES),
        default=None,
        help="explicitly set the output MET review status",
    )
    parser.add_argument("--approval-manifest", type=Path, default=DEFAULT_APPROVAL_MANIFEST)
    args = parser.parse_args()
    report = enrich(
        args.catalog,
        args.compendium,
        args.report_dir,
        args.force,
        args.review_status_code,
        args.approval_manifest,
    )
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
