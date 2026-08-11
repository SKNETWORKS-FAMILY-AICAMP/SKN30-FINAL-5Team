from __future__ import annotations

import json
from pathlib import Path

import pytest
from build_review_tranche_candidates import build_payload, verify_output, write_payload
from kspo_fitness100_pipeline import PipelineError

DATA_ROOT = Path(__file__).resolve().parents[2]
POLICY = DATA_ROOT / "normalized" / "review_tranche_3_selection.json"


def test_builds_traceable_production_ineligible_queue(tmp_path: Path) -> None:
    payload = build_payload(POLICY)

    assert payload["status"] == "DRAFT"
    assert payload["review_method_code"] == "AGENT_ONLY"
    assert payload["production_eligible"] is False
    assert payload["summary"] == {
        "candidate_count": 11,
        "track_counts": {"kspo": 7, "wger": 4},
    }
    records = payload["records"]
    assert isinstance(records, list)
    assert [record["queue_position"] for record in records] == list(range(1, 12))
    assert all(record["review_decision"] == "PENDING" for record in records)
    assert all(record["required_review_codes"] for record in records)

    output = tmp_path / "candidates.json"
    write_payload(output, payload)
    assert verify_output(POLICY, output)["status"] == "valid"


def test_rejects_candidate_from_existing_review_batch(tmp_path: Path) -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy["candidates"][0]["source_identity"] = (
        "473449ac7d8cb935a59634c9113dd99907d813efa8dedb2922e358b550c2fc26"
    )
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PipelineError, match="already reviewed"):
        build_payload(path)


def test_rejects_unregistered_taxonomy_code(tmp_path: Path) -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy["candidates"][0]["target_movement_pattern_code"] = "BALANCE"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PipelineError, match="unregistered movement pattern"):
        build_payload(path)


def test_rejects_tampered_output(tmp_path: Path) -> None:
    payload = build_payload(POLICY)
    records = payload["records"]
    assert isinstance(records, list) and isinstance(records[0], dict)
    records[0]["review_decision"] = "INCLUDE"
    output = tmp_path / "candidates.json"
    write_payload(output, payload)

    with pytest.raises(PipelineError, match="does not match"):
        verify_output(POLICY, output)
