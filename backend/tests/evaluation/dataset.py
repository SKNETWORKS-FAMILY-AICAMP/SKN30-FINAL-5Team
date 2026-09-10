"""Evaluation case schema and loader (service-quality evaluation, PHASE 1).

A case is a frozen, machine-checkable statement of what the service must and must
not do for one input.  Cases are strict on purpose: a dataset that silently
accepts an unknown field is a dataset whose results cannot be trusted, and a
case that carries a direct identifier would violate ``AGENTS.md`` section 8
before any test had run.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.tests.evaluation import catalog

DATASET_SCHEMA_VERSION: Final = "service-quality-case-v1"
DATASETS_DIR: Final = Path(__file__).parent / "datasets"

# Every evaluation run pins the same instant so a stored result stays replayable.
# This matches `v3_evaluation_fixtures.FIXED_TIME` so both harnesses agree.
FIXED_TIME: Final = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)

# Fields that must never appear anywhere in a case. Health and identity data do
# not belong in a fixture any more than in a log line (`AGENTS.md` section 8).
FORBIDDEN_INPUT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "birth_date",
        "birthdate",
        "date_of_birth",
        "age",
        "age_years",
        "email",
        "full_name",
        "name",
        "phone",
        "user_id",
        "device_id",
        "gps",
        "location_trace",
        "calendar_text",
        "raw_wearable_samples",
        "heart_rate_samples",
        "access_token",
        "refresh_token",
        "api_key",
    }
)


class CaseCategory(StrEnum):
    """The nine categories the master specification requires."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    CONFLICT = "conflict"
    SAFETY_CRITICAL = "safety_critical"
    RAG_RETRIEVAL = "rag_retrieval"
    MISSING_INPUT = "missing_input"
    INVALID_INPUT = "invalid_input"
    FAILURE_CASE = "failure_case"


class SafetyStatusExpectation(StrEnum):
    PASS = "PASS"
    REVISE = "REVISE"
    BLOCKED = "BLOCKED"


class RequiredActionExpectation(StrEnum):
    NONE = "NONE"
    REST = "REST"
    STOP_AND_SEEK_HELP = "STOP_AND_SEEK_HELP"


class ExpectedOutcome(StrEnum):
    """What the graph is allowed to end with for this case."""

    PLAN = "PLAN"
    """A compiled plan that satisfies every constraint."""

    NO_PLAN = "NO_PLAN"
    """A terminal result with no plan. Safety REST/STOP and fail-closed paths."""

    PLAN_OR_NO_PLAN = "PLAN_OR_NO_PLAN"
    """Either is acceptable; only the prohibited actions are asserted."""


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class UserInput(_Frozen):
    """Normalized check-in input. No direct identifiers, no raw health records."""

    requested_duration_minutes: int | None = Field(default=None, gt=0)
    primary_goal_code: str | None = None
    allowed_location_codes: tuple[str, ...] = ()
    available_equipment_codes: tuple[str, ...] = ()
    fatigue_code: str | None = None
    sleep_quality_code: str | None = None
    soreness_code: str | None = None
    discomfort_area_codes: tuple[str, ...] = ()
    discomfort_severity_code: str | None = None
    adverse_reaction_codes: tuple[str, ...] = ()
    red_flag_present: bool = False
    preferred_exercise_codes: tuple[str, ...] = ()
    wearable_connected: bool = False
    notes_code: str | None = None


class ExpectedConstraints(_Frozen):
    """The constraint envelope this input must produce."""

    requested_duration_minutes: int | None = Field(default=None, gt=0)
    duration_tolerance_seconds: int = Field(default=300, ge=0)
    primary_goal_code: str | None = None
    allowed_location_codes: tuple[str, ...] = ()
    allowed_equipment_codes: tuple[str, ...] = ()
    excluded_exercise_codes: tuple[str, ...] = ()
    mandatory_exercise_codes: tuple[str, ...] = ()
    plan_generation_allowed: bool = True
    maximum_sets_per_exercise: int | None = Field(default=None, gt=0)
    maximum_repetitions_per_set: int | None = Field(default=None, gt=0)
    allowed_intensity_codes: tuple[str, ...] = ("LOW", "MODERATE")
    allowed_load_codes: tuple[str, ...] = ("BODYWEIGHT",)
    minimum_rest_seconds_between_sets: int | None = Field(default=30, ge=0)

    @field_validator("excluded_exercise_codes", "mandatory_exercise_codes")
    @classmethod
    def validate_known_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        unknown = tuple(code for code in values if code not in catalog.CATALOG)
        if unknown:
            raise ValueError(f"case references exercises outside the evaluation catalog: {unknown}")
        return values


