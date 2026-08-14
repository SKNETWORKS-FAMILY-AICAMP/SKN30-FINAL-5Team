"""Framework-independent replay and publication contracts for decision persistence."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from backend.app.domain.agents.contracts import (
    AGENT_PROPOSAL_SCHEMA_VERSION,
    REQUIRED_AGENT_TYPES,
    AgentProposal,
    RecommendedActionCode,
)
from backend.app.domain.agents.coordinator import (
    COORDINATOR_VERSION,
    CoordinatorCandidate,
    CoordinatorInput,
    CoordinatorResult,
    CoordinatorStatusCode,
    coordinate,
)
from backend.app.domain.rules.duration import (
    DurationAdjustmentSourceCode,
    DurationRuleError,
    validate_requested_duration,
)
from backend.app.domain.rules.safety import SafetyStatusCode

DECISION_INPUT_SCHEMA_VERSION: Final[Literal["0.1.0"]] = "0.1.0"
_MACHINE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_PLAN_ACTIONS = frozenset(
    {
        RecommendedActionCode.KEEP,
        RecommendedActionCode.DOWNSHIFT,
        RecommendedActionCode.CHANGE,
        RecommendedActionCode.RECOVERY,
    }
)
_PUBLIC_SUCCESS_SAFETY_PAIRS = frozenset(
    {
        (CoordinatorStatusCode.PASS, SafetyStatusCode.PASS),
        (CoordinatorStatusCode.REVISE, SafetyStatusCode.REVISE),
        (CoordinatorStatusCode.BLOCKED, SafetyStatusCode.BLOCKED),
    }
)


def _validate_machine_reference(value: str, *, field_name: str) -> str:
    if not _MACHINE_REFERENCE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must contain only a structured machine reference")
    return value


class DecisionInputSnapshot(BaseModel):
    """Minimum identifier-free input persisted for Coordinator reconstruction.

    Proposals and candidates are deliberately excluded because persistence stores them as
    separate records. Context references identify normalized inputs without copying raw health
    records or direct identifiers into the decision snapshot.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    input_schema_version: Literal["0.1.0"] = DECISION_INPUT_SCHEMA_VERSION
    context_reference_codes: tuple[str, ...]
    profile_duration_minutes: int = Field(gt=0)
    requested_duration_minutes: int = Field(gt=0)
    duration_adjustment_source_code: DurationAdjustmentSourceCode

    @field_validator("context_reference_codes")
    @classmethod
    def validate_context_reference_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("context_reference_codes must not be empty")
        for value in values:
            _validate_machine_reference(value, field_name="context_reference_codes")
        if len(values) != len(set(values)):
            raise ValueError("context_reference_codes must not contain duplicates")
        return values

    @model_validator(mode="after")
    def validate_duration_request(self) -> Self:
        try:
            validate_requested_duration(
                profile_duration_minutes=self.profile_duration_minutes,
                requested_duration_minutes=self.requested_duration_minutes,
                adjustment_source_code=self.duration_adjustment_source_code,
            )
        except DurationRuleError as exc:
            raise ValueError("decision snapshot carries an invalid duration request") from exc
        return self


class DecisionVersionBundle(BaseModel):
    """Version combination that must survive storage and retrieval unchanged."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    input_schema_version: Literal["0.1.0"] = DECISION_INPUT_SCHEMA_VERSION
    proposal_schema_version: Literal["0.1.0"] = AGENT_PROPOSAL_SCHEMA_VERSION
    catalog_version: str
    policy_version: str
    safety_rule_version: str
    duration_rule_version: Literal["1.0.0"]
    graph_version: str
    coordinator_version: Literal["0.2.0"] = COORDINATOR_VERSION

    @field_validator(
        "catalog_version",
        "policy_version",
        "safety_rule_version",
        "graph_version",
    )
    @classmethod
    def validate_version_fields(cls, value: str, info: ValidationInfo) -> str:
        return _validate_machine_reference(value, field_name=info.field_name or "version field")


class FinalRoutineOptionLink(BaseModel):
    """Internal link between a successful Coordinator result and its one public routine option."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    option_code: Literal["FINAL_ROUTINE"] = "FINAL_ROUTINE"
    action_code: RecommendedActionCode
    selected_candidate_id: str

    @field_validator("selected_candidate_id")
    @classmethod
    def validate_candidate_id(cls, value: str) -> str:
        return _validate_machine_reference(value, field_name="selected_candidate_id")

    @model_validator(mode="after")
    def validate_plan_action(self) -> Self:
        if self.action_code not in _PLAN_ACTIONS:
            raise ValueError("FINAL_ROUTINE option requires a plan-producing action")
        return self


