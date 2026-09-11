"""Why a run produced no model plan, split into classes that compare fairly.

`llm_plan_rate` counts runs that reached the user with a model-authored plan.
It is the pre-registered metric and it is not changed here. But it turned out to
measure two different things at once, and only one of them is symmetric across
the architectures being compared.

`SpecialistAgentProposal` carries a `proposal_status_code`, and the Training
prompt tells the agent when to answer `NEEDS_INPUT`. `SingleAgentPlanDraft` has
no status field at all and requires `min_length=1` prescriptions, so a baseline
agent has no way to decline: it returns a plan or it breaks. Across the two paid
held-out runs Training declined on 11 of 58 runs and the baselines declined on
none, because they structurally could not.

So a decline and a rejected plan are not the same event, and averaging them into
one rate compares an architecture that may say no against one that may not.
Splitting them leaves the pre-registered number untouched while making visible
which part of the gap is a like-for-like comparison. See
`docs/test/ROUND2_HELDOUT_RESULTS.md` section 9.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from backend.app.domain.agents.v3_contracts import SpecialistAgentTypeCode


class OutcomeClass(StrEnum):
    """What became of one run, from the model's side of the gates."""

    PLAN = "PLAN"
    """A model-authored plan passed every deterministic gate."""

    DECLINED = "DECLINED"
    """The agent used a contractual option to not produce a plan.

    Available to the multi-agent path only, which is the whole reason this
    class exists separately.
    """

    CONTRACT = "CONTRACT"
    """The agent answered but broke its output contract."""

    GATE = "GATE"
    """A well-formed plan the deterministic compiler or validator refused."""

    PROVIDER = "PROVIDER"
    """A technical failure: timeout, or the provider was unavailable."""


_ROLES: Final = tuple(item.value for item in SpecialistAgentTypeCode)


def _role_codes(*suffixes: str) -> frozenset[str]:
    """Codes `nodes._run_specialist` builds as `V3_{ROLE}{suffix}`.

    Derived from the role enum rather than matched by suffix: plain suffix
    matching claimed `V3_COMPILATION_FAILED` as a specialist decline, which is
    the compiler refusing a plan and the opposite of what this class means.
    """

    return frozenset(f"V3_{role}{suffix}" for role in _ROLES for suffix in suffixes)


# An agent's own verdict on its inputs. `_NOT_READY` is the Training readiness
# gate; `_FAILED` is the agent reporting it could not answer. Neither is a
# malformed answer -- the proposal validated, it just declined to plan.
_DECLINED_CODES: Final = _role_codes("_NOT_READY", "_FAILED")

# The answer arrived and did not satisfy the contract it was bound to.
_CONTRACT_CODES: Final = _role_codes("_PROPOSAL_INVALID", "_NO_PROPOSAL", "_MISSING") | {
    "LLM_AGENT_SCHEMA_INVALID",
    "LLM_AGENT_DOMAIN_INVALID",
    "V3_PLAN_SPEC_MISSING",
}

_PROVIDER_CODES: Final = _role_codes("_TIMEOUT") | {"LLM_AGENT_PROVIDER_UNAVAILABLE"}

# The plan was well-formed and the deterministic layer still refused it. Every
# architecture passes through this layer, so this class compares like for like.
_GATE_CODES: Final = frozenset(
    {
        "V3_COMPILATION_FAILED",
        "V3_VALIDATION_FAILED",
    }
)


def classify(
    *,
    has_plan: bool,
    used_fallback: bool,
    failure_codes: Iterable[str],
    violation_codes: Iterable[str] = (),
) -> OutcomeClass:
    """Name the single reason this run produced no model plan.

    A run can carry several codes -- a declining specialist and the missing
    PlanSpec that follows from it -- so the classes are ordered by which one
    explains the others. A decline explains a downstream absence; a contract
    breach explains a compilation failure; an integrity violation is only
    reached by a plan that was otherwise well formed.
    """

    if has_plan and not used_fallback:
        return OutcomeClass.PLAN

    codes = tuple(failure_codes)
    if any(code in _PROVIDER_CODES for code in codes):
        return OutcomeClass.PROVIDER
    if any(code in _DECLINED_CODES for code in codes):
        return OutcomeClass.DECLINED
    if any(code in _CONTRACT_CODES for code in codes):
        return OutcomeClass.CONTRACT
    if any(code in _GATE_CODES for code in codes):
        return OutcomeClass.GATE
    if tuple(violation_codes) or codes:
        # An integrity violation code appearing as a failure code, or any code
        # this taxonomy has not met. Both mean a compiled plan the gates refused.
        return OutcomeClass.GATE
    # No plan and no recorded reason. Real before `CaseEvaluation` carried
    # failure codes, so it is named rather than folded into a class it might
    # not belong to.
    return OutcomeClass.GATE


@dataclass(frozen=True, slots=True)
class OutcomeBreakdown:
    """One architecture's runs, split by what stopped them."""

    counts: Mapping[OutcomeClass, int]
    run_count: int

    @property
    def plan_rate(self) -> float | None:
        """The pre-registered metric, reproduced from the same classification."""

        return self._rate(self.counts.get(OutcomeClass.PLAN, 0))

    @property
    def decline_rate(self) -> float | None:
        """Runs lost to an option the baselines do not have."""

        return self._rate(self.counts.get(OutcomeClass.DECLINED, 0))

    @property
    def rejected_rate(self) -> float | None:
        """Runs lost to checks every architecture faces.

        Contract, gate and provider failures together. This is the part of the
        availability gap that compares like for like; it is a companion to the
        pre-registered plan rate, not a replacement for it.
        """

        rejected = sum(
            self.counts.get(item, 0)
            for item in (OutcomeClass.CONTRACT, OutcomeClass.GATE, OutcomeClass.PROVIDER)
        )
        return self._rate(rejected)

    def _rate(self, count: int) -> float | None:
        if self.run_count == 0:
            return None
        return round(count / self.run_count, 4)

    def to_json(self) -> dict[str, object]:
        return {
            "run_count": self.run_count,
            "counts": {item.value: self.counts.get(item, 0) for item in OutcomeClass},
            "plan_rate": self.plan_rate,
            "decline_rate": self.decline_rate,
            "rejected_rate": self.rejected_rate,
            "note": (
                "DECLINED is available to the multi-agent path only: a baseline "
                "output schema has no status field and requires at least one "
                "prescription. rejected_rate is the architecture-symmetric part."
            ),
        }


def breakdown(items: Iterable[OutcomeClass]) -> OutcomeBreakdown:
    counts: dict[OutcomeClass, int] = {}
    total = 0
    for item in items:
        counts[item] = counts.get(item, 0) + 1
        total += 1
    return OutcomeBreakdown(counts=counts, run_count=total)


__all__ = ["OutcomeBreakdown", "OutcomeClass", "breakdown", "classify"]
