from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DecisionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_date: date
    daily_context_id: UUID
    expected_context_version: int = Field(gt=0)


class DecisionRegenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_plan_id: UUID
    expected_regeneration_sequence: Literal[0, 1]


class DecisionPlanItem(BaseModel):
    plan_item_id: UUID
    exercise_id: UUID
    exercise_name: str
    sequence: int
    # Optional with a default so payloads stored before the plan carried a
    # session shape still validate; new plans always set it explicitly.
    phase_code: str = "MAIN"
    tier_code: str
    sets: int
    reps: int | None
    work_seconds: int
    rest_seconds: int
    transition_seconds: int
    estimated_item_seconds: int
    instruction_available: bool
    mascot_animation_asset_key: str | None = None
    replacement_of_exercise_id: UUID | None = None


class DecisionPlan(BaseModel):
    plan_id: UUID
    # How many times the user has edited this plan. Zero means untouched, and it is the
    # token the edit endpoints check, so a client that reloads the plan can keep editing.
    plan_revision: int = 0
    action_code: str
    training_type_code: str
    body_focus_code: str | None
    requested_duration_minutes: int
    estimated_duration_seconds: int
    expected_duration_min_seconds: int | None = None
    expected_duration_max_seconds: int | None = None
    duration_estimation_policy_version: str | None = None
    estimated_calories_burned: float | None
    setup_seconds: int
    warmup_seconds: int
    cooldown_seconds: int
    items: list[DecisionPlanItem]


class PlanItemSetRepetitionRequest(BaseModel):
    """One item's volume, replaced by the user's own numbers.

    The location is deliberately absent, and `extra="forbid"` rejects a client that
    sends one: a set-count edit is not where the approved location changes.

    The bounds are input sanity, not a training or medical threshold. Nothing in the
    reviewed data approves a per-item ceiling for a user edit, so the only thing being
    asserted is that the request is a plausible one; `DOMAIN_RULES.md` 11.2's volume
    ceiling for user edits is still an open question.
    """

    model_config = ConfigDict(extra="forbid")

    expected_plan_id: UUID
    expected_plan_revision: int = Field(ge=0)
    sets: int = Field(ge=1)
    # Required for a repetition-based item and rejected for a duration-based one; the
    # service decides which, because only the stored plan knows the item's timing mode.
    reps: int | None = Field(default=None, ge=1)


class PlanItemOrderRequest(BaseModel):
    """The order the user wants, as the full list of the items they may move.

    Before the session starts that is every item. Once blocks have been completed it is
    the incomplete ones only: finished blocks keep the positions they were performed in.
    """

    model_config = ConfigDict(extra="forbid")

    expected_plan_id: UUID
    expected_plan_revision: int = Field(ge=0)
    ordered_plan_item_ids: list[UUID] = Field(min_length=1)


class PlanRevisionResponse(BaseModel):
    """The plan as it now stands, plus the token the next edit has to present."""

    decision_id: UUID
    plan_revision: int
    final_plan: DecisionPlan


class DecisionOptionResponse(BaseModel):
    option_id: UUID
    option_code: Literal["FINAL_ROUTINE", "REST"]
    action_code: str
    plan_id: UUID | None = None
    selectable: bool = True
    blocked_reason_code: str | None = None


class PublicAgentSummary(BaseModel):
    agent_type_code: str
    recommendation_code: str | None
    reason_codes: list[str]
    summary: str


class SafetySummary(BaseModel):
    safety_status_code: str
    vetoed: bool
    reason_codes: list[str]
    summary: str


class Guidance(BaseModel):
    code: str
    title: str
    message: str
    tone_code: Literal["SERIOUS", "NEUTRAL"]


class DecisionResponse(BaseModel):
    decision_id: UUID
    local_date: date
    status_code: Literal["COMPLETED"]
    safety_status_code: Literal["PASS", "REVISE", "BLOCKED"]
    action_code: str
    requested_duration_minutes: int
    duration_adjustment_source_code: str
    final_plan: DecisionPlan | None
    options: list[DecisionOptionResponse]
    reason_codes: list[str]
    adjustment_reason_codes: list[str] | None = None
    summary: str
    guidance: Guidance | None = None
    public_agent_summaries: list[PublicAgentSummary] | None = None
    safety_summary: SafetySummary | None = None
    generation_mode_code: Literal["ORIGINAL", "REGENERATED"] | None = None
    decision_engine_code: (
        Literal["DETERMINISTIC", "LLM_MULTI_AGENT", "DETERMINISTIC_FALLBACK"] | None
    ) = None
    root_decision_id: UUID | None = None
    parent_decision_id: UUID | None = None
    regeneration_sequence: Literal[0, 1, 2] | None = None
    meaningful_difference_codes: (
        list[
            Literal[
                "CORE_EXERCISE_CHANGED",
                "SET_REP_STRUCTURE_CHANGED",
                "EXERCISE_ORDER_CHANGED",
                "ROUTINE_STRUCTURE_CHANGED",
            ]
        ]
        | None
    ) = None
    created_at: datetime


__all__ = [
    "DecisionCreateRequest",
    "DecisionPlan",
    "DecisionRegenerationRequest",
    "DecisionResponse",
    "PlanItemOrderRequest",
    "PlanItemSetRepetitionRequest",
    "PlanRevisionResponse",
]
