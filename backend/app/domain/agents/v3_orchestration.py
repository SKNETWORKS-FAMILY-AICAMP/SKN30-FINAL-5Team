"""Framework-independent routing, fallback, regeneration, and V3 graph result contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_compiler import (
    CompiledPlan,
    DeterministicFallbackPlanSpec,
    compile_plan,
)
from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_ORDER,
    ConstraintEnvelope,
    PlanSpec,
    SpecialistAgentProposal,
    _canonical_codes,
    _canonical_hash,
    _hash_value,
)
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationContext,
    IntegrityValidationResult,
    IntegrityValidationStatusCode,
    IntegrityViolationCode,
    validate_plan_integrity,
)
from backend.app.domain.rules.safety import SafetyRequiredActionCode

FALLBACK_REQUEST_SCHEMA_VERSION: Final[Literal["v3-fallback-request-v1"]] = "v3-fallback-request-v1"
FALLBACK_OUTCOME_SCHEMA_VERSION: Final[Literal["v3-fallback-outcome-v1"]] = "v3-fallback-outcome-v1"
REGENERATION_DIFFERENCE_SCHEMA_VERSION: Final[Literal["v3-regeneration-difference-v1"]] = (
    "v3-regeneration-difference-v1"
)
TERMINAL_RESULT_SCHEMA_VERSION: Final[Literal["v3-terminal-result-v1"]] = "v3-terminal-result-v1"
V3_GRAPH_RESULT_SCHEMA_VERSION: Final[Literal["v3-graph-result-v1"]] = "v3-graph-result-v1"


class OrchestrationRouteCode(StrEnum):
    COMPLETE = "COMPLETE"
    COORDINATOR_REPAIR = "COORDINATOR_REPAIR"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"
    TERMINAL = "TERMINAL"


class GraphTerminalStatusCode(StrEnum):
    COMPLETED = "COMPLETED"
    NEEDS_INPUT = "NEEDS_INPUT"
    REST = "REST"
    STOP_AND_SEEK_HELP = "STOP_AND_SEEK_HELP"
    FAILED = "FAILED"


class TerminalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["v3-terminal-result-v1"] = TERMINAL_RESULT_SCHEMA_VERSION
    status_code: GraphTerminalStatusCode
    reason_codes: tuple[str, ...] = Field(min_length=1)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_codes(values, field_name="terminal reason codes")

    @model_validator(mode="after")
    def validate_terminal(self) -> Self:
        if self.status_code is GraphTerminalStatusCode.COMPLETED:
            raise ValueError("COMPLETED is not a plan-less TerminalResult")
        return self


def route_after_integrity_validation(
    validation: IntegrityValidationResult,
) -> OrchestrationRouteCode:
    if validation.status_code is IntegrityValidationStatusCode.PASS:
        return OrchestrationRouteCode.COMPLETE
    codes = {item.code for item in validation.violations}
    if (
        validation.status_code is IntegrityValidationStatusCode.REPAIRABLE
        and validation.repair_attempt == 0
    ):
        return OrchestrationRouteCode.COORDINATOR_REPAIR
    if codes & {
        IntegrityViolationCode.STOP_AND_SEEK_HELP,
        IntegrityViolationCode.PLAN_GENERATION_FORBIDDEN,
        IntegrityViolationCode.APPROVED_SAFE_EXERCISE_UNAVAILABLE,
        IntegrityViolationCode.REQUIRED_INPUT_MISSING,
        IntegrityViolationCode.POLICY_DATA_INCOMPLETE,
    }:
        return OrchestrationRouteCode.TERMINAL
    return OrchestrationRouteCode.DETERMINISTIC_FALLBACK


class FallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["v3-fallback-request-v1"] = FALLBACK_REQUEST_SCHEMA_VERSION
    constraint_envelope: ConstraintEnvelope
    exercise_pool: ExercisePoolSnapshot
    fallback_version: str
    request_hash: str

    @field_validator("request_hash")
    @classmethod
    def validate_request_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="fallback request hash")

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        _canonical_codes((self.fallback_version,), field_name="fallback_version")
        if self.exercise_pool.constraint_envelope_hash != self.constraint_envelope.envelope_hash:
            raise ValueError("fallback envelope and pool hashes do not match")
        if self.request_hash != _canonical_hash(self._hash_payload()):
            raise ValueError("request_hash does not match fallback request")
        return self

    def _hash_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "envelope_hash": self.constraint_envelope.envelope_hash,
            "pool_hash": self.exercise_pool.pool_hash,
            "fallback_version": self.fallback_version,
        }

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": FALLBACK_REQUEST_SCHEMA_VERSION, **values}
        envelope = payload["constraint_envelope"]
        pool = payload["exercise_pool"]
        if not isinstance(envelope, ConstraintEnvelope) or not isinstance(
            pool, ExercisePoolSnapshot
        ):
            raise ValueError("fallback request requires typed envelope and pool")
        payload["request_hash"] = _canonical_hash(
            {
                "schema_version": FALLBACK_REQUEST_SCHEMA_VERSION,
                "envelope_hash": envelope.envelope_hash,
                "pool_hash": pool.pool_hash,
                "fallback_version": payload["fallback_version"],
            }
        )
        return cls.model_validate(payload)


class DeterministicFallbackProvider(Protocol):
    def generate(self, request: FallbackRequest) -> DeterministicFallbackPlanSpec | None: ...


class FallbackOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["v3-fallback-outcome-v1"] = FALLBACK_OUTCOME_SCHEMA_VERSION
    fallback_version: str
    fallback_used: Literal[True] = True
    compiled_plan: CompiledPlan | None
    integrity_validation: IntegrityValidationResult
    terminal_result: TerminalResult | None
    outcome_hash: str

    @field_validator("outcome_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="fallback outcome hash")

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        _canonical_codes((self.fallback_version,), field_name="fallback_version")
        passed = self.integrity_validation.status_code is IntegrityValidationStatusCode.PASS
        if passed != (self.compiled_plan is not None and self.terminal_result is None):
            raise ValueError("only a validated fallback may expose a compiled plan")
        if not passed and self.terminal_result is None:
            raise ValueError("invalid fallback requires a plan-less terminal result")
        if self.outcome_hash != _canonical_hash(
            self.model_dump(mode="json", exclude={"outcome_hash"})
        ):
            raise ValueError("outcome_hash does not match fallback outcome")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {
            "schema_version": FALLBACK_OUTCOME_SCHEMA_VERSION,
            "fallback_used": True,
            **values,
        }
        payload["outcome_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


def _terminal_for_envelope(
    envelope: ConstraintEnvelope,
    *,
    default_status: GraphTerminalStatusCode,
) -> TerminalResult:
    if envelope.safety_required_action_code is SafetyRequiredActionCode.STOP_AND_SEEK_HELP:
        return TerminalResult(
            status_code=GraphTerminalStatusCode.STOP_AND_SEEK_HELP,
            reason_codes=("SAFETY_STOP_AND_SEEK_HELP",),
        )
    if envelope.safety_required_action_code is SafetyRequiredActionCode.REST:
        return TerminalResult(
            status_code=GraphTerminalStatusCode.REST,
            reason_codes=("SAFETY_REST",),
        )
    return TerminalResult(status_code=default_status, reason_codes=("FALLBACK_UNAVAILABLE",))


def execute_deterministic_fallback(
    provider: DeterministicFallbackProvider,
    *,
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
    fallback_version: str,
    compiler_version: str,
    validator_version: str,
    validation_context: IntegrityValidationContext,
    terminal_status_if_unavailable: GraphTerminalStatusCode = GraphTerminalStatusCode.FAILED,
) -> FallbackOutcome:
    """Run a port result through the same compiler and integrity validator."""

    if not envelope.plan_generation_allowed or envelope.safety_required_action_code is not None:
        validation = validate_plan_integrity(
            None,
            envelope=envelope,
            pool=pool,
            repair_attempt=0,
            validator_version=validator_version,
            context=validation_context.model_copy(update={"fallback_plan_validation": True}),
        )
        return FallbackOutcome.create(
            fallback_version=fallback_version,
            compiled_plan=None,
            integrity_validation=validation,
            terminal_result=_terminal_for_envelope(
                envelope, default_status=terminal_status_if_unavailable
            ),
        )

    request = FallbackRequest.create(
        constraint_envelope=envelope,
        exercise_pool=pool,
        fallback_version=fallback_version,
    )
    fallback_plan = provider.generate(request)
    compiled: CompiledPlan | None = None
    if fallback_plan is not None:
        try:
            if fallback_plan.fallback_version != fallback_version:
                raise ValueError("fallback version mismatch")
            compiled = compile_plan(
                fallback_plan,
                envelope=envelope,
                pool=pool,
                compiler_version=compiler_version,
            )
        except ValueError:
            compiled = None
    context = validation_context.model_copy(update={"fallback_plan_validation": compiled is None})
    validation = validate_plan_integrity(
        compiled,
        envelope=envelope,
        pool=pool,
        repair_attempt=0,
        validator_version=validator_version,
        context=context,
    )
    terminal = None
    if validation.status_code is not IntegrityValidationStatusCode.PASS:
        terminal = _terminal_for_envelope(envelope, default_status=terminal_status_if_unavailable)
    return FallbackOutcome.create(
        fallback_version=fallback_version,
        compiled_plan=compiled if terminal is None else None,
        integrity_validation=validation,
        terminal_result=terminal,
    )


class RegenerationDifferenceCode(StrEnum):
    CORE_EXERCISE_CHANGED = "CORE_EXERCISE_CHANGED"
    SET_REPETITION_STRUCTURE_CHANGED = "SET_REPETITION_STRUCTURE_CHANGED"
    EXERCISE_SEQUENCE_CHANGED = "EXERCISE_SEQUENCE_CHANGED"
    ROUTINE_COMPOSITION_CHANGED = "ROUTINE_COMPOSITION_CHANGED"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    NO_MEANINGFUL_DIFFERENCE = "NO_MEANINGFUL_DIFFERENCE"
    REGENERATION_LIMIT_REACHED = "REGENERATION_LIMIT_REACHED"


_DIFFERENCE_ORDER = tuple(RegenerationDifferenceCode)


class RegenerationDifferenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["v3-regeneration-difference-v1"] = (
        REGENERATION_DIFFERENCE_SCHEMA_VERSION
    )
    generation_sequence: int = Field(gt=0)
    meaningful: bool
    difference_codes: tuple[RegenerationDifferenceCode, ...] = Field(min_length=1)
    result_hash: str

    @field_validator("result_hash")
    @classmethod
    def validate_result_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="regeneration difference hash")

    @model_validator(mode="after")
    def validate_difference(self) -> Self:
        if self.difference_codes != tuple(
            sorted(set(self.difference_codes), key=_DIFFERENCE_ORDER.index)
        ):
            raise ValueError("difference codes must be unique and canonical")
        meaningful_codes = {
            RegenerationDifferenceCode.CORE_EXERCISE_CHANGED,
            RegenerationDifferenceCode.SET_REPETITION_STRUCTURE_CHANGED,
            RegenerationDifferenceCode.EXERCISE_SEQUENCE_CHANGED,
            RegenerationDifferenceCode.ROUTINE_COMPOSITION_CHANGED,
        }
        if self.meaningful != bool(set(self.difference_codes) & meaningful_codes):
            raise ValueError("meaningful flag does not match structural difference codes")
        if self.generation_sequence > 2 and self.difference_codes != (
            RegenerationDifferenceCode.REGENERATION_LIMIT_REACHED,
        ):
            raise ValueError("third generation must be rejected")
        if self.result_hash != _canonical_hash(
            self.model_dump(mode="json", exclude={"result_hash"})
        ):
            raise ValueError("result_hash does not match regeneration difference")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": REGENERATION_DIFFERENCE_SCHEMA_VERSION, **values}
        payload["result_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


def evaluate_regeneration_difference(
    previous: CompiledPlan,
    regenerated: CompiledPlan,
    *,
    generation_sequence: int,
) -> RegenerationDifferenceResult:
    if generation_sequence > 2:
        return RegenerationDifferenceResult.create(
            generation_sequence=generation_sequence,
            meaningful=False,
            difference_codes=(RegenerationDifferenceCode.REGENERATION_LIMIT_REACHED,),
        )
    if generation_sequence not in (1, 2):
        raise ValueError("generation_sequence must be 1 or 2")

    previous_items = tuple(item.prescription for item in previous.exercises)
    regenerated_items = tuple(item.prescription for item in regenerated.exercises)
    codes: tuple[RegenerationDifferenceCode, ...]
    if previous.action_code == regenerated.action_code and previous_items == regenerated_items:
        codes = (RegenerationDifferenceCode.EXACT_DUPLICATE,)
    else:
        differences: set[RegenerationDifferenceCode] = set()
        previous_ids = tuple(item.exercise_id for item in previous_items)
        regenerated_ids = tuple(item.exercise_id for item in regenerated_items)
        if set(previous_ids) != set(regenerated_ids):
            differences.add(RegenerationDifferenceCode.CORE_EXERCISE_CHANGED)
        elif previous_ids != regenerated_ids:
            differences.add(RegenerationDifferenceCode.EXERCISE_SEQUENCE_CHANGED)
        previous_structure = {
            item.exercise_id: (item.sets, item.repetitions_per_set) for item in previous_items
        }
        regenerated_structure = {
            item.exercise_id: (item.sets, item.repetitions_per_set) for item in regenerated_items
        }
        if previous_structure != regenerated_structure:
            differences.add(RegenerationDifferenceCode.SET_REPETITION_STRUCTURE_CHANGED)
        if previous.action_code is not regenerated.action_code:
            differences.add(RegenerationDifferenceCode.ROUTINE_COMPOSITION_CHANGED)
        if not differences:
            differences.add(RegenerationDifferenceCode.NO_MEANINGFUL_DIFFERENCE)
        codes = tuple(code for code in _DIFFERENCE_ORDER if code in differences)
    meaningful = any(
        code
        in {
            RegenerationDifferenceCode.CORE_EXERCISE_CHANGED,
            RegenerationDifferenceCode.SET_REPETITION_STRUCTURE_CHANGED,
            RegenerationDifferenceCode.EXERCISE_SEQUENCE_CHANGED,
            RegenerationDifferenceCode.ROUTINE_COMPOSITION_CHANGED,
        }
        for code in codes
    )
    return RegenerationDifferenceResult.create(
        generation_sequence=generation_sequence,
        meaningful=meaningful,
        difference_codes=codes,
    )


class V3GraphResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["v3-graph-result-v1"] = V3_GRAPH_RESULT_SCHEMA_VERSION
    graph_version: str
    terminal_status_code: GraphTerminalStatusCode
    envelope_hash: str
    pool_hash: str
    round_one_proposals: tuple[SpecialistAgentProposal, ...]
    coordinator_initial_plan: PlanSpec | None
    coordinator_repair_plan: PlanSpec | None
    compiled_plan: CompiledPlan | None
    integrity_violation_codes: tuple[IntegrityViolationCode, ...]
    fallback_used: bool
    fallback_version: str | None
    regeneration_difference: RegenerationDifferenceResult | None
    final_plan: CompiledPlan | None
    terminal_result: TerminalResult | None
    result_hash: str

    @field_validator("envelope_hash", "pool_hash", "result_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="graph result hash")

    @field_validator("integrity_violation_codes")
    @classmethod
    def validate_integrity_codes(
        cls, values: tuple[IntegrityViolationCode, ...]
    ) -> tuple[IntegrityViolationCode, ...]:
        if values != tuple(code for code in IntegrityViolationCode if code in set(values)):
            raise ValueError("integrity violation codes must be unique and canonical")
        return values

    @model_validator(mode="after")
    def validate_graph_result(self) -> Self:
        _canonical_codes((self.graph_version,), field_name="graph_version")
        proposal_roles = tuple(item.agent_type_code for item in self.round_one_proposals)
        if proposal_roles != tuple(
            role for role in SPECIALIST_AGENT_ORDER if role in proposal_roles
        ):
            raise ValueError("Round 1 proposals must use canonical role order")
        if len(proposal_roles) != len(set(proposal_roles)):
            raise ValueError("Round 1 proposals must not contain duplicate roles")
        if any(
            proposal.envelope_hash != self.envelope_hash or proposal.pool_hash != self.pool_hash
            for proposal in self.round_one_proposals
        ):
            raise ValueError("Round 1 proposals must reference the graph envelope and pool")
        if (
            self.coordinator_initial_plan is not None
            and self.coordinator_initial_plan.repair_attempt != 0
        ):
            raise ValueError("initial Coordinator plan must use repair attempt 0")
        if (
            self.coordinator_repair_plan is not None
            and self.coordinator_repair_plan.repair_attempt != 1
        ):
            raise ValueError("repair Coordinator plan must use repair attempt 1")
        if self.fallback_used != (self.fallback_version is not None):
            raise ValueError("fallback use and version must agree")
        if self.fallback_version is not None:
            _canonical_codes((self.fallback_version,), field_name="fallback_version")
        completed = self.terminal_status_code is GraphTerminalStatusCode.COMPLETED
        if completed != (self.final_plan is not None and self.terminal_result is None):
            raise ValueError("completed graph requires exactly one final plan")
        if not completed and (
            self.final_plan is not None
            or self.terminal_result is None
            or self.terminal_result.status_code is not self.terminal_status_code
        ):
            raise ValueError("plan-less graph requires a matching terminal result")
        if self.final_plan is not None and self.compiled_plan != self.final_plan:
            raise ValueError("final plan must be the validated compiled plan")
        if completed and self.integrity_violation_codes:
            raise ValueError("completed graph cannot retain integrity violations")
        for plan in (self.coordinator_initial_plan, self.coordinator_repair_plan):
            if plan is not None and (
                plan.envelope_hash != self.envelope_hash or plan.pool_hash != self.pool_hash
            ):
                raise ValueError("Coordinator plans must reference the graph envelope and pool")
        if self.compiled_plan is not None and (
            self.compiled_plan.envelope_hash != self.envelope_hash
            or self.compiled_plan.pool_hash != self.pool_hash
        ):
            raise ValueError("compiled plan must reference the graph envelope and pool")
        if self.result_hash != _canonical_hash(
            self.model_dump(mode="json", exclude={"result_hash"})
        ):
            raise ValueError("result_hash does not match graph result")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {
            "schema_version": V3_GRAPH_RESULT_SCHEMA_VERSION,
            "coordinator_initial_plan": None,
            "coordinator_repair_plan": None,
            "compiled_plan": None,
            "fallback_used": False,
            "fallback_version": None,
            "regeneration_difference": None,
            "final_plan": None,
            "terminal_result": None,
            **values,
        }
        payload["result_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


__all__ = [
    "FALLBACK_OUTCOME_SCHEMA_VERSION",
    "FALLBACK_REQUEST_SCHEMA_VERSION",
    "REGENERATION_DIFFERENCE_SCHEMA_VERSION",
    "TERMINAL_RESULT_SCHEMA_VERSION",
    "V3_GRAPH_RESULT_SCHEMA_VERSION",
    "DeterministicFallbackProvider",
    "FallbackOutcome",
    "FallbackRequest",
    "GraphTerminalStatusCode",
    "OrchestrationRouteCode",
    "RegenerationDifferenceCode",
    "RegenerationDifferenceResult",
    "TerminalResult",
    "V3GraphResult",
    "evaluate_regeneration_difference",
    "execute_deterministic_fallback",
    "route_after_integrity_validation",
]
