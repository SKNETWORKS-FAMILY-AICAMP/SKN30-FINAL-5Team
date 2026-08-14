import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.domain.agents.coordinator import (
    COORDINATOR_VERSION,
    CoordinatorInput,
    CoordinatorStatusCode,
    coordinate,
)
from backend.app.domain.agents.runner import ProposalAgent, ProposalRequest, run_required_agents
from backend.app.domain.rules.duration import DURATION_RULE_VERSION, DurationAdjustmentSourceCode
from backend.app.domain.rules.safety import SAFETY_ENGINE_VERSION
from backend.app.modules.decisions.agents import default_agents
from backend.app.modules.decisions.application import DecisionContextAssembler
from backend.app.modules.decisions.codes import (
    DECISION_GRAPH_VERSION,
    DECISION_INPUT_SCHEMA_VERSION,
    DECISION_POLICY_VERSION,
)
from backend.app.modules.decisions.context import DecisionContext
from backend.app.modules.decisions.ports import DecisionRepositoryPort
from backend.app.modules.decisions.schemas import DecisionCreateRequest, DecisionResponse


class DecisionNotFoundError(Exception):
    pass


class DecisionContextNotFoundError(Exception):
    pass


class StaleDecisionContextError(Exception):
    pass


class DecisionInputUnavailableError(Exception):
    pass


class DecisionFailedError(Exception):
    pass


class IdempotencyKeyReusedError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class DecisionService:
    def __init__(
        self,
        repository: DecisionRepositoryPort,
        *,
        agents: Sequence[ProposalAgent[DecisionContext, object]] | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._context_assembler = DecisionContextAssembler(repository)
        self._agents = tuple(agents) if agents is not None else default_agents()
        self._clock = clock

    def create(
        self, session: Session, user_id: UUID, request: DecisionCreateRequest, idempotency_key: UUID
    ) -> DecisionResponse:
        request_hash = _hash(request.model_dump(mode="json"))
        outcome: str | None = None
        response: DecisionResponse | None = None
        with session.begin():
            self._repository.acquire_lock(session, user_id, idempotency_key)
            prior = self._repository.get_idempotency(session, user_id, idempotency_key)
            if prior is not None:
                if prior.request_hash != request_hash:
                    raise IdempotencyKeyReusedError
                outcome = str(prior.response_payload.get("outcome_code"))
                if outcome == "COMPLETED":
                    response = DecisionResponse.model_validate(prior.response_payload["response"])
            else:
                assembly = self._context_assembler.assemble(
                    session, user_id, request.daily_context_id
                )
                if assembly is None or assembly.context.local_date != request.local_date:
                    raise DecisionContextNotFoundError
                if assembly.context.context_version != request.expected_context_version:
                    raise StaleDecisionContextError
                snapshot = assembly.context.snapshot()
                input_hash = _hash(
                    {
                        "schema_version": DECISION_INPUT_SCHEMA_VERSION,
                        "snapshot": snapshot,
                        "catalog_version": assembly.catalog_version,
                        "policy_version": DECISION_POLICY_VERSION,
                        "safety_rule_version": SAFETY_ENGINE_VERSION,
                        "duration_rule_version": DURATION_RULE_VERSION,
                        "graph_version": DECISION_GRAPH_VERSION,
                        "coordinator_version": COORDINATOR_VERSION,
                    }
                )
                source = DurationAdjustmentSourceCode(
                    assembly.context.duration_adjustment_source_code
                )
                proposal_request = ProposalRequest(
                    context=assembly.context,
                    candidates=(assembly.candidate,),
                    candidate_exercise_ids=assembly.candidate.exercise_ids,
                    requested_duration_minutes=assembly.context.requested_duration_minutes,
                    duration_adjustment_source_code=source,
                    policy_version=DECISION_POLICY_VERSION,
                )
                batch = run_required_agents(request=proposal_request, agents=self._agents)
                result = coordinate(
                    CoordinatorInput(
                        proposals=batch.proposals,
                        candidates=(assembly.candidate,),
                        profile_duration_minutes=assembly.context.profile_duration_minutes,
                        requested_duration_minutes=assembly.context.requested_duration_minutes,
                        duration_adjustment_source_code=source,
                        policy_version=DECISION_POLICY_VERSION,
                        catalog_version=assembly.catalog_version,
                        catalog_status_code=assembly.catalog_status_code,
                        catalog_review_status_code=assembly.catalog_review_status_code,
                        catalog_production_eligible=assembly.catalog_production_eligible,
                        catalog_activated=assembly.catalog_activated,
                        safety_rule_version=SAFETY_ENGINE_VERSION,
                        duration_rule_version=DURATION_RULE_VERSION,
                    )
                )
                decision_id = self._repository.persist(
                    session,
                    user_id=user_id,
                    assembly=assembly,
                    input_snapshot=snapshot,
                    input_hash=input_hash,
                    proposals=batch.proposals,
                    result=result,
                    now=self._clock(),
                )
                outcome = result.status_code.value
                payload: dict[str, object] = {
                    "outcome_code": outcome,
                    "decision_id": str(decision_id),
                }
                if result.status_code in {
                    CoordinatorStatusCode.PASS,
                    CoordinatorStatusCode.REVISE,
                    CoordinatorStatusCode.BLOCKED,
                }:
                    stored = self._repository.get_response(session, user_id, decision_id)
                    if stored is None:
                        raise RuntimeError("atomically persisted decision cannot be read")
                    response = DecisionResponse.model_validate(stored)
                    payload = {
                        "outcome_code": "COMPLETED",
                        "response": response.model_dump(mode="json"),
                    }
                    outcome = "COMPLETED"
                self._repository.save_idempotency(
                    session,
                    user_id=user_id,
                    key=idempotency_key,
                    request_hash=request_hash,
                    payload=payload,
                    now=self._clock(),
                )
        if outcome == CoordinatorStatusCode.NEEDS_INPUT.value:
            raise DecisionInputUnavailableError
        if outcome == CoordinatorStatusCode.FAILED.value:
            raise DecisionFailedError
        if response is None:
            raise DecisionFailedError
        return response

    def get(self, session: Session, user_id: UUID, decision_id: UUID) -> DecisionResponse:
        payload = self._repository.get_response(session, user_id, decision_id)
        if payload is None:
            raise DecisionNotFoundError
        return DecisionResponse.model_validate(payload)


__all__ = [
    "DecisionService",
    "DecisionNotFoundError",
    "DecisionContextNotFoundError",
    "StaleDecisionContextError",
    "DecisionInputUnavailableError",
    "DecisionFailedError",
    "IdempotencyKeyReusedError",
]
