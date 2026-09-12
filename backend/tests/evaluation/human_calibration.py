"""Build the PHASE 10 blinded human-calibration packet."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

SELECTION_VERSION = "phase10-human-calibration-selection-v1"
SCORE_DIMENSIONS = (
    "personalization_score",
    "feasibility_score",
    "consistency_score",
    "explanation_quality_score",
    "groundedness_score",
    "overall_quality_score",
)
BLIND_COLUMNS = (
    "sample_id",
    "case_id",
    "category",
    "user_context",
    "routine_plan",
    "decision_codes",
    *SCORE_DIMENSIONS,
    "human_score",
    "reviewer_confidence",
    "reviewer_notes",
)

# Twenty-four judged outputs, balanced to eight per architecture. The reviewer-facing
# CSV never includes the architecture code or the stored judge result.
SELECTED_OUTPUTS = (
    ("SQ-SIMPLE-001", "MULTI_AGENT"),
    ("SQ-SIMPLE-001", "SINGLE_AGENT_RAG"),
    ("SQ-SIMPLE-001", "SINGLE_LLM"),
    ("SQ-MODERATE-002", "MULTI_AGENT"),
    ("SQ-MODERATE-001", "SINGLE_AGENT_RAG"),
    ("SQ-MODERATE-002", "SINGLE_LLM"),
    ("SQ-COMPLEX-001", "MULTI_AGENT"),
    ("SQ-COMPLEX-002", "SINGLE_AGENT_RAG"),
    ("SQ-COMPLEX-002", "SINGLE_LLM"),
    ("SQ-CONFLICT-001", "MULTI_AGENT"),
    ("SQ-CONFLICT-002", "MULTI_AGENT"),
    ("SQ-CONFLICT-002", "SINGLE_AGENT_RAG"),
    ("SQ-CONFLICT-001", "SINGLE_LLM"),
    ("SQ-CONFLICT-003", "SINGLE_LLM"),
    ("SQ-SAFETY-001", "SINGLE_AGENT_RAG"),
    ("SQ-SAFETY-001", "SINGLE_LLM"),
    ("SQ-RAG-001", "MULTI_AGENT"),
    ("SQ-RAG-002", "MULTI_AGENT"),
    ("SQ-RAG-001", "SINGLE_AGENT_RAG"),
    ("SQ-RAG-002", "SINGLE_LLM"),
    ("SQ-FAILURE-001", "MULTI_AGENT"),
    ("SQ-FAILURE-001", "SINGLE_AGENT_RAG"),
    ("SQ-FAILURE-002", "SINGLE_AGENT_RAG"),
    ("SQ-FAILURE-001", "SINGLE_LLM"),
)


@dataclass(frozen=True, slots=True)
class CalibrationItem:
    sample_id: str
    case_id: str
    category: str
    architecture_code: str
    payload: Mapping[str, Any]
    judge_score: Mapping[str, Any]


def load_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _judge_index(
    judge_payloads: Mapping[str, Mapping[str, Any]],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    index: dict[tuple[str, str], Mapping[str, Any]] = {}
    for architecture_code, payload in judge_payloads.items():
        scores = payload.get("scores")
        if not isinstance(scores, list):
            raise ValueError(f"judge scores missing for {architecture_code}")
        for score in scores:
            if isinstance(score, dict) and score.get("mean_score") is not None:
                index[(str(score["case_id"]), architecture_code)] = score
    return index


def _blind_order_key(selection: tuple[str, str]) -> str:
    case_id, architecture_code = selection
    return hashlib.sha256(f"{SELECTION_VERSION}|{case_id}|{architecture_code}".encode()).hexdigest()


def build_items(
    pairwise_payload: Mapping[str, Any],
    judge_payloads: Mapping[str, Mapping[str, Any]],
) -> list[CalibrationItem]:
    cases = pairwise_payload.get("cases")
    if not isinstance(cases, dict):
        raise ValueError("pairwise payload must contain a cases object")
    judges = _judge_index(judge_payloads)
    items: list[CalibrationItem] = []
    for ordinal, (case_id, architecture_code) in enumerate(
        sorted(SELECTED_OUTPUTS, key=_blind_order_key), start=1
    ):
        case = cases.get(case_id)
        if not isinstance(case, dict):
            raise ValueError(f"selected case is missing: {case_id}")
        architectures = case.get("architectures")
        if not isinstance(architectures, dict):
            raise ValueError(f"architectures missing: {case_id}")
        plan_payload = architectures.get(architecture_code)
        if not isinstance(plan_payload, dict):
            raise ValueError(f"selected output is missing: {case_id}/{architecture_code}")
        judge_score = judges.get((case_id, architecture_code))
        if judge_score is None:
            raise ValueError(f"judge score is missing: {case_id}/{architecture_code}")
        items.append(
            CalibrationItem(
                sample_id=f"HC-{ordinal:03d}",
                case_id=case_id,
                category=str(case["category"]),
                architecture_code=architecture_code,
                payload=plan_payload,
                judge_score=judge_score,
            )
        )
    return items


def _format_user_context(payload: Mapping[str, Any]) -> str:
    context = payload.get("user_context")
    if not isinstance(context, dict):
        return ""
    ceiling = context.get("recovery_ceiling")
    ceiling = ceiling if isinstance(ceiling, dict) else {}
    locations = context.get("allowed_location_codes", [])
    location_text = ", ".join(str(value) for value in locations)
    intensities = ceiling.get("allowed_intensity_codes", [])
    intensity_text = (
        ", ".join(str(value) for value in intensities)
        if isinstance(intensities, list)
        else str(intensities)
    )
    return "\n".join(
        (
            f"목표: {context.get('primary_goal_code', '')}",
            f"장소: {location_text}",
            f"요청 시간: {context.get('requested_duration_minutes', '')}분",
            f"제외 운동 수: {context.get('excluded_exercise_count', '')}",
            f"허용 강도: {intensity_text}",
            f"운동당 최대 세트: {ceiling.get('maximum_sets_per_exercise', '')}",
            f"세트당 최대 반복: {ceiling.get('maximum_repetitions_per_set', '')}",
            f"최소 휴식: {ceiling.get('minimum_rest_seconds_between_sets', '')}초",
        )
    )


def _format_plan(payload: Mapping[str, Any]) -> str:
    plan = payload.get("plan")
    if not isinstance(plan, dict):
        return "계획 없음"
    lines = [
        f"조정: {plan.get('action_code', '')}",
        f"예상 시간: {plan.get('estimated_duration_seconds', '')}초",
    ]
    exercises = plan.get("exercises")
    if isinstance(exercises, list):
        for exercise in exercises:
            if not isinstance(exercise, dict):
                continue
            lines.append(
                "{sequence}. [{phase}] {code} | {intensity} | {sets}세트 x "
                "{reps}회 | 휴식 {rest}초 | {location}".format(
                    sequence=exercise.get("sequence", ""),
                    phase=exercise.get("phase_code", ""),
                    code=exercise.get("stable_code", ""),
                    intensity=exercise.get("intensity_code", ""),
                    sets=exercise.get("sets", ""),
                    reps=exercise.get("repetitions_per_set", ""),
                    rest=exercise.get("rest_seconds_between_sets", ""),
                    location=exercise.get("location_code", ""),
                )
            )
    return "\n".join(lines)


def blind_rows(items: Sequence[CalibrationItem]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in items:
        row: dict[str, object] = {
            "sample_id": item.sample_id,
            "case_id": item.case_id,
            "category": item.category,
            "user_context": _format_user_context(item.payload),
            "routine_plan": _format_plan(item.payload),
            "decision_codes": "\n".join(
                str(value) for value in item.payload.get("decision_codes", [])
            ),
            "human_score": "",
            "reviewer_confidence": "",
            "reviewer_notes": "",
        }
        row.update({dimension: "" for dimension in SCORE_DIMENSIONS})
        rows.append(row)
    return rows


def render_blind_csv(items: Sequence[CalibrationItem]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=BLIND_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(blind_rows(items))
    return stream.getvalue()


def build_reference(items: Sequence[CalibrationItem]) -> dict[str, object]:
    architecture_counts = Counter(item.architecture_code for item in items)
    category_counts = Counter(item.category for item in items)
    return {
        "phase": "PHASE 10 Human Calibration",
        "selection_version": SELECTION_VERSION,
        "blind": True,
        "sample_count": len(items),
        "instructions": "Do not share this file with human reviewers before scoring.",
        "architecture_counts": dict(sorted(architecture_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "samples": [
            {
                "sample_id": item.sample_id,
                "case_id": item.case_id,
                "category": item.category,
                "architecture_code": item.architecture_code,
                "judge_score": item.judge_score["mean_score"],
                "judge_dimension_scores": item.judge_score["scores"],
                "judge_prompt_version": item.judge_score["prompt_version"],
                "judge_rubric_version": item.judge_score["rubric_version"],
            }
            for item in items
        ],
    }


def write_packet(
    *,
    pairwise_path: Path,
    judge_paths: Mapping[str, Path],
    output_dir: Path,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    items = build_items(
        load_json(pairwise_path),
        {code: load_json(path) for code, path in judge_paths.items()},
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    blind_path = output_dir / "blind_evaluation_form.csv"
    reference_path = output_dir / "sealed_judge_reference.json"
    existing = [path for path in (blind_path, reference_path) if path.exists()]
    if existing and not overwrite:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"refusing to overwrite existing calibration files: {names}")
    blind_path.write_text("\ufeff" + render_blind_csv(items), encoding="utf-8")
    reference_path.write_text(
        json.dumps(build_reference(items), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return blind_path, reference_path


__all__ = [
    "BLIND_COLUMNS",
    "SCORE_DIMENSIONS",
    "SELECTED_OUTPUTS",
    "build_items",
    "build_reference",
    "render_blind_csv",
    "write_packet",
]
