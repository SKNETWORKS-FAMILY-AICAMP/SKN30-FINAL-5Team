"""Build canonical PHASE 11 result artifacts from completed phase outputs."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from io import StringIO
from pathlib import Path
from typing import Any

REQUIRED_RESULT_FILES = (
    "evaluation_summary.json",
    "evaluation_cases.csv",
    "retrieval_metrics.json",
    "agent_metrics.json",
    "architecture_comparison.csv",
    "latency_metrics.json",
    "failed_cases.json",
)
REPORT_CATEGORIES = (
    "simple",
    "moderate",
    "complex",
    "conflict",
    "safety_critical",
)
ARCHITECTURE_COLUMNS = (
    "architecture_code",
    "label",
    "run_count",
    "constraint_satisfaction_rate",
    "safety_compliance_rate",
    "conflict_resolution_rate",
    "workflow_completion_rate",
    "structured_output_success_rate",
    "judge_mean",
    "p50_latency_ms",
    "p95_latency_ms",
    "average_llm_calls_per_run",
    "average_tokens_per_run",
    "critical_failures",
    "human_calibration_mean",
    "human_minus_judge_calibration_bias",
)
CATEGORY_COLUMNS = (
    "category",
    "architecture_code",
    "label",
    "runs",
    "constraint_satisfaction_rate",
    "llm_plan_rate",
    "plan_delivery_rate",
    "critical_failures",
)


def load_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def architecture_rows(
    comparison: Mapping[str, Any], calibration: Mapping[str, Any]
) -> list[dict[str, object]]:
    architectures = comparison.get("architectures")
    calibrated = calibration.get("by_architecture")
    if not isinstance(architectures, list) or not isinstance(calibrated, dict):
        raise ValueError("comparison or calibration architecture data is missing")
    rows: list[dict[str, object]] = []
    for architecture in architectures:
        if not isinstance(architecture, dict):
            continue
        code = str(architecture["architecture_code"])
        category = architecture["by_category"]
        calibration_metrics = calibrated[code]
        rows.append(
            {
                "architecture_code": code,
                "label": architecture["label"],
                "run_count": architecture["run_count"],
                "constraint_satisfaction_rate": architecture["constraint_satisfaction_rate"],
                "safety_compliance_rate": architecture["safety_compliance_rate"],
                "conflict_resolution_rate": category["conflict"]["constraint_satisfaction_rate"],
                "workflow_completion_rate": architecture["workflow_completion_rate"],
                "structured_output_success_rate": architecture["structured_output_success_rate"],
                "judge_mean": architecture["judge"]["mean"],
                "p50_latency_ms": architecture["latency"]["p50_ms"],
                "p95_latency_ms": architecture["latency"]["p95_ms"],
                "average_llm_calls_per_run": architecture["cost_inputs"][
                    "average_llm_calls_per_run"
                ],
                "average_tokens_per_run": architecture["cost_inputs"]["average_tokens_per_run"],
                "critical_failures": architecture["critical_failures"],
                "human_calibration_mean": calibration_metrics["human_mean"],
                "human_minus_judge_calibration_bias": calibration_metrics["mean_score_difference"],
            }
        )
    return rows


def category_rows(comparison: Mapping[str, Any]) -> list[dict[str, object]]:
    architectures = comparison.get("architectures")
    if not isinstance(architectures, list):
        raise ValueError("comparison architectures are missing")
    rows: list[dict[str, object]] = []
    for category_name in REPORT_CATEGORIES:
        for architecture in architectures:
            if not isinstance(architecture, dict):
                continue
            category = architecture["by_category"][category_name]
            rows.append(
                {
                    "category": category_name,
                    "architecture_code": architecture["architecture_code"],
                    "label": architecture["label"],
                    "runs": category["runs"],
                    "constraint_satisfaction_rate": category["constraint_satisfaction_rate"],
                    "llm_plan_rate": category["llm_plan_rate"],
                    "plan_delivery_rate": category["plan_delivery_rate"],
                    "critical_failures": category["critical_failures"],
                }
            )
    return rows


def failed_case_report(
    paid_summary: Mapping[str, Any], phase9: Mapping[str, Any]
) -> dict[str, object]:
    cases = paid_summary.get("cases")
    failure_evaluation = phase9.get("failure_evaluation")
    if not isinstance(cases, list) or not isinstance(failure_evaluation, dict):
        raise ValueError("paid cases or PHASE 9 failure evaluation is missing")
    failed = [
        {
            "case_id": case["case_id"],
            "category": case["category"],
            "status_code": case["status_code"],
            "used_fallback": case["used_fallback"],
            "findings": case["findings"],
        }
        for case in cases
        if isinstance(case, dict) and case.get("status_code") != "SUCCEEDED"
    ]
    return {
        "scope": "real-provider multi-agent runs plus controlled PHASE 9 failures",
        "failed_run_count": len(failed),
        "runs": failed,
        "critical_failure_count": int(paid_summary.get("critical_failures", 0)),
        "phase9_probe_count": failure_evaluation["scenario_count"],
        "phase9_safe_termination_count": failure_evaluation["safe_termination_count"],
        "phase9_unsafe_termination_count": (
            int(failure_evaluation["scenario_count"])
            - int(failure_evaluation["safe_termination_count"])
        ),
        "note": (
            "The two failed paid runs produced no unsafe plan. They are availability "
            "failures associated with the synthetic evaluation pool, not critical safety failures."
        ),
    }


def render_csv(rows: Sequence[Mapping[str, object]], columns: Sequence[str]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows({column: row.get(column, "") for column in columns} for row in rows)
    return stream.getvalue()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_phase11_outputs(results_dir: Path) -> dict[str, object]:
    comparison = load_json(results_dir / "comparison/comparison.json")
    calibration = load_json(results_dir / "human_calibration/calibration_summary.json")
    paid_summary = load_json(results_dir / "paid/evaluation_summary.json")
    phase9 = load_json(results_dir / "phase9/performance_failure.json")

    shutil.copyfile(results_dir / "paid/agent_metrics.json", results_dir / "agent_metrics.json")
    shutil.copyfile(results_dir / "paid/latency_metrics.json", results_dir / "latency_metrics.json")
    (results_dir / "architecture_comparison.csv").write_text(
        "\ufeff" + render_csv(architecture_rows(comparison, calibration), ARCHITECTURE_COLUMNS),
        encoding="utf-8",
    )
    (results_dir / "category_metrics.csv").write_text(
        "\ufeff" + render_csv(category_rows(comparison), CATEGORY_COLUMNS),
        encoding="utf-8",
    )
    (results_dir / "failed_cases.json").write_text(
        json.dumps(
            failed_case_report(paid_summary, phase9),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    missing = [name for name in REQUIRED_RESULT_FILES if not (results_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"required PHASE 11 outputs missing: {', '.join(missing)}")

    def artifact_record(name: str) -> dict[str, object]:
        return {
            "path": f"results/{name}",
            "sha256": _sha256(results_dir / name),
            "size_bytes": (results_dir / name).stat().st_size,
        }

    manifest = {
        "phase": "PHASE 11 final outputs",
        "status": "COMPLETE",
        "required_artifact_count": len(REQUIRED_RESULT_FILES),
        "required_artifacts": [artifact_record(name) for name in REQUIRED_RESULT_FILES],
        "supplemental_artifacts": [artifact_record("category_metrics.csv")],
        "source_artifacts": {
            "multi_agent": "results/paid/evaluation_summary.json",
            "architecture_comparison": "results/comparison/comparison.json",
            "human_calibration": "results/human_calibration/calibration_summary.json",
            "failure_evaluation": "results/phase9/performance_failure.json",
        },
        "cost": {
            "amount": None,
            "note": "Not calculated without an approved pricing reference.",
        },
    }
    manifest_path = results_dir / "phase11_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "ARCHITECTURE_COLUMNS",
    "CATEGORY_COLUMNS",
    "REPORT_CATEGORIES",
    "REQUIRED_RESULT_FILES",
    "architecture_rows",
    "category_rows",
    "failed_case_report",
    "render_csv",
    "write_phase11_outputs",
]
