from uuid import UUID

from backend.app.db.repositories.vector_index import IndexableExerciseRecord
from backend.scripts.compare_single_multi_agent import (
    ArchitectureResult,
    build_scenarios,
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
        "LIMITED_TIME_GENERAL_20",
        "FATIGUE_GENERAL_30",
        "HEALTHY_MUSCLE_30",
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


def test_summarize_keeps_architecture_cost_and_quality_separate() -> None:
    results = (
        ArchitectureResult(
            "CASE_A",
            "SINGLE_TRAINING",
            True,
            True,
            "COMPLETED",
            None,
            (),
            False,
            1,
            100,
            20,
            1000,
            1800,
            0,
            3,
            ("COOLDOWN", "MAIN", "WARMUP"),
        ),
        ArchitectureResult(
            "CASE_A",
            "MULTI_V3",
            True,
            True,
            "COMPLETED",
            None,
            (),
            False,
            4,
            400,
            80,
            2000,
            1800,
            0,
            3,
            ("COOLDOWN", "MAIN", "WARMUP"),
        ),
    )

    summary = summarize(results)

    assert summary["SINGLE_TRAINING"]["completed_count"] == 1
    assert summary["SINGLE_TRAINING"]["provider_call_count"] == 1
    assert summary["MULTI_V3"]["integrity_pass_count"] == 1
    assert summary["MULTI_V3"]["provider_call_count"] == 4
