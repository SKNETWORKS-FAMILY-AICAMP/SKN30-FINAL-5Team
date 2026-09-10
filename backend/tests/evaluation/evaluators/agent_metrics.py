"""PHASE 4: the seven multi-agent workflow metrics.

Every number here is read from `InvocationAudit` and `V3GraphResult`, which the
graph already produces (`langgraph/state.py`).  No LangSmith is required for any
of them -- that is worth stating plainly, because the master specification offers
LangSmith as the source and the service deliberately disables it.

One metric is deliberately *not* pass/fail.  Recovery and Feasibility answer with
advisory `adjustment_codes` that carry no deterministic enforcement (ADR-0015),
so "did the coordinator follow Recovery?" is recorded as an observation.  Scoring
it would be testing a requirement the design does not make.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_ORDER,
    SpecialistAgentTypeCode,
)
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult

SPECIALIST_ROLE_CODES: Final[tuple[str, ...]] = tuple(role.value for role in SPECIALIST_AGENT_ORDER)
COORDINATOR_ROLE_CODE: Final = "COORDINATOR"
_RATE_QUANTUM: Final = Decimal("0.0001")


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float((Decimal(numerator) / Decimal(denominator)).quantize(_RATE_QUANTUM))


@dataclass(frozen=True, slots=True)
class RunMetrics:
    """One run, reduced to the facts the seven metrics aggregate."""

    case_id: str
    category: str
    status_code: str

    invoked_roles: frozenset[str]
    expected_roles: frozenset[str]
    role_separation_held: bool
    state_context_held: bool
    plan_references_proposals: bool
    workflow_completed: bool
    structured_output_succeeded: bool
    safety_respected: bool
    coordinator_used_training_plan: bool | None
    advisory_codes_present: bool
    repair_attempts: int
    used_fallback: bool
    llm_call_count: int
    input_tokens: int
    output_tokens: int

    @property
    def invocation_accuracy(self) -> bool:
        """Exactly the roles the run should have called, and no others."""

        return self.invoked_roles == self.expected_roles


def _expected_roles(run: CaseRunResult) -> frozenset[str]:
    """Which roles a correct run of this case calls.

    A blocked safety envelope calls none: `validate_entry` terminates before the
    parallel agents, which is both a cost and a privacy property.
    """

    envelope = run.scenario.constraint_envelope
    if not envelope.plan_generation_allowed or envelope.safety_required_action_code is not None:
        return frozenset()
    roles = set(SPECIALIST_ROLE_CODES)
    # The coordinator only runs when all three specialists returned READY.
    if len(run.graph_result.round_one_proposals) == len(SPECIALIST_ROLE_CODES):
        roles.add(COORDINATOR_ROLE_CODE)
    return frozenset(roles)


def _coordinator_used_training_plan(run: CaseRunResult) -> bool | None:
    """Whether the coordinator's plan is built from Training's prescriptions.

    Returns None when there is nothing to compare -- no coordinator plan, or no
    Training proposal -- rather than scoring an absence as a failure.
    """

    plan = run.graph_result.coordinator_agent_plan
    training = next(
        (
            proposal
            for proposal in run.graph_result.round_one_proposals
            if proposal.agent_type_code is SpecialistAgentTypeCode.TRAINING
        ),
        None,
    )
    if plan is None or training is None or not training.exercise_prescriptions:
        return None
    training_ids = {item.exercise_id for item in training.exercise_prescriptions}
    plan_ids = {item.exercise_id for item in plan.exercise_prescriptions}
    return plan_ids.issubset(training_ids)


def collect_run_metrics(run: CaseRunResult) -> RunMetrics:
    envelope = run.scenario.constraint_envelope
    proposals = run.graph_result.round_one_proposals

    advisory = [
        proposal
        for proposal in proposals
        if proposal.agent_type_code is not SpecialistAgentTypeCode.TRAINING
    ]
    role_separation_held = all(not proposal.exercise_prescriptions for proposal in advisory)
    state_context_held = all(
        proposal.envelope_hash == envelope.envelope_hash
        and proposal.pool_hash == run.scenario.exercise_pool.pool_hash
        for proposal in proposals
    )

    plan_spec = run.plan_spec
    plan_references_proposals = True
    if plan_spec is not None and proposals:
        referenced = {
            reference.agent_type_code: reference.proposal_hash
            for reference in plan_spec.proposal_references
        }
        plan_references_proposals = all(
            referenced.get(proposal.agent_type_code) == proposal.proposal_hash
            for proposal in proposals
        )

    blocked = (
        not envelope.plan_generation_allowed or envelope.safety_required_action_code is not None
    )
    safety_respected = (
        not run.has_plan
        if blocked
        else not (run.scenario.excluded_exercise_ids & set(run.prescribed_exercise_ids))
    )

    # A workflow completes when it reaches a terminal status the client can act
    # on. A blocked envelope terminating as REST is a completed workflow, not a
    # failed one: it answered the user correctly.
    workflow_completed = run.status_code in {"SUCCEEDED"} or blocked

    structured_output_succeeded = not any(
        audit.status_code in {"INVALID_OUTPUT", "FAILED", "TIMEOUT"}
        for audit in run.graph_result.invocation_audits
    )

    input_tokens, output_tokens = run.token_usage
    return RunMetrics(
        case_id=run.case.case_id,
        category=run.case.category.value,
        status_code=run.status_code,
        invoked_roles=frozenset(item.role_code for item in run.invocations),
        expected_roles=_expected_roles(run),
        role_separation_held=role_separation_held,
        state_context_held=state_context_held,
        plan_references_proposals=plan_references_proposals,
        workflow_completed=workflow_completed,
        structured_output_succeeded=structured_output_succeeded,
        safety_respected=safety_respected,
        coordinator_used_training_plan=_coordinator_used_training_plan(run),
        advisory_codes_present=all(proposal.adjustment_codes for proposal in advisory)
        if advisory
        else False,
        repair_attempts=run.repair_attempts,
        used_fallback=run.used_fallback,
        llm_call_count=run.llm_call_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


@dataclass
class AgentMetricsReport:
    """The seven metrics, plus the advisory observations kept out of them."""

    architecture_code: str
    provider_label: str
    runs: list[RunMetrics] = field(default_factory=list)

    def _count(self, predicate: str) -> int:
        return sum(1 for run in self.runs if getattr(run, predicate))

    @property
    def agent_invocation_accuracy(self) -> float | None:
        return _rate(sum(1 for run in self.runs if run.invocation_accuracy), len(self.runs))

    @property
    def agent_role_consistency(self) -> float | None:
        return _rate(self._count("role_separation_held"), len(self.runs))

    @property
    def state_consistency(self) -> float | None:
        held = sum(
            1 for run in self.runs if run.state_context_held and run.plan_references_proposals
        )
        return _rate(held, len(self.runs))

    @property
    def workflow_completion_rate(self) -> float | None:
        return _rate(self._count("workflow_completed"), len(self.runs))

    @property
    def safety_compliance_rate(self) -> float | None:
        return _rate(self._count("safety_respected"), len(self.runs))

    @property
    def structured_output_success_rate(self) -> float | None:
        return _rate(self._count("structured_output_succeeded"), len(self.runs))

    @property
    def coordinator_conflict_resolution_accuracy(self) -> float | None:
        """Conflicts the coordinator resolved without breaking a hard bound.

        A resolution is correct when the compiled plan passed integrity
        validation while every deterministic constraint held. The advisory
        codes are not part of this: they carry no enforcement.
        """

        applicable = [run for run in self.runs if run.expected_roles]
        if not applicable:
            return None
        correct = sum(
            1
            for run in applicable
            if run.safety_respected
            and run.state_context_held
            and run.plan_references_proposals
            and run.workflow_completed
        )
        return _rate(correct, len(applicable))

    @property
    def advisory_observations(self) -> dict[str, object]:
        followed = [
            run.coordinator_used_training_plan
            for run in self.runs
            if run.coordinator_used_training_plan is not None
        ]
        return {
            "note": (
                "Recovery and Feasibility advise; ADR-0015 gives their adjustment "
                "codes no deterministic enforcement. Recorded, never scored."
            ),
            "runs_with_advisory_codes": self._count("advisory_codes_present"),
            "coordinator_plan_within_training_draft": sum(1 for value in followed if value),
            "coordinator_plan_comparisons": len(followed),
        }

    def to_json(self) -> dict[str, object]:
        by_category: dict[str, dict[str, int]] = {}
        for run in self.runs:
            bucket = by_category.setdefault(
                run.category, {"runs": 0, "completed": 0, "safety_respected": 0}
            )
            bucket["runs"] += 1
            bucket["completed"] += int(run.workflow_completed)
            bucket["safety_respected"] += int(run.safety_respected)

        return {
            "architecture_code": self.architecture_code,
            "provider": self.provider_label,
            "run_count": len(self.runs),
            "agent_invocation_accuracy": self.agent_invocation_accuracy,
            "agent_role_consistency": self.agent_role_consistency,
            "state_consistency": self.state_consistency,
            "workflow_completion_rate": self.workflow_completion_rate,
            "coordinator_conflict_resolution_accuracy": (
                self.coordinator_conflict_resolution_accuracy
            ),
            "safety_compliance_rate": self.safety_compliance_rate,
            "structured_output_success_rate": self.structured_output_success_rate,
            "advisory_observations": self.advisory_observations,
            "by_category": by_category,
            "totals": {
                "llm_calls": sum(run.llm_call_count for run in self.runs),
                "input_tokens": sum(run.input_tokens for run in self.runs),
                "output_tokens": sum(run.output_tokens for run in self.runs),
                "repairs": sum(run.repair_attempts for run in self.runs),
                "fallbacks": sum(1 for run in self.runs if run.used_fallback),
            },
        }

    def dumps(self) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, indent=2, sort_keys=True)


def build_report(
    runs: Sequence[CaseRunResult],
    *,
    architecture_code: str,
    provider_label: str,
) -> AgentMetricsReport:
    return AgentMetricsReport(
        architecture_code=architecture_code,
        provider_label=provider_label,
        runs=[collect_run_metrics(run) for run in runs],
    )


__all__ = [
    "COORDINATOR_ROLE_CODE",
    "SPECIALIST_ROLE_CODES",
    "AgentMetricsReport",
    "RunMetrics",
    "build_report",
    "collect_run_metrics",
]
