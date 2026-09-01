from dataclasses import replace
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.db.repositories.vector_index import IndexableExerciseRecord
from backend.app.domain.agents.v3_contracts import ExercisePrescription, PlanActionCode
from backend.scripts.compare_single_multi_agent import (
    ArchitectureResult,
    SingleIntegratedPlan,
    blind_review_records,
    build_scenarios,
    suitability_assessment,
    summarize,
)


def _record(index: int, phase: str, *, goal: str = "GENERAL_FITNESS") -> IndexableExerciseRecord:
    exercise_id = UUID(int=index)
    return IndexableExerciseRecord(
        exercise_id=exercise_id,
        catalog_version_id=UUID(int=999),
        catalog_version_code="exercise-catalog-test-v1",
        catalog_manifest_hash="a" * 64,
        name_ko=f"운동 {index}",
        name_en=f"Exercise {index}",
        instruction_summary_ko="검증용 운동",
        instruction_content_version="content-v1",
        training_type_code="STRENGTH",
        body_focus_code="FULL_BODY",
        primary_movement_pattern_code="PUSH",
        difficulty_code="BEGINNER",
        recovery_eligible=True,
        review_status_code="DOMAIN_APPROVED",
        review_method_code="DOMAIN_REVIEWER",
        status_interpretation_code="PRODUCTION_APPROVED",
        production_eligible=True,
        goal_codes=(goal,),
        equipment_codes=("BODYWEIGHT",),
        location_codes=("HOME",),
        phase_codes=(phase,),
        prescription_experience_level_codes=("BEGINNER",),
        stable_code=f"exercise_{index}",
        timing_mode_code="REPS",
        default_seconds_per_rep=3,
        default_rest_seconds=30,
        default_transition_seconds=10,
        role_eligibility_code="CORE" if phase == "MAIN" else "SUPPORT",
    )


def test_build_scenarios_uses_the_same_approved_pool_contract_for_both_architectures() -> None:
    records = tuple(
        _record(index, phase, goal=goal)
        for goal_index, goal in enumerate(("GENERAL_FITNESS", "MUSCLE_GAIN"))
        for phase_index, phase in enumerate(("WARMUP", "MAIN", "COOLDOWN"))
        for index in range(
            1 + goal_index * 20 + phase_index * 4,
            5 + goal_index * 20 + phase_index * 4,
        )
    )

    scenarios = build_scenarios(records, catalog_version="exercise-catalog-test-v1")

    assert tuple(item.code for item in scenarios) == (
        "HEALTHY_GENERAL_30",
        "HEALTHY_MUSCLE_30",
        "LIMITED_TIME_GENERAL_20",
        "FATIGUE_GENERAL_30",
        "FATIGUE_LIMITED_GENERAL_20",
        "FATIGUE_MUSCLE_30",
    )
    assert tuple(item.group_code for item in scenarios) == (
        "BASELINE",
        "BASELINE",
        "SINGLE_CONSTRAINT",
        "SINGLE_CONSTRAINT",
        "JOINT_CONSTRAINT",
        "JOINT_CONSTRAINT",
    )
    for scenario in scenarios:
        assert scenario.pool.constraint_envelope_hash == scenario.envelope.envelope_hash
        assert scenario.pool.catalog_version == scenario.envelope.catalog_version
        assert {phase for item in scenario.pool.exercises for phase in item.phase_codes} == {
            "WARMUP",
            "MAIN",
            "COOLDOWN",
        }
        assert all("HOME" in item.location_codes for item in scenario.pool.exercises)


def _result(
    architecture: str,
    *,
    completed: bool = True,
    scenario_group: str = "JOINT_CONSTRAINT",
) -> ArchitectureResult:
    return ArchitectureResult(
        scenario_code="CASE_A",
        scenario_group_code=scenario_group,  # type: ignore[arg-type]
        repeat_index=1,
        architecture_code=architecture,  # type: ignore[arg-type]
        completed=completed,
        integrity_passed=completed,
        terminal_status_code="COMPLETED" if completed else "FAILED",
        failure_code=None if completed else "MODEL_FAILED",
        violation_codes=(),
        fallback_used=False,
        provider_call_count=1 if architecture == "SINGLE_INTEGRATED" else 4,
        input_token_count=100 if architecture == "SINGLE_INTEGRATED" else 400,
        output_token_count=20 if architecture == "SINGLE_INTEGRATED" else 80,
        latency_ms=1000 if architecture == "SINGLE_INTEGRATED" else 2000,
        estimated_duration_seconds=1800 if completed else None,
        duration_delta_seconds=0 if completed else None,
        exercise_count=3 if completed else 0,
        phase_codes=("COOLDOWN", "MAIN", "WARMUP") if completed else (),
        phase_complete=completed,
        goal_core_main_count=1 if completed else 0,
        recovery_eligible_percent=100 if completed else None,
        action_code="DOWNSHIFT" if completed else None,
        expected_action_matched=completed,
        exercise_codes=("warmup", "main", "cooldown") if completed else (),
        prescription_summaries=(
            ({"stable_code": "warmup", "phase_code": "WARMUP"},) if completed else ()
        ),
    )


