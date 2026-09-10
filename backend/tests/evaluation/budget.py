"""Forecast the provider work a paid evaluation would do, before it is run.

Two halves, kept apart on purpose.

**Volume is measured.** Call counts come from the graph's own structure and token
volumes from serializing the real prompts the four adapters build. Those numbers
are facts about this dataset and do not depend on anyone's price list.

**Cost is not estimated.** `docs/runbooks/v3-shadow-evaluation.md` states that
vendor prices are not hard-coded and that a cost must not be written when the
approved pricing reference is absent. So this module converts volume to currency
only when a `V3ApprovedPricingReference` is supplied, and otherwise reports the
volume and says the cost is unavailable. Inventing a rate to fill the gap would
produce exactly the kind of confident-looking number a budget decision should
never rest on.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final, cast

from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    CoordinatorInput,
    SpecialistAgentInput,
    SpecialistAgentTypeCode,
)
from backend.app.integrations.llm_agents.models import LlmAgentRoleCode
from backend.app.integrations.llm_agents.payload import coordinator_payload, specialist_payload
from backend.app.integrations.llm_agents.prompts import ROLE_PROMPTS, messages_for
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.app.integrations.llm_agents.specialists import (
    FeasibilityAgentAdapter,
    RecoveryAgentAdapter,
    TrainingAgentAdapter,
)
from backend.app.modules.decisions.v3_evaluation import V3ApprovedPricingReference
from backend.tests.evaluation.dataset import EvaluationCase, ExpectedOutcome
from backend.tests.evaluation.runners.fake_chat import Script, ScriptedChatModel
from backend.tests.evaluation.runners.payloads import PayloadBuilder
from backend.tests.evaluation.scenario import build_scenario

# A blocked envelope terminates before any agent runs, so those cases cost
# nothing. Everything else calls three specialists plus one coordinator.
CALLS_PER_PLANNING_RUN: Final = 4

# One repair round is possible but not typical. Applied as a headroom factor
# rather than assumed, so the forecast is a ceiling and not a hope.
REPAIR_HEADROOM: Final = Decimal("1.25")

# `llm_agents_max_output_tokens` bounds each structured answer. This is the
# deployed staging value (compose.staging.v3production.yaml), not the library
# default of 1200, which is too small for Training's measured output.
MAX_OUTPUT_TOKENS_PER_CALL: Final = 4000

# Rough characters-per-token for the machine-code payloads these prompts carry.
# `messages_for` serializes with ensure_ascii=True and the agent payload
# allowlist admits no Korean, so the content is ASCII JSON.
CHARS_PER_TOKEN: Final = 4

# What each role actually returns, as opposed to what it is allowed to.
# Training and Coordinator are the reviewed measurements recorded in
# `config.py` (2,375-2,893 and 2,047-2,913); the two advisory roles are from
# this harness's own first paid run, which observed 358 and 324 output tokens.
# The ceiling above bounds the worst case; these describe the likely bill, and
# reporting only the ceiling would overstate it roughly threefold.
TYPICAL_OUTPUT_TOKENS: Final[dict[str, int]] = {
    "TRAINING": 2900,
    "RECOVERY": 400,
    "FEASIBILITY": 400,
    "COORDINATOR": 2900,
    "JUDGE": 500,
}


@dataclass(frozen=True, slots=True)
class RolePromptVolume:
    role_code: str
    call_count: int
    total_prompt_chars: int

    @property
    def prompt_tokens(self) -> int:
        return self.total_prompt_chars // CHARS_PER_TOKEN


@dataclass(frozen=True, slots=True)
class PhaseForecast:
    """One phase's provider work, measured from the real prompts."""

    phase: str
    run_count: int
    roles: tuple[RolePromptVolume, ...]
    repeats: int = 1
    output_tokens_per_call: int = MAX_OUTPUT_TOKENS_PER_CALL

    @property
    def call_count(self) -> int:
        return sum(role.call_count for role in self.roles) * self.repeats

    @property
    def prompt_tokens(self) -> int:
        return sum(role.prompt_tokens for role in self.roles) * self.repeats

    @property
    def max_output_tokens(self) -> int:
        return self.call_count * self.output_tokens_per_call

    @property
    def typical_output_tokens(self) -> int:
        """What the roles in this phase are likely to actually return."""

        per_pass = sum(
            role.call_count * TYPICAL_OUTPUT_TOKENS.get(role.role_code, self.output_tokens_per_call)
            for role in self.roles
        )
        return per_pass * self.repeats

    def with_headroom(self) -> tuple[int, int]:
        """Upper bound: every call returns its full allowance."""

        prompt = int(Decimal(self.prompt_tokens) * REPAIR_HEADROOM)
        output = int(Decimal(self.max_output_tokens) * REPAIR_HEADROOM)
        return prompt, output

    def typical_with_headroom(self) -> tuple[int, int]:
        """Likely bill: measured output volumes rather than the allowance."""

        prompt = int(Decimal(self.prompt_tokens) * REPAIR_HEADROOM)
        output = int(Decimal(self.typical_output_tokens) * REPAIR_HEADROOM)
        return prompt, output


