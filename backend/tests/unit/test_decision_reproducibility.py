from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.coordinator import coordinate
from backend.app.domain.agents.reproducibility import (
    DecisionInputSnapshot,
    DecisionReplayEnvelope,
    DecisionVersionBundle,
    FinalRoutineOptionLink,
    decision_input_hash,
    successful_decision_response_allowed,
)
from backend.app.domain.rules.duration import DurationAdjustmentSourceCode
from backend.app.domain.rules.safety import SafetyStatusCode
from backend.tests.scenarios.decision_golden_fixtures import (
    DECISION_GOLDEN_CASES,
    DecisionGoldenCase,
)


def _healthy_case() -> DecisionGoldenCase:
    return next(case for case in DECISION_GOLDEN_CASES if case.case_code == "HEALTHY_KEEP")


def _snapshot(
    *,
    context_reference_codes: tuple[str, ...] = ("CHECK_IN.NORMAL", "ROUTINE.ACTIVE"),
) -> DecisionInputSnapshot:
    return DecisionInputSnapshot(
        context_reference_codes=context_reference_codes,
        profile_duration_minutes=40,
        requested_duration_minutes=40,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
    )


def _envelope() -> DecisionReplayEnvelope:
    case = _healthy_case()
    result = coordinate(case.coordinator_input)
    return DecisionReplayEnvelope(
        input_snapshot=_snapshot(),
        versions=DecisionVersionBundle(
            catalog_version=case.versions.catalog_version,
            policy_version=case.versions.policy_version,
            safety_rule_version=case.versions.safety_rule_version,
            duration_rule_version=case.versions.duration_rule_version,
            graph_version=case.versions.graph_version,
            coordinator_version=case.versions.coordinator_version,
            proposal_schema_version=case.versions.proposal_schema_version,
        ),
        proposals=case.coordinator_input.proposals,
        candidates=case.coordinator_input.candidates,
        coordinator_result=result,
        final_routine_option=FinalRoutineOptionLink(
            action_code=result.final_action_code,
            selected_candidate_id=result.selected_candidate_id,
        ),
    )


def test_snapshot_hash_is_stable_for_json_key_and_reference_order() -> None:
    original = _snapshot()
    reordered_references = _snapshot(
        context_reference_codes=tuple(reversed(original.context_reference_codes))
    )
    payload = original.model_dump(mode="json")
    reversed_key_payload = dict(reversed(tuple(payload.items())))
    restored = DecisionInputSnapshot.model_validate_json(
        json.dumps(reversed_key_payload, ensure_ascii=False)
    )

    assert decision_input_hash(original) == decision_input_hash(reordered_references)
    assert decision_input_hash(original) == decision_input_hash(restored)
    assert len(decision_input_hash(original)) == 64


def test_snapshot_hash_changes_for_meaningful_duration_change() -> None:
    original = _snapshot()
    override = DecisionInputSnapshot(
        context_reference_codes=original.context_reference_codes,
        profile_duration_minutes=40,
        requested_duration_minutes=30,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.USER_OVERRIDE,
    )

    assert decision_input_hash(original) != decision_input_hash(override)


@pytest.mark.parametrize(
    "forbidden_field",
    ("date_of_birth", "age", "email", "full_name", "token", "raw_health_record"),
)
def test_snapshot_rejects_sensitive_or_uncontracted_fields(forbidden_field: str) -> None:
    payload = _snapshot().model_dump()
    payload[forbidden_field] = "SENSITIVE_SENTINEL"

    with pytest.raises(ValidationError):
        DecisionInputSnapshot.model_validate(payload)


def test_snapshot_rejects_duplicate_context_references() -> None:
    with pytest.raises(ValidationError):
        _snapshot(context_reference_codes=("CHECK_IN.NORMAL", "CHECK_IN.NORMAL"))


def test_replay_envelope_rejects_missing_proposal_record() -> None:
    envelope = _envelope()
    payload = json.loads(envelope.model_dump_json())
    payload["proposals"] = payload["proposals"][:-1]

    with pytest.raises(ValidationError, match="one separate proposal"):
        DecisionReplayEnvelope.model_validate_json(json.dumps(payload))


def test_replay_envelope_rejects_version_combination_drift() -> None:
    envelope = _envelope()
    payload = json.loads(envelope.model_dump_json())
    payload["versions"]["graph_version"] = "graph-v2"
    payload["versions"]["policy_version"] = "policy-v2"

    with pytest.raises(ValidationError, match="policy version"):
        DecisionReplayEnvelope.model_validate_json(json.dumps(payload))


def test_replay_envelope_rejects_final_option_candidate_mismatch() -> None:
    envelope = _envelope()
    payload = json.loads(envelope.model_dump_json())
    payload["final_routine_option"]["selected_candidate_id"] = "candidate-other"

    with pytest.raises(ValidationError, match="does not link"):
        DecisionReplayEnvelope.model_validate_json(json.dumps(payload))


def test_success_response_requires_persistence_and_public_success_status() -> None:
    envelope = _envelope()
    result = envelope.coordinator_result

    assert successful_decision_response_allowed(result=result, persistence_succeeded=True)
    assert not successful_decision_response_allowed(result=result, persistence_succeeded=False)
    inconsistent_safety = result.model_copy(update={"safety_status_code": SafetyStatusCode.BLOCKED})
    assert not successful_decision_response_allowed(
        result=inconsistent_safety,
        persistence_succeeded=True,
    )

    failed_case = next(
        case for case in DECISION_GOLDEN_CASES if case.case_code == "REQUIRED_AGENT_FAILURE"
    )
    failed_result = coordinate(failed_case.coordinator_input)
    assert not successful_decision_response_allowed(
        result=failed_result,
        persistence_succeeded=True,
    )
