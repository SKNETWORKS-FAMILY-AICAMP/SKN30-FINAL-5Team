"""Pure metrics and review artifacts for offline V3 shadow evaluation."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import to_jsonable_python

from backend.app.domain.agents.v3_contracts import ExercisePrescription
from backend.app.modules.decisions.v3_shadow import (
    V3ShadowExecutionResult,
    V3ShadowInvocationMetric,
    V3ShadowInvocationStatusCode,
    V3ShadowPlanProjection,
    V3ShadowRoleCode,
    V3ShadowSafetyMetric,
    V3ShadowSafetyViolationCode,
    V3ShadowUsageMetric,
    V3ShadowUsageStatusCode,
)

EVALUATION_SUMMARY_SCHEMA_VERSION: Final[Literal["v3-evaluation-summary-v1"]] = (
    "v3-evaluation-summary-v1"
)
EXPERT_REVIEW_SCHEMA_VERSION: Final[Literal["v3-expert-review-v1"]] = "v3-expert-review-v1"
PRICING_SCHEMA_VERSION: Final[Literal["v3-approved-pricing-v1"]] = "v3-approved-pricing-v1"
_RATE_QUANTUM = Decimal("0.000001")
_COST_QUANTUM = Decimal("0.000000000001")
_ROLE_ORDER = tuple(V3ShadowRoleCode)


def _canonical_json(value: object) -> str:
    return json.dumps(
        to_jsonable_python(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(_RATE_QUANTUM)


def _percentile(values: tuple[int, ...], percentile: Decimal) -> int | None:
    """Return the deterministic nearest-rank percentile."""

    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(float(percentile * len(ordered))))
    return ordered[rank - 1]


class V3EvaluationStatusCode(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class V3ExpertReviewStatusCode(StrEnum):
    NOT_REVIEWED = "NOT_REVIEWED"
    REVIEWED = "REVIEWED"


class V3ReviewerDecisionCode(StrEnum):
    PENDING = "PENDING"
    V1_PREFERRED = "V1_PREFERRED"
    V3_PREFERRED = "V3_PREFERRED"
    EQUIVALENT = "EQUIVALENT"
    REJECT_BOTH = "REJECT_BOTH"


class V3PricingMismatchError(ValueError):
    pass


class V3EvaluationPrivacyError(ValueError):
    pass


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class V3LatencyDistribution(_FrozenModel):
    sample_count: int = Field(ge=0)
    p50_ms: int | None = Field(default=None, ge=0)
    p95_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.sample_count == 0 and (self.p50_ms is not None or self.p95_ms is not None):
            raise ValueError("empty latency samples must remain unavailable")
        if self.sample_count > 0 and (self.p50_ms is None or self.p95_ms is None):
            raise ValueError("non-empty latency samples require p50 and p95")
        return self


class V3RoleLatencyDistribution(V3LatencyDistribution):
    role_code: V3ShadowRoleCode


class V3ViolationCount(_FrozenModel):
    violation_code: str
    count: int = Field(gt=0)


class V3EvaluationSummary(_FrozenModel):
    schema_version: Literal["v3-evaluation-summary-v1"] = EVALUATION_SUMMARY_SCHEMA_VERSION
    evaluation_status_code: V3EvaluationStatusCode
    total_case_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    terminal_count: int = Field(ge=0)
    safety_invariant_pass_rate: Decimal | None = Field(default=None, ge=0, le=1)
    safety_veto_override_count: int = Field(ge=0)
    constraint_violation_rate: Decimal | None = Field(default=None, ge=0, le=1)
    pool_membership_violation_rate: Decimal | None = Field(default=None, ge=0, le=1)
    structured_output_success_rate: Decimal | None = Field(default=None, ge=0, le=1)
    agent_failure_rate: Decimal | None = Field(default=None, ge=0, le=1)
    coordinator_failure_rate: Decimal | None = Field(default=None, ge=0, le=1)
    review_routing_rate: Decimal | None = Field(default=None, ge=0, le=1)
    repair_rate: Decimal | None = Field(default=None, ge=0, le=1)
    repair_success_rate: Decimal | None = Field(default=None, ge=0, le=1)
    deterministic_fallback_rate: Decimal | None = Field(default=None, ge=0, le=1)
    no_plan_terminal_rate: Decimal | None = Field(default=None, ge=0, le=1)
    total_latency: V3LatencyDistribution
    role_latencies: tuple[V3RoleLatencyDistribution, ...]
    provider_timeout_rate: Decimal | None = Field(default=None, ge=0, le=1)
    input_token_count_total: int | None = Field(default=None, ge=0)
    output_token_count_total: int | None = Field(default=None, ge=0)
    average_token_count_per_decision: Decimal | None = Field(default=None, ge=0)
    total_cost: Decimal | None = Field(default=None, ge=0)
    average_cost_per_decision: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = None
    expert_review_status_code: V3ExpertReviewStatusCode
    expert_review_agreement_rate: Decimal | None = Field(default=None, ge=0, le=1)
    hard_gate_violation_counts: tuple[V3ViolationCount, ...]
    report_only_thresholds_applied: Literal[False] = False
    summary_hash: str

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        if self.terminal_count != self.total_case_count:
            raise ValueError("every shadow result must be terminal")
        if self.completed_count > self.total_case_count:
            raise ValueError("completed_count cannot exceed total_case_count")
        expected_status = (
            V3EvaluationStatusCode.NOT_AVAILABLE
            if self.total_case_count == 0
            else (
                V3EvaluationStatusCode.FAILED
                if self.hard_gate_violation_counts
                else V3EvaluationStatusCode.PASSED
            )
        )
        if self.evaluation_status_code is not expected_status:
            raise ValueError("evaluation status does not match hard safety gates")
        if tuple(item.role_code for item in self.role_latencies) != _ROLE_ORDER:
            raise ValueError("role latency metrics must use canonical role order")
        codes = tuple(item.violation_code for item in self.hard_gate_violation_counts)
        if codes != tuple(sorted(set(codes))):
            raise ValueError("hard gate violation counts must use canonical order")
        cost_values = (self.total_cost, self.average_cost_per_decision, self.currency_code)
        if any(value is None for value in cost_values) and any(
            value is not None for value in cost_values
        ):
            raise ValueError("cost totals, average, and currency are all-or-none")
        expected_hash = _canonical_hash(self.model_dump(mode="json", exclude={"summary_hash"}))
        if self.summary_hash != expected_hash:
            raise ValueError("summary_hash does not match canonical metrics")
        return self


class V3ApprovedPricingReference(_FrozenModel):
    pricing_schema_version: Literal["v3-approved-pricing-v1"] = PRICING_SCHEMA_VERSION
    provider_code: str
    model_code: str
    currency_code: str
    input_token_unit: int = Field(gt=0)
    output_token_unit: int = Field(gt=0)
    input_unit_price: Decimal = Field(ge=0, allow_inf_nan=False)
    output_unit_price: Decimal = Field(ge=0, allow_inf_nan=False)
    effective_at: datetime
    source_reference: str

    @field_validator("effective_at")
    @classmethod
    def validate_effective_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("pricing effective_at must include timezone information")
        return value


class V3PlanComparison(_FrozenModel):
    case_code: str
    v1_plan: V3ShadowPlanProjection | None
    v3_plan: V3ShadowPlanProjection | None
    final_action_equal: bool
    plan_presence_equal: bool
    requested_duration_preserved: bool
    exercise_set_equal: bool
    exercise_order_equal: bool
    terminal_status_code: str
    fallback_used: bool
    public_reason_codes: tuple[str, ...]
    difference_codes: tuple[str, ...]
    hard_constraint_failed: bool


class V3ExpertReviewArtifact(_FrozenModel):
    schema_version: Literal["v3-expert-review-v1"] = EXPERT_REVIEW_SCHEMA_VERSION
    case_code: str
    v1_plan: V3ShadowPlanProjection | None
    v3_plan: V3ShadowPlanProjection | None
    safety_invariant_passed: bool
    safety_violation_codes: tuple[V3ShadowSafetyViolationCode, ...]
    constraint_violation_codes: tuple[str, ...]
    difference_codes: tuple[str, ...]
    reviewer_decision: V3ReviewerDecisionCode = V3ReviewerDecisionCode.PENDING
    reviewer_reason_codes: tuple[str, ...] = ()
    reviewer_role_code: str | None = None
    reviewed_at: datetime | None = None
    review_policy_version: str

    @model_validator(mode="after")
    def validate_review_state(self) -> Self:
        pending = self.reviewer_decision is V3ReviewerDecisionCode.PENDING
        review_values = (self.reviewer_role_code, self.reviewed_at)
        if pending and (
            self.reviewer_reason_codes or any(value is not None for value in review_values)
        ):
            raise ValueError("pending expert review cannot claim reviewer evidence")
        if not pending and (
            not self.reviewer_reason_codes or any(value is None for value in review_values)
        ):
            raise ValueError("completed expert review requires role, time, and reason codes")
        return self


def calculate_decision_cost(
    result: V3ShadowExecutionResult,
    pricing: V3ApprovedPricingReference,
) -> Decimal | None:
    usage = result.usage
    if usage.status_code is not V3ShadowUsageStatusCode.COMPLETE:
        return None
    if result.provider_code != pricing.provider_code or result.model_version != pricing.model_code:
        raise V3PricingMismatchError("pricing provider/model does not match the shadow result")
    if usage.input_token_count is None or usage.output_token_count is None:
        return None
    cost = (
        Decimal(usage.input_token_count) / pricing.input_token_unit * pricing.input_unit_price
        + Decimal(usage.output_token_count) / pricing.output_token_unit * pricing.output_unit_price
    )
    return cost.quantize(_COST_QUANTUM)


def _latency(values: tuple[int, ...]) -> V3LatencyDistribution:
    return V3LatencyDistribution(
        sample_count=len(values),
        p50_ms=_percentile(values, Decimal("0.50")),
        p95_ms=_percentile(values, Decimal("0.95")),
    )


def _usage_totals(
    results: tuple[V3ShadowExecutionResult, ...],
) -> tuple[int | None, int | None, Decimal | None, Decimal | None, Decimal | None, str | None]:
    if not results:
        return None, None, None, None, None, None
    if any(item.usage.status_code is V3ShadowUsageStatusCode.UNAVAILABLE for item in results):
        return None, None, None, None, None, None
    complete = tuple(
        item.usage for item in results if item.usage.status_code is V3ShadowUsageStatusCode.COMPLETE
    )
    input_total = sum(item.input_token_count or 0 for item in complete)
    output_total = sum(item.output_token_count or 0 for item in complete)
    average_tokens = (Decimal(input_total + output_total) / len(results)).quantize(_RATE_QUANTUM)
    if not complete:
        return input_total, output_total, average_tokens, None, None, None
    if any(item.decision_cost is None for item in complete):
        return input_total, output_total, average_tokens, None, None, None
    currencies = {item.currency_code for item in complete}
    if len(currencies) > 1:
        return input_total, output_total, average_tokens, None, None, None
    total_cost = sum((item.decision_cost or Decimal(0) for item in complete), Decimal(0))
    average_cost = (total_cost / len(results)).quantize(_COST_QUANTUM)
    currency = next(iter(currencies), None)
    return input_total, output_total, average_tokens, total_cost, average_cost, currency


def evaluate_shadow_results(
    values: tuple[V3ShadowExecutionResult, ...],
) -> V3EvaluationSummary:
    """Evaluate only immutable shadow results; no provider or repository is called."""

    results = tuple(sorted(values, key=lambda item: (item.scenario_code, item.result_hash)))
    total = len(results)
    invocations = tuple(metric for item in results for metric in item.invocation_metrics)
    agent_invocations = tuple(
        item for item in invocations if item.role_code is not V3ShadowRoleCode.COORDINATOR
    )
    coordinator_invocations = tuple(
        item for item in invocations if item.role_code is V3ShadowRoleCode.COORDINATOR
    )
    repaired = tuple(item for item in results if item.repair_attempt_count > 0)
    hard_counts: dict[str, int] = {}
    for result in results:
        for code in result.safety.violation_codes:
            hard_counts[code.value] = hard_counts.get(code.value, 0) + 1
        for constraint_code in result.constraint_violation_codes:
            key = f"CONSTRAINT/{constraint_code}"
            hard_counts[key] = hard_counts.get(key, 0) + 1
    violation_counts = tuple(
        V3ViolationCount(violation_code=code, count=count)
        for code, count in sorted(hard_counts.items())
    )
    input_total, output_total, average_tokens, total_cost, average_cost, currency = _usage_totals(
        results
    )
    summary_values: dict[str, object] = {
        "evaluation_status_code": (
            V3EvaluationStatusCode.NOT_AVAILABLE
            if total == 0
            else (
                V3EvaluationStatusCode.FAILED if violation_counts else V3EvaluationStatusCode.PASSED
            )
        ),
        "total_case_count": total,
        "completed_count": sum(item.plan is not None for item in results),
        "terminal_count": total,
        "safety_invariant_pass_rate": _rate(
            sum(item.safety.invariant_passed for item in results), total
        ),
        "safety_veto_override_count": sum(
            V3ShadowSafetyViolationCode.SAFETY_VETO_OVERRIDDEN in item.safety.violation_codes
            for item in results
        ),
        "constraint_violation_rate": _rate(
            sum(bool(item.constraint_violation_codes) for item in results), total
        ),
        "pool_membership_violation_rate": _rate(
            sum(
                V3ShadowSafetyViolationCode.EXERCISE_POOL_MEMBERSHIP_VIOLATED
                in item.safety.violation_codes
                for item in results
            ),
            total,
        ),
        "structured_output_success_rate": _rate(
            sum(item.structured_output_status_code.value == "SUCCEEDED" for item in results),
            total,
        ),
        "agent_failure_rate": _rate(
            sum(
                item.status_code is not V3ShadowInvocationStatusCode.SUCCEEDED
                for item in agent_invocations
            ),
            len(agent_invocations),
        ),
        "coordinator_failure_rate": _rate(
            sum(
                item.status_code is not V3ShadowInvocationStatusCode.SUCCEEDED
                for item in coordinator_invocations
            ),
            len(coordinator_invocations),
        ),
        "review_routing_rate": _rate(sum(item.review_attempt_count > 0 for item in results), total),
        "repair_rate": _rate(len(repaired), total),
        "repair_success_rate": _rate(
            sum(item.plan is not None and not item.constraint_violation_codes for item in repaired),
            len(repaired),
        ),
        "deterministic_fallback_rate": _rate(sum(item.fallback_used for item in results), total),
        "no_plan_terminal_rate": _rate(sum(item.plan is None for item in results), total),
        "total_latency": _latency(tuple(item.total_latency_ms for item in results)),
        "role_latencies": tuple(
            V3RoleLatencyDistribution(
                role_code=role,
                **_latency(
                    tuple(item.latency_ms for item in invocations if item.role_code is role)
                ).model_dump(),
            )
            for role in _ROLE_ORDER
        ),
        "provider_timeout_rate": _rate(
            sum(item.status_code is V3ShadowInvocationStatusCode.TIMEOUT for item in invocations),
            len(invocations),
        ),
        "input_token_count_total": input_total,
        "output_token_count_total": output_total,
        "average_token_count_per_decision": average_tokens,
        "total_cost": total_cost,
        "average_cost_per_decision": average_cost,
        "currency_code": currency,
        "expert_review_status_code": V3ExpertReviewStatusCode.NOT_REVIEWED,
        "expert_review_agreement_rate": None,
        "hard_gate_violation_counts": violation_counts,
        "report_only_thresholds_applied": False,
    }
    payload = {"schema_version": EVALUATION_SUMMARY_SCHEMA_VERSION, **summary_values}
    payload["summary_hash"] = _canonical_hash(payload)
    return V3EvaluationSummary.model_validate(payload)


def compare_shadow_result(
    baseline: V3ShadowPlanProjection | None,
    result: V3ShadowExecutionResult,
) -> V3PlanComparison:
    v1_ids = tuple(item.exercise_id for item in baseline.prescriptions) if baseline else ()
    v3_ids = tuple(item.exercise_id for item in result.plan.prescriptions) if result.plan else ()
    differences: list[str] = []
    if (baseline is None) != (result.plan is None):
        differences.append("PLAN_PRESENCE_CHANGED")
    if baseline and result.plan and baseline.action_code != result.plan.action_code:
        differences.append("FINAL_ACTION_CHANGED")
    if set(v1_ids) != set(v3_ids):
        differences.append("EXERCISE_SET_CHANGED")
    elif v1_ids != v3_ids:
        differences.append("EXERCISE_ORDER_CHANGED")
    return V3PlanComparison(
        case_code=result.scenario_code,
        v1_plan=baseline,
        v3_plan=result.plan,
        final_action_equal=bool(
            baseline and result.plan and baseline.action_code == result.plan.action_code
        )
        or baseline is result.plan,
        plan_presence_equal=(baseline is None) == (result.plan is None),
        requested_duration_preserved=(
            result.plan is None
            or result.plan.estimated_duration_seconds == result.plan.requested_duration_minutes * 60
        ),
        exercise_set_equal=set(v1_ids) == set(v3_ids),
        exercise_order_equal=v1_ids == v3_ids,
        terminal_status_code=result.terminal_status_code.value,
        fallback_used=result.fallback_used,
        public_reason_codes=result.failure_codes,
        difference_codes=tuple(sorted(differences)),
        hard_constraint_failed=(
            not result.safety.invariant_passed or bool(result.constraint_violation_codes)
        ),
    )


def build_expert_review_artifact(
    comparison: V3PlanComparison,
    result: V3ShadowExecutionResult,
    *,
    review_policy_version: str,
) -> V3ExpertReviewArtifact:
    return V3ExpertReviewArtifact(
        case_code=result.scenario_code,
        v1_plan=comparison.v1_plan,
        v3_plan=comparison.v3_plan,
        safety_invariant_passed=result.safety.invariant_passed,
        safety_violation_codes=result.safety.violation_codes,
        constraint_violation_codes=result.constraint_violation_codes,
        difference_codes=comparison.difference_codes,
        review_policy_version=review_policy_version,
    )


def summarize_expert_reviews(
    artifacts: tuple[V3ExpertReviewArtifact, ...],
) -> tuple[V3ExpertReviewStatusCode, Decimal | None]:
    """Return agreement with V3 among completed expert reviews only."""

    reviewed = tuple(
        artifact
        for artifact in artifacts
        if artifact.reviewer_decision is not V3ReviewerDecisionCode.PENDING
    )
    if not reviewed:
        return V3ExpertReviewStatusCode.NOT_REVIEWED, None
    agreed = sum(
        artifact.reviewer_decision
        in (V3ReviewerDecisionCode.V3_PREFERRED, V3ReviewerDecisionCode.EQUIVALENT)
        for artifact in reviewed
    )
    return V3ExpertReviewStatusCode.REVIEWED, _rate(agreed, len(reviewed))


_ALLOWED_REPORT_KEYS = frozenset(
    {
        "generated_at",
        "harness_version",
        "fixture_version",
        "fixture_hash",
        "repeat_count",
        "provider_calls_allowed",
        "files",
        "file_name",
        "sha256",
        "record_count",
    }
    | set(V3EvaluationSummary.model_fields)
    | set(V3LatencyDistribution.model_fields)
    | set(V3RoleLatencyDistribution.model_fields)
    | set(V3ViolationCount.model_fields)
    | set(V3PlanComparison.model_fields)
    | set(V3ExpertReviewArtifact.model_fields)
    | set(V3ShadowExecutionResult.model_fields)
    | set(V3ShadowPlanProjection.model_fields)
    | set(V3ShadowSafetyMetric.model_fields)
    | set(V3ShadowUsageMetric.model_fields)
    | set(V3ShadowInvocationMetric.model_fields)
    | set(ExercisePrescription.model_fields)
)


def validate_report_privacy(value: object) -> None:
    """Reject every report key that is not present in the committed schema allowlist."""

    if isinstance(value, BaseModel):
        validate_report_privacy(value.model_dump(mode="json"))
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            if key not in _ALLOWED_REPORT_KEYS:
                raise V3EvaluationPrivacyError("report contains a non-allowlisted key")
            validate_report_privacy(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            validate_report_privacy(nested)


def summary_markdown(summary: V3EvaluationSummary) -> str:
    def shown(value: object) -> str:
        return "NOT_AVAILABLE" if value is None else str(value)

    lines = [
        "# V3 synthetic shadow evaluation",
        "",
        f"- Status: {summary.evaluation_status_code.value}",
        f"- Cases: {summary.total_case_count}",
        f"- Safety invariant pass rate: {shown(summary.safety_invariant_pass_rate)}",
        f"- Constraint violation rate: {shown(summary.constraint_violation_rate)}",
        f"- Structured output success rate: {shown(summary.structured_output_success_rate)}",
        f"- Deterministic fallback rate: {shown(summary.deterministic_fallback_rate)}",
        f"- Total latency p50/p95 ms: {shown(summary.total_latency.p50_ms)} / "
        f"{shown(summary.total_latency.p95_ms)}",
        f"- Average cost per decision: {shown(summary.average_cost_per_decision)}",
        f"- Expert review: {summary.expert_review_status_code.value}",
        "",
        "Latency, cost, fallback, structured-output, and expert-review thresholds are report-only; "
        "no production promotion threshold was applied.",
    ]
    return "\n".join(lines) + "\n"


__all__ = [
    "EVALUATION_SUMMARY_SCHEMA_VERSION",
    "EXPERT_REVIEW_SCHEMA_VERSION",
    "PRICING_SCHEMA_VERSION",
    "V3ApprovedPricingReference",
    "V3EvaluationPrivacyError",
    "V3EvaluationStatusCode",
    "V3EvaluationSummary",
    "V3ExpertReviewArtifact",
    "V3ExpertReviewStatusCode",
    "V3LatencyDistribution",
    "V3PlanComparison",
    "V3PricingMismatchError",
    "V3ReviewerDecisionCode",
    "V3RoleLatencyDistribution",
    "V3ViolationCount",
    "build_expert_review_artifact",
    "calculate_decision_cost",
    "compare_shadow_result",
    "evaluate_shadow_results",
    "summary_markdown",
    "summarize_expert_reviews",
    "validate_report_privacy",
]
