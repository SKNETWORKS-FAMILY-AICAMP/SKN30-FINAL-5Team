"""Analyze completed PHASE 10 consensus labels against the sealed Judge scores."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from io import StringIO
from pathlib import Path
from typing import Any

from backend.tests.evaluation.human_calibration import SCORE_DIMENSIONS

JUDGE_DIMENSIONS = {
    "personalization_score": "PERSONALIZATION",
    "feasibility_score": "FEASIBILITY",
    "consistency_score": "CONSISTENCY",
    "explanation_quality_score": "EXPLANATION_QUALITY",
    "groundedness_score": "GROUNDEDNESS",
    "overall_quality_score": "OVERALL_QUALITY",
}
VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
RESULT_COLUMNS = (
    "sample_id",
    "case_id",
    "category",
    "architecture_code",
    *SCORE_DIMENSIONS,
    "human_score",
    "judge_score",
    "score_difference",
    "absolute_difference",
    "reviewer_confidence",
    "reviewer_notes",
)


class CalibrationInputError(ValueError):
    """Raised when a human calibration form is incomplete or malformed."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_reference(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _score(value: str, *, field: str, sample_id: str, errors: list[str]) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        errors.append(f"{sample_id}: {field} must be numeric")
        return 0.0
    if not math.isfinite(parsed) or not 1.0 <= parsed <= 5.0:
        errors.append(f"{sample_id}: {field} must be between 1 and 5")
    return parsed


def _reference_index(reference: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    samples = reference.get("samples")
    if not isinstance(samples, list):
        raise ValueError("sealed reference must contain samples")
    return {str(sample["sample_id"]): sample for sample in samples if isinstance(sample, dict)}


def analyze_rows(
    rows: Sequence[Mapping[str, str]], reference: Mapping[str, Any]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    references = _reference_index(reference)
    errors: list[str] = []
    seen: set[str] = set()
    results: list[dict[str, object]] = []
    for row in rows:
        sample_id = row.get("sample_id", "")
        if not sample_id:
            errors.append("row without sample_id")
            continue
        if sample_id in seen:
            errors.append(f"duplicate sample_id: {sample_id}")
            continue
        seen.add(sample_id)
        sealed = references.get(sample_id)
        if sealed is None:
            errors.append(f"unknown sample_id: {sample_id}")
            continue
        if row.get("case_id") != sealed.get("case_id"):
            errors.append(f"{sample_id}: case_id does not match sealed reference")
        if row.get("category") != sealed.get("category"):
            errors.append(f"{sample_id}: category does not match sealed reference")

        scores = {
            dimension: _score(
                row.get(dimension, ""),
                field=dimension,
                sample_id=sample_id,
                errors=errors,
            )
            for dimension in SCORE_DIMENSIONS
        }
        confidence = row.get("reviewer_confidence", "")
        if confidence not in VALID_CONFIDENCE:
            errors.append(f"{sample_id}: reviewer_confidence must be HIGH, MEDIUM, or LOW")
        human_score = sum(scores.values()) / len(scores)
        entered_human_score = row.get("human_score", "").strip()
        if entered_human_score:
            entered = _score(
                entered_human_score,
                field="human_score",
                sample_id=sample_id,
                errors=errors,
            )
            if not math.isclose(entered, human_score, abs_tol=0.0001):
                errors.append(f"{sample_id}: human_score does not match dimension mean")
        judge_score = float(sealed["judge_score"])
        difference = human_score - judge_score
        results.append(
            {
                "sample_id": sample_id,
                "case_id": row["case_id"],
                "category": row["category"],
                "architecture_code": sealed["architecture_code"],
                **scores,
                "human_score": round(human_score, 4),
                "judge_score": judge_score,
                "score_difference": round(difference, 4),
                "absolute_difference": round(abs(difference), 4),
                "reviewer_confidence": confidence,
                "reviewer_notes": row.get("reviewer_notes", ""),
                "judge_dimension_scores": sealed["judge_dimension_scores"],
            }
        )

    missing = sorted(set(references) - seen)
    if missing:
        errors.append(f"missing sample_ids: {', '.join(missing)}")
    if errors:
        raise CalibrationInputError(errors)
    return results, build_summary(results)


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_variance = sum((value - left_mean) ** 2 for value in left)
    right_variance = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_variance * right_variance)
    return None if denominator == 0 else numerator / denominator


def _average_ranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        average_rank = ((cursor + 1) + end) / 2
        for original_index, _ in ordered[cursor:end]:
            ranks[original_index] = average_rank
        cursor = end
    return ranks


def _metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    human = [float(row["human_score"]) for row in rows]
    judge = [float(row["judge_score"]) for row in rows]
    differences = [left - right for left, right in zip(human, judge, strict=True)]
    count = len(rows)
    return {
        "sample_count": count,
        "human_mean": round(sum(human) / count, 4),
        "judge_mean": round(sum(judge) / count, 4),
        "mean_score_difference": round(sum(differences) / count, 4),
        "mean_absolute_error": round(sum(abs(value) for value in differences) / count, 4),
        "root_mean_squared_error": round(
            math.sqrt(sum(value**2 for value in differences) / count), 4
        ),
        "within_0_5_count": sum(abs(value) <= 0.5 for value in differences),
        "within_0_5_rate": round(sum(abs(value) <= 0.5 for value in differences) / count, 4),
        "pearson_correlation": (
            None if (pearson := _pearson(human, judge)) is None else round(pearson, 4)
        ),
        "spearman_correlation": (
            None
            if (spearman := _pearson(_average_ranks(human), _average_ranks(judge))) is None
            else round(spearman, 4)
        ),
    }


def _group_metrics(
    rows: Sequence[Mapping[str, object]], field: str
) -> dict[str, dict[str, object]]:
    grouped: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[field])].append(row)
    return {name: _metrics(group) for name, group in sorted(grouped.items())}


