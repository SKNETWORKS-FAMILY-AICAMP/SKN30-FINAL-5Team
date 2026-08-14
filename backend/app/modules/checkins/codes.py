from enum import StrEnum

DAILY_CONTEXT_RESPONSE_SCHEMA_VERSION = "daily-context-response-v1"
DAILY_CONTEXT_ENDPOINT_CODE = "PUT_DAILY_CONTEXT"


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


__all__ = [
    "DAILY_CONTEXT_ENDPOINT_CODE",
    "DAILY_CONTEXT_RESPONSE_SCHEMA_VERSION",
    "DiscomfortSeverityCode",
    "DurationAdjustmentSourceCode",
    "FatigueLevelCode",
]
