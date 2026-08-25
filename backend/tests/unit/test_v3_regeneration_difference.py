from backend.app.domain.agents.v3_compiler import CompiledPlan, compile_plan
from backend.app.domain.agents.v3_contracts import CoordinatorInput, PlanActionCode, PlanSpec
from backend.app.domain.agents.v3_orchestration import (
    RegenerationDifferenceCode,
    evaluate_regeneration_difference,
)
from backend.tests.unit.test_v3_agent_contracts import A, B, envelope, pool, prescription
from backend.tests.unit.test_v3_coordinator_contracts import coordinator_input, plan

COMPILER_VERSION = "v3-plan-compiler-v1"


def compile_source(source: PlanSpec, current_input: CoordinatorInput) -> CompiledPlan:
    return compile_plan(
        source,
        envelope=current_input.constraint_envelope,
        pool=current_input.exercise_pool,
        compiler_version=COMPILER_VERSION,
        coordinator_input=current_input,
    )


def replace_plan(source: PlanSpec, **updates: object) -> PlanSpec:
    payload = source.model_dump(exclude={"plan_hash"})
    payload.update(updates)
    return PlanSpec.create(**payload)


def test_exact_duplicate_and_summary_only_change_are_not_meaningful() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    source = plan(current_input)
    previous = compile_source(source, current_input)
    summary_only = compile_source(
        replace_plan(source, public_summary_code="ANOTHER_PUBLIC_CODE"), current_input
    )

    exact = evaluate_regeneration_difference(previous, previous, generation_sequence=1)
    summary = evaluate_regeneration_difference(previous, summary_only, generation_sequence=1)

    assert exact.difference_codes == (RegenerationDifferenceCode.EXACT_DUPLICATE,)
    assert summary.difference_codes == (RegenerationDifferenceCode.EXACT_DUPLICATE,)
    assert not exact.meaningful
    assert not summary.meaningful


def test_exercise_sequence_and_set_rep_changes_are_meaningful() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    previous = compile_source(plan(current_input), current_input)
    reordered = compile_source(
        plan(
            current_input,
            plan_prescriptions=(prescription(B, 1), prescription(A, 2)),
        ),
        current_input,
    )
    adjusted = compile_source(
        plan(
            current_input,
            plan_prescriptions=(prescription(A, 1, sets=2), prescription(B, 2)),
        ),
        current_input,
    )

    sequence_result = evaluate_regeneration_difference(previous, reordered, generation_sequence=1)
    structure_result = evaluate_regeneration_difference(previous, adjusted, generation_sequence=2)

    assert sequence_result.difference_codes == (
        RegenerationDifferenceCode.EXERCISE_SEQUENCE_CHANGED,
    )
    assert structure_result.difference_codes == (
        RegenerationDifferenceCode.SET_REPETITION_STRUCTURE_CHANGED,
    )
    assert sequence_result.meaningful
    assert structure_result.meaningful


def test_core_exercise_or_composition_change_is_meaningful() -> None:
    current_envelope = envelope(mandatory_ids=())
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    source = plan(current_input)
    previous = compile_source(source, current_input)
    exercise_changed = compile_source(
        plan(current_input, plan_prescriptions=(prescription(A, 1),)), current_input
    )
    composition_changed = compile_source(
        replace_plan(source, action_code=PlanActionCode.CHANGE), current_input
    )

    exercise_result = evaluate_regeneration_difference(
        previous, exercise_changed, generation_sequence=1
    )
    composition_result = evaluate_regeneration_difference(
        previous, composition_changed, generation_sequence=1
    )

    assert RegenerationDifferenceCode.CORE_EXERCISE_CHANGED in exercise_result.difference_codes
    assert composition_result.difference_codes == (
        RegenerationDifferenceCode.ROUTINE_COMPOSITION_CHANGED,
    )


def test_time_only_change_is_not_meaningful_without_an_approved_threshold() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    previous = compile_source(plan(current_input), current_input)
    time_only = compile_source(
        plan(
            current_input,
            plan_prescriptions=(
                prescription(A, 1).model_copy(update={"transition_seconds": 16}),
                prescription(B, 2),
            ),
        ),
        current_input,
    )

    result = evaluate_regeneration_difference(previous, time_only, generation_sequence=1)

    assert result.difference_codes == (RegenerationDifferenceCode.NO_MEANINGFUL_DIFFERENCE,)
    assert not result.meaningful


def test_third_generation_is_rejected_with_stable_code() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    compiled = compile_source(plan(current_input), current_input)

    result = evaluate_regeneration_difference(compiled, compiled, generation_sequence=3)

    assert result.difference_codes == (RegenerationDifferenceCode.REGENERATION_LIMIT_REACHED,)
    assert not result.meaningful
