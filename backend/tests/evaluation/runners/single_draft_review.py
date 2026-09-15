"""Architecture E runner: B draft, parallel critics, bounded patching."""

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
from backend.tests.evaluation.single_draft_review import (
    DraftReview,
    DraftReviewOutcome,
    PatchDecision,
    materialize_reviewed_draft,
)
from backend.tests.evaluation.single_draft_review_provider import (
    SingleDraftReviewProviderAdapter,
)

ARCHITECTURE_SINGLE_DRAFT_REVIEW = "SINGLE_DRAFT_PARALLEL_CRITICS"
EVAL_MODEL_CODE = "eval-single-draft-review-scripted-v1"


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
class SingleDraftReviewRunResult:
    base_run: CaseRunResult
    original_run: CaseRunResult
    draft: SingleAgentPlanDraft | None
    reviews: tuple[DraftReview, ...]
    decision: PatchDecision | None
    outcome: DraftReviewOutcome | None
    review_completed: bool
    original_preserved: bool
    preservation_codes: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.outcome and self.outcome.changed and not self.original_preserved)

    @property
    def specialist_disagreement(self) -> bool:
        return bool(self.outcome and self.outcome.specialist_disagreement)

    @property
    def applied_adjustment_count(self) -> int:
        return len(self.outcome.applied_adjustment_ids) if self.changed and self.outcome else 0


