import ast
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.v3_contracts import ExercisePrescription
from backend.app.domain.agents.v3_orchestration import GraphTerminalStatusCode
from backend.app.modules.decisions.v3_shadow import (
    V3ShadowCase,
    V3ShadowExecutionRequest,
    V3ShadowExecutionResult,
    V3ShadowInvocationMetric,
    V3ShadowInvocationPhaseCode,
    V3ShadowInvocationStatusCode,
    V3ShadowPlanProjection,
    V3ShadowRoleCode,
    V3ShadowSafetyMetric,
    V3ShadowSafetyViolationCode,
    V3ShadowStructuredOutputStatusCode,
    V3ShadowUsageMetric,
    V3ShadowUsageStatusCode,
)

EXERCISE_ID = UUID("00000000-0000-0000-0000-000000000001")
FIXTURE_HASH = "a" * 64
PLAN_HASH = "b" * 64


def _prescription() -> ExercisePrescription:
    return ExercisePrescription(
        exercise_id=EXERCISE_ID,
        sequence=1,
        sets=2,
        repetitions_per_set=8,
        rest_seconds_between_sets=30,
        transition_seconds=10,
        intensity_code="LOW",
        location_code="HOME",
    )


def _plan() -> V3ShadowPlanProjection:
    return V3ShadowPlanProjection(
        action_code="KEEP",
        requested_duration_minutes=30,
        estimated_duration_seconds=1800,
        prescriptions=(_prescription(),),
        plan_hash=PLAN_HASH,
    )


def _case() -> V3ShadowCase:
    return V3ShadowCase.create(
        scenario_code="HEALTHY_ORIGINAL",
        fixture_version="v3-shadow-golden-v1",
        fixture_hash=FIXTURE_HASH,
        baseline_plan=_plan(),
    )


def _invocation() -> V3ShadowInvocationMetric:
    return V3ShadowInvocationMetric(
        role_code=V3ShadowRoleCode.TRAINING,
        phase_code=V3ShadowInvocationPhaseCode.PROPOSE,
        status_code=V3ShadowInvocationStatusCode.SUCCEEDED,
        attempt_count=1,
        latency_ms=100,
        provider_code="OPENAI",
        model_version="approved-model-v1",
        prompt_version="training-prompt-v1",
        output_schema_version="specialist-agent-proposal-v1",
        input_token_count=20,
        output_token_count=10,
    )


def _usage() -> V3ShadowUsageMetric:
    return V3ShadowUsageMetric(
        status_code=V3ShadowUsageStatusCode.COMPLETE,
        provider_call_count=1,
        input_token_count=20,
        output_token_count=10,
        decision_cost=Decimal("0.001"),
        currency_code="USD",
        pricing_reference_version="pricing-v1",
    )


def _result(**overrides: object) -> V3ShadowExecutionResult:
    values: dict[str, object] = {
        "scenario_code": "HEALTHY_ORIGINAL",
        "case_hash": _case().case_hash,
        "graph_version": "v3-graph-v1",
        "policy_version": "policy-v1",
        "catalog_version": "catalog-v1",
        "prompt_version": "prompt-set-v1",
        "provider_code": "OPENAI",
        "model_version": "approved-model-v1",
        "terminal_status_code": GraphTerminalStatusCode.COMPLETED,
        "plan": _plan(),
        "safety": V3ShadowSafetyMetric(invariant_passed=True),
        "structured_output_status_code": V3ShadowStructuredOutputStatusCode.SUCCEEDED,
        "constraint_violation_codes": (),
        "invocation_metrics": (_invocation(),),
        "review_attempt_count": 0,
        "repair_attempt_count": 0,
        "fallback_used": False,
        "failure_codes": (),
        "total_latency_ms": 120,
        "usage": _usage(),
    }
    values.update(overrides)
    return V3ShadowExecutionResult.create(**values)


def test_shadow_case_and_result_have_stable_hashes() -> None:
    first_case = _case()
    second_case = _case()
    first_result = _result()
    second_result = _result()

    assert first_case.case_hash == second_case.case_hash
    assert first_result.result_hash == second_result.result_hash


