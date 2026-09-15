"""Executable runner for the ADR-0025 candidate-review experiment."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, cast

from backend.app.domain.agents.v3_contracts import CoordinatorInput
from backend.app.integrations.langgraph.state import InvocationAudit
from backend.app.integrations.llm_agents.models import (
    LlmAgentFailureCode,
    LlmAgentRoleCode,
    StructuredAgentResult,
)
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.tests.evaluation.candidate_review import (
    CandidateReview,
    CandidateSelection,
    CandidateSet,
    DeliberationOutcome,
    materialize_selection,
)
from backend.tests.evaluation.candidate_review_provider import CandidateReviewProviderAdapter
from backend.tests.evaluation.dataset import EvaluationCase
from backend.tests.evaluation.runners.fake_chat import InvocationLog, Script
from backend.tests.evaluation.runners.openai_provider import ProviderContext
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult
from backend.tests.evaluation.runners.single_agent import (
    SingleAgentPlanDraft,
    SingleAgentRunner,
    synthesize_proposals,
)
from backend.tests.evaluation.scenario import Scenario, build_scenario

ARCHITECTURE_CANDIDATE_REVIEW = "MULTI_AGENT_CANDIDATE_REVIEW"
EVAL_MODEL_CODE = "eval-candidate-review-scripted-v1"


def _audit(
    result: StructuredAgentResult[Any], *, role_code: str, phase_code: str
) -> InvocationAudit:
    telemetry = result.telemetry
    failure = result.failure
    status = "SUCCEEDED"
    if failure is not None:
        status = {
            LlmAgentFailureCode.PROVIDER_TIMEOUT: "TIMEOUT",
            LlmAgentFailureCode.SCHEMA_INVALID: "INVALID_OUTPUT",
            LlmAgentFailureCode.DOMAIN_INVALID: "INVALID_OUTPUT",
        }.get(failure.code, "FAILED")
    return InvocationAudit(
        role_code=role_code,
        phase_code=phase_code,
        status_code=status,
        attempt_count=telemetry.attempt_count if telemetry else 0,
        latency_ms=telemetry.latency_ms if telemetry else 0,
        input_token_count=telemetry.input_token_count if telemetry else None,
        output_token_count=telemetry.output_token_count if telemetry else None,
        provider_usage_present=telemetry.provider_usage_present if telemetry else False,
        failure_code=failure.code.value if failure else None,
    )


@dataclass(frozen=True, slots=True)
class CandidateReviewRunResult:
    base_run: CaseRunResult
    candidate_set: CandidateSet | None
    reviews: tuple[CandidateReview, ...]
    selection: CandidateSelection | None
    outcome: DeliberationOutcome | None

    @property
    def selection_changed(self) -> bool:
        return bool(self.outcome and self.outcome.selection_changed)

    @property
    def specialist_disagreement(self) -> bool:
        return bool(self.outcome and self.outcome.specialist_disagreement)

    @property
    def applied_adjustment_count(self) -> int:
        return len(self.outcome.applied_adjustment_ids) if self.outcome else 0


@dataclass(slots=True)
class CandidateReviewRunner:
    provider: ProviderContext | None = None
    chat_model: object | None = None
    model_code: str = EVAL_MODEL_CODE

    def _invoker(self) -> StructuredChatInvoker:
        if self.provider is not None:
            return StructuredChatInvoker(
                chat_model=cast(Any, self.provider.chat_model),
                model_code=self.provider.model_code,
                max_attempts=self.provider.max_attempts,
                use_native_json_schema=True,
                tracing_enabled=self.provider.tracing_enabled,
            )
        if self.chat_model is None:
            raise ValueError("chat_model is required for an offline candidate-review run")
        return StructuredChatInvoker(
            chat_model=cast(Any, self.chat_model),
            model_code=self.model_code,
            max_attempts=1,
            use_native_json_schema=False,
        )

    async def run(self, case: EvaluationCase) -> CandidateReviewRunResult:
        return await self.run_scenario(build_scenario(case))

    async def run_scenario(self, scenario: Scenario) -> CandidateReviewRunResult:
        started_ns = time.monotonic_ns()
        adapter = CandidateReviewProviderAdapter(invoker=self._invoker())
        audits: list[InvocationAudit] = []
        candidate_set: CandidateSet | None = None
        reviews: tuple[CandidateReview, ...] = ()
        selection: CandidateSelection | None = None
        outcome: DeliberationOutcome | None = None
        failure_code = LlmAgentFailureCode.PROVIDER_UNAVAILABLE

        generated = await adapter.generate_candidates(
            envelope=scenario.constraint_envelope, pool=scenario.exercise_pool
        )
        audits.append(
            _audit(
                generated,
                role_code=LlmAgentRoleCode.TRAINING.value,
                phase_code="CANDIDATE_GENERATION",
            )
        )
        candidate_set = generated.output
        if candidate_set is not None:
            review_results = await adapter.review_both(
                envelope=scenario.constraint_envelope,
                pool=scenario.exercise_pool,
                candidate_set=candidate_set,
            )
            for role, result in zip(("RECOVERY", "FEASIBILITY"), review_results, strict=True):
                audits.append(_audit(result, role_code=role, phase_code="CROSS_REVIEW"))
            if all(result.output is not None for result in review_results):
                reviews = cast(
                    tuple[CandidateReview, CandidateReview],
                    tuple(result.output for result in review_results),
                )
                selected = await adapter.select_candidate(
                    candidate_set=candidate_set, reviews=cast(Any, reviews)
                )
                audits.append(
                    _audit(
                        selected,
                        role_code=LlmAgentRoleCode.COORDINATOR.value,
                        phase_code="SELECTION",
                    )
                )
                selection = selected.output
                if selection is not None:
                    try:
                        baseline = candidate_set.candidates[0].exercise_prescriptions
                        proposals = synthesize_proposals(
                            envelope=scenario.constraint_envelope,
                            pool=scenario.exercise_pool,
                            prescriptions=baseline,
                        )
                        coordinator_input = CoordinatorInput(
                            constraint_envelope=scenario.constraint_envelope,
                            exercise_pool=scenario.exercise_pool,
                            proposals=proposals,
                            repair_attempt=0,
                            repair_violation_codes=(),
                        )
                        outcome = materialize_selection(
                            candidate_set=candidate_set,
                            reviews=reviews,
                            selection=selection,
                            coordinator_input=coordinator_input,
                        )
                    except Exception:  # noqa: BLE001 - fail closed into shipped fallback
                        outcome = None
                        failure_code = LlmAgentFailureCode.DOMAIN_INVALID

        finalizer = SingleAgentRunner()
        if outcome is not None:
            plan = outcome.plan_spec
            final_input: StructuredAgentResult[SingleAgentPlanDraft] = (
                StructuredAgentResult.success(
                    SingleAgentPlanDraft.create(
                        envelope_hash=plan.envelope_hash,
                        pool_hash=plan.pool_hash,
                        action_code=plan.action_code,
                        requested_duration_minutes=plan.requested_duration_minutes,
                        estimated_duration_seconds=plan.estimated_duration_seconds,
                        exercise_prescriptions=plan.exercise_prescriptions,
                        decision_codes=plan.decision_codes,
                        public_summary_code=plan.public_summary_code,
                    )
                )
            )
        else:
            final_input = StructuredAgentResult.failed(
                code=failure_code,
                role_code=LlmAgentRoleCode.COORDINATOR,
                prompt_version="eval-candidate-review-v1",
                output_schema_version="candidate-selection-v1",
                model_code=self.provider.model_code if self.provider else self.model_code,
                attempt_count=1,
            )
        graph_result = finalizer._finalize(  # noqa: SLF001 - shared evaluation gate
            final_input,
            envelope=scenario.constraint_envelope,
            pool=scenario.exercise_pool,
        )
        graph_result = replace(
            graph_result,
            graph_version="eval-candidate-review-v1",
            invocation_audits=tuple(audits),
        )
        elapsed_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
        base_run = CaseRunResult(
            case=scenario.case,
            scenario=scenario,
            architecture_code=ARCHITECTURE_CANDIDATE_REVIEW,
            script=Script(),
            graph_result=graph_result,
            invocations=tuple(InvocationLog(a.role_code, "INITIAL", a.status_code) for a in audits),
            wall_clock_ms=elapsed_ms,
        )
        return CandidateReviewRunResult(base_run, candidate_set, reviews, selection, outcome)


__all__ = [
    "ARCHITECTURE_CANDIDATE_REVIEW",
    "CandidateReviewRunResult",
    "CandidateReviewRunner",
]