def measure_prompt_volume(cases: tuple[EvaluationCase, ...]) -> tuple[RolePromptVolume, ...]:
    """Serialize the real prompts for these cases and total them per role."""

    totals: dict[str, list[int]] = {}
    for case in cases:
        scenario = build_scenario(case)
        envelope = scenario.constraint_envelope
        pool = scenario.exercise_pool
        chat_model = ScriptedChatModel(
            script=Script(), payload_builder=PayloadBuilder(envelope=envelope, pool=pool)
        )
        invoker = StructuredChatInvoker(
            chat_model=cast(object, chat_model),  # type: ignore[arg-type]
            model_code="budget-forecast",
            max_attempts=1,
        )
        proposals = []
        for adapter, role in (
            (TrainingAgentAdapter, LlmAgentRoleCode.TRAINING),
            (RecoveryAgentAdapter, LlmAgentRoleCode.RECOVERY),
            (FeasibilityAgentAdapter, LlmAgentRoleCode.FEASIBILITY),
        ):
            result = asyncio.run(
                adapter(invoker=invoker).apropose(constraint_envelope=envelope, exercise_pool=pool)
            )
            if result.output is None:
                continue
            proposals.append(result.output)
            totals.setdefault(role.value, []).append(_specialist_prompt_chars(role, envelope, pool))
        if len(proposals) == 3:
            totals.setdefault(LlmAgentRoleCode.COORDINATOR.value, []).append(
                _coordinator_prompt_chars(envelope, pool, tuple(proposals))
            )
    return tuple(
        RolePromptVolume(
            role_code=role_code,
            call_count=len(values),
            total_prompt_chars=sum(values),
        )
        for role_code, values in sorted(totals.items())
    )


def _specialist_prompt_chars(
    role: LlmAgentRoleCode, envelope: ConstraintEnvelope, pool: object
) -> int:
    agent_input = SpecialistAgentInput(
        agent_type_code=SpecialistAgentTypeCode(role.value),
        constraint_envelope=envelope,
        envelope_hash=envelope.envelope_hash,
        exercise_pool=pool,  # type: ignore[arg-type]
        pool_hash=pool.pool_hash,  # type: ignore[attr-defined]
    )
    messages = messages_for(
        ROLE_PROMPTS[role],
        output_schema_version="specialist-agent-proposal-v1",
        payload=specialist_payload(agent_input),
    )
    return sum(len(str(message.content)) for message in messages)


def _coordinator_prompt_chars(
    envelope: ConstraintEnvelope, pool: object, proposals: tuple[object, ...]
) -> int:
    coordinator_input = CoordinatorInput(
        constraint_envelope=envelope,
        exercise_pool=pool,  # type: ignore[arg-type]
        proposals=proposals,  # type: ignore[arg-type]
        repair_attempt=0,
    )
    messages = messages_for(
        ROLE_PROMPTS[LlmAgentRoleCode.COORDINATOR],
        output_schema_version="plan-spec-v1",
        payload=coordinator_payload(coordinator_input),
    )
    return sum(len(str(message.content)) for message in messages)


def measure_judge_volume(cases: tuple[EvaluationCase, ...]) -> RolePromptVolume:
    """Measure the judge request, which is far smaller than an agent prompt.

    A judge sees one compiled plan and the rubric; an agent sees the whole
    approved pool. Folding the two together would overstate the judge phase
    several times over.
    """

    from backend.tests.evaluation.harness import run_case
    from backend.tests.evaluation.judge.judge import build_judge_payload, judge_request_text
    from backend.tests.evaluation.judge.rubric import SYSTEM_INSTRUCTION

    total = 0
    calls = 0
    for case in cases:
        run = run_case(case)
        if run.compiled_plan is None:
            continue
        text = judge_request_text(build_judge_payload(run))
        # The rubric is Korean and serialized without ASCII escaping, so its
        # characters cost more than one token each. Counted at double rate so
        # the forecast stays an upper bound rather than an optimistic one.
        total += (len(text) + len(SYSTEM_INSTRUCTION)) * 2
        calls += 1
    return RolePromptVolume(role_code="JUDGE", call_count=calls, total_prompt_chars=total)


# A judge answers with six scores and six short rationales, not a plan.
JUDGE_MAX_OUTPUT_TOKENS: Final = 600


def load_pricing(path: Path) -> V3ApprovedPricingReference:
    """Load an approved pricing reference. There is no built-in default."""

    return V3ApprovedPricingReference.model_validate_json(path.read_text(encoding="utf-8"))


