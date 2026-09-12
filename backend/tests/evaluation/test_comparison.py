"""PHASE 6: assert the comparison is fair before believing any number it produces.

A benchmark that quietly handicaps the baseline produces a result that looks like
evidence and is not.  These tests pin the conditions that make the A/B/C
comparison mean something -- identical instructions, identical downstream gate,
identical safety enforcement, and metrics that decline to score a question an
architecture was never asked.

Everything here runs against the scripted model and costs nothing.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.app.domain.agents.v3_contracts import (
    PlanSpec,
    SpecialistAgentTypeCode,
    V3ProposalStatusCode,
)
from backend.app.integrations.llm_agents.models import LlmAgentRoleCode
from backend.app.integrations.llm_agents.payload import project_exercise_pool
from backend.app.integrations.llm_agents.prompts import ROLE_PROMPTS
from backend.tests.evaluation.architectures import (
    ARCHITECTURE_MULTI_AGENT,
    ARCHITECTURE_SINGLE_AGENT_RAG,
    ARCHITECTURE_SINGLE_LLM,
    COMPARED_ARCHITECTURES,
)
from backend.tests.evaluation.comparison import ArchitectureResult, ComparisonReport
from backend.tests.evaluation.comparison_cli import _execute, select_case_ids
from backend.tests.evaluation.dataset import EvaluationCase
from backend.tests.evaluation.evaluators import evaluate_case
from backend.tests.evaluation.evaluators.agent_metrics import build_report as build_agent_report
from backend.tests.evaluation.harness import EXCLUSION_CASES, GRAPH_CASES
from backend.tests.evaluation.judge.judge import build_judge_payload
from backend.tests.evaluation.runners.fake_chat import (
    Script,
    ScriptCode,
    ScriptedChatModel,
    register_prompt_role,
)
from backend.tests.evaluation.runners.payloads import SingleAgentPayloadBuilder
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult, MultiAgentRunner
from backend.tests.evaluation.runners.single_agent import (
    _DROPPED_CLAUSES,
    NO_SPECIALIST_ADVICE_CODE,
    SINGLE_AGENT_INSTRUCTION,
    SINGLE_AGENT_RAG_PROMPT_VERSION,
    SINGLE_LLM_PROMPT_VERSION,
    SingleAgentPlanDraft,
    SingleAgentRunner,
    single_agent_payload,
    synthesize_proposals,
)
from backend.tests.evaluation.scenario import build_scenario


def test_paid_subset_selection_preserves_dataset_order_and_rejects_unknown_ids() -> None:
    cases = tuple(GRAPH_CASES[:3])
    selected = select_case_ids(cases, (cases[2].case_id, cases[0].case_id))

    assert tuple(case.case_id for case in selected) == (cases[0].case_id, cases[2].case_id)
    with pytest.raises(ValueError, match="unknown case IDs"):
        select_case_ids(cases, ("UNKNOWN-CASE",))


def test_report_records_the_selected_dataset() -> None:
    report = asyncio.run(
        _execute(
            architectures=(),
            repeats=1,
            max_calls=0,
            offline=True,
            judge_enabled=False,
            dataset="expanded_heldout_cases",
        )
    )

    assert report.dataset_name == "expanded_heldout_cases"
    assert report.to_json()["dataset"] == "expanded_heldout_cases"


# Fields `PlanSpec` carries that describe an orchestration a baseline does not
# have. Any growth in this set is a fairness regression and must be argued for.
ARCHITECTURE_ONLY_PLAN_FIELDS = {"proposal_references", "repair_attempt"}
SERVER_OWNED_PLAN_FIELDS = {"plan_hash", "schema_version"}


@pytest.fixture(autouse=True)
def _baseline_prompts_registered() -> None:
    register_prompt_role(SINGLE_LLM_PROMPT_VERSION, LlmAgentRoleCode.COORDINATOR)
    register_prompt_role(SINGLE_AGENT_RAG_PROMPT_VERSION, LlmAgentRoleCode.COORDINATOR)


def _run(architecture_code: str, case: EvaluationCase, script: Script) -> CaseRunResult:
    scenario = build_scenario(case)
    if architecture_code == ARCHITECTURE_MULTI_AGENT:
        return asyncio.run(MultiAgentRunner().run_scenario(scenario, script))
    chat_model = ScriptedChatModel(
        script=script,
        payload_builder=SingleAgentPayloadBuilder(
            envelope=scenario.constraint_envelope, pool=scenario.exercise_pool
        ),
    )
    runner = SingleAgentRunner(architecture_code=architecture_code, chat_model=chat_model)
    return asyncio.run(runner.run_scenario(scenario, script))


# -- fairness of the instructions ---------------------------------------


def test_baseline_instruction_is_built_from_the_shipped_training_prompt() -> None:
    """The baseline is not handed a weaker specification of the same task."""

    training = ROLE_PROMPTS[LlmAgentRoleCode.TRAINING].instruction
    assert training in SINGLE_AGENT_INSTRUCTION


@pytest.mark.parametrize(
    "rule",
    [
        "at most 10 distinct exercises",
        "at most 2 of them in WARMUP",
        "WARMUP first, then MAIN, then COOLDOWN",
        "within five minutes of the requested duration",
        "never include excluded IDs",
        "Select exercise IDs only from the supplied pool",
    ],
)
def test_baseline_instruction_keeps_every_planning_rule(rule: str) -> None:
    assert rule in SINGLE_AGENT_INSTRUCTION


def test_dropped_clauses_name_real_sentences_in_the_shipped_prompts() -> None:
    """The audit list has to be an audit, not decoration.

    Each entry must quote text that genuinely exists in a production prompt;
    otherwise the record of "what was removed" proves nothing.
    """

    shipped = " ".join(prompt.instruction for prompt in ROLE_PROMPTS.values())
    for clause, reason in _DROPPED_CLAUSES:
        assert clause in shipped, clause
        assert reason
        assert clause not in SINGLE_AGENT_INSTRUCTION


def test_baseline_mentions_recovery_and_feasibility_responsibilities() -> None:
    assert "Recovery perspective" in SINGLE_AGENT_INSTRUCTION
    assert "Feasibility perspective" in SINGLE_AGENT_INSTRUCTION


# -- fairness of the output schema --------------------------------------


def test_draft_schema_is_plan_spec_minus_only_orchestration_fields() -> None:
    plan_fields = set(PlanSpec.model_fields)
    draft_fields = set(SingleAgentPlanDraft.model_fields)
    missing = plan_fields - draft_fields
    assert missing == ARCHITECTURE_ONLY_PLAN_FIELDS | SERVER_OWNED_PLAN_FIELDS
    assert not draft_fields - plan_fields


def _first_exercise(payload: dict[str, object]) -> dict[str, object]:
    pool = payload["exercise_pool"]
    assert isinstance(pool, dict)
    exercises = pool["exercises"]
    assert isinstance(exercises, list)
    first = exercises[0]
    assert isinstance(first, dict)
    return first


# -- fairness of the retrieval payload ----------------------------------


def test_architecture_b_receives_the_production_pool_projection() -> None:
    scenario = build_scenario(GRAPH_CASES[0])
    payload = single_agent_payload(
        envelope=scenario.constraint_envelope,
        pool=scenario.exercise_pool,
        with_retrieved_detail=True,
    )
    assert payload["exercise_pool"] == project_exercise_pool(scenario.exercise_pool)


def test_architecture_a_sees_strictly_less_of_the_pool_than_b() -> None:
    scenario = build_scenario(GRAPH_CASES[0])
    envelope = scenario.constraint_envelope
    pool = scenario.exercise_pool
    thin = single_agent_payload(envelope=envelope, pool=pool, with_retrieved_detail=False)
    full = single_agent_payload(envelope=envelope, pool=pool, with_retrieved_detail=True)

    thin_exercise = _first_exercise(thin)
    full_exercise = _first_exercise(full)
    assert set(thin_exercise) < set(full_exercise)
    # The retrieval contribution being measured must be absent from A.
    for withheld in ("phase_codes", "role_eligibility_code", "fitt_context", "goal_codes"):
        assert withheld not in thin_exercise
        assert withheld in full_exercise


# -- the contract adapter invents nothing -------------------------------


def test_synthesized_advisory_proposals_carry_no_invented_advice() -> None:
    scenario = build_scenario(GRAPH_CASES[0])
    run = _run(ARCHITECTURE_SINGLE_AGENT_RAG, GRAPH_CASES[0], Script())
    assert run.plan_spec is not None

    proposals = synthesize_proposals(
        envelope=scenario.constraint_envelope,
        pool=scenario.exercise_pool,
        prescriptions=run.plan_spec.exercise_prescriptions,
    )
    training, recovery, feasibility = proposals
    assert training.agent_type_code is SpecialistAgentTypeCode.TRAINING
    assert training.exercise_prescriptions == run.plan_spec.exercise_prescriptions
    for advisory in (recovery, feasibility):
        assert advisory.proposal_status_code is V3ProposalStatusCode.READY
        assert advisory.exercise_prescriptions == ()
        assert advisory.adjustment_codes == (NO_SPECIALIST_ADVICE_CODE,)


# -- the downstream gate is the same ------------------------------------


@pytest.mark.parametrize("architecture_code", COMPARED_ARCHITECTURES)
def test_every_architecture_produces_the_same_plan_from_the_same_script(
    architecture_code: str,
) -> None:
    """The plumbing must not advantage anyone.

    With one scripted answer driving all three, any difference in the compiled
    plan would come from the harness rather than from the architecture, and
    every later number would be measuring that difference instead.
    """

    reference = _run(ARCHITECTURE_MULTI_AGENT, GRAPH_CASES[0], Script())
    run = _run(architecture_code, GRAPH_CASES[0], Script())
    assert run.has_plan
    assert run.prescribed_exercise_ids == reference.prescribed_exercise_ids


@pytest.mark.parametrize(
    "architecture_code", [ARCHITECTURE_SINGLE_LLM, ARCHITECTURE_SINGLE_AGENT_RAG]
)
def test_baseline_cannot_prescribe_a_safety_excluded_exercise(
    architecture_code: str,
) -> None:
    """The enforcement point is shared, so a baseline is bound by it too."""

    case = EXCLUSION_CASES[0]
    run = _run(
        architecture_code,
        case,
        Script(training=ScriptCode.SAFETY_VIOLATING, coordinator=ScriptCode.SAFETY_VIOLATING),
    )
    excluded = build_scenario(case).excluded_exercise_ids
    assert not excluded & set(run.prescribed_exercise_ids)
    evaluation = evaluate_case(run)
    assert not evaluation.critical_failures


@pytest.mark.parametrize(
    "architecture_code", [ARCHITECTURE_SINGLE_LLM, ARCHITECTURE_SINGLE_AGENT_RAG]
)
def test_baseline_rejecting_a_plan_falls_back_rather_than_returning_nothing(
    architecture_code: str,
) -> None:
    run = _run(
        architecture_code,
        GRAPH_CASES[0],
        Script(training=ScriptCode.POOL_ESCAPE, coordinator=ScriptCode.POOL_ESCAPE),
    )
    assert run.plan_spec is None
    if run.has_plan:
        assert run.used_fallback


# -- metrics decline to score absent questions --------------------------


def test_multi_agent_only_metrics_are_absent_for_a_baseline() -> None:
    baseline = build_agent_report(
        [_run(ARCHITECTURE_SINGLE_AGENT_RAG, GRAPH_CASES[0], Script())],
        architecture_code=ARCHITECTURE_SINGLE_AGENT_RAG,
        provider_label="scripted",
    )
    multi = build_agent_report(
        [_run(ARCHITECTURE_MULTI_AGENT, GRAPH_CASES[0], Script())],
        architecture_code=ARCHITECTURE_MULTI_AGENT,
        provider_label="scripted",
    )

    assert baseline.agent_role_consistency is None
    assert baseline.state_consistency is None
    assert multi.agent_role_consistency == 1.0
    assert multi.state_consistency == 1.0
    # The metrics both architectures can answer stay answered.
    assert baseline.safety_compliance_rate is not None
    assert baseline.workflow_completion_rate is not None


def test_a_single_call_is_not_scored_as_a_missed_invocation() -> None:
    report = build_agent_report(
        [_run(ARCHITECTURE_SINGLE_LLM, GRAPH_CASES[0], Script())],
        architecture_code=ARCHITECTURE_SINGLE_LLM,
        provider_label="scripted",
    )
    assert report.agent_invocation_accuracy == 1.0


# -- the judge is blinded -----------------------------------------------


def test_blind_judge_payload_hides_the_field_that_identifies_the_architecture() -> None:
    run = _run(ARCHITECTURE_MULTI_AGENT, GRAPH_CASES[0], Script())
    assert "advisory_codes" in build_judge_payload(run)
    assert "advisory_codes" not in build_judge_payload(run, blind=True)


def test_blind_payloads_do_not_differ_in_shape_between_architectures() -> None:
    multi = build_judge_payload(
        _run(ARCHITECTURE_MULTI_AGENT, GRAPH_CASES[0], Script()), blind=True
    )
    single = build_judge_payload(
        _run(ARCHITECTURE_SINGLE_AGENT_RAG, GRAPH_CASES[0], Script()), blind=True
    )
    assert set(multi) == set(single)


# -- the report itself ---------------------------------------------------


def test_comparison_report_separates_model_plans_from_fallback_delivery() -> None:
    """`llm_plan_rate` must not absorb the deterministic fallback's work."""

    good = _run(ARCHITECTURE_SINGLE_AGENT_RAG, GRAPH_CASES[0], Script())
    fell_back = _run(
        ARCHITECTURE_SINGLE_AGENT_RAG,
        GRAPH_CASES[0],
        Script(training=ScriptCode.POOL_ESCAPE, coordinator=ScriptCode.POOL_ESCAPE),
    )
    if not fell_back.has_plan:
        pytest.skip("this case has no viable deterministic fallback")

    result = ArchitectureResult(
        architecture_code=ARCHITECTURE_SINGLE_AGENT_RAG,
        model_label="scripted",
        runs=[good, fell_back],
        evaluations=[evaluate_case(good), evaluate_case(fell_back)],
    )
    assert result.plan_delivery_rate == 1.0
    assert result.llm_plan_rate == 0.5


def test_report_records_the_fairness_conditions_and_its_own_caveats() -> None:
    report = ComparisonReport(notes=("blind judge",))
    body = report.to_json()
    conditions = body["fairness_conditions"]
    assert isinstance(conditions, dict)
    assert conditions["output_schema"]
    assert body["judge_blind"] is True
    assert body["notes"] == ["blind judge"]
