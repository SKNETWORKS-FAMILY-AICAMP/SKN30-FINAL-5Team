"""Session shape, role separation, and state integrity across the graph.

Shape is a reviewed property, not a presentation detail: a session opens with
preparation and closes with settling (`domain/rules/plan_shape.py`).  Role
separation is ADR-0015: only Training owns a plan, and Recovery and Feasibility
advise.  Both are checked here against what the run actually produced.
"""

from __future__ import annotations

from backend.app.domain.agents.v3_contracts import SPECIALIST_AGENT_ORDER, SpecialistAgentTypeCode
from backend.app.domain.rules.plan_shape import (
    MAX_PHASE_EXERCISE_TYPES,
    MAX_PLAN_EXERCISE_TYPES,
    PLAN_PHASE_ORDER,
    families_over_budget,
    has_consecutive_main_repetition,
)
from backend.tests.evaluation.evaluators.findings import DefectClass, Finding, Severity
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult

_ADVISORY_ROLES = (SpecialistAgentTypeCode.RECOVERY, SpecialistAgentTypeCode.FEASIBILITY)


def evaluate(run: CaseRunResult) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    findings.extend(_role_separation(run))
    findings.extend(_state_integrity(run))
    plan = run.compiled_plan
    if plan is not None:
        findings.extend(_shape(run))
    return tuple(findings)


def _role_separation(run: CaseRunResult) -> list[Finding]:
    """ADR-0015: an advisory specialist never submits an exercise plan."""

    findings: list[Finding] = []
    if not run.case.expected_agent_behavior.advisory_roles_have_no_prescriptions:
        return findings
    for proposal in run.graph_result.round_one_proposals:
        if proposal.agent_type_code in _ADVISORY_ROLES and proposal.exercise_prescriptions:
            findings.append(
                Finding(
                    check_code="ADVISORY_ROLE_SUBMITTED_PLAN",
                    severity=Severity.MAJOR,
                    expected=f"{proposal.agent_type_code.value} submits adjustment codes only",
                    observed=(
                        f"{proposal.agent_type_code.value} carried "
                        f"{len(proposal.exercise_prescriptions)} prescriptions"
                    ),
                    defect_class=DefectClass.SERVICE,
                )
            )
    training = [
        proposal
        for proposal in run.graph_result.round_one_proposals
        if proposal.agent_type_code is SpecialistAgentTypeCode.TRAINING
    ]
    if run.case.expected_agent_behavior.training_owns_plan and training:
        if not training[0].exercise_prescriptions:
            findings.append(
                Finding(
                    check_code="TRAINING_PROPOSAL_WITHOUT_PLAN",
                    severity=Severity.MAJOR,
                    expected="a READY Training proposal carries the draft plan",
                    observed="Training proposal carried no prescriptions",
                    defect_class=DefectClass.SERVICE,
                )
            )
    return findings


def _state_integrity(run: CaseRunResult) -> list[Finding]:
    """Proposals must reach the coordinator in canonical role order, hashes intact.

    The three specialist branches merge through an append reducer, so their
    arrival order is whichever finished first.  `collect_proposals` re-reads them
    by role, which is what makes a run replayable; this asserts that it did.
    """

    findings: list[Finding] = []
    proposals = run.graph_result.round_one_proposals
    if not proposals:
        return findings

    order = tuple(proposal.agent_type_code for proposal in proposals)
    if len(order) == len(SPECIALIST_AGENT_ORDER) and order != SPECIALIST_AGENT_ORDER:
        findings.append(
            Finding(
                check_code="PROPOSAL_ROLE_ORDER_NOT_CANONICAL",
                severity=Severity.MAJOR,
                expected=f"proposals in {[role.value for role in SPECIALIST_AGENT_ORDER]}",
                observed=f"proposals in {[role.value for role in order]}",
                defect_class=DefectClass.SERVICE,
            )
        )

    envelope_hash = run.scenario.constraint_envelope.envelope_hash
    pool_hash = run.scenario.exercise_pool.pool_hash
    for proposal in proposals:
        if proposal.envelope_hash != envelope_hash or proposal.pool_hash != pool_hash:
            findings.append(
                Finding(
                    check_code="AGENT_STATE_CONTEXT_LOST",
                    severity=Severity.CRITICAL,
                    expected="every proposal references the run's envelope and pool",
                    observed=f"{proposal.agent_type_code.value} referenced another context",
                    defect_class=DefectClass.SERVICE,
                )
            )

    plan_spec = run.plan_spec
    if plan_spec is not None:
        referenced = {
            reference.agent_type_code: reference.proposal_hash
            for reference in plan_spec.proposal_references
        }
        for proposal in proposals:
            expected_hash = referenced.get(proposal.agent_type_code)
            if expected_hash is not None and expected_hash != proposal.proposal_hash:
                findings.append(
                    Finding(
                        check_code="PLAN_REFERENCES_DIFFERENT_PROPOSAL",
                        severity=Severity.CRITICAL,
                        expected="the plan references the proposals this run produced",
                        observed=f"{proposal.agent_type_code.value} hash does not match",
                        defect_class=DefectClass.SERVICE,
                    )
                )
    return findings


