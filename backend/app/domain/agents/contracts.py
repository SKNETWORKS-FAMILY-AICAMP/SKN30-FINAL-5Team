"""Versioned, framework-independent contracts for specialist agent proposals."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import ClassVar, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from backend.app.domain.rules.duration import DurationAdjustmentSourceCode
from backend.app.domain.rules.safety import SafetyStatusCode

AGENT_PROPOSAL_SCHEMA_VERSION: Final[Literal["0.1.0"]] = "0.1.0"
_MACHINE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class AgentTypeCode(StrEnum):
    TRAINING = "TRAINING"
    RECOVERY = "RECOVERY"
    SAFETY = "SAFETY"
    FEASIBILITY = "FEASIBILITY"


REQUIRED_AGENT_TYPES = (
    AgentTypeCode.TRAINING,
    AgentTypeCode.RECOVERY,
    AgentTypeCode.SAFETY,
    AgentTypeCode.FEASIBILITY,
)


class ProposalStatusCode(StrEnum):
    READY = "READY"
    NEEDS_INPUT = "NEEDS_INPUT"
    FAILED = "FAILED"


class RecommendedActionCode(StrEnum):
    KEEP = "KEEP"
    DOWNSHIFT = "DOWNSHIFT"
    CHANGE = "CHANGE"
    RECOVERY = "RECOVERY"
    REST = "REST"
    STOP_AND_SEEK_HELP = "STOP_AND_SEEK_HELP"


class ProposalBatchStatusCode(StrEnum):
    READY = "READY"
    NEEDS_INPUT = "NEEDS_INPUT"
    FAILED = "FAILED"


def _validate_machine_reference(value: str, *, field_name: str) -> str:
    if not _MACHINE_REFERENCE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must contain only a structured machine reference")
    return value


def _validate_canonical_references(
    values: tuple[str, ...],
    *,
    field_name: str,
) -> tuple[str, ...]:
    for value in values:
        _validate_machine_reference(value, field_name=field_name)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    if values != tuple(sorted(values)):
        raise ValueError(f"{field_name} must use canonical sorted order")
    return values


class AgentProposal(BaseModel):
    """Internal alpha proposal contract; never contains free-form reasoning."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["0.1.0"] = AGENT_PROPOSAL_SCHEMA_VERSION
    agent_type_code: AgentTypeCode
    proposal_status_code: ProposalStatusCode
    recommended_action_code: RecommendedActionCode | None = None
    requested_duration_minutes: int = Field(gt=0)
    estimated_duration_seconds: int | None = Field(default=None, ge=0)
    duration_adjustment_source_code: DurationAdjustmentSourceCode
    intensity_delta: int = 0
    required_goal_tags: tuple[str, ...] = ()
    preferred_exercise_ids: tuple[str, ...] = ()
    excluded_exercise_ids: tuple[str, ...] = ()
    hard_constraint_codes: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    evidence_reference_codes: tuple[str, ...] = ()
    policy_version: str
    safety_status_code: SafetyStatusCode | None = None
    safety_vetoed: bool | None = None

    _reference_fields: ClassVar[tuple[str, ...]] = (
        "required_goal_tags",
        "preferred_exercise_ids",
        "excluded_exercise_ids",
        "hard_constraint_codes",
        "reason_codes",
        "evidence_reference_codes",
    )

    @field_validator(*_reference_fields)
    @classmethod
    def validate_reference_fields(
        cls,
        value: tuple[str, ...],
        info: ValidationInfo,
    ) -> tuple[str, ...]:
        field_name = info.field_name or "reference field"
        return _validate_canonical_references(value, field_name=field_name)

    @field_validator("policy_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        return _validate_machine_reference(value, field_name="policy_version")

    @model_validator(mode="after")
    def validate_contract_invariants(self) -> Self:
        if set(self.preferred_exercise_ids) & set(self.excluded_exercise_ids):
            raise ValueError("an exercise cannot be both preferred and excluded")

        if self.proposal_status_code is ProposalStatusCode.READY:
            if self.recommended_action_code is None or self.estimated_duration_seconds is None:
                raise ValueError("READY proposals require an action and estimated duration")
            expected_seconds = self.requested_duration_minutes * 60
            if self.estimated_duration_seconds != expected_seconds:
                raise ValueError("READY proposals must preserve the requested duration")
        elif (
            self.recommended_action_code is not None or self.estimated_duration_seconds is not None
        ):
            raise ValueError("non-READY proposals cannot claim an action or estimated duration")

        if self.agent_type_code is AgentTypeCode.SAFETY:
            self._validate_safety_fields()
        elif self.safety_status_code is not None or self.safety_vetoed is not None:
            raise ValueError("only SAFETY proposals may carry safety status or veto fields")
        return self

    def _validate_safety_fields(self) -> None:
        if self.safety_status_code is None or self.safety_vetoed is None:
            raise ValueError("SAFETY proposals require safety status and veto fields")

        expected_status = {
            ProposalStatusCode.NEEDS_INPUT: SafetyStatusCode.NEEDS_INPUT,
            ProposalStatusCode.FAILED: SafetyStatusCode.FAILED,
        }.get(self.proposal_status_code)
        if expected_status is not None and self.safety_status_code is not expected_status:
            raise ValueError("SAFETY proposal status must match its safety status")
        if self.proposal_status_code is ProposalStatusCode.READY and self.safety_status_code in {
            SafetyStatusCode.NEEDS_INPUT,
            SafetyStatusCode.FAILED,
        }:
            raise ValueError("NEEDS_INPUT and FAILED safety results are not READY proposals")
        if (
            self.safety_status_code
            in {
                SafetyStatusCode.NEEDS_INPUT,
                SafetyStatusCode.BLOCKED,
                SafetyStatusCode.FAILED,
            }
            and not self.safety_vetoed
        ):
            raise ValueError("fail-closed safety states require a veto")
        if self.safety_status_code is SafetyStatusCode.PASS and self.safety_vetoed:
            raise ValueError("PASS safety status cannot carry a veto")
        terminal_actions = {
            RecommendedActionCode.REST,
            RecommendedActionCode.STOP_AND_SEEK_HELP,
        }
        if (
            self.safety_status_code is SafetyStatusCode.BLOCKED
            and self.recommended_action_code not in terminal_actions
        ):
            raise ValueError("BLOCKED safety status requires a terminal action")
        if (
            self.safety_status_code in {SafetyStatusCode.PASS, SafetyStatusCode.REVISE}
            and self.recommended_action_code in terminal_actions
        ):
            raise ValueError("non-blocked safety status cannot recommend a terminal action")

    @classmethod
    def failed(
        cls,
        *,
        agent_type_code: AgentTypeCode,
        requested_duration_minutes: int,
        duration_adjustment_source_code: DurationAdjustmentSourceCode,
        policy_version: str,
        reason_code: str,
    ) -> Self:
        safety_status = SafetyStatusCode.FAILED if agent_type_code is AgentTypeCode.SAFETY else None
        safety_vetoed = True if agent_type_code is AgentTypeCode.SAFETY else None
        return cls(
            agent_type_code=agent_type_code,
            proposal_status_code=ProposalStatusCode.FAILED,
            requested_duration_minutes=requested_duration_minutes,
            duration_adjustment_source_code=duration_adjustment_source_code,
            reason_codes=(reason_code,),
            policy_version=policy_version,
            safety_status_code=safety_status,
            safety_vetoed=safety_vetoed,
        )


class ProposalBatch(BaseModel):
    """Four required proposals in canonical order with a fail-closed batch status."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposals: tuple[AgentProposal, ...]

    @model_validator(mode="after")
    def validate_required_proposals(self) -> Self:
        agent_types = tuple(proposal.agent_type_code for proposal in self.proposals)
        if agent_types != REQUIRED_AGENT_TYPES:
            raise ValueError("proposal batch must contain all required agents in canonical order")
        shared_fields = (
            "schema_version",
            "requested_duration_minutes",
            "duration_adjustment_source_code",
            "policy_version",
        )
        for field_name in shared_fields:
            values = {getattr(proposal, field_name) for proposal in self.proposals}
            if len(values) != 1:
                raise ValueError(f"proposal batch must share one {field_name}")
        return self

    @property
    def status_code(self) -> ProposalBatchStatusCode:
        statuses = {proposal.proposal_status_code for proposal in self.proposals}
        if ProposalStatusCode.FAILED in statuses:
            return ProposalBatchStatusCode.FAILED
        if ProposalStatusCode.NEEDS_INPUT in statuses:
            return ProposalBatchStatusCode.NEEDS_INPUT
        return ProposalBatchStatusCode.READY

    @property
    def exercise_plan_success_forbidden(self) -> bool:
        if self.status_code is not ProposalBatchStatusCode.READY:
            return True
        safety_proposal = self.by_agent_type(AgentTypeCode.SAFETY)
        return safety_proposal.safety_status_code in {
            SafetyStatusCode.NEEDS_INPUT,
            SafetyStatusCode.BLOCKED,
            SafetyStatusCode.FAILED,
        }

    def by_agent_type(self, agent_type_code: AgentTypeCode) -> AgentProposal:
        return self.proposals[REQUIRED_AGENT_TYPES.index(agent_type_code)]