def test_shadow_request_contains_only_synthetic_references() -> None:
    request = V3ShadowExecutionRequest(
        case=_case(),
        graph_version="v3-graph-v1",
        policy_version="policy-v1",
        catalog_version="catalog-v1",
        prompt_version="prompt-set-v1",
        provider_code="OPENAI",
        model_version="approved-model-v1",
        snapshot_is_fresh=True,
    )

    assert "user_id" not in V3ShadowExecutionRequest.model_fields
    with pytest.raises(ValidationError):
        V3ShadowExecutionRequest.model_validate(
            {**request.model_dump(), "user_id": str(EXERCISE_ID)}
        )
    with pytest.raises(ValidationError):
        V3ShadowExecutionRequest.model_validate({**request.model_dump(), "prompt_text": "hidden"})


def test_safety_metric_is_fail_closed_and_canonical() -> None:
    violation = V3ShadowSafetyViolationCode.SAFETY_VETO_OVERRIDDEN
    failed = V3ShadowSafetyMetric(invariant_passed=False, violation_codes=(violation,))

    assert not failed.invariant_passed
    with pytest.raises(ValidationError, match="does not match"):
        V3ShadowSafetyMetric(invariant_passed=True, violation_codes=(violation,))
    with pytest.raises(ValidationError, match="unique and canonical"):
        V3ShadowSafetyMetric(
            invariant_passed=False,
            violation_codes=(violation, violation),
        )


def test_invocation_role_phase_and_token_pairs_are_validated() -> None:
    invalid_phase = _invocation().model_dump()
    invalid_phase["phase_code"] = V3ShadowInvocationPhaseCode.COORDINATE
    with pytest.raises(ValidationError, match="role and phase"):
        V3ShadowInvocationMetric.model_validate(invalid_phase)

    payload = _invocation().model_dump()
    payload["output_token_count"] = None
    with pytest.raises(ValidationError, match="present together"):
        V3ShadowInvocationMetric.model_validate(payload)


@pytest.mark.parametrize(
    "usage",
    [
        {
            "status_code": V3ShadowUsageStatusCode.NOT_APPLICABLE,
            "provider_call_count": 1,
        },
        {
            "status_code": V3ShadowUsageStatusCode.UNAVAILABLE,
            "provider_call_count": 1,
            "input_token_count": 10,
            "output_token_count": 5,
        },
        {
            "status_code": V3ShadowUsageStatusCode.COMPLETE,
            "provider_call_count": 1,
        },
        {
            "status_code": V3ShadowUsageStatusCode.COMPLETE,
            "provider_call_count": 1,
            "input_token_count": 10,
            "output_token_count": 5,
            "decision_cost": Decimal("0.1"),
        },
    ],
)
def test_usage_never_fabricates_tokens_or_partial_cost(usage: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        V3ShadowUsageMetric.model_validate(usage)


def test_terminal_result_cannot_expose_a_plan() -> None:
    with pytest.raises(ValidationError, match="only a completed"):
        _result(
            terminal_status_code=GraphTerminalStatusCode.STOP_AND_SEEK_HELP,
            safety=V3ShadowSafetyMetric(
                invariant_passed=False,
                violation_codes=(V3ShadowSafetyViolationCode.SAFETY_VETO_OVERRIDDEN,),
            ),
        )


def test_invocation_metrics_require_canonical_unique_order() -> None:
    coordinator = V3ShadowInvocationMetric(
        role_code=V3ShadowRoleCode.COORDINATOR,
        phase_code=V3ShadowInvocationPhaseCode.COORDINATE,
        status_code=V3ShadowInvocationStatusCode.SUCCEEDED,
        attempt_count=1,
        latency_ms=50,
        provider_code="OPENAI",
        model_version="approved-model-v1",
        prompt_version="coordinator-prompt-v1",
        output_schema_version="plan-spec-v1",
    )
    with pytest.raises(ValidationError, match="canonically ordered"):
        _result(invocation_metrics=(coordinator, _invocation()), total_latency_ms=150)


def test_hash_tampering_is_rejected() -> None:
    result = _result()
    with pytest.raises(ValidationError, match="result_hash"):
        V3ShadowExecutionResult.model_validate({**result.model_dump(), "result_hash": "f" * 64})


def test_shadow_contract_has_no_framework_or_provider_sdk_imports() -> None:
    module_path = Path(__file__).parents[2] / "app" / "modules" / "decisions" / "v3_shadow.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_roots = {
        "fastapi",
        "langchain",
        "langgraph",
        "openai",
        "qdrant_client",
        "sqlalchemy",
    }
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )

    assert imported_roots.isdisjoint(forbidden_roots)