def _shape(run: CaseRunResult) -> list[Finding]:
    plan = run.compiled_plan
    assert plan is not None
    findings: list[Finding] = []
    prescriptions = [item.prescription for item in plan.exercises]
    phases = [item.phase_code for item in prescriptions]

    if set(phases) != set(PLAN_PHASE_ORDER):
        findings.append(
            Finding(
                check_code="PLAN_PHASE_COVERAGE_INVALID",
                severity=Severity.MAJOR,
                expected="the plan covers WARMUP, MAIN and COOLDOWN",
                observed=f"phases present: {sorted(set(phases))}",
                defect_class=DefectClass.SERVICE,
            )
        )
    ranks = [PLAN_PHASE_ORDER.index(phase) for phase in phases if phase in PLAN_PHASE_ORDER]
    if ranks != sorted(ranks):
        findings.append(
            Finding(
                check_code="PLAN_PHASE_ORDER_INVALID",
                severity=Severity.MAJOR,
                expected="WARMUP precedes MAIN, which precedes COOLDOWN",
                observed=f"phase order: {phases}",
                defect_class=DefectClass.SERVICE,
            )
        )

    sequences = [item.sequence for item in prescriptions]
    if sequences != list(range(1, len(prescriptions) + 1)):
        findings.append(
            Finding(
                check_code="PRESCRIPTION_SEQUENCE_NOT_CONTIGUOUS",
                severity=Severity.MAJOR,
                expected="sequences run 1..n without gaps",
                observed=f"sequences: {sequences}",
                defect_class=DefectClass.SERVICE,
            )
        )

    distinct = {item.exercise_id for item in prescriptions}
    if len(distinct) > MAX_PLAN_EXERCISE_TYPES:
        findings.append(
            Finding(
                check_code="PLAN_EXERCISE_VARIETY_EXCEEDED",
                severity=Severity.MAJOR,
                expected=f"at most {MAX_PLAN_EXERCISE_TYPES} distinct exercises",
                observed=f"{len(distinct)} distinct exercises",
                defect_class=DefectClass.SERVICE,
            )
        )
    for phase_code, cap in MAX_PHASE_EXERCISE_TYPES.items():
        phase_ids = {item.exercise_id for item in prescriptions if item.phase_code == phase_code}
        if len(phase_ids) > cap:
            findings.append(
                Finding(
                    check_code="PHASE_EXERCISE_VARIETY_EXCEEDED",
                    severity=Severity.MAJOR,
                    expected=f"at most {cap} distinct exercises in {phase_code}",
                    observed=f"{len(phase_ids)} in {phase_code}",
                    defect_class=DefectClass.SERVICE,
                )
            )

    over_budget = families_over_budget(
        (item.prescription.exercise_id, item.catalog_record.family_code) for item in plan.exercises
    )
    if over_budget:
        findings.append(
            Finding(
                check_code="PLAN_EXERCISE_FAMILY_REPEATED",
                severity=Severity.MINOR,
                expected="one exercise per catalog family",
                observed=f"families over budget: {list(over_budget)}",
                defect_class=DefectClass.SERVICE,
            )
        )

    if has_consecutive_main_repetition(
        tuple((item.exercise_id, item.phase_code) for item in prescriptions)
    ):
        findings.append(
            Finding(
                check_code="PLAN_MAIN_REPEAT_CONSECUTIVE",
                severity=Severity.MINOR,
                expected="neighbouring main blocks use different movements",
                observed="two adjacent main blocks repeat one exercise",
                defect_class=DefectClass.SERVICE,
            )
        )
    return findings


__all__ = ["evaluate"]
