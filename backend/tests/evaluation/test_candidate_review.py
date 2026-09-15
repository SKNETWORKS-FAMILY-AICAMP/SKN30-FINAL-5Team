"""Free structural and safety checks for the ADR-0025 experiment."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.v3_compiler import compile_plan
from backend.app.domain.agents.v3_contracts import CoordinatorInput, ExercisePrescription
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationContext,
    IntegrityValidationStatusCode,
    validate_plan_integrity,
)
from backend.tests.evaluation.candidate_review import (
    AdjustmentCode,
    BoundedAdjustment,
    CandidateDraft,
    CandidateReview,
    CandidateSelection,
    CandidateSet,
    materialize_selection,
)
from backend.tests.evaluation.dataset import EvaluationCase
from backend.tests.evaluation.harness import EXCLUSION_CASES, GRAPH_CASES
from backend.tests.evaluation.runners.fake_chat import Script
from backend.tests.evaluation.runners.run_multi_agent import MultiAgentRunner
from backend.tests.evaluation.scenario import Scenario, build_scenario


def _context(
    case: EvaluationCase = GRAPH_CASES[0],
) -> tuple[Scenario, tuple[ExercisePrescription, ...], CoordinatorInput]:
    scenario = build_scenario(case)
    run = asyncio.run(MultiAgentRunner().run_scenario(scenario, Script()))
    assert run.plan_spec is not None
    assert len(run.graph_result.round_one_proposals) == 3
    coordinator_input = CoordinatorInput(
        constraint_envelope=scenario.constraint_envelope,
        exercise_pool=scenario.exercise_pool,
        proposals=run.graph_result.round_one_proposals,
        repair_attempt=0,
        repair_violation_codes=(),
    )
    return scenario, run.plan_spec.exercise_prescriptions, coordinator_input


def _different_prescriptions(
    prescriptions: tuple[ExercisePrescription, ...],
) -> tuple[ExercisePrescription, ...]:
    first, *remaining = prescriptions
    changed = first.model_copy(
        update={"rest_seconds_between_sets": first.rest_seconds_between_sets + 1}
    )
    return (changed, *remaining)


def _candidate_set(
    case: EvaluationCase = GRAPH_CASES[0],
) -> tuple[Scenario, CandidateSet, CoordinatorInput]:
    scenario, prescriptions, coordinator_input = _context(case)
    goal = CandidateDraft.create(
        candidate_code="GOAL_FOCUSED",
        objective_code="GOAL_PRESERVATION",
        exercise_prescriptions=prescriptions,
    )
    recovery = CandidateDraft.create(
        candidate_code="RECOVERY_FOCUSED",
        objective_code="RECOVERY_LOAD",
        exercise_prescriptions=_different_prescriptions(prescriptions),
    )
    candidates = CandidateSet.create(
        envelope_hash=scenario.constraint_envelope.envelope_hash,
        pool_hash=scenario.exercise_pool.pool_hash,
        requested_duration_minutes=scenario.constraint_envelope.requested_duration_minutes,
        baseline_candidate_code=goal.candidate_code,
        candidates=(goal, recovery),
    )
    return scenario, candidates, coordinator_input


def _reviews(
    candidates: CandidateSet,
    *,
    recovery_adjustments: tuple[BoundedAdjustment, ...] = (),
    disagree: bool = False,
) -> tuple[CandidateReview, CandidateReview]:
    recovery_ranking = ("RECOVERY_FOCUSED", "GOAL_FOCUSED")
    feasibility_ranking = ("GOAL_FOCUSED", "RECOVERY_FOCUSED") if disagree else recovery_ranking
    return (
        CandidateReview.create(
            role_code="RECOVERY",
            candidate_set_hash=candidates.candidate_set_hash,
            ranked_candidate_codes=recovery_ranking,
            adjustments=recovery_adjustments,
            review_codes=("RECOVERY_PREFERS_LOWER_LOAD",),
        ),
        CandidateReview.create(
            role_code="FEASIBILITY",
            candidate_set_hash=candidates.candidate_set_hash,
            ranked_candidate_codes=feasibility_ranking,
            review_codes=("FEASIBILITY_REVIEWED",),
        ),
    )


def _selection(candidates: CandidateSet, *adjustment_ids: str) -> CandidateSelection:
    return CandidateSelection.create(
        candidate_set_hash=candidates.candidate_set_hash,
        selected_candidate_code="RECOVERY_FOCUSED",
        accepted_adjustment_ids=tuple(sorted(adjustment_ids)),
        decision_codes=("CROSS_REVIEW_CONSIDERED",),
    )


def test_candidate_set_rejects_cosmetic_duplicate_plans() -> None:
    scenario, prescriptions, _ = _context()
    first = CandidateDraft.create(
        candidate_code="FIRST",
        objective_code="GOAL_PRESERVATION",
        exercise_prescriptions=prescriptions,
    )
    second = CandidateDraft.create(
        candidate_code="SECOND",
        objective_code="RECOVERY_LOAD",
        exercise_prescriptions=prescriptions,
    )

    with pytest.raises(ValidationError, match="materially different"):
        CandidateSet.create(
            envelope_hash=scenario.constraint_envelope.envelope_hash,
            pool_hash=scenario.exercise_pool.pool_hash,
            requested_duration_minutes=scenario.constraint_envelope.requested_duration_minutes,
            baseline_candidate_code="FIRST",
            candidates=(first, second),
        )


def test_cross_review_selection_reuses_common_compiler_and_validator() -> None:
    scenario, candidates, coordinator_input = _candidate_set()
    outcome = materialize_selection(
        candidate_set=candidates,
        reviews=_reviews(candidates, disagree=True),
        selection=_selection(candidates),
        coordinator_input=coordinator_input,
    )

    selected = next(
        item for item in candidates.candidates if item.candidate_code == "RECOVERY_FOCUSED"
    )
    assert outcome.plan_spec.exercise_prescriptions == selected.exercise_prescriptions
    assert outcome.selection_changed is True
    assert outcome.specialist_disagreement is True
    compiled = compile_plan(
        outcome.plan_spec,
        envelope=scenario.constraint_envelope,
        pool=scenario.exercise_pool,
        compiler_version="eval-candidate-compiler-v1",
        coordinator_input=coordinator_input,
    )
    validation = validate_plan_integrity(
        compiled,
        envelope=scenario.constraint_envelope,
        pool=scenario.exercise_pool,
        repair_attempt=0,
        validator_version="eval-candidate-validator-v1",
        context=IntegrityValidationContext(),
    )
    assert validation.status_code is IntegrityValidationStatusCode.PASS


def test_coordinator_cannot_invent_an_adjustment() -> None:
    _, candidates, coordinator_input = _candidate_set()
    with pytest.raises(ValueError, match="no specialist submitted"):
        materialize_selection(
            candidate_set=candidates,
            reviews=_reviews(candidates),
            selection=_selection(candidates, "INVENTED_ADJUSTMENT"),
            coordinator_input=coordinator_input,
        )


def test_review_originated_bounded_adjustment_is_applied_server_side() -> None:
    _, candidates, coordinator_input = _candidate_set()
    selected = next(
        item for item in candidates.candidates if item.candidate_code == "RECOVERY_FOCUSED"
    )
    current_rest = selected.exercise_prescriptions[0].rest_seconds_between_sets
    adjustment = BoundedAdjustment(
        adjustment_id="RECOVERY_REST_1",
        candidate_code=selected.candidate_code,
        prescription_sequence=1,
        adjustment_code=AdjustmentCode.INCREASE_REST,
        value=current_rest + 1,
    )
    outcome = materialize_selection(
        candidate_set=candidates,
        reviews=_reviews(candidates, recovery_adjustments=(adjustment,)),
        selection=_selection(candidates, adjustment.adjustment_id),
        coordinator_input=coordinator_input,
    )

    assert outcome.applied_adjustment_ids == (adjustment.adjustment_id,)
    assert outcome.plan_spec.exercise_prescriptions[0].rest_seconds_between_sets == (
        current_rest + 1
    )
    assert outcome.plan_spec.action_code.value == "DOWNSHIFT"


@pytest.mark.parametrize(
    ("code", "value", "message"),
    [
        (AdjustmentCode.REDUCE_SETS, 999, "strictly reduce"),
        (AdjustmentCode.REDUCE_REPETITIONS, 999, "strictly reduce"),
        (AdjustmentCode.INCREASE_REST, 1, "strictly increase"),
    ],
)
def test_bounded_adjustment_cannot_relax_its_declared_direction(
    code: AdjustmentCode, value: int, message: str
) -> None:
    _, candidates, coordinator_input = _candidate_set()
    adjustment = BoundedAdjustment(
        adjustment_id="RECOVERY_CHANGE_1",
        candidate_code="RECOVERY_FOCUSED",
        prescription_sequence=1,
        adjustment_code=code,
        value=value,
    )
    with pytest.raises(ValueError, match=message):
        materialize_selection(
            candidate_set=candidates,
            reviews=_reviews(candidates, recovery_adjustments=(adjustment,)),
            selection=_selection(candidates, adjustment.adjustment_id),
            coordinator_input=coordinator_input,
        )


def test_conflicting_review_adjustments_are_rejected() -> None:
    _, candidates, coordinator_input = _candidate_set()
    first = BoundedAdjustment(
        adjustment_id="RECOVERY_REST_1",
        candidate_code="RECOVERY_FOCUSED",
        prescription_sequence=1,
        adjustment_code=AdjustmentCode.INCREASE_REST,
        value=120,
    )
    second = BoundedAdjustment(
        adjustment_id="FEASIBILITY_REST_1",
        candidate_code="RECOVERY_FOCUSED",
        prescription_sequence=1,
        adjustment_code=AdjustmentCode.INCREASE_REST,
        value=180,
    )
    recovery, feasibility = _reviews(candidates, recovery_adjustments=(first,))
    feasibility = CandidateReview.create(
        role_code="FEASIBILITY",
        candidate_set_hash=candidates.candidate_set_hash,
        ranked_candidate_codes=feasibility.ranked_candidate_codes,
        adjustments=(second,),
        review_codes=("FEASIBILITY_REVIEWED",),
    )
    with pytest.raises(ValueError, match="same field"):
        materialize_selection(
            candidate_set=candidates,
            reviews=(recovery, feasibility),
            selection=_selection(candidates, first.adjustment_id, second.adjustment_id),
            coordinator_input=coordinator_input,
        )


def test_selected_safety_excluded_exercise_never_becomes_a_plan() -> None:
    case = EXCLUSION_CASES[0]
    scenario, candidates, coordinator_input = _candidate_set(case)
    unsafe_id = scenario.constraint_envelope.excluded_exercise_ids[0]
    unsafe_source = candidates.candidates[1]
    prescriptions = list(unsafe_source.exercise_prescriptions)
    main_index = next(
        index for index, item in enumerate(prescriptions) if item.phase_code == "MAIN"
    )
    prescriptions[main_index] = prescriptions[main_index].model_copy(
        update={"exercise_id": unsafe_id}
    )
    unsafe = CandidateDraft.create(
        candidate_code=unsafe_source.candidate_code,
        objective_code=unsafe_source.objective_code,
        exercise_prescriptions=tuple(prescriptions),
    )
    tampered = CandidateSet.create(
        envelope_hash=candidates.envelope_hash,
        pool_hash=candidates.pool_hash,
        requested_duration_minutes=candidates.requested_duration_minutes,
        baseline_candidate_code=candidates.baseline_candidate_code,
        candidates=(candidates.candidates[0], unsafe),
    )

    with pytest.raises(ValueError, match="Safety exclusions"):
        materialize_selection(
            candidate_set=tampered,
            reviews=_reviews(tampered),
            selection=_selection(tampered),
            coordinator_input=coordinator_input,
        )
