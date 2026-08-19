import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.domain.agents.contracts import RecommendedActionCode
from backend.app.domain.agents.coordinator import (
    COORDINATOR_VERSION,
    CoordinatorCandidate,
    CoordinatorInput,
    CoordinatorStatusCode,
    DownshiftAdjustmentCode,
    coordinate,
)
from backend.app.domain.agents.runner import ProposalAgent, ProposalRequest, run_required_agents
from backend.app.domain.rules.duration import DURATION_RULE_VERSION, DurationAdjustmentSourceCode
from backend.app.domain.rules.safety import (
    SAFETY_ENGINE_VERSION,
    AdverseReactionCode,
    BodyAreaCode,
    Discomfort,
    DiscomfortSeverityCode,
    SafetyCandidate,
    SafetyCandidateItem,
    SafetyContext,
    SafetyEvaluation,
    SafetyStatusCode,
    evaluate_safety,
)
from backend.app.modules.decisions.agents import default_agents
from backend.app.modules.decisions.application import DecisionContextAssembler
from backend.app.modules.decisions.codes import (
    DECISION_GRAPH_VERSION,
    DECISION_INPUT_SCHEMA_VERSION,
    DECISION_POLICY_VERSION,
)
from backend.app.modules.decisions.context import DecisionContext
from backend.app.modules.decisions.explanations import build_explanation
from backend.app.modules.decisions.ports import (
    AdjustedCandidateData,
    AlternativeItemData,
    DecisionAssembly,
    DecisionRepositoryPort,
    NarrationProviderPort,
)
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


def _safety_context(context: DecisionContext) -> SafetyContext:
    return SafetyContext(
        discomforts=tuple(
            Discomfort(BodyAreaCode(area), DiscomfortSeverityCode[severity])
            for area, severity in context.discomforts
        ),
        adverse_reaction_codes=tuple(
            AdverseReactionCode(code) for code in context.adverse_reaction_codes
        ),
        attention_area_codes=tuple(BodyAreaCode(code) for code in context.attention_area_codes),
    )


def _base_safety_candidate(assembly: DecisionAssembly) -> SafetyCandidate:
    if assembly.safety_candidate is not None:
        return assembly.safety_candidate
    return SafetyCandidate(
        items=tuple(
            SafetyCandidateItem(exercise_id, assembly.catalog_version, "UNSPECIFIED")
            for exercise_id in assembly.candidate.exercise_ids
        )
    )


def _candidate_data(
    assembly: DecisionAssembly,
    *,
    candidate_id: str,
) -> dict[str, object]:
    return {**assembly.candidate_data, "candidate_code": candidate_id}


