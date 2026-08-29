from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.domain.agents.contracts import AgentProposal
from backend.app.domain.agents.coordinator import CoordinatorCandidate, CoordinatorResult
from backend.app.domain.rules.safety import SafetyCandidate, SafetyCandidateItem, SafetyRuleSet
from backend.app.modules.decisions.context import DecisionContext

if TYPE_CHECKING:  # pragma: no cover - import cycle only exists for type checking
    from backend.app.modules.decisions.explanations import DecisionExplanation


@dataclass(frozen=True, slots=True)
class CandidateItemData:
    exercise_id: UUID
    sequence: int
    phase_code: str
    tier_code: str
    sets: int
    reps: int | None
    work_seconds_per_set: int | None
    rest_seconds_per_set: int
    transition_seconds: int
    intensity_code: str
    instruction_content_version: str
    display_name: str
    work_seconds: int
    rest_seconds: int


@dataclass(frozen=True, slots=True)
class AlternativeItemData:
    source_exercise_id: UUID
    item: CandidateItemData
    safety_item: SafetyCandidateItem
    evidence_reference_code: str = ""
    pain_discomfort_area_code: str | None = None
    condition_code: str | None = None
    service_action_code: str | None = None
    target_strategy_code: str | None = None


@dataclass(frozen=True, slots=True)
class AdjustedCandidateData:
    candidate: CoordinatorCandidate
    candidate_data: dict[str, Any]
    items: tuple[CandidateItemData, ...]
    safety_candidate: SafetyCandidate
    evidence_reference_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionAssembly:
    context: DecisionContext
    routine_id: UUID
    catalog_version_id: UUID
    catalog_version: str
    catalog_status_code: Literal["ACTIVE"]
    catalog_review_status_code: Literal["DOMAIN_APPROVED"]
    catalog_production_eligible: Literal[True]
    catalog_activated: Literal[True]
    candidate: CoordinatorCandidate
    candidate_data: dict[str, Any]
    items: tuple[CandidateItemData, ...]
    safety_candidate: SafetyCandidate | None = None
    safety_rule_set: SafetyRuleSet | None = None
    alternative_items: tuple[AlternativeItemData, ...] = ()
    adjusted_candidates: tuple[AdjustedCandidateData, ...] = ()
    # Narration tone only. It is not a decision input and stays out of the input snapshot.
    coaching_style_code: str = "SUPPORTIVE"

    @property
    def coordinator_candidates(self) -> tuple[CoordinatorCandidate, ...]:
        return (self.candidate,) + tuple(
            adjusted.candidate for adjusted in self.adjusted_candidates
        )


@dataclass(frozen=True, slots=True)
class StoredIdempotency:
    request_hash: str
    response_payload: dict[str, Any]


class DecisionRepositoryPort(Protocol):
    def acquire_lock(self, session: Session, user_id: UUID, key: UUID) -> None: ...
    def get_idempotency(
        self, session: Session, user_id: UUID, key: UUID
    ) -> StoredIdempotency | None: ...
    def assemble(
        self, session: Session, user_id: UUID, daily_context_id: UUID
    ) -> DecisionAssembly | None: ...
    def persist(
        self,
        session: Session,
        *,
        user_id: UUID,
        assembly: DecisionAssembly,
        input_snapshot: dict[str, Any],
        input_hash: str,
        proposals: tuple[AgentProposal, ...],
        result: CoordinatorResult,
        explanation: DecisionExplanation,
        now: datetime,
    ) -> UUID: ...
    def save_idempotency(
        self,
        session: Session,
        *,
        user_id: UUID,
        key: UUID,
        request_hash: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None: ...
    def get_response(
        self, session: Session, user_id: UUID, decision_id: UUID
    ) -> dict[str, Any] | None: ...
    def get_response_for_date(
        self, session: Session, user_id: UUID, local_date: date
    ) -> dict[str, Any] | None: ...


class NarrationProviderUnavailableError(Exception):
    """No approved narration provider is configured for this environment."""


class NarrationProviderFailedError(Exception):
    """The configured provider did not return a usable narration payload."""


@dataclass(frozen=True, slots=True)
class NarrationPrompt:
    """Codes-only narration request; the payload never carries free text or identifiers."""

    prompt_version: str
    instruction: str
    slot_codes: tuple[str, ...]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NarrationCompletion:
    """One sentence per requested slot, plus the model that produced them."""

    model_code: str
    sentences: dict[str, str] = field(default_factory=dict)


class NarrationProviderPort(Protocol):
    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion: ...
