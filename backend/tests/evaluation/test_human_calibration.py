"""Contract tests for the PHASE 10 blinded review packet."""

from __future__ import annotations

import csv
from collections import Counter
from io import StringIO
from pathlib import Path

import pytest

from backend.tests.evaluation.human_calibration import (
    SCORE_DIMENSIONS,
    CalibrationItem,
    build_items,
    build_reference,
    load_json,
    render_blind_csv,
    write_packet,
)
from backend.tests.evaluation.human_calibration_cli import DEFAULT_JUDGE_PATHS

ROOT = Path(__file__).resolve().parents[3]


def _items() -> list[CalibrationItem]:
    return build_items(
        load_json(ROOT / "results/pairwise/payloads.json"),
        {code: load_json(ROOT / path) for code, path in DEFAULT_JUDGE_PATHS.items()},
    )


def test_selection_has_24_unique_blind_samples_balanced_by_architecture() -> None:
    items = _items()

    assert len(items) == 24
    assert len({item.sample_id for item in items}) == 24
    assert Counter(item.architecture_code for item in items) == {
        "MULTI_AGENT": 8,
        "SINGLE_AGENT_RAG": 8,
        "SINGLE_LLM": 8,
    }
    assert set(item.category for item in items) == {
        "simple",
        "moderate",
        "complex",
        "conflict",
        "safety_critical",
        "rag_retrieval",
        "failure_case",
    }


def test_reviewer_csv_contains_no_judge_or_architecture_information() -> None:
    rendered = render_blind_csv(_items())
    rows = list(csv.DictReader(StringIO(rendered)))

    assert len(rows) == 24
    assert "judge_score" not in rows[0]
    assert "architecture_code" not in rows[0]
    assert "model_label" not in rows[0]
    assert "MULTI_AGENT" not in rendered
    assert "SINGLE_AGENT_RAG" not in rendered
    assert "SINGLE_LLM" not in rendered
    assert all(row["human_score"] == "" for row in rows)
    assert all(row[dimension] == "" for row in rows for dimension in SCORE_DIMENSIONS)


def test_sealed_reference_retains_join_keys_and_judge_scores() -> None:
    reference = build_reference(_items())

    assert reference["sample_count"] == 24
    assert reference["blind"] is True
    assert reference["architecture_counts"] == {
        "MULTI_AGENT": 8,
        "SINGLE_AGENT_RAG": 8,
        "SINGLE_LLM": 8,
    }
    samples = reference["samples"]
    assert isinstance(samples, list)
    assert all(sample["judge_score"] is not None for sample in samples)


def test_generator_does_not_overwrite_human_work_by_default(tmp_path: Path) -> None:
    pairwise_path = ROOT / "results/pairwise/payloads.json"
    judge_paths = {code: ROOT / path for code, path in DEFAULT_JUDGE_PATHS.items()}
    write_packet(
        pairwise_path=pairwise_path,
        judge_paths=judge_paths,
        output_dir=tmp_path,
    )

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_packet(
            pairwise_path=pairwise_path,
            judge_paths=judge_paths,
            output_dir=tmp_path,
        )
