from __future__ import annotations

import json
from pathlib import Path

import pytest
from kspo_fitness100_pipeline import PipelineError, sha256_bytes
from review_tranche_3_candidates import build_results, verify_results, write_results

DATA_ROOT = Path(__file__).resolve().parents[2]
PLAN = DATA_ROOT / "normalized" / "review_tranche_3.agent.json"


def test_partitions_every_candidate_and_preserves_agent_only_state(tmp_path: Path) -> None:
    payload = build_results(PLAN)

    assert payload["summary"] == {
        "candidate_count": 11,
        "included": 6,
        "excluded": 5,
        "track_included": {"kspo": 3, "wger": 3},
    }
    records = payload["records"]
    assert isinstance(records, list)
    assert [record["queue_position"] for record in records] == list(range(1, 12))
    assert all(record["production_eligible"] is False for record in records)
    assert all(len(record["evidence"]) == 4 for record in records)

    output = tmp_path / "results.json"
    write_results(output, payload)
    assert verify_results(PLAN, output)["status"] == "valid"


def test_rejects_incomplete_partition(tmp_path: Path) -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["excludes"].pop()
    path = tmp_path / "plan.json"
    queue_path = DATA_ROOT.parent / plan["queue"]["path"]
    policy_path = DATA_ROOT.parent / plan["review_policy"]["path"]
    plan["queue"]["sha256"] = sha256_bytes(queue_path.read_bytes())
    plan["review_policy"]["sha256"] = sha256_bytes(policy_path.read_bytes())
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PipelineError, match="partition"):
        build_results(path)


def test_rejects_existing_stable_code(tmp_path: Path) -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["includes"][0]["stable_code"] = "push_up"
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PipelineError, match="stable codes"):
        build_results(path)


def test_rejects_tampered_results(tmp_path: Path) -> None:
    payload = build_results(PLAN)
    records = payload["records"]
    assert isinstance(records, list) and isinstance(records[0], dict)
    records[0]["production_eligible"] = True
    output = tmp_path / "results.json"
    write_results(output, payload)

    with pytest.raises(PipelineError, match="do not match"):
        verify_results(PLAN, output)
