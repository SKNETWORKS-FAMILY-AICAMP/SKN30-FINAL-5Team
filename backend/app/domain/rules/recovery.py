"""Deterministic daily Recovery level derived from sleep and reported fatigue."""

from enum import StrEnum

RECOVERY_POLICY_VERSION = "sleep-fatigue-recovery-v1"


class RecoveryLevelCode(StrEnum):
    NORMAL = "NORMAL"
    LIGHT = "LIGHT"
    VERY_LIGHT = "VERY_LIGHT"


def recovery_level(*, sleep_minutes: int | None, fatigue_level_code: str) -> RecoveryLevelCode:
    """Apply the approved sleep/fatigue matrix without treating missing sleep as rest."""

    matrix = {
        "LOW": (
            RecoveryLevelCode.NORMAL,
            RecoveryLevelCode.NORMAL,
            RecoveryLevelCode.LIGHT,
            RecoveryLevelCode.NORMAL,
        ),
        "MODERATE": (
            RecoveryLevelCode.NORMAL,
            RecoveryLevelCode.LIGHT,
            RecoveryLevelCode.VERY_LIGHT,
            RecoveryLevelCode.LIGHT,
        ),
        "HIGH": (
            RecoveryLevelCode.LIGHT,
            RecoveryLevelCode.VERY_LIGHT,
            RecoveryLevelCode.VERY_LIGHT,
            RecoveryLevelCode.VERY_LIGHT,
        ),
    }
    try:
        values = matrix[fatigue_level_code]
    except KeyError as exc:
        raise ValueError("fatigue_level_code is not approved") from exc
    if sleep_minutes is None:
        return values[3]
    if sleep_minutes >= 420:
        return values[0]
    if sleep_minutes >= 360:
        return values[1]
    return values[2]


__all__ = ["RECOVERY_POLICY_VERSION", "RecoveryLevelCode", "recovery_level"]
