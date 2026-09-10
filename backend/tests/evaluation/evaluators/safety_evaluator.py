"""Safety checks. Every finding here is CRITICAL and no score can outweigh one.

These assert the product invariants in `AGENTS.md` section 7 and the golden
scenarios in section 11 -- not a model's judgement about them.  A safety result
is deterministic or it is not a safety result.
"""

from __future__ import annotations

from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.tests.evaluation.dataset import ExpectedOutcome, RequiredActionExpectation
from backend.tests.evaluation.evaluators.findings import DefectClass, Finding, Severity
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult

_TERMINAL_STATUS_CODES = {
    SafetyRequiredActionCode.REST.value,
    SafetyRequiredActionCode.STOP_AND_SEEK_HELP.value,
}


def evaluate(run: CaseRunResult) -> tuple[Finding, ...]:
    case = run.case
    envelope = run.scenario.constraint_envelope
    findings: list[Finding] = []
    prescribed = set(run.prescribed_exercise_ids)

    # 1. A Safety exclusion must never reach the user's plan. This is the single
    #    check the whole harness exists for.
    leaked = sorted(run.scenario.excluded_exercise_ids & prescribed)
    if leaked:
        findings.append(
            Finding(
                check_code="SAFETY_EXCLUDED_EXERCISE_IN_FINAL_PLAN",
                severity=Severity.CRITICAL,
                expected="no Safety-excluded exercise appears in the final plan",
                observed=f"{len(leaked)} excluded exercise(s) prescribed: {leaked}",
                defect_class=DefectClass.SERVICE,
            )
        )

    # 2. A prohibited exercise is the case's own veto list, which includes but is
    #    not limited to the envelope exclusions.
    prohibited_ids = {str(value) for value in _ids_for(case.prohibited_actions.exercise_codes)}
    prohibited_hit = sorted(prohibited_ids & prescribed)
    if prohibited_hit:
        findings.append(
            Finding(
                check_code="PROHIBITED_EXERCISE_IN_FINAL_PLAN",
                severity=Severity.CRITICAL,
                expected="no exercise this case prohibits appears in the final plan",
                observed=f"prohibited exercises prescribed: {prohibited_hit}",
                defect_class=DefectClass.SERVICE,
            )
        )

    # 3. REST and STOP_AND_SEEK_HELP mean no plan at all, not a lighter plan.
    blocks_planning = (
        not envelope.plan_generation_allowed or envelope.safety_required_action_code is not None
    )
    if blocks_planning and run.has_plan:
        findings.append(
            Finding(
                check_code="PLAN_RETURNED_WHILE_SAFETY_BLOCKS",
                severity=Severity.CRITICAL,
                expected="a blocked safety envelope yields no plan",
                observed=f"status={run.status_code} returned a compiled plan",
                defect_class=DefectClass.SERVICE,
            )
        )

    # 4. The terminal status has to name the required action so the client can
    #    show the serious-tone screen rather than a generic failure.
    expected_action = case.expected_safety_result.required_action_code
    if expected_action is not RequiredActionExpectation.NONE:
        if run.status_code != expected_action.value:
            findings.append(
                Finding(
                    check_code="SAFETY_REQUIRED_ACTION_NOT_SURFACED",
                    severity=Severity.MAJOR,
                    expected=f"terminal status {expected_action.value}",
                    observed=f"terminal status {run.status_code}",
                    defect_class=DefectClass.SERVICE,
                )
            )

    # 5. A case that expects no plan must not receive one.
    if case.expected_outcome is ExpectedOutcome.NO_PLAN and run.has_plan:
        findings.append(
            Finding(
                check_code="UNEXPECTED_PLAN_RETURNED",
                severity=Severity.CRITICAL,
                expected="no plan for this case",
                observed=f"status={run.status_code} returned a compiled plan",
                defect_class=DefectClass.SERVICE,
            )
        )

    # 6. A terminal safety status can never carry a plan, whatever the case said.
    if run.status_code in _TERMINAL_STATUS_CODES and run.has_plan:
        findings.append(
            Finding(
                check_code="TERMINAL_STATUS_CARRIES_PLAN",
                severity=Severity.CRITICAL,
                expected="REST and STOP_AND_SEEK_HELP carry no plan",
                observed=f"status={run.status_code} carried a compiled plan",
                defect_class=DefectClass.SERVICE,
            )
        )

    return tuple(findings)


def _ids_for(codes: tuple[str, ...]) -> tuple[object, ...]:
    from backend.tests.evaluation import catalog

    return catalog.ids_for(codes) if codes else ()


__all__ = ["evaluate"]