def _dimension_metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    metrics: dict[str, object] = {}
    for human_dimension, judge_dimension in JUDGE_DIMENSIONS.items():
        human = [float(row[human_dimension]) for row in rows]
        judge = [
            float(row["judge_dimension_scores"][judge_dimension])  # type: ignore[index]
            for row in rows
        ]
        differences = [left - right for left, right in zip(human, judge, strict=True)]
        metrics[human_dimension] = {
            "human_mean": round(sum(human) / len(rows), 4),
            "judge_mean": round(sum(judge) / len(rows), 4),
            "mean_score_difference": round(sum(differences) / len(rows), 4),
            "mean_absolute_error": round(sum(abs(value) for value in differences) / len(rows), 4),
        }
    return metrics


def build_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        "phase": "PHASE 10 Human Calibration",
        "label_type": "PM and development-lead consensus",
        "inter_rater_agreement": None,
        "inter_rater_note": ("Not calculable because only the final consensus label was recorded."),
        "difference_definition": "human_score - judge_score",
        "overall": _metrics(rows),
        "by_architecture": _group_metrics(rows, "architecture_code"),
        "by_category": _group_metrics(rows, "category"),
        "by_dimension": _dimension_metrics(rows),
    }


def render_results_csv(rows: Sequence[Mapping[str, object]]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=RESULT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows({column: row.get(column, "") for column in RESULT_COLUMNS} for row in rows)
    return stream.getvalue()


def write_analysis(*, form_path: Path, reference_path: Path, output_dir: Path) -> tuple[Path, Path]:
    results, summary = analyze_rows(load_rows(form_path), load_reference(reference_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "calibration_results.csv"
    summary_path = output_dir / "calibration_summary.json"
    results_path.write_text("\ufeff" + render_results_csv(results), encoding="utf-8")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return results_path, summary_path


__all__ = [
    "CalibrationInputError",
    "analyze_rows",
    "build_summary",
    "load_reference",
    "load_rows",
    "render_results_csv",
    "write_analysis",
]
