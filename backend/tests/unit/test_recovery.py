import pytest

from backend.app.domain.rules.recovery import RecoveryLevelCode, recovery_level


@pytest.mark.parametrize(
    ("sleep_minutes", "fatigue_level_code", "expected"),
    [
        (420, "LOW", RecoveryLevelCode.NORMAL),
        (360, "LOW", RecoveryLevelCode.NORMAL),
        (359, "LOW", RecoveryLevelCode.LIGHT),
        (420, "MODERATE", RecoveryLevelCode.NORMAL),
        (360, "MODERATE", RecoveryLevelCode.LIGHT),
        (359, "MODERATE", RecoveryLevelCode.VERY_LIGHT),
        (420, "HIGH", RecoveryLevelCode.LIGHT),
        (360, "HIGH", RecoveryLevelCode.VERY_LIGHT),
        (359, "HIGH", RecoveryLevelCode.VERY_LIGHT),
        (None, "LOW", RecoveryLevelCode.NORMAL),
        (None, "MODERATE", RecoveryLevelCode.LIGHT),
        (None, "HIGH", RecoveryLevelCode.VERY_LIGHT),
    ],
)
def test_sleep_and_fatigue_matrix(
    sleep_minutes: int | None, fatigue_level_code: str, expected: RecoveryLevelCode
) -> None:
    assert (
        recovery_level(sleep_minutes=sleep_minutes, fatigue_level_code=fatigue_level_code)
        is expected
    )


def test_unapproved_fatigue_code_is_rejected() -> None:
    with pytest.raises(ValueError):
        recovery_level(sleep_minutes=420, fatigue_level_code="UNKNOWN")