def _build_adjusted_candidates(
    assembly: DecisionAssembly,
    context: SafetyContext,
    base_safety_candidate: SafetyCandidate,
    base_evaluation: SafetyEvaluation,
) -> tuple[AdjustedCandidateData, ...]:
    adjusted: list[AdjustedCandidateData] = []
    if base_evaluation.caution_exercise_codes or assembly.context.fatigue_level_code == "MODERATE":
        candidate_id = f"{assembly.candidate.candidate_id}-approved-downshift"
        candidate = assembly.candidate.model_copy(
            update={
                "candidate_id": candidate_id,
                "action_code": RecommendedActionCode.DOWNSHIFT,
                "downshift_adjustment_codes": (DownshiftAdjustmentCode.INTENSITY_REDUCED,),
            }
        )
        adjusted.append(
            AdjustedCandidateData(
                candidate=candidate,
                candidate_data=_candidate_data(assembly, candidate_id=candidate_id),
                items=tuple(replace(item, intensity_code="LOW") for item in assembly.items),
                safety_candidate=base_safety_candidate,
            )
        )

    excluded = set(base_evaluation.excluded_exercise_codes)
    if not excluded:
        return tuple(adjusted)
    alternatives_by_source: dict[str, AlternativeItemData] = {}
    for source_id in sorted(excluded):
        options = sorted(
            (
                alternative
                for alternative in assembly.alternative_items
                if str(alternative.source_exercise_id) == source_id
            ),
            key=lambda value: str(value.item.exercise_id),
        )
        for alternative in options:
            alternative_evaluation = evaluate_safety(
                context,
                SafetyCandidate(items=(alternative.safety_item,)),
                assembly.safety_rule_set,
            )
            if (
                alternative_evaluation.status_code
                in {
                    SafetyStatusCode.PASS,
                    SafetyStatusCode.REVISE,
                }
                and not alternative_evaluation.excluded_exercise_codes
            ):
                alternatives_by_source[source_id] = alternative
                break
    if set(alternatives_by_source) != excluded:
        return tuple(adjusted)

    replacement_safety = {
        str(alternative.source_exercise_id): alternative.safety_item
        for alternative in alternatives_by_source.values()
    }
    changed_items = tuple(
        replace(
            item,
            exercise_id=alternatives_by_source[str(item.exercise_id)].item.exercise_id,
            instruction_content_version=alternatives_by_source[
                str(item.exercise_id)
            ].item.instruction_content_version,
            display_name=alternatives_by_source[str(item.exercise_id)].item.display_name,
            intensity_code=(
                "LOW"
                if alternatives_by_source[str(item.exercise_id)].item.intensity_code == "LOW"
                else item.intensity_code
            ),
        )
        if str(item.exercise_id) in alternatives_by_source
        else item
        for item in assembly.items
    )
    changed_safety_items_by_code = {
        changed.exercise_code: changed
        for item in base_safety_candidate.items
        for changed in (replacement_safety.get(item.exercise_code, item),)
    }
    changed_safety_items = tuple(
        changed_safety_items_by_code[code] for code in sorted(changed_safety_items_by_code)
    )
    exercise_ids = tuple(sorted({str(item.exercise_id) for item in changed_items}))
    changed_safety_candidate = SafetyCandidate(items=changed_safety_items)
    changed_evaluation = evaluate_safety(
        context,
        changed_safety_candidate,
        assembly.safety_rule_set,
    )
    if changed_evaluation.status_code not in {SafetyStatusCode.PASS, SafetyStatusCode.REVISE}:
        return tuple(adjusted)
    if changed_evaluation.excluded_exercise_codes:
        return tuple(adjusted)

    candidate_id = f"{assembly.candidate.candidate_id}-safety-change"
    candidate = assembly.candidate.model_copy(
        update={
            "candidate_id": candidate_id,
            "action_code": RecommendedActionCode.CHANGE,
            "exercise_ids": exercise_ids,
        }
    )
    adjusted.append(
        AdjustedCandidateData(
            candidate=candidate,
            candidate_data=_candidate_data(assembly, candidate_id=candidate_id),
            items=changed_items,
            safety_candidate=changed_safety_candidate,
            evidence_reference_codes=tuple(
                sorted(
                    alternative.evidence_reference_code
                    for alternative in alternatives_by_source.values()
                    if alternative.evidence_reference_code
                )
            ),
        )
    )
    return tuple(adjusted)


def _prepare_safety(
    assembly: DecisionAssembly,
) -> tuple[DecisionAssembly, tuple[tuple[str, SafetyEvaluation], ...]]:
    context = _safety_context(assembly.context)
    base_candidate = _base_safety_candidate(assembly)
    base_evaluation = evaluate_safety(context, base_candidate, assembly.safety_rule_set)
    adjusted = _build_adjusted_candidates(
        assembly,
        context,
        base_candidate,
        base_evaluation,
    )
    prepared = replace(assembly, adjusted_candidates=adjusted)
    evaluations = [(assembly.candidate.candidate_id, base_evaluation)]
    evaluations.extend(
        (
            candidate.candidate.candidate_id,
            evaluate_safety(context, candidate.safety_candidate, assembly.safety_rule_set),
        )
        for candidate in adjusted
    )
    return prepared, tuple(sorted(evaluations, key=lambda value: value[0]))


