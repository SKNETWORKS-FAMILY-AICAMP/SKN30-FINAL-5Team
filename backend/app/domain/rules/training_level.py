"""Deterministic exercise-difficulty and FITT experience compatibility policy."""

from typing import Final

TRAINING_LEVEL_COMPATIBILITY_POLICY_VERSION: Final = "training-level-compatibility-v1"

_ALLOWED_EXERCISE_DIFFICULTIES: Final[dict[str, tuple[str, ...]]] = {
    "BEGINNER": ("BEGINNER",),
    "INTERMEDIATE": ("BEGINNER", "INTERMEDIATE"),
}


def allowed_exercise_difficulty_codes(experience_level_code: str) -> tuple[str, ...]:
    """Return cumulative exercise difficulties allowed for a user or FITT level."""

    return _ALLOWED_EXERCISE_DIFFICULTIES.get(experience_level_code, ())


def is_exercise_allowed_for_user(
    *, exercise_difficulty_code: str, user_experience_level_code: str
) -> bool:
    return exercise_difficulty_code in allowed_exercise_difficulty_codes(user_experience_level_code)


def is_exercise_prescription_compatible(
    *, exercise_difficulty_code: str, prescription_experience_level_code: str
) -> bool:
    """Allow FITT levels at or above the exercise's intrinsic difficulty."""

    return exercise_difficulty_code in allowed_exercise_difficulty_codes(
        prescription_experience_level_code
    )


__all__ = [
    "TRAINING_LEVEL_COMPATIBILITY_POLICY_VERSION",
    "allowed_exercise_difficulty_codes",
    "is_exercise_allowed_for_user",
    "is_exercise_prescription_compatible",
]
