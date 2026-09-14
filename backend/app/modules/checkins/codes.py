from enum import StrEnum

from backend.app.domain.rules.safety import NRS_PAIN_POLICY_VERSION

DAILY_CONTEXT_RESPONSE_SCHEMA_VERSION = "daily-context-response-v2"
DAILY_CONTEXT_ENDPOINT_CODE = "PUT_DAILY_CONTEXT"
DAILY_PAIN_POLICY_VERSION = NRS_PAIN_POLICY_VERSION


class FatigueLevelCode(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class DurationAdjustmentSourceCode(StrEnum):
    PROFILE = "PROFILE"
    USER_OVERRIDE = "USER_OVERRIDE"


class DiscomfortSeverityCode(StrEnum):
    MILD = "MILD"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"


class SleepSourceCode(StrEnum):
    MANUAL = "MANUAL"
    WEARABLE = "WEARABLE"


__all__ = [
    "DAILY_CONTEXT_ENDPOINT_CODE",
    "DAILY_CONTEXT_RESPONSE_SCHEMA_VERSION",
    "DAILY_PAIN_POLICY_VERSION",
    "DiscomfortSeverityCode",
    "DurationAdjustmentSourceCode",
    "FatigueLevelCode",
    "SleepSourceCode",
]
