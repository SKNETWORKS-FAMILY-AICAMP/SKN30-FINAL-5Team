from backend.app.modules.workouts.calorie_met_mapping import (
    approved_met_value_for_exercise_name,
    approved_met_values_by_exercise_name,
)


def test_only_reviewed_production_met_mapping_is_loaded() -> None:
    values = approved_met_values_by_exercise_name()

    # The reviewed source has 208 rows; two duplicate source names have the same
    # approved value, yielding 206 unambiguous runtime name keys.
    assert len(values) == 206
    assert approved_met_value_for_exercise_name("barbell deadlift") is not None
    assert approved_met_value_for_exercise_name("not a reviewed exercise") is None
