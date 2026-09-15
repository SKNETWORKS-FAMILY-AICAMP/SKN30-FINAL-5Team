"""Architecture-neutral diagnostics for the pre-registered Round 3 comparison.

Round 2 keeps its published metric names and values.  This module adds views
that answer questions those metrics could not answer fairly: whether the user
received a model or fallback plan, which graph stage failed, how much time each
provider role consumed, and how uncertain a proportion is at small sample sizes.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from backend.app.integrations.langgraph.state import InvocationAudit
from backend.tests.evaluation.outcomes import OutcomeClass, classify

_Z_95: Final = 1.959963984540054


class DeliveryOutcome(StrEnum):
    """What the service ultimately delivered, independent of authorship."""

    MODEL_PLAN = "MODEL_PLAN"
    FALLBACK_PLAN = "FALLBACK_PLAN"
    NO_PLAN = "NO_PLAN"


class FailureStage(StrEnum):
    """Stable graph stages that do not expose prompt or health contents."""

    ENTRY = "ENTRY"
    TRAINING = "TRAINING"
    RECOVERY = "RECOVERY"
    FEASIBILITY = "FEASIBILITY"
    COORDINATOR_INITIAL = "COORDINATOR_INITIAL"
    COMPILER = "COMPILER"
    INTEGRITY_VALIDATOR = "INTEGRITY_VALIDATOR"
    COORDINATOR_REPAIR = "COORDINATOR_REPAIR"
    FALLBACK = "FALLBACK"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    lower: float
    upper: float

    def to_json(self) -> dict[str, float]:
        return {"lower": self.lower, "upper": self.upper}


def wilson_interval(successes: int, total: int) -> ConfidenceInterval | None:
    """Return a Wilson 95% interval without adding a statistics dependency."""

    if successes < 0 or total < 0 or successes > total:
        raise ValueError("successes and total must satisfy 0 <= successes <= total")
    if total == 0:
        return None
    proportion = successes / total
    z_squared = _Z_95**2
    denominator = 1 + z_squared / total
    centre = (proportion + z_squared / (2 * total)) / denominator
    margin = (
        _Z_95
        * math.sqrt(
            proportion * (1 - proportion) / total + z_squared / (4 * total**2)
        )
        / denominator
    )
    return ConfidenceInterval(round(centre - margin, 4), round(centre + margin, 4))


def delivery_outcome(*, has_plan: bool, used_fallback: bool) -> DeliveryOutcome:
    if has_plan and used_fallback:
        return DeliveryOutcome.FALLBACK_PLAN
    if has_plan:
        return DeliveryOutcome.MODEL_PLAN
    return DeliveryOutcome.NO_PLAN


def _audit_stage(audit: InvocationAudit) -> FailureStage:
    if audit.role_code == "TRAINING":
        return FailureStage.TRAINING
    if audit.role_code == "RECOVERY":
        return FailureStage.RECOVERY
    if audit.role_code == "FEASIBILITY":
        return FailureStage.FEASIBILITY
    if audit.role_code == "COORDINATOR" and audit.phase_code == "REPAIR":
        return FailureStage.COORDINATOR_REPAIR
    if audit.role_code == "COORDINATOR":
        return FailureStage.COORDINATOR_INITIAL
    return FailureStage.UNKNOWN


def _code_stage(code: str) -> FailureStage:
    if code.startswith(("REST", "STOP_AND_SEEK_HELP", "PLAN_GENERATION_FORBIDDEN", "V3_INPUT_")):
        return FailureStage.ENTRY
    for role, stage in (
        ("TRAINING", FailureStage.TRAINING),
        ("RECOVERY", FailureStage.RECOVERY),
        ("FEASIBILITY", FailureStage.FEASIBILITY),
    ):
        if code.startswith(f"V3_{role}_"):
            return stage
    if code.startswith("V3_COORDINATOR_REPAIR_"):
        return FailureStage.COORDINATOR_REPAIR
    if code.startswith("V3_COORDINATOR_"):
        return FailureStage.COORDINATOR_INITIAL
    if code in {
        "V3_COMPILATION_FAILED",
        "V3_COMPILED_PLAN_MISSING",
        "V3_PLAN_SPEC_MISSING",
    }:
        return FailureStage.COMPILER
    if code.startswith("V3_INTEGRITY_") or code == "V3_VALIDATION_FAILED":
        return FailureStage.INTEGRITY_VALIDATOR
    if code.startswith("V3_FALLBACK_"):
        return FailureStage.FALLBACK
    return FailureStage.UNKNOWN


def failure_stages(
    *,
    failure_codes: Iterable[str],
    violation_codes: Iterable[str],
    invocation_audits: Iterable[InvocationAudit],
) -> tuple[FailureStage, ...]:
    """Return canonical unique stages, using audits to locate generic LLM errors."""

    stages: set[FailureStage] = set()
    audited_generic_codes: set[str] = set()
    for audit in invocation_audits:
        if audit.failure_code is None:
            continue
        stages.add(_audit_stage(audit))
        audited_generic_codes.add(audit.failure_code)

    for code in failure_codes:
        # Generic adapter errors such as LLM_AGENT_DOMAIN_INVALID carry no role
        # in their string.  When an audit exists, it is the authoritative stage.
        if code in audited_generic_codes:
            continue
        stages.add(_code_stage(code))
    if tuple(violation_codes):
        stages.add(FailureStage.INTEGRITY_VALIDATOR)
    if len(stages) > 1:
        stages.discard(FailureStage.UNKNOWN)
    return tuple(stage for stage in FailureStage if stage in stages)


@dataclass(frozen=True, slots=True)
class NormalizedRunOutcome:
    delivery: DeliveryOutcome
    model_outcome: OutcomeClass
    failure_stages: tuple[FailureStage, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "delivery": self.delivery.value,
            "model_outcome": self.model_outcome.value,
            "failure_stages": [stage.value for stage in self.failure_stages],
        }


class _RunLike(Protocol):
    has_plan: bool
    used_fallback: bool
    failure_codes: tuple[str, ...]
    violation_codes: tuple[str, ...]


def normalize_run(run: _RunLike, audits: Iterable[InvocationAudit]) -> NormalizedRunOutcome:
    return NormalizedRunOutcome(
        delivery=delivery_outcome(has_plan=run.has_plan, used_fallback=run.used_fallback),
        model_outcome=classify(
            has_plan=run.has_plan,
            used_fallback=run.used_fallback,
            failure_codes=run.failure_codes,
            violation_codes=run.violation_codes,
        ),
        failure_stages=failure_stages(
            failure_codes=run.failure_codes,
            violation_codes=run.violation_codes,
            invocation_audits=audits,
        ),
    )


def summarize_outcomes(
    runs: Sequence[_RunLike], audits: Sequence[Sequence[InvocationAudit]]
) -> dict[str, object]:
    if len(runs) != len(audits):
        raise ValueError("runs and audits must have the same length")
    normalized = [normalize_run(run, item) for run, item in zip(runs, audits, strict=True)]
    delivery = Counter(item.delivery.value for item in normalized)
    models = Counter(item.model_outcome.value for item in normalized)
    stages = Counter(stage.value for item in normalized for stage in item.failure_stages)
    model_plans = delivery[DeliveryOutcome.MODEL_PLAN.value]
    delivered = model_plans + delivery[DeliveryOutcome.FALLBACK_PLAN.value]
    return {
        "run_count": len(runs),
        "delivery_counts": {item.value: delivery[item.value] for item in DeliveryOutcome},
        "model_outcome_counts": {item.value: models[item.value] for item in OutcomeClass},
        "failure_stage_counts": {item.value: stages[item.value] for item in FailureStage},
        "model_plan_rate_ci95": _interval_json(wilson_interval(model_plans, len(runs))),
        "plan_delivery_rate_ci95": _interval_json(wilson_interval(delivered, len(runs))),
    }


def _interval_json(interval: ConfidenceInterval | None) -> dict[str, float] | None:
    return None if interval is None else interval.to_json()


def summarize_invocations(audits: Iterable[InvocationAudit]) -> dict[str, dict[str, object]]:
    """Aggregate provider latency and tokens by role and phase."""

    buckets: dict[str, list[InvocationAudit]] = {}
    for audit in audits:
        buckets.setdefault(f"{audit.role_code}:{audit.phase_code}", []).append(audit)
    result: dict[str, dict[str, object]] = {}
    for key, rows in sorted(buckets.items()):
        latencies = [row.latency_ms for row in rows]
        result[key] = {
            "calls": len(rows),
            "failed_calls": sum(1 for row in rows if row.failure_code is not None),
            "p50_latency_ms": _nearest_rank(latencies, 0.50),
            "p95_latency_ms": _nearest_rank(latencies, 0.95),
            "input_tokens": sum(row.input_token_count or 0 for row in rows),
            "output_tokens": sum(row.output_token_count or 0 for row in rows),
        }
    return result


def _nearest_rank(values: Sequence[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True, slots=True)
class PairedPlanComparison:
    pairs: int
    left_wins: int
    right_wins: int
    ties: int

    def to_json(self) -> dict[str, object]:
        decisive = self.left_wins + self.right_wins
        interval = wilson_interval(self.left_wins, decisive)
        return {
            "pairs": self.pairs,
            "left_wins": self.left_wins,
            "right_wins": self.right_wins,
            "ties": self.ties,
            "left_win_rate_among_decisive": (
                None if decisive == 0 else round(self.left_wins / decisive, 4)
            ),
            "left_win_rate_ci95": _interval_json(interval),
        }


class _PairedRunLike(Protocol):
    case: object
    has_plan: bool
    used_fallback: bool


def paired_model_plan_comparison(
    left: Sequence[_PairedRunLike], right: Sequence[_PairedRunLike]
) -> PairedPlanComparison:
    """Pair repeated runs by their recorded order and reject misaligned inputs."""

    if len(left) != len(right):
        raise ValueError("paired architecture runs must have the same length")
    left_wins = right_wins = ties = 0
    for left_run, right_run in zip(left, right, strict=True):
        left_id = getattr(left_run.case, "case_id", None)
        right_id = getattr(right_run.case, "case_id", None)
        if left_id != right_id:
            raise ValueError("paired architecture runs must have identical case order")
        left_plan = left_run.has_plan and not left_run.used_fallback
        right_plan = right_run.has_plan and not right_run.used_fallback
        if left_plan and not right_plan:
            left_wins += 1
        elif right_plan and not left_plan:
            right_wins += 1
        else:
            ties += 1
    return PairedPlanComparison(len(left), left_wins, right_wins, ties)


__all__ = [
    "ConfidenceInterval",
    "DeliveryOutcome",
    "FailureStage",
    "NormalizedRunOutcome",
    "PairedPlanComparison",
    "delivery_outcome",
    "failure_stages",
    "normalize_run",
    "paired_model_plan_comparison",
    "summarize_invocations",
    "summarize_outcomes",
    "wilson_interval",
]
