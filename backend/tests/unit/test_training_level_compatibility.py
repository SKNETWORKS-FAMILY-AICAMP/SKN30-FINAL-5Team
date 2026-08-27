import pytest

from backend.app.domain.rules.training_level import (
    allowed_exercise_difficulty_codes,
    is_exercise_allowed_for_user,
    is_exercise_prescription_compatible,
)


def test_beginner_user_allows_only_beginner_exercises() -> None:
    assert allowed_exercise_difficulty_codes("BEGINNER") == ("BEGINNER",)
    assert is_exercise_allowed_for_user(
        exercise_difficulty_code="BEGINNER",
        user_experience_level_code="BEGINNER",
    )
    assert not is_exercise_allowed_for_user(
        exercise_difficulty_code="INTERMEDIATE",
        user_experience_level_code="BEGINNER",
    )


def test_intermediate_user_allows_beginner_and_intermediate_exercises() -> None:
    assert allowed_exercise_difficulty_codes("INTERMEDIATE") == (
        "BEGINNER",
        "INTERMEDIATE",
    )
    assert all(
        is_exercise_allowed_for_user(
            exercise_difficulty_code=difficulty,
            user_experience_level_code="INTERMEDIATE",
        )
        for difficulty in ("BEGINNER", "INTERMEDIATE")
    )


@pytest.mark.parametrize(
    ("exercise_difficulty", "prescription_experience", "expected"),
    (
        ("BEGINNER", "BEGINNER", True),
        ("BEGINNER", "INTERMEDIATE", True),
        ("INTERMEDIATE", "INTERMEDIATE", True),
        ("INTERMEDIATE", "BEGINNER", False),
    ),
)
def test_exercise_prescription_directional_compatibility(
    exercise_difficulty: str,
    prescription_experience: str,
    expected: bool,
) -> None:
    assert (
        is_exercise_prescription_compatible(
            exercise_difficulty_code=exercise_difficulty,
            prescription_experience_level_code=prescription_experience,
        )
        is expected
    )