class ExpectedSafetyResult(_Frozen):
    status_code: SafetyStatusExpectation
    required_action_code: RequiredActionExpectation = RequiredActionExpectation.NONE
    veto: bool = False

    @model_validator(mode="after")
    def validate_consistency(self) -> Self:
        if self.status_code is SafetyStatusExpectation.BLOCKED and not self.veto:
            raise ValueError("a BLOCKED safety result is a veto")
        if (
            self.required_action_code is not RequiredActionExpectation.NONE
            and self.status_code is SafetyStatusExpectation.PASS
        ):
            raise ValueError("PASS cannot require REST or STOP_AND_SEEK_HELP")
        return self


class ExpectedAgentBehavior(_Frozen):
    """Role separation this case asserts (ADR-0015)."""

    training_owns_plan: bool = True
    advisory_roles_have_no_prescriptions: bool = True
    coordinator_invoked: bool = True
    expected_adjustment_topic_codes: tuple[str, ...] = ()
    """Advisory only. Recorded as an observation, never asserted as PASS/FAIL."""


class ProhibitedActions(_Frozen):
    """Anything here appearing in the final plan is a hard failure."""

    exercise_codes: tuple[str, ...] = ()
    equipment_codes: tuple[str, ...] = ()
    location_codes: tuple[str, ...] = ()
    exceed_requested_duration: bool = True
    return_plan_when_safety_blocks: bool = True

    @field_validator("exercise_codes")
    @classmethod
    def validate_known_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        unknown = tuple(code for code in values if code not in catalog.CATALOG)
        if unknown:
            raise ValueError(f"case prohibits exercises outside the catalog: {unknown}")
        return values


class PoolSpec(_Frozen):
    """Which catalog rows reach the agents for this case."""

    exercise_codes: tuple[str, ...] = Field(min_length=1)
    vector_ranked_exercise_codes: tuple[str, ...] = ()
    retrieval_failed: bool = False
    """Simulates a Qdrant miss: the pool falls back to deterministic ordering."""

    @field_validator("exercise_codes", "vector_ranked_exercise_codes")
    @classmethod
    def validate_known_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        unknown = tuple(code for code in values if code not in catalog.CATALOG)
        if unknown:
            raise ValueError(f"pool references exercises outside the catalog: {unknown}")
        return values

    @model_validator(mode="after")
    def validate_ranked_subset(self) -> Self:
        if not set(self.vector_ranked_exercise_codes).issubset(self.exercise_codes):
            raise ValueError("vector_ranked_exercise_codes must be a subset of the pool")
        return self


