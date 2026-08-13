"""Deterministic, fail-closed coordinator for the four specialist proposals."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from backend.app.domain.agents.contracts import (
    AGENT_PROPOSAL_SCHEMA_VERSION,
    REQUIRED_AGENT_TYPES,
    AgentProposal,
    AgentTypeCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.rules.duration import (
    DURATION_RULE_VERSION,
    DurationAdjustmentSourceCode,
    DurationPlan,
    DurationRuleError,
    calculate_estimated_duration_seconds,
    require_exact_duration,
    validate_requested_duration,
)
from backend.app.domain.rules.safety import SafetyStatusCode

COORDINATOR_VERSION: Final[Literal["0.2.0"]] = "0.2.0"
_MACHINE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_PLAN_ACTIONS = frozenset(
    {
        RecommendedActionCode.KEEP,
        RecommendedActionCode.DOWNSHIFT,
        RecommendedActionCode.CHANGE,
        RecommendedActionCode.RECOVERY,
    }
)
_TERMINAL_ACTIONS = frozenset(
    {
        RecommendedActionCode.REST,
        RecommendedActionCode.STOP_AND_SEEK_HELP,
    }
)


class CoordinatorStatusCode(StrEnum):
    PASS = "PASS"
    REVISE = "REVISE"
    NEEDS_INPUT = "NEEDS_INPUT"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class DownshiftAdjustmentCode(StrEnum):
    LOAD_REDUCED = "LOAD_REDUCED"
    INTENSITY_REDUCED = "INTENSITY_REDUCED"
    SETS_REDUCED = "SETS_REDUCED"
    REPS_REDUCED = "REPS_REDUCED"
    DIFFICULTY_REDUCED = "DIFFICULTY_REDUCED"
    EXERCISE_TYPE_ADJUSTED = "EXERCISE_TYPE_ADJUSTED"
    REST_STRUCTURE_ADJUSTED = "REST_STRUCTURE_ADJUSTED"


def _validate_machine_reference(value: str, *, field_name: str) -> str:
    if not _MACHINE_REFERENCE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must contain only a structured machine reference")
    return value


def _canonical_references(values: set[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


class CoordinatorCandidate(BaseModel):
    """One approved common candidate; the coordinator may select but never mutate it."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        strict=True,
    )

    candidate_id: str
    action_code: RecommendedActionCode
    exercise_ids: tuple[str, ...]
    goal_tags: tuple[str, ...] = ()
    downshift_adjustment_codes: tuple[DownshiftAdjustmentCode, ...] = ()
    catalog_version: str
    duration_plan: DurationPlan

    @field_validator("candidate_id", "catalog_version")
    @classmethod
    def validate_machine_fields(cls, value: str, info: ValidationInfo) -> str:
        return _validate_machine_reference(value, field_name=info.field_name or "machine field")

    @field_validator("exercise_ids", "goal_tags")
    @classmethod
    def validate_reference_fields(
        cls,
        values: tuple[str, ...],
        info: ValidationInfo,
    ) -> tuple[str, ...]:
        field_name = info.field_name or "reference field"
        if field_name == "exercise_ids" and not values:
            raise ValueError("exercise_ids must not be empty")
        for value in values:
            _validate_machine_reference(value, field_name=field_name)
        if len(values) != len(set(values)):
            raise ValueError(f"{field_name} must not contain duplicates")
        if values != tuple(sorted(values)):
            raise ValueError(f"{field_name} must use canonical sorted order")
        return values

    @model_validator(mode="after")
    def validate_candidate_action(self) -> Self:
        if self.action_code not in _PLAN_ACTIONS:
            raise ValueError("common candidates must carry a plan-producing action")
        if len(self.downshift_adjustment_codes) != len(set(self.downshift_adjustment_codes)):
            raise ValueError("downshift_adjustment_codes must not contain duplicates")
        if self.downshift_adjustment_codes != tuple(sorted(self.downshift_adjustment_codes)):
            raise ValueError("downshift_adjustment_codes must use canonical sorted order")
        if (
            self.action_code is RecommendedActionCode.DOWNSHIFT
            and not self.downshift_adjustment_codes
        ):
            raise ValueError("DOWNSHIFT candidates require an approved burden adjustment")
        if (
            self.action_code is not RecommendedActionCode.DOWNSHIFT
            and self.downshift_adjustment_codes
        ):
            raise ValueError("only DOWNSHIFT candidates may carry burden adjustments")
        return self

    @property
    def estimated_duration_seconds(self) -> int:
        return calculate_estimated_duration_seconds(self.duration_plan)


