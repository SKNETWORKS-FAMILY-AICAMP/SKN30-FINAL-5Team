import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_compiler import DeterministicFallbackPlanSpec, compile_plan
from backend.app.domain.agents.v3_conflicts import detect_proposal_conflicts
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    PlanActionCode,
    RecoveryCeiling,
)
from backend.app.domain.agents.v3_orchestration import (
    FallbackRequest,
    GraphTerminalStatusCode,
    OrchestrationRouteCode,
    V3GraphResult,
    execute_deterministic_fallback,
    graph_result_conflicts,
    route_after_integrity_validation,
)
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationContext,
    IntegrityValidationResult,
    IntegrityValidationStatusCode,
    validate_plan_integrity,
)
from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.tests.unit.test_v3_agent_contracts import OUTSIDE, A, B, envelope, pool, prescription
from backend.tests.unit.test_v3_coordinator_contracts import coordinator_input, plan, proposals

COMPILER_VERSION = "v3-plan-compiler-v1"
VALIDATOR_VERSION = "v3-integrity-validator-v1"


def fallback_spec(
    current_envelope: ConstraintEnvelope,
    current_pool: ExercisePoolSnapshot,
    *,
    outside: bool = False,
) -> DeterministicFallbackPlanSpec:
    second_id = OUTSIDE if outside else B
    return DeterministicFallbackPlanSpec.create(
        envelope_hash=current_envelope.envelope_hash,
        pool_hash=current_pool.pool_hash,
        action_code=PlanActionCode.KEEP,
        requested_duration_minutes=6,
        estimated_duration_seconds=330,
        exercise_prescriptions=(prescription(A, 1), prescription(second_id, 2)),
        reason_codes=("DETERMINISTIC_FALLBACK",),
        fallback_version="fallback-v1",
    )


class FakeFallbackProvider:
    def __init__(self, result: DeterministicFallbackPlanSpec | None) -> None:
        self.result = result
        self.calls: list[FallbackRequest] = []

    def generate(self, request: FallbackRequest) -> DeterministicFallbackPlanSpec | None:
        self.calls.append(request)
        return self.result


def validation_for_duration(*, repair_attempt: int) -> IntegrityValidationResult:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    compiled = compile_plan(
        plan(current_input),
        envelope=current_envelope,
        pool=current_pool,
        compiler_version=COMPILER_VERSION,
        coordinator_input=current_input,
    ).model_copy(update={"estimated_duration_seconds": 1799})
    return validate_plan_integrity(
        compiled,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=repair_attempt,
        validator_version=VALIDATOR_VERSION,
        context=IntegrityValidationContext(approved_safe_alternative_ids=(B,)),
    )


def test_repairable_violation_routes_to_coordinator_exactly_once() -> None:
    initial = validation_for_duration(repair_attempt=0)
    repeated = validation_for_duration(repair_attempt=1)

    assert initial.status_code is IntegrityValidationStatusCode.REPAIRABLE
    assert route_after_integrity_validation(initial) is OrchestrationRouteCode.COORDINATOR_REPAIR
    assert repeated.status_code is IntegrityValidationStatusCode.NON_REPAIRABLE
    assert (
        route_after_integrity_validation(repeated) is OrchestrationRouteCode.DETERMINISTIC_FALLBACK
    )


def test_valid_deterministic_fallback_passes_compiler_and_validator() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    provider = FakeFallbackProvider(fallback_spec(current_envelope, current_pool))

    outcome = execute_deterministic_fallback(
        provider,
        envelope=current_envelope,
        pool=current_pool,
        fallback_version="fallback-v1",
        compiler_version=COMPILER_VERSION,
        validator_version=VALIDATOR_VERSION,
        validation_context=IntegrityValidationContext(approved_safe_alternative_ids=(B,)),
    )

    assert len(provider.calls) == 1
    assert outcome.compiled_plan is not None
    assert outcome.integrity_validation.status_code is IntegrityValidationStatusCode.PASS
    assert outcome.terminal_result is None


def test_invalid_fallback_returns_planless_failed_terminal() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    provider = FakeFallbackProvider(fallback_spec(current_envelope, current_pool, outside=True))

    outcome = execute_deterministic_fallback(
        provider,
        envelope=current_envelope,
        pool=current_pool,
        fallback_version="fallback-v1",
        compiler_version=COMPILER_VERSION,
        validator_version=VALIDATOR_VERSION,
        validation_context=IntegrityValidationContext(approved_safe_alternative_ids=(B,)),
    )

    assert outcome.compiled_plan is None
    assert outcome.terminal_result is not None
    assert outcome.terminal_result.status_code is GraphTerminalStatusCode.FAILED