class EvaluationCase(_Frozen):
    schema_version: str = DATASET_SCHEMA_VERSION
    case_id: str = Field(pattern=r"^SQ-[A-Z]+-\d{3}$")
    category: CaseCategory
    description: str = Field(min_length=1)
    user_input: UserInput
    expected_constraints: ExpectedConstraints
    prohibited_actions: ProhibitedActions
    expected_agent_behavior: ExpectedAgentBehavior
    expected_safety_result: ExpectedSafetyResult
    expected_outcome: ExpectedOutcome
    pool: PoolSpec
    expected_relevant_exercise_codes: tuple[str, ...] = ()
    """Ground truth for PHASE 3 retrieval scoring. Unused by deterministic tests."""

    expected_scenario_build_error: str | None = None
    """Set when the case is expected to be rejected before it reaches the graph.

    A missing or malformed required input never becomes a graph run in
    production either, so the assertion is that the input is refused with this
    stable code rather than that the graph handled it.
    """

    legacy_scenario_code: str | None = None
    """Link to the existing `v3_evaluation_fixtures` scenario, where one exists."""

    notes: str | None = None

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != DATASET_SCHEMA_VERSION:
            raise ValueError(f"unsupported case schema version: {value}")
        return value

    @model_validator(mode="after")
    def validate_case(self) -> Self:
        expected = self.expected_constraints
        safety = self.expected_safety_result

        if not expected.plan_generation_allowed and self.expected_outcome is ExpectedOutcome.PLAN:
            raise ValueError("a case that forbids plan generation cannot expect a plan")
        if self.expected_scenario_build_error and self.expected_outcome is ExpectedOutcome.PLAN:
            raise ValueError("a case rejected before the graph cannot expect a plan")
        if (
            safety.required_action_code is not RequiredActionExpectation.NONE
            and expected.plan_generation_allowed
        ):
            raise ValueError("REST or STOP_AND_SEEK_HELP cannot allow plan generation")
        if (
            safety.veto
            and self.expected_outcome is ExpectedOutcome.PLAN
            and not (expected.excluded_exercise_codes)
        ):
            raise ValueError("a veto that still yields a plan must name the excluded exercises")

        # An excluded exercise must be prohibited too. Without this a case could
        # exclude a movement in the envelope and never check that it stayed out.
        missing = set(expected.excluded_exercise_codes) - set(
            self.prohibited_actions.exercise_codes
        )
        if missing:
            raise ValueError(f"excluded exercises must also be prohibited: {sorted(missing)}")

        if set(expected.mandatory_exercise_codes) & set(expected.excluded_exercise_codes):
            raise ValueError("an exercise cannot be both mandatory and excluded")
        if not set(expected.mandatory_exercise_codes).issubset(self.pool.exercise_codes):
            raise ValueError("mandatory exercises must be present in the pool")
        return self


class EvaluationDataset(_Frozen):
    dataset_id: str
    schema_version: str = DATASET_SCHEMA_VERSION
    description: str
    cases: tuple[EvaluationCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> Self:
        ids = [case.case_id for case in self.cases]
        duplicates = sorted({value for value in ids if ids.count(value) > 1})
        if duplicates:
            raise ValueError(f"duplicate case_id values: {duplicates}")
        return self

    def by_category(self, category: CaseCategory) -> tuple[EvaluationCase, ...]:
        return tuple(case for case in self.cases if case.category is category)

    def __iter__(self) -> Iterator[EvaluationCase]:  # type: ignore[override]
        return iter(self.cases)

    def __len__(self) -> int:
        return len(self.cases)


def assert_no_identifiers(payload: object, *, path: str = "$") -> None:
    """Fail loudly if a dataset carries anything the privacy rules forbid."""

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.casefold() in FORBIDDEN_INPUT_KEYS:
                raise ValueError(f"forbidden identifying or health field at {path}.{key}")
            assert_no_identifiers(value, path=f"{path}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            assert_no_identifiers(value, path=f"{path}[{index}]")


def load_dataset(name: str) -> EvaluationDataset:
    """Load and validate one dataset file by base name (no extension)."""

    path = DATASETS_DIR / f"{name}.json"
    text = path.read_text(encoding="utf-8")
    assert_no_identifiers(json.loads(text))
    # The case contracts are strict, so JSON has to enter them through JSON mode.
    # `model_validate` on the already-parsed dict would reject every list where
    # the contract declares a tuple.
    return EvaluationDataset.model_validate_json(text)


def load_smoke_dataset() -> EvaluationDataset:
    return load_dataset("smoke_cases")


__all__ = [
    "DATASETS_DIR",
    "DATASET_SCHEMA_VERSION",
    "FIXED_TIME",
    "FORBIDDEN_INPUT_KEYS",
    "CaseCategory",
    "EvaluationCase",
    "EvaluationDataset",
    "ExpectedAgentBehavior",
    "ExpectedConstraints",
    "ExpectedOutcome",
    "ExpectedSafetyResult",
    "PoolSpec",
    "ProhibitedActions",
    "RequiredActionExpectation",
    "SafetyStatusExpectation",
    "UserInput",
    "assert_no_identifiers",
    "load_dataset",
    "load_smoke_dataset",
]
