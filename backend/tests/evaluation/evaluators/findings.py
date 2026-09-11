"""Structured findings shared by every evaluator and every runner.

The master specification asks for more than PASS/FAIL: a result has to say what
was expected, what happened, and -- separately -- whether the service or the test
is at fault.  Keeping `defect_class` on the finding itself means that judgement
is recorded at the moment of detection rather than reconstructed later from a
log, which is how a harness bug quietly becomes a reported service defect.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    """A safety or product invariant was broken. One occurrence fails the run."""

    MAJOR = "MAJOR"
    """A contract the service promises was broken, without a safety impact."""

    MINOR = "MINOR"
    """A deviation worth reporting that breaks no stated contract."""

    INFO = "INFO"
    """An observation. Never fails a case."""


class DefectClass(StrEnum):
    SERVICE = "SERVICE"
    """The service behaved incorrectly."""

    TEST = "TEST"
    """The harness or the case is wrong; the service is not implicated."""

    UNDETERMINED = "UNDETERMINED"
    """Needs a human read before it can be attributed."""

    NOT_A_DEFECT = "NOT_A_DEFECT"
    """Recorded behaviour that is correct by design. Used for observations."""


@dataclass(frozen=True, slots=True)
class Finding:
    check_code: str
    severity: Severity
    expected: str
    observed: str
    defect_class: DefectClass = DefectClass.UNDETERMINED

    @property
    def fails_case(self) -> bool:
        return self.severity in {Severity.CRITICAL, Severity.MAJOR} and (
            self.defect_class is not DefectClass.NOT_A_DEFECT
        )


@dataclass(frozen=True, slots=True)
class CaseEvaluation:
    case_id: str
    category: str
    architecture_code: str
    script_summary: str
    status_code: str
    has_plan: bool
    used_fallback: bool
    repair_attempts: int
    llm_call_count: int
    input_tokens: int
    output_tokens: int
    wall_clock_ms: int
    findings: tuple[Finding, ...] = ()

    # Why a run fell back, not just that it did. The held-out comparison
    # recorded `used_fallback` alone, so explaining its seven multi-agent
    # fallbacks meant reading LangSmith traces after the fact -- and a run
    # without tracing would have left no explanation at all.
    failure_codes: tuple[str, ...] = ()
    violation_codes: tuple[str, ...] = ()
    decline_reason_codes: tuple[str, ...] = ()

    @property
    def failures(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.fails_case)

    @property
    def observations(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if not finding.fails_case)

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def critical_failures(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.failures if finding.severity is Severity.CRITICAL)

    def to_json(self) -> dict[str, object]:
        body = asdict(self)
        body["passed"] = self.passed
        return body


@dataclass
class EvaluationReport:
    """Every case in one run, plus the aggregates the report tables need."""

    run_id: str
    architecture_code: str
    cases: list[CaseEvaluation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(case.passed for case in self.cases)

    @property
    def critical_failure_count(self) -> int:
        return sum(len(case.critical_failures) for case in self.cases)

    def by_category(self) -> dict[str, dict[str, int]]:
        summary: dict[str, dict[str, int]] = {}
        for case in self.cases:
            bucket = summary.setdefault(case.category, {"total": 0, "passed": 0, "failed": 0})
            bucket["total"] += 1
            bucket["passed" if case.passed else "failed"] += 1
        return summary

    def to_json(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "architecture_code": self.architecture_code,
            "case_count": len(self.cases),
            "passed": self.passed,
            "critical_failure_count": self.critical_failure_count,
            "by_category": self.by_category(),
            "cases": [case.to_json() for case in self.cases],
        }

    def dumps(self) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, indent=2, sort_keys=True)


__all__ = [
    "CaseEvaluation",
    "DefectClass",
    "EvaluationReport",
    "Finding",
    "Severity",
]
