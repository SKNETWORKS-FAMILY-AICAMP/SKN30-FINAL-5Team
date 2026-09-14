from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_7_backend_bundle.py"
spec = importlib.util.spec_from_file_location("met_v207", SCRIPT)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def inputs():
    base = builder.load_builder(builder.ROOT)
    return (
        base._read_csv(base.NORMALIZED_CATALOG),
        json.loads((builder.ROOT / builder.APPROVAL).read_text()),
        base._sha256(base.NORMALIZED_CATALOG),
    )


def test_full_bundle_preserves_baseline_and_is_deterministic(tmp_path):
    base = builder.load_builder(builder.ROOT)
    frozen = builder.snapshot(builder.ROOT / builder.BASELINE.parent, base)
    first = builder.build(target=tmp_path / "one", reports=tmp_path / "r1")
    second = builder.build(target=tmp_path / "two", reports=tmp_path / "r2")
    assert first == second
    assert first["met_non_null_count"] == first["domain_approved_count"] == 237
    assert first["met_null_count"] == 0
    assert builder.snapshot(builder.ROOT / builder.BASELINE.parent, base) == frozen
    rows, approval, source_hash = inputs()
    builder.verify_semantics(
        tmp_path / "one",
        builder.ROOT / builder.BASELINE,
        builder.project_met(rows, approval, source_hash),
    )
    builder.verify_manifests(tmp_path / "one", base)
    for row in builder.read_jsonl(tmp_path / "one/catalog/exercises.jsonl"):
        assert set(builder.MET_FIELDS) <= row.keys()
        assert "met_reviewed_at" not in row and "met_reviewer_code" not in row
    with pytest.raises(ValueError, match="overwrite"):
        builder.build(target=tmp_path / "one", reports=tmp_path / "r3")
    path = tmp_path / "one/catalog/exercises.jsonl"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="hash/size"):
        builder.verify_manifests(tmp_path / "one", base)


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "inf", "-inf", "abc"])
def test_rejects_invalid_met(value):
    rows, approval, source_hash = inputs()
    rows[0]["met_value"] = value
    with pytest.raises(ValueError, match="MET"):
        builder.project_met(rows, approval, source_hash)


@pytest.mark.parametrize("field", builder.MET_FIELDS[1:])
def test_rejects_missing_provenance(field):
    rows, approval, source_hash = inputs()
    rows[0][field] = ""
    with pytest.raises(ValueError):
        builder.project_met(rows, approval, source_hash)


def test_rejects_approval_hash_and_count_mismatch():
    rows, approval, source_hash = inputs()
    with pytest.raises(ValueError, match="hash"):
        builder.project_met(rows, approval, "0" * 64)
    approval["approved_record_count"] -= 1
    with pytest.raises(ValueError, match="count"):
        builder.project_met(rows, approval, source_hash)


def test_null_unapproved_and_non_null_unapproved():
    rows, approval, source_hash = inputs()
    rows[0]["met_review_status_code"] = "REVIEW_REQUIRED"
    with pytest.raises(ValueError, match="unapproved MET"):
        builder.project_met(rows, approval, source_hash)
    rows[0]["met_value"] = ""
    approval["approved_record_count"] -= 1
    result = builder.project_met(rows, approval, source_hash)
    assert result[rows[0]["stable_code"]]["met_value"] is None


def test_failure_does_not_publish(tmp_path, monkeypatch):
    def fail(*args):
        raise ValueError("non-MET semantic changes")

    monkeypatch.setattr(builder, "verify_semantics", fail)
    target, reports = tmp_path / "bundle", tmp_path / "reports"
    with pytest.raises(ValueError, match="non-MET"):
        builder.build(target=target, reports=reports)
    assert not target.exists() and not reports.exists()
