"""Contract tests for the PHASE 11 canonical artifacts."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from backend.tests.evaluation.phase11_outputs import (
    REPORT_CATEGORIES,
    REQUIRED_RESULT_FILES,
    architecture_rows,
    category_rows,
    failed_case_report,
    load_json,
    render_csv,
    write_phase11_outputs,
)

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "results"


def test_architecture_comparison_contains_all_three_fairness_profiles() -> None:
    rows = architecture_rows(
        load_json(RESULTS / "comparison/comparison.json"),
        load_json(RESULTS / "human_calibration/calibration_summary.json"),
    )

    assert {row["architecture_code"] for row in rows} == {
        "SINGLE_LLM",
        "SINGLE_AGENT_RAG",
        "MULTI_AGENT",
    }
    multi = next(row for row in rows if row["architecture_code"] == "MULTI_AGENT")
    single_rag = next(row for row in rows if row["architecture_code"] == "SINGLE_AGENT_RAG")
    assert multi["safety_compliance_rate"] == single_rag["safety_compliance_rate"] == 1.0
    assert float(multi["average_tokens_per_run"]) > float(single_rag["average_tokens_per_run"])


def test_category_output_has_every_required_category_for_each_architecture() -> None:
    rows = category_rows(load_json(RESULTS / "comparison/comparison.json"))
    rendered = render_csv(rows, tuple(rows[0]))
    parsed = list(csv.DictReader(StringIO(rendered)))

    assert len(parsed) == len(REPORT_CATEGORIES) * 3
    assert {row["category"] for row in parsed} == set(REPORT_CATEGORIES)


def test_failed_case_rollup_distinguishes_availability_from_safety() -> None:
    report = failed_case_report(
        load_json(RESULTS / "paid/evaluation_summary.json"),
        load_json(RESULTS / "phase9/performance_failure.json"),
    )

    assert report["failed_run_count"] == 2
    assert report["critical_failure_count"] == 0
    assert report["phase9_unsafe_termination_count"] == 0


def test_writer_produces_every_required_artifact_and_manifest(tmp_path: Path) -> None:
    for name in (
        "evaluation_summary.json",
        "evaluation_cases.csv",
        "retrieval_metrics.json",
    ):
        (tmp_path / name).write_bytes((RESULTS / name).read_bytes())
    for directory in ("paid", "comparison", "human_calibration", "phase9"):
        source = RESULTS / directory
        target = tmp_path / directory
        target.mkdir()
        for file in source.iterdir():
            if file.is_file():
                (target / file.name).write_bytes(file.read_bytes())

    manifest = write_phase11_outputs(tmp_path)

    assert manifest["status"] == "COMPLETE"
    assert all((tmp_path / name).is_file() for name in REQUIRED_RESULT_FILES)
    assert (tmp_path / "category_metrics.csv").is_file()
    assert (tmp_path / "phase11_manifest.json").is_file()