class CoordinatorInput(BaseModel):
    """Minimal, identifier-free input envelope for one coordinator decision."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    coordinator_version: Literal["0.2.0"] = COORDINATOR_VERSION
    proposals: tuple[AgentProposal, ...]
    candidates: tuple[CoordinatorCandidate, ...]
    profile_duration_minutes: int = Field(gt=0)
    requested_duration_minutes: int = Field(gt=0)
    duration_adjustment_source_code: DurationAdjustmentSourceCode
    policy_version: str
    catalog_version: str
    catalog_status_code: Literal["ACTIVE"]
    catalog_review_status_code: Literal["DOMAIN_APPROVED"]
    catalog_production_eligible: Literal[True]
    catalog_activated: Literal[True]
    safety_rule_version: str
    duration_rule_version: str

    @field_validator(
        "policy_version",
        "catalog_version",
        "safety_rule_version",
        "duration_rule_version",
    )
    @classmethod
    def validate_version_fields(cls, value: str, info: ValidationInfo) -> str:
        return _validate_machine_reference(value, field_name=info.field_name or "version field")


class CoordinatorResult(BaseModel):
    """Versioned internal result; persistence and public API mapping remain separate."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    coordinator_version: Literal["0.2.0"] = COORDINATOR_VERSION
    status_code: CoordinatorStatusCode
    safety_status_code: SafetyStatusCode
    final_action_code: RecommendedActionCode | None
    selected_candidate_id: str | None
    requested_duration_minutes: int = Field(gt=0)
    duration_adjustment_source_code: DurationAdjustmentSourceCode
    estimated_duration_seconds: int | None = Field(default=None, ge=0)
    applied_agent_types: tuple[AgentTypeCode, ...]
    reason_codes: tuple[str, ...]
    blocked_reason_codes: tuple[str, ...]
    proposal_schema_version: Literal["0.1.0"] = AGENT_PROPOSAL_SCHEMA_VERSION
    policy_version: str
    catalog_version: str
    safety_rule_version: str
    duration_rule_version: str

    @field_validator("selected_candidate_id")
    @classmethod
    def validate_selected_candidate_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_machine_reference(value, field_name="selected_candidate_id")

    @field_validator(
        "policy_version",
        "catalog_version",
        "safety_rule_version",
        "duration_rule_version",
    )
    @classmethod
    def validate_version_fields(cls, value: str, info: ValidationInfo) -> str:
        return _validate_machine_reference(value, field_name=info.field_name or "version field")

    @field_validator("reason_codes", "blocked_reason_codes")
    @classmethod
    def validate_reason_codes(
        cls,
        values: tuple[str, ...],
        info: ValidationInfo,
    ) -> tuple[str, ...]:
        field_name = info.field_name or "reason codes"
        for value in values:
            _validate_machine_reference(value, field_name=field_name)
        if values != _canonical_references(values):
            raise ValueError(f"{field_name} must be unique and canonically sorted")
        return values

    @model_validator(mode="after")
    def validate_result_shape(self) -> Self:
        has_plan = self.status_code in {
            CoordinatorStatusCode.PASS,
            CoordinatorStatusCode.REVISE,
        }
        if has_plan:
            if self.final_action_code not in _PLAN_ACTIONS:
                raise ValueError("PASS and REVISE results require a plan-producing action")
            if self.selected_candidate_id is None or self.estimated_duration_seconds is None:
                raise ValueError("PASS and REVISE results require one selected candidate")
            if self.estimated_duration_seconds != self.requested_duration_minutes * 60:
                raise ValueError("selected candidate must preserve requested duration")
            if self.applied_agent_types != REQUIRED_AGENT_TYPES:
                raise ValueError("successful results must apply all required proposals")
            return self

        if self.selected_candidate_id is not None or self.estimated_duration_seconds is not None:
            raise ValueError("non-plan results cannot select a candidate or estimated duration")
        if self.status_code is CoordinatorStatusCode.BLOCKED:
            if self.final_action_code not in _TERMINAL_ACTIONS:
                raise ValueError("BLOCKED results require REST or STOP_AND_SEEK_HELP")
        elif self.final_action_code is not None:
            raise ValueError("NEEDS_INPUT and FAILED results cannot claim a final action")
        return self