def _safety_rule_version(assembly: DecisionAssembly) -> str:
    if assembly.safety_rule_set is not None:
        return assembly.safety_rule_set.version_code
    return SAFETY_ENGINE_VERSION


class DecisionService:
    def __init__(
        self,
        repository: DecisionRepositoryPort,
        *,
        agents: Sequence[ProposalAgent[DecisionContext, CoordinatorCandidate]] | None = None,
        narration_provider: NarrationProviderPort | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._context_assembler = DecisionContextAssembler(repository)
        self._agents = tuple(agents) if agents is not None else default_agents()
        # Optional narration only. Its absence or failure never changes the decision.
        self._narration_provider = narration_provider
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
                assembly, safety_evaluations = _prepare_safety(assembly)
                safety_rule_version = _safety_rule_version(assembly)
                snapshot = assembly.context.snapshot()
                input_hash = _hash(
                    {
                        "schema_version": DECISION_INPUT_SCHEMA_VERSION,
                        "snapshot": snapshot,
                        "catalog_version": assembly.catalog_version,
                        "policy_version": DECISION_POLICY_VERSION,
                        "safety_engine_version": SAFETY_ENGINE_VERSION,
                        "safety_rule_version": safety_rule_version,
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
                    candidates=assembly.coordinator_candidates,
                    candidate_exercise_ids=tuple(
                        sorted(
                            {
                                exercise_id
                                for candidate in assembly.coordinator_candidates
                                for exercise_id in candidate.exercise_ids
                            }
                        )
                    ),
                    requested_duration_minutes=assembly.context.requested_duration_minutes,
                    duration_adjustment_source_code=source,
                    policy_version=DECISION_POLICY_VERSION,
                    candidate_safety_evaluations=safety_evaluations,
                    candidate_evidence_reference_codes=tuple(
                        sorted(
                            (
                                candidate.candidate.candidate_id,
                                candidate.evidence_reference_codes,
                            )
                            for candidate in assembly.adjusted_candidates
                            if candidate.evidence_reference_codes
                        )
                    ),
                )
                batch = run_required_agents(request=proposal_request, agents=self._agents)
                result = coordinate(
                    CoordinatorInput(
                        proposals=batch.proposals,
                        candidates=assembly.coordinator_candidates,
                        profile_duration_minutes=assembly.context.profile_duration_minutes,
                        requested_duration_minutes=assembly.context.requested_duration_minutes,
                        duration_adjustment_source_code=source,
                        policy_version=DECISION_POLICY_VERSION,
                        catalog_version=assembly.catalog_version,
                        catalog_status_code=assembly.catalog_status_code,
                        catalog_review_status_code=assembly.catalog_review_status_code,
                        catalog_production_eligible=assembly.catalog_production_eligible,
                        catalog_activated=assembly.catalog_activated,
                        safety_rule_version=safety_rule_version,
                        duration_rule_version=DURATION_RULE_VERSION,
                    )
                )
                explanation = build_explanation(
                    result=result,
                    proposals=batch.proposals,
                    coaching_style_code=assembly.coaching_style_code,
                    provider=self._narration_provider,
                )
                decision_id = self._repository.persist(
                    session,
                    user_id=user_id,
                    assembly=assembly,
                    input_snapshot=snapshot,
                    input_hash=input_hash,
                    proposals=batch.proposals,
                    result=result,
                    explanation=explanation,
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

    def get_for_date(self, session: Session, user_id: UUID, local_date: date) -> DecisionResponse:
        """Return the day's stored decision so a client restart can resume it.

        Reading never re-runs agents or narration; it replays what was stored.
        """

        payload = self._repository.get_response_for_date(session, user_id, local_date)
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
