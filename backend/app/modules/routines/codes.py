from enum import StrEnum

ROUTINE_RESPONSE_SCHEMA_VERSION = "1.0"


class RoutineStatusCode(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class RoutinePhaseCode(StrEnum):
    WARMUP = "WARMUP"
    MAIN = "MAIN"
    COOLDOWN = "COOLDOWN"


class RoutineTierCode(StrEnum):
    CORE = "CORE"
    SUPPORT = "SUPPORT"
    OPTIONAL = "OPTIONAL"


class ScheduleRuleCode(StrEnum):
    ROTATION = "ROTATION"


__all__ = [
    "ROUTINE_RESPONSE_SCHEMA_VERSION",
    "RoutinePhaseCode",
    "RoutineStatusCode",
    "RoutineTierCode",
    "ScheduleRuleCode",
]