class DecisionReplayEnvelope(BaseModel):
    """Persistence-neutral records required to replay one Coordinator result."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    input_snapshot: DecisionInputSnapshot
    versions: DecisionVersionBundle
    proposals: tuple[AgentProposal, ...]
    candidates: tuple[CoordinatorCandidate, ...]
    coordinator_result: CoordinatorResult
    final_routine_option: FinalRoutineOptionLink | None = None

    @model_validator(mode="after")
    def validate_replay_contract(self) -> Self:
        self._validate_versions()
        self._validate_proposals()
        self._validate_final_option()
        replayed_result = coordinate(self.to_coordinator_input())
        if replayed_result != self.coordinator_result:
            raise ValueError("stored Coordinator result does not match deterministic replay")
        return self

    def _validate_versions(self) -> None:
        if self.input_snapshot.input_schema_version != self.versions.input_schema_version:
            raise ValueError("input schema version changed across persistence records")
        for proposal in self.proposals:
            if proposal.schema_version != self.versions.proposal_schema_version:
                raise ValueError("proposal schema version changed across persistence records")
            if proposal.policy_version != self.versions.policy_version:
                raise ValueError("proposal policy version changed across persistence records")
        if any(
            candidate.catalog_version != self.versions.catalog_version
            for candidate in self.candidates
        ):
            raise ValueError("candidate catalog version changed across persistence records")
        result = self.coordinator_result
        version_pairs = (
            (result.proposal_schema_version, self.versions.proposal_schema_version),
            (result.policy_version, self.versions.policy_version),
            (result.catalog_version, self.versions.catalog_version),
            (result.safety_rule_version, self.versions.safety_rule_version),
            (result.duration_rule_version, self.versions.duration_rule_version),
            (result.coordinator_version, self.versions.coordinator_version),
        )
        if any(stored != expected for stored, expected in version_pairs):
            raise ValueError("Coordinator result version combination changed after storage")

    def _validate_proposals(self) -> None:
        agent_types = tuple(proposal.agent_type_code for proposal in self.proposals)
        if len(agent_types) != len(REQUIRED_AGENT_TYPES) or set(agent_types) != set(
            REQUIRED_AGENT_TYPES
        ):
            raise ValueError("persistence must retain one separate proposal per required agent")

    def _validate_final_option(self) -> None:
        result = self.coordinator_result
        has_plan = result.status_code in {
            CoordinatorStatusCode.PASS,
            CoordinatorStatusCode.REVISE,
        }
        if not has_plan:
            if self.final_routine_option is not None:
                raise ValueError("non-plan results cannot publish a FINAL_ROUTINE option")
            return
        if self.final_routine_option is None:
            raise ValueError("plan result requires one FINAL_ROUTINE option link")
        if (
            self.final_routine_option.action_code is not result.final_action_code
            or self.final_routine_option.selected_candidate_id != result.selected_candidate_id
        ):
            raise ValueError("final option does not link to the Coordinator-selected candidate")
        candidate_ids = {candidate.candidate_id for candidate in self.candidates}
        if self.final_routine_option.selected_candidate_id not in candidate_ids:
            raise ValueError("final option references a candidate that was not persisted")

    def to_coordinator_input(self) -> CoordinatorInput:
        """Reconstruct the framework-independent Coordinator input after retrieval."""

        return CoordinatorInput(
            coordinator_version=self.versions.coordinator_version,
            proposals=self.proposals,
            candidates=self.candidates,
            profile_duration_minutes=self.input_snapshot.profile_duration_minutes,
            requested_duration_minutes=self.input_snapshot.requested_duration_minutes,
            duration_adjustment_source_code=(self.input_snapshot.duration_adjustment_source_code),
            policy_version=self.versions.policy_version,
            catalog_version=self.versions.catalog_version,
            catalog_status_code="ACTIVE",
            catalog_review_status_code="DOMAIN_APPROVED",
            catalog_production_eligible=True,
            catalog_activated=True,
            safety_rule_version=self.versions.safety_rule_version,
            duration_rule_version=self.versions.duration_rule_version,
        )


def canonical_snapshot_bytes(snapshot: DecisionInputSnapshot) -> bytes:
    """Return canonical UTF-8 JSON without changing sequence-bearing domain fields."""

    payload = snapshot.model_dump(mode="json")
    payload["context_reference_codes"] = sorted(payload["context_reference_codes"])
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def decision_input_hash(snapshot: DecisionInputSnapshot) -> str:
    """Return the stable SHA-256 digest used to identify an equivalent input snapshot."""

    return hashlib.sha256(canonical_snapshot_bytes(snapshot)).hexdigest()


def successful_decision_response_allowed(
    *,
    result: CoordinatorResult,
    persistence_succeeded: bool,
) -> bool:
    """Gate successful publication on atomic persistence and a public success status."""

    return (
        persistence_succeeded
        and (
            result.status_code,
            result.safety_status_code,
        )
        in _PUBLIC_SUCCESS_SAFETY_PAIRS
    )


__all__ = [
    "DECISION_INPUT_SCHEMA_VERSION",
    "DecisionInputSnapshot",
    "DecisionReplayEnvelope",
    "DecisionVersionBundle",
    "FinalRoutineOptionLink",
    "canonical_snapshot_bytes",
    "decision_input_hash",
    "successful_decision_response_allowed",
]
