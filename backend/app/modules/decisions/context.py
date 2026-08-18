from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DecisionContext:
    local_date: date
    daily_context_id: UUID
    context_version: int
    fatigue_level_code: str
    requested_duration_minutes: int
    duration_adjustment_source_code: str
    location_code: str
    sleep_minutes: int | None
    fasting_state_code: str | None
    hydration_state_code: str | None
    discomforts: tuple[tuple[str, str], ...]
    adverse_reaction_codes: tuple[str, ...]
    profile_duration_minutes: int
    primary_goal_code: str
    experience_level_code: str
    equipment_codes: tuple[str, ...]
    attention_area_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attention_area_codes",
            tuple(sorted(set(self.attention_area_codes))),
        )

    def snapshot(self) -> dict[str, object]:
        return {
            "local_date": self.local_date.isoformat(),
            "daily_context_id": str(self.daily_context_id),
            "context_version": self.context_version,
            "fatigue_level_code": self.fatigue_level_code,
            "requested_duration_minutes": self.requested_duration_minutes,
            "duration_adjustment_source_code": self.duration_adjustment_source_code,
            "location_code": self.location_code,
            "sleep_minutes": self.sleep_minutes,
            "fasting_state_code": self.fasting_state_code,
            "hydration_state_code": self.hydration_state_code,
            "discomforts": [
                {"body_area_code": area, "severity_code": severity}
                for area, severity in self.discomforts
            ],
            "adverse_reaction_codes": list(self.adverse_reaction_codes),
            "profile": {
                "primary_goal_code": self.primary_goal_code,
                "experience_level_code": self.experience_level_code,
                "default_requested_duration_minutes": self.profile_duration_minutes,
                "equipment_codes": list(self.equipment_codes),
                "attention_area_codes": list(self.attention_area_codes),
            },
        }