def _result(
    coordinator_input: CoordinatorInput,
    *,
    status_code: CoordinatorStatusCode,
    safety_status_code: SafetyStatusCode,
    final_action_code: RecommendedActionCode | None = None,
    selected_candidate: CoordinatorCandidate | None = None,
    applied_agent_types: tuple[AgentTypeCode, ...] = (),
    reason_codes: set[str] | tuple[str, ...] = (),
    blocked_reason_codes: set[str] | tuple[str, ...] = (),
) -> CoordinatorResult:
    return CoordinatorResult(
        status_code=status_code,
        safety_status_code=safety_status_code,
        final_action_code=final_action_code,
        selected_candidate_id=(selected_candidate.candidate_id if selected_candidate else None),
        requested_duration_minutes=coordinator_input.requested_duration_minutes,
        duration_adjustment_source_code=coordinator_input.duration_adjustment_source_code,
        estimated_duration_seconds=(
            selected_candidate.estimated_duration_seconds if selected_candidate else None
        ),
        applied_agent_types=applied_agent_types,
        reason_codes=_canonical_references(reason_codes),
        blocked_reason_codes=_canonical_references(blocked_reason_codes),
        policy_version=coordinator_input.policy_version,
        catalog_version=coordinator_input.catalog_version,
        safety_rule_version=coordinator_input.safety_rule_version,
        duration_rule_version=coordinator_input.duration_rule_version,
    )


def _available_safety_status(proposals: tuple[AgentProposal, ...]) -> SafetyStatusCode:
    safety_proposals = tuple(
        proposal for proposal in proposals if proposal.agent_type_code is AgentTypeCode.SAFETY
    )
    if len(safety_proposals) != 1 or safety_proposals[0].safety_status_code is None:
        return SafetyStatusCode.FAILED
    return safety_proposals[0].safety_status_code


def _proposal_shape_failures(proposals: tuple[AgentProposal, ...]) -> set[str]:
    failures: set[str] = set()
    if len(proposals) != len(REQUIRED_AGENT_TYPES):
        failures.add("REQUIRED_PROPOSAL_COUNT_INVALID")

    present_types = tuple(proposal.agent_type_code for proposal in proposals)
    for agent_type in REQUIRED_AGENT_TYPES:
        count = present_types.count(agent_type)
        if count == 0:
            failures.add(f"REQUIRED_AGENT_MISSING.{agent_type.value}")
        elif count > 1:
            failures.add(f"REQUIRED_AGENT_DUPLICATE.{agent_type.value}")
    return failures


def _proposal_reason_codes(proposals: tuple[AgentProposal, ...]) -> set[str]:
    return {reason_code for proposal in proposals for reason_code in proposal.reason_codes}


def _target_action(
    proposals: dict[AgentTypeCode, AgentProposal],
) -> RecommendedActionCode | None:
    safety = proposals[AgentTypeCode.SAFETY]
    if safety.safety_status_code is SafetyStatusCode.REVISE:
        return safety.recommended_action_code

    for agent_type in (
        AgentTypeCode.FEASIBILITY,
        AgentTypeCode.RECOVERY,
        AgentTypeCode.TRAINING,
        AgentTypeCode.SAFETY,
    ):
        action = proposals[agent_type].recommended_action_code
        if action is not None and action is not RecommendedActionCode.KEEP:
            return action
    return RecommendedActionCode.KEEP


def _candidate_preference_key(
    candidate: CoordinatorCandidate,
    proposals: dict[AgentTypeCode, AgentProposal],
) -> tuple[int, int, int, int, str]:
    candidate_exercises = set(candidate.exercise_ids)

    def preferred_count(agent_type: AgentTypeCode) -> int:
        return len(candidate_exercises & set(proposals[agent_type].preferred_exercise_ids))

    return (
        -preferred_count(AgentTypeCode.FEASIBILITY),
        -preferred_count(AgentTypeCode.RECOVERY),
        -preferred_count(AgentTypeCode.TRAINING),
        -preferred_count(AgentTypeCode.SAFETY),
        candidate.candidate_id,
    )