@dataclass(slots=True)
class SingleDraftReviewRunner:
    provider: ProviderContext | None = None
    training_chat_model: object | None = None
    review_chat_model: object | None = None
    model_code: str = EVAL_MODEL_CODE
    max_attempts: int = 1

    def _review_invoker(self) -> StructuredChatInvoker:
        if self.provider is not None:
            return StructuredChatInvoker(
                chat_model=cast(Any, self.provider.chat_model),
                model_code=self.provider.model_code,
                max_attempts=self.provider.max_attempts,
                use_native_json_schema=True,
                tracing_enabled=self.provider.tracing_enabled,
            )
        if self.review_chat_model is None:
            raise ValueError("review_chat_model is required for an offline E run")
        return StructuredChatInvoker(
            chat_model=cast(Any, self.review_chat_model),
            model_code=self.model_code,
            max_attempts=self.max_attempts,
            use_native_json_schema=False,
        )

    async def run(self, case: EvaluationCase) -> SingleDraftReviewRunResult:
        return await self.run_scenario(build_scenario(case))

    async def run_scenario(
        self, scenario: Scenario, original_run: CaseRunResult | None = None
    ) -> SingleDraftReviewRunResult:
        started_ns = time.monotonic_ns()
        training = SingleAgentRunner(
            provider=self.provider,
            chat_model=self.training_chat_model,
        )
        original = original_run or await training.run_scenario(scenario, Script())
        if original.scenario != scenario:
            raise ValueError("shared original run belongs to another scenario")
        training_audits = tuple(
            replace(audit, role_code="TRAINING", phase_code="DRAFT_GENERATION")
            for audit in original.graph_result.invocation_audits
        )
        audits = list(training_audits)
        draft: SingleAgentPlanDraft | None = None
        reviews: tuple[DraftReview, ...] = ()
        decision: PatchDecision | None = None
        outcome: DraftReviewOutcome | None = None
        review_completed = False
        original_preserved = False
        preservation_codes: list[str] = []
        chosen_graph = original.graph_result

        plan = original.plan_spec
        if plan is not None and not original.used_fallback:
            draft = SingleAgentPlanDraft.create(
                envelope_hash=plan.envelope_hash,
                pool_hash=plan.pool_hash,
                action_code=plan.action_code,
                requested_duration_minutes=plan.requested_duration_minutes,
                estimated_duration_seconds=plan.estimated_duration_seconds,
                exercise_prescriptions=plan.exercise_prescriptions,
                decision_codes=plan.decision_codes,
                public_summary_code=plan.public_summary_code,
            )
            adapter = SingleDraftReviewProviderAdapter(invoker=self._review_invoker())
            review_results = await adapter.review_both(draft=draft, pool=scenario.exercise_pool)
            for role, result in zip(("RECOVERY", "FEASIBILITY"), review_results, strict=True):
                audits.append(_audit(result, role_code=role, phase_code="DRAFT_REVIEW"))
            if all(result.output is not None for result in review_results):
                reviews = cast(
                    tuple[DraftReview, DraftReview],
                    tuple(result.output for result in review_results),
                )
                selected = await adapter.select(draft=draft, reviews=reviews)
                audits.append(
                    _audit(
                        selected,
                        role_code=LlmAgentRoleCode.COORDINATOR.value,
                        phase_code="PATCH_SELECTION",
                    )
                )
                decision = selected.output
                if decision is not None:
                    review_completed = True
                    proposals = synthesize_proposals(
                        envelope=scenario.constraint_envelope,
                        pool=scenario.exercise_pool,
                        prescriptions=draft.exercise_prescriptions,
                    )
                    coordinator_input = CoordinatorInput(
                        constraint_envelope=scenario.constraint_envelope,
                        exercise_pool=scenario.exercise_pool,
                        proposals=proposals,
                        repair_attempt=0,
                        repair_violation_codes=(),
                    )
                    try:
                        outcome = materialize_reviewed_draft(
                            draft=draft,
                            reviews=reviews,
                            decision=decision,
                            coordinator_input=coordinator_input,
                        )
                    except Exception:  # noqa: BLE001 - preserve the valid draft
                        original_preserved = True
                        preservation_codes.append("PATCH_MATERIALIZATION_REJECTED")
                    else:
                        if not outcome.changed:
                            preservation_codes.append("NO_CHANGE_KEEP_DRAFT")
                        else:
                            reviewed = outcome.plan_spec
                            final_input = StructuredAgentResult.success(
                                SingleAgentPlanDraft.create(
                                    envelope_hash=reviewed.envelope_hash,
                                    pool_hash=reviewed.pool_hash,
                                    action_code=reviewed.action_code,
                                    requested_duration_minutes=reviewed.requested_duration_minutes,
                                    estimated_duration_seconds=reviewed.estimated_duration_seconds,
                                    exercise_prescriptions=reviewed.exercise_prescriptions,
                                    decision_codes=reviewed.decision_codes,
                                    public_summary_code=reviewed.public_summary_code,
                                )
                            )
                            gated = training._finalize(  # noqa: SLF001
                                final_input,
                                envelope=scenario.constraint_envelope,
                                pool=scenario.exercise_pool,
                            )
                            if gated.used_fallback or gated.compiled_plan is None:
                                original_preserved = True
                                preservation_codes.append("PATCH_FAILED_FINAL_GATE")
                            else:
                                chosen_graph = gated
                else:
                    original_preserved = True
                    preservation_codes.append("COORDINATOR_FAILED_KEEP_DRAFT")
            else:
                original_preserved = True
                preservation_codes.append("CRITIC_FAILED_KEEP_DRAFT")

        chosen_graph = replace(
            chosen_graph,
            graph_version="eval-single-draft-parallel-critics-v1",
            invocation_audits=tuple(audits),
        )
        elapsed_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
        final_run = CaseRunResult(
            case=scenario.case,
            scenario=scenario,
            architecture_code=ARCHITECTURE_SINGLE_DRAFT_REVIEW,
            script=Script(),
            graph_result=chosen_graph,
            invocations=tuple(
                InvocationLog(audit.role_code, "INITIAL", audit.status_code) for audit in audits
            ),
            wall_clock_ms=elapsed_ms,
        )
        return SingleDraftReviewRunResult(
            base_run=final_run,
            original_run=original,
            draft=draft,
            reviews=reviews,
            decision=decision,
            outcome=outcome,
            review_completed=review_completed,
            original_preserved=original_preserved,
            preservation_codes=tuple(preservation_codes),
        )


__all__ = [
    "ARCHITECTURE_SINGLE_DRAFT_REVIEW",
    "SingleDraftReviewRunResult",
    "SingleDraftReviewRunner",
]