def test_summarize_keeps_architecture_cost_and_quality_separate() -> None:
    results = (_result("SINGLE_INTEGRATED"), _result("MULTI_V3"))

    summary = summarize(results)

    assert summary["SINGLE_INTEGRATED"]["completed_count"] == 1
    assert summary["SINGLE_INTEGRATED"]["provider_call_count"] == 1
    assert summary["MULTI_V3"]["integrity_pass_count"] == 1
    assert summary["MULTI_V3"]["provider_call_count"] == 4
    assert summary["MULTI_V3"]["goal_preserved_count"] == 1
    assert summary["MULTI_V3"]["joint_constraint_completed_count"] == 1


def test_single_integrated_plan_requires_all_session_phases() -> None:
    prescription = ExercisePrescription(
        exercise_id=UUID(int=1),
        sequence=1,
        phase_code="MAIN",
        sets=2,
        repetitions_per_set=10,
        rest_seconds_between_sets=30,
        transition_seconds=10,
        intensity_code="LOW",
        location_code="HOME",
    )

    with pytest.raises(ValidationError, match="all session phases"):
        SingleIntegratedPlan(
            action_code=PlanActionCode.KEEP,
            exercise_prescriptions=(prescription,),
            decision_codes=("BASELINE_PLAN",),
        )


def test_blind_review_template_hides_architecture_labels_and_keeps_key_separate() -> None:
    reviews, keys = blind_review_records((_result("SINGLE_INTEGRATED"), _result("MULTI_V3")))

    assert len(reviews) == 1
    assert "architecture" not in str(reviews[0]).lower()
    assert reviews[0]["review"] == {
        "goal_preservation_winner": "PENDING",
        "recovery_appropriateness_winner": "PENDING",
        "feasibility_winner": "PENDING",
        "overall_winner": "PENDING",
        "reviewer_code": "PENDING",
    }
    assert {keys[0]["candidate_a_architecture"], keys[0]["candidate_b_architecture"]} == {
        "SINGLE_INTEGRATED",
        "MULTI_V3",
    }


def test_blind_review_excludes_unpaired_failures() -> None:
    reviews, keys = blind_review_records(
        (_result("SINGLE_INTEGRATED", completed=False), _result("MULTI_V3"))
    )

    assert reviews == ()
    assert keys == ()


def test_suitability_requires_baseline_parity_and_joint_constraint_advantage() -> None:
    results: list[ArchitectureResult] = []
    for repeat_index in range(1, 4):
        for group in ("BASELINE", "JOINT_CONSTRAINT"):
            for scenario_suffix in ("A", "B"):
                single = _result(
                    "SINGLE_INTEGRATED",
                    completed=group == "BASELINE",
                    scenario_group=group,
                )
                multi = _result("MULTI_V3", scenario_group=group)
                results.extend(
                    (
                        replace(
                            single,
                            scenario_code=f"{group}_{scenario_suffix}",
                            repeat_index=repeat_index,
                        ),
                        replace(
                            multi,
                            scenario_code=f"{group}_{scenario_suffix}",
                            repeat_index=repeat_index,
                        ),
                    )
                )

    assessment = suitability_assessment(tuple(results))

    assert assessment["automatic_evidence_status"] == "SUPPORTS_ROLE_SEPARATION"
    assert assessment["decision_rules"] == {
        "baseline_non_degradation": True,
        "joint_constraint_advantage": True,
        "blind_expert_review": "PENDING",
    }
    assert assessment["final_conclusion_status"] == "PENDING_BLIND_EXPERT_REVIEW"