def coordinate(coordinator_input: CoordinatorInput) -> CoordinatorResult:
    """Select one approved common candidate under deterministic priority rules.

    The function never calls an LLM, creates an exercise, mutates a candidate, or performs a
    second safety evaluation. All failure results use fixed machine-readable codes only.
    """

    proposals = coordinator_input.proposals
    safety_status = _available_safety_status(proposals)
    shape_failures = _proposal_shape_failures(proposals)
    if shape_failures:
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            reason_codes=shape_failures,
            blocked_reason_codes=shape_failures,
        )

    by_agent_type = {proposal.agent_type_code: proposal for proposal in proposals}
    canonical_proposals = tuple(by_agent_type[agent_type] for agent_type in REQUIRED_AGENT_TYPES)
    applied_agent_types = REQUIRED_AGENT_TYPES

    metadata_invalid = any(
        proposal.requested_duration_minutes != coordinator_input.requested_duration_minutes
        or proposal.duration_adjustment_source_code
        is not coordinator_input.duration_adjustment_source_code
        or proposal.policy_version != coordinator_input.policy_version
        for proposal in canonical_proposals
    )
    if metadata_invalid:
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes={"PROPOSAL_INPUT_MISMATCH"},
            blocked_reason_codes={"PROPOSAL_INPUT_MISMATCH"},
        )

    failed_agents = {
        f"REQUIRED_PROPOSAL_FAILED.{proposal.agent_type_code.value}"
        for proposal in canonical_proposals
        if proposal.proposal_status_code is ProposalStatusCode.FAILED
    }
    if failed_agents:
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes=failed_agents,
            blocked_reason_codes=failed_agents,
        )

    needs_input_agents = {
        f"REQUIRED_PROPOSAL_NEEDS_INPUT.{proposal.agent_type_code.value}"
        for proposal in canonical_proposals
        if proposal.proposal_status_code is ProposalStatusCode.NEEDS_INPUT
    }
    if needs_input_agents:
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.NEEDS_INPUT,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes=needs_input_agents,
            blocked_reason_codes=needs_input_agents,
        )

    safety_proposal = by_agent_type[AgentTypeCode.SAFETY]
    if safety_proposal.safety_status_code is SafetyStatusCode.PASS and (
        safety_proposal.safety_vetoed or safety_proposal.excluded_exercise_ids
    ):
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes={"SAFETY_PROPOSAL_INCONSISTENT"},
            blocked_reason_codes={"SAFETY_PROPOSAL_INCONSISTENT"},
        )
    if safety_proposal.excluded_exercise_ids and not safety_proposal.safety_vetoed:
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes={"SAFETY_PROPOSAL_INCONSISTENT"},
            blocked_reason_codes={"SAFETY_PROPOSAL_INCONSISTENT"},
        )

    proposal_reasons = _proposal_reason_codes(canonical_proposals)
    if safety_proposal.safety_status_code is SafetyStatusCode.BLOCKED:
        if safety_proposal.recommended_action_code not in _TERMINAL_ACTIONS:
            return _result(
                coordinator_input,
                status_code=CoordinatorStatusCode.FAILED,
                safety_status_code=safety_status,
                applied_agent_types=applied_agent_types,
                reason_codes={"SAFETY_PROPOSAL_INCONSISTENT"},
                blocked_reason_codes={"SAFETY_PROPOSAL_INCONSISTENT"},
            )
        blocked_reasons = proposal_reasons | {"SAFETY_BLOCKED"}
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.BLOCKED,
            safety_status_code=SafetyStatusCode.BLOCKED,
            final_action_code=safety_proposal.recommended_action_code,
            applied_agent_types=applied_agent_types,
            reason_codes=blocked_reasons,
            blocked_reason_codes=blocked_reasons,
        )

    candidate_ids = tuple(candidate.candidate_id for candidate in coordinator_input.candidates)
    if len(candidate_ids) != len(set(candidate_ids)):
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes={"COMMON_CANDIDATE_ID_DUPLICATE"},
            blocked_reason_codes={"COMMON_CANDIDATE_ID_DUPLICATE"},
        )
    if any(
        candidate.catalog_version != coordinator_input.catalog_version
        for candidate in coordinator_input.candidates
    ):
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes={"COMMON_CANDIDATE_VERSION_MISMATCH"},
            blocked_reason_codes={"COMMON_CANDIDATE_VERSION_MISMATCH"},
        )
    if coordinator_input.duration_rule_version != DURATION_RULE_VERSION:
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes={"DURATION_RULE_VERSION_UNSUPPORTED"},
            blocked_reason_codes={"DURATION_RULE_VERSION_UNSUPPORTED"},
        )

    common_exercise_ids = {
        exercise_id
        for candidate in coordinator_input.candidates
        for exercise_id in candidate.exercise_ids
    }
    proposal_exercise_ids = {
        exercise_id
        for proposal in canonical_proposals
        for exercise_id in (
            *proposal.preferred_exercise_ids,
            *proposal.excluded_exercise_ids,
        )
    }
    if not proposal_exercise_ids.issubset(common_exercise_ids):
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes={"PROPOSAL_EXERCISE_OUTSIDE_COMMON_CANDIDATES"},
            blocked_reason_codes={"PROPOSAL_EXERCISE_OUTSIDE_COMMON_CANDIDATES"},
        )

    try:
        duration_request = validate_requested_duration(
            profile_duration_minutes=coordinator_input.profile_duration_minutes,
            requested_duration_minutes=coordinator_input.requested_duration_minutes,
            adjustment_source_code=coordinator_input.duration_adjustment_source_code,
        )
    except DurationRuleError:
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes={"DURATION_REQUEST_INVALID"},
            blocked_reason_codes={"DURATION_REQUEST_INVALID"},
        )

    excluded_exercise_ids = {
        exercise_id
        for proposal in canonical_proposals
        for exercise_id in proposal.excluded_exercise_ids
    }
    required_goal_tags = {
        goal_tag for proposal in canonical_proposals for goal_tag in proposal.required_goal_tags
    }
    eligible_candidates: list[CoordinatorCandidate] = []
    rejection_reasons: set[str] = set()
    for candidate in coordinator_input.candidates:
        if set(candidate.exercise_ids) & excluded_exercise_ids:
            rejection_reasons.add("CANDIDATE_CONTAINS_EXCLUDED_EXERCISE")
            continue
        if not required_goal_tags.issubset(candidate.goal_tags):
            rejection_reasons.add("CANDIDATE_MISSING_REQUIRED_GOAL")
            continue
        try:
            require_exact_duration(duration_request, candidate.duration_plan)
        except DurationRuleError:
            rejection_reasons.add("CANDIDATE_DURATION_MISMATCH")
            continue
        eligible_candidates.append(candidate)

    target_action = _target_action(by_agent_type)
    if target_action not in _PLAN_ACTIONS:
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.FAILED,
            safety_status_code=safety_status,
            applied_agent_types=applied_agent_types,
            reason_codes={"PROPOSAL_ACTION_INCONSISTENT"},
            blocked_reason_codes={"PROPOSAL_ACTION_INCONSISTENT"},
        )
    action_candidates = [
        candidate for candidate in eligible_candidates if candidate.action_code is target_action
    ]
    if not action_candidates:
        if eligible_candidates:
            rejection_reasons.add("CANDIDATE_REQUIRED_ACTION_UNAVAILABLE")
        blocked_reasons = rejection_reasons | {"NO_ELIGIBLE_COMMON_CANDIDATE"}
        return _result(
            coordinator_input,
            status_code=CoordinatorStatusCode.BLOCKED,
            safety_status_code=safety_status,
            final_action_code=RecommendedActionCode.REST,
            applied_agent_types=applied_agent_types,
            reason_codes={"NO_ELIGIBLE_COMMON_CANDIDATE"},
            blocked_reason_codes=blocked_reasons,
        )

    selected_candidate = min(
        action_candidates,
        key=lambda candidate: _candidate_preference_key(candidate, by_agent_type),
    )
    result_status = (
        CoordinatorStatusCode.REVISE
        if safety_status is SafetyStatusCode.REVISE
        else CoordinatorStatusCode.PASS
    )
    return _result(
        coordinator_input,
        status_code=result_status,
        safety_status_code=safety_status,
        final_action_code=selected_candidate.action_code,
        selected_candidate=selected_candidate,
        applied_agent_types=applied_agent_types,
        reason_codes=proposal_reasons | {"COMMON_CANDIDATE_SELECTED"},
    )
