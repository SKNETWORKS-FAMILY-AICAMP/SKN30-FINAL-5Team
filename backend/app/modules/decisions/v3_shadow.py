"""Framework-independent contracts for offline V3 shadow evaluation."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal, Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import to_jsonable_python

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    ExercisePrescription,
    RegenerationContext,
)
from backend.app.domain.agents.v3_orchestration import GraphTerminalStatusCode

SHADOW_CASE_SCHEMA_VERSION: Final[Literal["v3-shadow-case-v1"]] = "v3-shadow-case-v1"
SHADOW_REQUEST_SCHEMA_VERSION: Final[Literal["v3-shadow-request-v1"]] = "v3-shadow-request-v1"
SHADOW_PLAN_SCHEMA_VERSION: Final[Literal["v3-shadow-plan-projection-v1"]] = (
    "v3-shadow-plan-projection-v1"
)
SHADOW_INVOCATION_SCHEMA_VERSION: Final[Literal["v3-shadow-invocation-metric-v1"]] = (
    "v3-shadow-invocation-metric-v1"
)
SHADOW_SAFETY_SCHEMA_VERSION: Final[Literal["v3-shadow-safety-metric-v1"]] = (
    "v3-shadow-safety-metric-v1"
)
SHADOW_USAGE_SCHEMA_VERSION: Final[Literal["v3-shadow-usage-metric-v1"]] = (
    "v3-shadow-usage-metric-v1"
)
SHADOW_RESULT_SCHEMA_VERSION: Final[Literal["v3-shadow-result-v1"]] = "v3-shadow-result-v1"

_MACHINE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CREATE_CONTEXT_KEY = "v3_shadow_result_create"
_CREATE_CONTEXT_SENTINEL = object()


def _machine_code(value: str, *, field_name: str) -> str:
    if not _MACHINE_CODE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a structured machine code")
    return value


def _hash_value(value: str, *, field_name: str) -> str:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _canonical_hash(value: object) -> str:
    canonical = json.dumps(
        to_jsonable_python(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _canonical_machine_codes(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    for value in values:
        _machine_code(value, field_name=field_name)
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be unique and canonically sorted")
    return values


class V3ShadowFailureCode(StrEnum):
    SHADOW_DISABLED = "V3_SHADOW_DISABLED"
    INPUT_INVALID = "V3_SHADOW_INPUT_INVALID"
    INPUT_STALE = "V3_SHADOW_INPUT_STALE"
    PROVIDER_NOT_CONFIGURED = "V3_SHADOW_PROVIDER_NOT_CONFIGURED"
    PROVIDER_UNAVAILABLE = "V3_SHADOW_PROVIDER_UNAVAILABLE"
    GRAPH_FAILED = "V3_SHADOW_GRAPH_FAILED"
    AUDIT_ARTIFACT_INCOMPLETE = "V3_SHADOW_AUDIT_ARTIFACT_INCOMPLETE"
    SAFETY_INVARIANT_FAILED = "V3_SHADOW_SAFETY_INVARIANT_FAILED"


class V3ShadowRoleCode(StrEnum):
    TRAINING = "TRAINING"
    RECOVERY = "RECOVERY"
    FEASIBILITY = "FEASIBILITY"
    COORDINATOR = "COORDINATOR"


class V3ShadowInvocationPhaseCode(StrEnum):
    PROPOSE = "PROPOSE"
    REVIEW = "REVIEW"
    COORDINATE = "COORDINATE"
    REPAIR = "REPAIR"


class V3ShadowInvocationStatusCode(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    INVALID_OUTPUT = "INVALID_OUTPUT"


class V3ShadowStructuredOutputStatusCode(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class V3ShadowUsageStatusCode(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class V3ShadowSafetyViolationCode(StrEnum):
    SAFETY_VETO_OVERRIDDEN = "SAFETY_VETO_OVERRIDDEN"
    PROVIDER_CALLED_AFTER_SAFETY_TERMINAL = "PROVIDER_CALLED_AFTER_SAFETY_TERMINAL"
    PLAN_RETURNED_WHEN_GENERATION_FORBIDDEN = "PLAN_RETURNED_WHEN_GENERATION_FORBIDDEN"
    EXERCISE_POOL_MEMBERSHIP_VIOLATED = "EXERCISE_POOL_MEMBERSHIP_VIOLATED"
    MANDATORY_EXERCISE_MISSING = "MANDATORY_EXERCISE_MISSING"
    DURATION_CONSTRAINT_VIOLATED = "DURATION_CONSTRAINT_VIOLATED"
    RECOVERY_CEILING_EXCEEDED = "RECOVERY_CEILING_EXCEEDED"
    PARTIAL_PROPOSALS_COORDINATED = "PARTIAL_PROPOSALS_COORDINATED"
    REVIEW_LIMIT_EXCEEDED = "REVIEW_LIMIT_EXCEEDED"
    REPAIR_LIMIT_EXCEEDED = "REPAIR_LIMIT_EXCEEDED"
    FALLBACK_SAFETY_WEAKENED = "FALLBACK_SAFETY_WEAKENED"


_SAFETY_VIOLATION_ORDER = tuple(V3ShadowSafetyViolationCode)
_ROLE_ORDER = tuple(V3ShadowRoleCode)
_PHASE_ORDER = tuple(V3ShadowInvocationPhaseCode)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class V3ShadowPlanProjection(_FrozenContract):
    """Identifier-free plan content suitable for synthetic expert review."""

    schema_version: Literal["v3-shadow-plan-projection-v1"] = SHADOW_PLAN_SCHEMA_VERSION
    action_code: str
    requested_duration_minutes: int = Field(gt=0)
    estimated_duration_seconds: int = Field(gt=0)
    prescriptions: tuple[ExercisePrescription, ...] = Field(min_length=1)
    plan_hash: str

    @field_validator("action_code")
    @classmethod
    def validate_action_code(cls, value: str) -> str:
        return _machine_code(value, field_name="action_code")

    @field_validator("plan_hash")
    @classmethod
    def validate_plan_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="plan_hash")

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.estimated_duration_seconds != self.requested_duration_minutes * 60:
            raise ValueError("shadow plan must preserve the requested duration")
        sequences = tuple(item.sequence for item in self.prescriptions)
        if sequences != tuple(range(1, len(self.prescriptions) + 1)):
            raise ValueError("shadow plan prescriptions must use canonical sequence")
        exercise_ids = tuple(item.exercise_id for item in self.prescriptions)
        if len(exercise_ids) != len(set(exercise_ids)):
            raise ValueError("shadow plan prescriptions must not contain duplicate exercises")
        return self


class V3ShadowCase(_FrozenContract):
    schema_version: Literal["v3-shadow-case-v1"] = SHADOW_CASE_SCHEMA_VERSION
    scenario_code: str
    fixture_version: str
    fixture_hash: str
    baseline_plan: V3ShadowPlanProjection | None = None
    case_hash: str

    @field_validator("scenario_code", "fixture_version")
    @classmethod
    def validate_codes(cls, value: str, info: ValidationInfo) -> str:
        return _machine_code(value, field_name=info.field_name or "shadow case code")

    @field_validator("fixture_hash", "case_hash")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        return _hash_value(value, field_name="shadow case hash")

    @model_validator(mode="after")
    def validate_case_hash(self) -> Self:
        expected = _canonical_hash(self.model_dump(mode="json", exclude={"case_hash"}))
        if self.case_hash != expected:
            raise ValueError("case_hash does not match the canonical shadow case")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": SHADOW_CASE_SCHEMA_VERSION, **values}
        payload["case_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


class V3ShadowExecutionRequest(_FrozenContract):
    """Synthetic case reference and server-owned version boundary."""

    schema_version: Literal["v3-shadow-request-v1"] = SHADOW_REQUEST_SCHEMA_VERSION
    case: V3ShadowCase
    graph_version: str
    policy_version: str
    catalog_version: str
    prompt_version: str
    provider_code: str
    model_version: str
    snapshot_is_fresh: bool

    @field_validator(
        "graph_version",
        "policy_version",
        "catalog_version",
        "prompt_version",
        "provider_code",
        "model_version",
    )
    @classmethod
    def validate_versions(cls, value: str, info: ValidationInfo) -> str:
        return _machine_code(value, field_name=info.field_name or "shadow version")


class V3ShadowInvocationMetric(_FrozenContract):
    schema_version: Literal["v3-shadow-invocation-metric-v1"] = SHADOW_INVOCATION_SCHEMA_VERSION
    role_code: V3ShadowRoleCode
    phase_code: V3ShadowInvocationPhaseCode
    status_code: V3ShadowInvocationStatusCode
    attempt_count: int = Field(ge=0, le=2)
    latency_ms: int = Field(ge=0)
    provider_code: str
    model_version: str
    prompt_version: str
    output_schema_version: str
    failure_code: str | None = None
    input_token_count: int | None = Field(default=None, ge=0)
    output_token_count: int | None = Field(default=None, ge=0)

    @field_validator("provider_code", "model_version", "prompt_version", "output_schema_version")
    @classmethod
    def validate_versions(cls, value: str, info: ValidationInfo) -> str:
        return _machine_code(value, field_name=info.field_name or "invocation version")

    @field_validator("failure_code")
    @classmethod
    def validate_failure_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _machine_code(value, field_name="failure_code")

    @model_validator(mode="after")
    def validate_invocation(self) -> Self:
        specialist = self.role_code is not V3ShadowRoleCode.COORDINATOR
        specialist_phase = self.phase_code in {
            V3ShadowInvocationPhaseCode.PROPOSE,
            V3ShadowInvocationPhaseCode.REVIEW,
        }
        if specialist != specialist_phase:
            raise ValueError("shadow invocation role and phase do not match")
        if self.status_code is V3ShadowInvocationStatusCode.SUCCEEDED:
            if self.attempt_count == 0 or self.failure_code is not None:
                raise ValueError("successful invocation requires attempts and no failure code")
        elif self.failure_code is None:
            raise ValueError("failed invocation requires a machine-readable failure code")
        tokens = (self.input_token_count, self.output_token_count)
        if (tokens[0] is None) != (tokens[1] is None):
            raise ValueError("input and output token counts must be present together")
        return self


class V3ShadowSafetyMetric(_FrozenContract):
    schema_version: Literal["v3-shadow-safety-metric-v1"] = SHADOW_SAFETY_SCHEMA_VERSION
    invariant_passed: bool
    violation_codes: tuple[V3ShadowSafetyViolationCode, ...] = ()

    @field_validator("violation_codes")
    @classmethod
    def validate_violation_codes(
        cls, values: tuple[V3ShadowSafetyViolationCode, ...]
    ) -> tuple[V3ShadowSafetyViolationCode, ...]:
        if values != tuple(sorted(set(values), key=_SAFETY_VIOLATION_ORDER.index)):
            raise ValueError("safety violation codes must be unique and canonical")
        return values

    @model_validator(mode="after")
    def validate_invariant(self) -> Self:
        if self.invariant_passed != (not self.violation_codes):
            raise ValueError("safety invariant status does not match its violation codes")
        return self


class V3ShadowUsageMetric(_FrozenContract):
    schema_version: Literal["v3-shadow-usage-metric-v1"] = SHADOW_USAGE_SCHEMA_VERSION
    status_code: V3ShadowUsageStatusCode
    provider_call_count: int = Field(ge=0)
    input_token_count: int | None = Field(default=None, ge=0)
    output_token_count: int | None = Field(default=None, ge=0)
    decision_cost: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency_code: str | None = None
    pricing_reference_version: str | None = None

    @field_validator("currency_code", "pricing_reference_version")
    @classmethod
    def validate_optional_codes(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _machine_code(value, field_name=info.field_name or "usage reference")

    @model_validator(mode="after")
    def validate_usage(self) -> Self:
        tokens = (self.input_token_count, self.output_token_count)
        cost_refs = (self.decision_cost, self.currency_code, self.pricing_reference_version)
        if self.status_code is V3ShadowUsageStatusCode.NOT_APPLICABLE:
            if self.provider_call_count != 0 or any(
                value is not None for value in (*tokens, *cost_refs)
            ):
                raise ValueError(
                    "non-applicable provider usage cannot contain calls, tokens, or cost"
                )
        elif self.status_code is V3ShadowUsageStatusCode.UNAVAILABLE:
            if self.provider_call_count == 0 or any(
                value is not None for value in (*tokens, *cost_refs)
            ):
                raise ValueError("unavailable usage requires calls without token or cost metadata")
        else:
            if self.provider_call_count == 0 or any(value is None for value in tokens):
                raise ValueError("complete usage requires provider calls and token counts")
            if any(value is not None for value in cost_refs) and any(
                value is None for value in cost_refs
            ):
                raise ValueError("cost amount, currency, and pricing version are all-or-none")
        return self


class V3ShadowExecutionResult(_FrozenContract):
    schema_version: Literal["v3-shadow-result-v1"] = SHADOW_RESULT_SCHEMA_VERSION
    scenario_code: str
    case_hash: str
    graph_version: str
    policy_version: str
    catalog_version: str
    prompt_version: str
    provider_code: str
    model_version: str
    terminal_status_code: GraphTerminalStatusCode
    plan: V3ShadowPlanProjection | None = None
    safety: V3ShadowSafetyMetric
    structured_output_status_code: V3ShadowStructuredOutputStatusCode
    constraint_violation_codes: tuple[str, ...] = ()
    invocation_metrics: tuple[V3ShadowInvocationMetric, ...] = ()
    review_attempt_count: int = Field(ge=0, le=3)
    repair_attempt_count: int = Field(ge=0, le=1)
    fallback_used: bool
    fallback_code: str | None = None
    fallback_version: str | None = None
    failure_codes: tuple[str, ...] = ()
    total_latency_ms: int = Field(ge=0)
    usage: V3ShadowUsageMetric
    result_hash: str

    @field_validator(
        "scenario_code",
        "graph_version",
        "policy_version",
        "catalog_version",
        "prompt_version",
        "provider_code",
        "model_version",
    )
    @classmethod
    def validate_machine_references(cls, value: str, info: ValidationInfo) -> str:
        return _machine_code(value, field_name=info.field_name or "shadow result version")

    @field_validator("case_hash", "result_hash")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        return _hash_value(value, field_name="shadow result hash")

    @field_validator("constraint_violation_codes", "failure_codes")
    @classmethod
    def validate_result_codes(
        cls, values: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_machine_codes(values, field_name=info.field_name or "shadow result codes")

    @field_validator("fallback_code", "fallback_version")
    @classmethod
    def validate_optional_fallback_code(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _machine_code(value, field_name=info.field_name or "fallback reference")

    @model_validator(mode="after")
    def validate_result(self, info: ValidationInfo) -> Self:
        if (self.terminal_status_code is GraphTerminalStatusCode.COMPLETED) != (
            self.plan is not None
        ):
            raise ValueError("only a completed shadow result may contain a plan")
        if self.fallback_used != (
            self.fallback_code is not None and self.fallback_version is not None
        ):
            raise ValueError("fallback use requires code and version")
        ordered_metrics = tuple(
            sorted(
                self.invocation_metrics,
                key=lambda item: (
                    _ROLE_ORDER.index(item.role_code),
                    _PHASE_ORDER.index(item.phase_code),
                ),
            )
        )
        keys = tuple((item.role_code, item.phase_code) for item in self.invocation_metrics)
        if self.invocation_metrics != ordered_metrics or len(keys) != len(set(keys)):
            raise ValueError("invocation metrics must be unique and canonically ordered")
        if self.invocation_metrics and self.total_latency_ms < max(
            item.latency_ms for item in self.invocation_metrics
        ):
            raise ValueError("total latency cannot be shorter than an invocation latency")
        creating = (
            info.context is not None
            and info.context.get(_CREATE_CONTEXT_KEY) is _CREATE_CONTEXT_SENTINEL
        )
        if not creating:
            expected_hash = _canonical_hash(self.model_dump(mode="json", exclude={"result_hash"}))
            if self.result_hash != expected_hash:
                raise ValueError("result_hash does not match the canonical shadow result")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": SHADOW_RESULT_SCHEMA_VERSION, **values}
        payload["result_hash"] = "0" * 64
        normalized = cls.model_validate(
            payload,
            context={_CREATE_CONTEXT_KEY: _CREATE_CONTEXT_SENTINEL},
        )
        canonical = normalized.model_dump(mode="json", exclude={"result_hash"})
        return normalized.model_copy(update={"result_hash": _canonical_hash(canonical)})


class V3ShadowExecutionError(RuntimeError):
    def __init__(self, code: V3ShadowFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


class V3ShadowRunnerPort(Protocol):
    """Runs one synthetic case without exposing it through a public API."""

    async def execute(
        self,
        request: V3ShadowExecutionRequest,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        regeneration_context: RegenerationContext | None = None,
    ) -> V3ShadowExecutionResult: ...


__all__ = [
    "V3ShadowCase",
    "V3ShadowExecutionError",
    "V3ShadowExecutionRequest",
    "V3ShadowExecutionResult",
    "V3ShadowFailureCode",
    "V3ShadowInvocationMetric",
    "V3ShadowInvocationPhaseCode",
    "V3ShadowInvocationStatusCode",
    "V3ShadowPlanProjection",
    "V3ShadowRoleCode",
    "V3ShadowRunnerPort",
    "V3ShadowSafetyMetric",
    "V3ShadowSafetyViolationCode",
    "V3ShadowStructuredOutputStatusCode",
    "V3ShadowUsageMetric",
    "V3ShadowUsageStatusCode",
]