def cost_for(
    *,
    prompt_tokens: int,
    output_tokens: int,
    pricing: V3ApprovedPricingReference,
) -> Decimal:
    input_cost = (
        Decimal(prompt_tokens) / Decimal(pricing.input_token_unit)
    ) * pricing.input_unit_price
    output_cost = (
        Decimal(output_tokens) / Decimal(pricing.output_token_unit)
    ) * pricing.output_unit_price
    return (input_cost + output_cost).quantize(Decimal("0.0001"))


@dataclass
class BudgetForecast:
    phases: list[PhaseForecast]
    pricing: V3ApprovedPricingReference | None = None

    @property
    def total_calls(self) -> int:
        return sum(phase.call_count for phase in self.phases)

    @property
    def total_prompt_tokens(self) -> int:
        return sum(phase.with_headroom()[0] for phase in self.phases)

    @property
    def total_output_tokens(self) -> int:
        return sum(phase.with_headroom()[1] for phase in self.phases)

    @property
    def typical_output_tokens(self) -> int:
        return sum(phase.typical_with_headroom()[1] for phase in self.phases)

    def to_json(self) -> dict[str, object]:
        body: dict[str, object] = {
            "measured": {
                "note": (
                    "Call counts come from the graph structure; token volumes from "
                    "serializing the real adapter prompts for this dataset. Output is "
                    "the configured per-call ceiling, so the totals are an upper bound."
                ),
                "chars_per_token_assumption": CHARS_PER_TOKEN,
                "max_output_tokens_per_call": MAX_OUTPUT_TOKENS_PER_CALL,
                "repair_headroom": str(REPAIR_HEADROOM),
                "total_llm_calls": self.total_calls,
                "total_prompt_tokens_with_headroom": self.total_prompt_tokens,
                "total_output_tokens_ceiling": self.total_output_tokens,
                "total_output_tokens_typical": self.typical_output_tokens,
                "typical_output_tokens_per_role": dict(sorted(TYPICAL_OUTPUT_TOKENS.items())),
                "phases": [
                    {
                        "phase": phase.phase,
                        "run_count": phase.run_count,
                        "repeats": phase.repeats,
                        "llm_calls": phase.call_count,
                        "prompt_tokens": phase.prompt_tokens,
                        "max_output_tokens": phase.max_output_tokens,
                        "typical_output_tokens": phase.typical_output_tokens,
                        "roles": [
                            {
                                "role_code": role.role_code,
                                "calls": role.call_count,
                                "prompt_tokens": role.prompt_tokens,
                            }
                            for role in phase.roles
                        ],
                    }
                    for phase in self.phases
                ],
            }
        }
        if self.pricing is None:
            body["cost"] = {
                "available": False,
                "reason": (
                    "No approved pricing reference supplied. "
                    "docs/runbooks/v3-shadow-evaluation.md: vendor prices are not "
                    "hard-coded and a cost must not be written without the approved "
                    "reference. Supply one with --pricing-reference to price this run."
                ),
            }
            return body

        ceiling = cost_for(
            prompt_tokens=self.total_prompt_tokens,
            output_tokens=self.total_output_tokens,
            pricing=self.pricing,
        )
        typical = cost_for(
            prompt_tokens=self.total_prompt_tokens,
            output_tokens=self.typical_output_tokens,
            pricing=self.pricing,
        )
        body["cost"] = {
            "available": True,
            "typical_total": str(typical),
            "currency_code": self.pricing.currency_code,
            "provider_code": self.pricing.provider_code,
            "model_code": self.pricing.model_code,
            "source_reference": self.pricing.source_reference,
            "ceiling_total": str(ceiling),
            "by_phase_typical": {
                phase.phase: str(
                    cost_for(
                        prompt_tokens=phase.typical_with_headroom()[0],
                        output_tokens=phase.typical_with_headroom()[1],
                        pricing=self.pricing,
                    )
                )
                for phase in self.phases
            },
        }
        return body

    def dumps(self) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, indent=2, sort_keys=True)


def planning_cases(cases: tuple[EvaluationCase, ...]) -> tuple[EvaluationCase, ...]:
    """Cases that actually reach a provider. Blocked ones cost nothing."""

    return tuple(
        case
        for case in cases
        if case.expected_constraints.plan_generation_allowed
        and case.expected_outcome is not ExpectedOutcome.NO_PLAN
    )


__all__ = [
    "CALLS_PER_PLANNING_RUN",
    "CHARS_PER_TOKEN",
    "MAX_OUTPUT_TOKENS_PER_CALL",
    "REPAIR_HEADROOM",
    "BudgetForecast",
    "PhaseForecast",
    "RolePromptVolume",
    "cost_for",
    "load_pricing",
    "measure_prompt_volume",
    "planning_cases",
]