def test_stop_and_seek_help_never_calls_or_changes_to_fallback_or_rest() -> None:
    blocked = ConstraintEnvelope.create(
        requested_duration_minutes=6,
        primary_goal_code="GENERAL_FITNESS",
        allowed_location_codes=("HOME",),
        allowed_equipment_codes=("BODYWEIGHT",),
        excluded_exercise_ids=(),
        mandatory_exercise_ids=(),
        recovery_ceiling=RecoveryCeiling(policy_version="recovery-policy-v1"),
        plan_generation_allowed=False,
        safety_required_action_code=SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
        policy_version="decision-policy-v3",
        catalog_version="catalog-v3",
        safety_rule_version="safety-rules-v3",
    )
    blocked_pool = pool(blocked)
    provider = FakeFallbackProvider(None)

    outcome = execute_deterministic_fallback(
        provider,
        envelope=blocked,
        pool=blocked_pool,
        fallback_version="fallback-v1",
        compiler_version=COMPILER_VERSION,
        validator_version=VALIDATOR_VERSION,
        validation_context=IntegrityValidationContext(),
    )

    assert provider.calls == []
    assert outcome.terminal_result is not None
    assert outcome.terminal_result.status_code is GraphTerminalStatusCode.STOP_AND_SEEK_HELP


def test_completed_graph_result_is_canonical_and_hash_stable() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_proposals = proposals(current_envelope, current_pool)
    conflicts = detect_proposal_conflicts(current_proposals, current_envelope, current_pool)
    current_input = coordinator_input(current_envelope, current_pool)
    current_plan = plan(current_input)
    compiled = compile_plan(
        current_plan,
        envelope=current_envelope,
        pool=current_pool,
        compiler_version=COMPILER_VERSION,
        coordinator_input=current_input,
    )
    validation = validate_plan_integrity(
        compiled,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=IntegrityValidationContext(approved_safe_alternative_ids=(B,)),
    )
    values = dict(
        graph_version="v3-orchestration-domain-v1",
        terminal_status_code=GraphTerminalStatusCode.COMPLETED,
        envelope_hash=current_envelope.envelope_hash,
        pool_hash=current_pool.pool_hash,
        round_one_proposals=current_proposals,
        conflict_codes=graph_result_conflicts(conflicts),
        review_target_agent_types=(),
        review_results=(),
        coordinator_initial_plan=current_plan,
        compiled_plan=compiled,
        integrity_violation_codes=tuple(item.code for item in validation.violations),
        final_plan=compiled,
    )

    first = V3GraphResult.create(**values)
    second = V3GraphResult.create(**values)

    assert first.result_hash == second.result_hash
    assert first.terminal_result is None


def test_graph_result_rejects_sensitive_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        V3GraphResult.model_validate(
            {
                "schema_version": "v3-graph-result-v1",
                "graph_version": "v3-orchestration-domain-v1",
                "terminal_status_code": GraphTerminalStatusCode.FAILED,
                "envelope_hash": "a" * 64,
                "pool_hash": "b" * 64,
                "round_one_proposals": (),
                "conflict_codes": (),
                "review_target_agent_types": (),
                "review_results": (),
                "coordinator_initial_plan": None,
                "coordinator_repair_plan": None,
                "compiled_plan": None,
                "integrity_violation_codes": (),
                "fallback_used": False,
                "fallback_version": None,
                "regeneration_difference": None,
                "final_plan": None,
                "terminal_result": {
                    "status_code": GraphTerminalStatusCode.FAILED,
                    "reason_codes": ("FAILED",),
                },
                "result_hash": "c" * 64,
                "raw_health_data": "forbidden",
            }
        )


def test_v3_domain_modules_have_no_framework_or_infrastructure_imports() -> None:
    module_dir = Path(__file__).parents[2] / "app" / "domain" / "agents"
    forbidden = {"fastapi", "langchain", "langgraph", "qdrant_client", "sqlalchemy"}
    for name in (
        "v3_conflicts.py",
        "v3_compiler.py",
        "v3_validation.py",
        "v3_orchestration.py",
    ):
        tree = ast.parse((module_dir / name).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module.split(".", maxsplit=1)[0])
        assert imported.isdisjoint(forbidden)
