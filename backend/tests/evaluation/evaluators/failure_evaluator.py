"""Termination, fail-closed behaviour, and bounded repair.

A workout service is judged on failure at least as much as on success: the
question is not whether the graph produced something, but whether what it
produced was safe and whether a failure was explicable afterwards.
"""

from __future__ import annotations

from typing import Final

from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.tests.evaluation.dataset import ExpectedOutcome
from backend.tests.evaluation.evaluators.findings import DefectClass, Finding, Severity
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult

# Every status `finalize` and `terminal` can produce (`langgraph/nodes.py`).
KNOWN_STATUS_CODES: Final[frozenset[str]] = frozenset(
    {
        "SUCCEEDED",
        "FAILED",
        "NO_ALTERNATIVE_AVAILABLE",
        SafetyRequiredActionCode.REST.value,
        SafetyRequiredActionCode.STOP_AND_SEEK_HELP.value,
        "V3_INPUT_STALE",
        "V3_ENVELOPE_POOL_HASH_MISMATCH",
        "V3_CATALOG_VERSION_MISMATCH",
        "V3_POOL_CATALOG_VERSION_MISMATCH",
        "V3_POLICY_VERSION_MISMATCH",
        "V3_SPECIALIST_PORTS_INCOMPLETE",
        "V3_TIMEOUT_CONFIG_INVALID",
        "REGENERATION_LIMIT_REACHED",
        "PLAN_GENERATION_FORBIDDEN",
    }
)

MAX_REPAIR_ATTEMPTS: Final = 1


def evaluate(run: CaseRunResult) -> tuple[Finding, ...]:
    findings: list[Finding] = []

    # 1. The graph must always terminate with a status the client can act on.
    if run.status_code not in KNOWN_STATUS_CODES:
        findings.append(
            Finding(
                check_code="UNKNOWN_TERMINAL_STATUS",
                severity=Severity.MAJOR,
                expected=f"a status within {sorted(KNOWN_STATUS_CODES)}",
                observed=run.status_code,
                defect_class=DefectClass.UNDETERMINED,
            )
        )

    # 2. Repair is bounded to one round. A second would be an unbounded loop
    #    wearing a different name.
    if run.repair_attempts > MAX_REPAIR_ATTEMPTS:
        findings.append(
            Finding(
                check_code="REPAIR_ATTEMPTS_EXCEEDED",
                severity=Severity.CRITICAL,
                expected=f"at most {MAX_REPAIR_ATTEMPTS} repair round",
                observed=f"{run.repair_attempts} repair rounds",
                defect_class=DefectClass.SERVICE,
            )
        )

    # 3. Fail closed. A non-success terminal status must not carry a plan.
    if run.status_code != "SUCCEEDED" and run.has_plan:
        findings.append(
            Finding(
                check_code="FAILED_RUN_RETURNED_PLAN",
                severity=Severity.CRITICAL,
                expected="a non-success status carries no plan",
                observed=f"status={run.status_code} carried a compiled plan",
                defect_class=DefectClass.SERVICE,
            )
        )

    # 4. A failure has to say why, or the decision cannot be reproduced from what
    #    was stored (`AGENTS.md` section 6).
    if run.status_code != "SUCCEEDED" and not run.failure_codes:
        findings.append(
            Finding(
                check_code="FAILURE_WITHOUT_REASON_CODE",
                severity=Severity.MAJOR,
                expected="a non-success run reports at least one failure code",
                observed=f"status={run.status_code} with no failure codes",
                defect_class=DefectClass.SERVICE,
            )
        )

    # 5. The case's own expectation, which only binds when the provider worked.
    #
    #    A case states what a *working* model should produce for its input. Once
    #    a fault is injected, withholding the plan is the correct outcome, not a
    #    missed expectation: the requirement under fault is to fail closed, which
    #    the checks above already assert. Reporting fail-closed behaviour as a
    #    defect here would invert the very property this harness exists to prove.
    expected = run.case.expected_outcome
    if expected is ExpectedOutcome.PLAN and not run.has_plan:
        if run.provider_was_compliant:
            findings.append(
                Finding(
                    check_code="EXPECTED_PLAN_NOT_PRODUCED",
                    severity=Severity.MAJOR,
                    expected="a compiled plan for this case",
                    observed=f"status={run.status_code}, failures={list(run.failure_codes)}",
                    defect_class=DefectClass.UNDETERMINED,
                )
            )
        else:
            findings.append(
                Finding(
                    check_code="PLAN_WITHHELD_UNDER_PROVIDER_FAULT",
                    severity=Severity.INFO,
                    expected="no unsafe plan while the provider is faulty",
                    observed=(
                        f"status={run.status_code}, failures={list(run.failure_codes)}; "
                        "the deterministic path produced no plan either"
                    ),
                    defect_class=DefectClass.NOT_A_DEFECT,
                )
            )

    # 6. A successful run must not smuggle failure codes alongside the plan.
    if run.status_code == "SUCCEEDED" and run.failure_codes:
        findings.append(
            Finding(
                check_code="SUCCESS_CARRIES_FAILURE_CODES",
                severity=Severity.MINOR,
                expected="a successful run reports no failure codes",
                observed=f"failure codes: {list(run.failure_codes)}",
                defect_class=DefectClass.UNDETERMINED,
            )
        )

    # 7. Which path answered is an observation, not a verdict: a fallback plan is
    #    a correct outcome when the provider failed, and reporting it as one lets
    #    the report separate "the model answered" from "the service answered".
    if run.used_fallback:
        findings.append(
            Finding(
                check_code="DETERMINISTIC_FALLBACK_USED",
                severity=Severity.INFO,
                expected="the deterministic path answers when the provider does not",
                observed=(
                    f"fallback produced {'a plan' if run.has_plan else 'no plan'}; "
                    f"failures={list(run.failure_codes)}"
                ),
                defect_class=DefectClass.NOT_A_DEFECT,
            )
        )
    return tuple(findings)


__all__ = ["KNOWN_STATUS_CODES", "MAX_REPAIR_ATTEMPTS", "evaluate"]
