from __future__ import annotations

import json
from pathlib import Path

import pytest
from collect_physical_activity_guidelines import (
    build_manifest,
    validate_compendium,
    verify_manifest,
    write_manifest,
)
from kspo_fitness100_pipeline import PipelineError

RAW_DIR = Path(__file__).resolve().parents[2] / "raw" / "physical_activity_guidelines"


def fake_fetcher(url: str) -> dict[str, object]:
    return {
        "final_url": url,
        "http_status": 200,
        "content_type": "application/pdf" if url.endswith(".pdf") else "text/html",
        "content_sha256": "a" * 64,
        "content_bytes": 1234,
    }


def test_builds_hash_only_manifest_and_verifies(tmp_path: Path) -> None:
    manifest = build_manifest(RAW_DIR, "2026-08-11T18:00:00+09:00", fake_fetcher)
    assert manifest["content_retention_code"] == "HASH_AND_MINIMUM_FACTS_ONLY"
    snapshots = manifest["snapshots"]
    assert isinstance(snapshots, list)
    assert len(snapshots) == 7
    http_snapshots = [
        snapshot
        for snapshot in snapshots
        if isinstance(snapshot, dict)
        if snapshot["collection_method_code"] == "HTTP_RESPONSE_HASH"
    ]
    fact_snapshots = [
        snapshot
        for snapshot in snapshots
        if isinstance(snapshot, dict)
        if snapshot["collection_method_code"] == "BROWSER_VERIFIED_FACT_HASH"
    ]
    assert len(http_snapshots) == 4
    assert len(fact_snapshots) == 3
    assert all(snapshot["content_sha256"] == "a" * 64 for snapshot in http_snapshots)
    assert all(
        snapshot["hash_scope_code"] == "STRUCTURED_FACTS_NOT_HTTP_RESPONSE"
        for snapshot in fact_snapshots
    )

    output = tmp_path / "snapshot_manifest.json"
    write_manifest(output, manifest)
    assert verify_manifest(RAW_DIR, output) == {
        "status": "valid",
        "source_count": 7,
        "guideline_fact_count": 14,
        "compendium_activity_count": 20,
    }


def test_rejects_compendium_exercise_mapping() -> None:
    path = RAW_DIR / "adult_compendium_mvp_reference_subset.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["normalized_exercise_id"] = "push_up"

    with pytest.raises(PipelineError, match="state or provenance"):
        validate_compendium(rows, {"ADULT_COMPENDIUM_PDF_2024"})


def test_rejects_changed_or_invalid_met_value() -> None:
    path = RAW_DIR / "adult_compendium_mvp_reference_subset.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["met_value"] = 0

    with pytest.raises(PipelineError, match="MET value"):
        validate_compendium(rows, {"ADULT_COMPENDIUM_PDF_2024"})


def test_rejects_manifest_after_local_fact_tamper(tmp_path: Path) -> None:
    manifest = build_manifest(RAW_DIR, "2026-08-11T18:00:00+09:00", fake_fetcher)
    local_files = manifest["local_files"]
    assert isinstance(local_files, list) and isinstance(local_files[0], dict)
    local_files[0]["sha256"] = "0" * 64
    output = tmp_path / "snapshot_manifest.json"
    write_manifest(output, manifest)

    with pytest.raises(PipelineError, match="local file hashes"):
        verify_manifest(RAW_DIR, output)
