"""Free provider-boundary checks for the ADR-0025 experiment."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage

from backend.app.domain.agents.v3_contracts import CoordinatorInput
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.tests.evaluation.candidate_review import (
    CandidateReview,
    CandidateSelection,
    CandidateSet,
    materialize_selection,
)
from backend.tests.evaluation.candidate_review_provider import (
    CANDIDATE_GENERATION_SCHEMA_VERSION,
    CANDIDATE_REVIEW_SCHEMA_VERSION,
    CANDIDATE_SELECTION_SCHEMA_VERSION,
    CandidateReviewProviderAdapter,
)
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.planner import compose_prescriptions
from backend.tests.evaluation.runners.candidate_review import CandidateReviewRunner
from backend.tests.evaluation.runners.fake_chat import Script
from backend.tests.evaluation.runners.run_multi_agent import MultiAgentRunner
from backend.tests.evaluation.scenario import Scenario, build_scenario


@dataclass
class _ExperimentalChatModel:
    training_payload: dict[str, object]
    training_payloads: list[dict[str, object]] | None = None
    calls: list[str] = field(default_factory=list)

    def with_structured_output(self, schema: object, **_: object) -> _Runnable:
        del schema
        return _Runnable(self)

    def answer(self, messages: list[BaseMessage]) -> dict[str, object]:
        content = messages[-1].content
        assert isinstance(content, str)
        body = json.loads(content)
        schema_version = body["output_schema_version"]
        request = body["input"]
        self.calls.append(schema_version)
        if schema_version == CANDIDATE_GENERATION_SCHEMA_VERSION:
            if self.training_payloads:
                parsed = self.training_payloads.pop(0)
            else:
                parsed = self.training_payload
        elif schema_version == CANDIDATE_REVIEW_SCHEMA_VERSION:
            codes = [item["candidate_code"] for item in request["candidate_set"]["candidates"]]
            parsed = {
                "ranked_candidate_codes": list(reversed(codes)),
                "adjustments": [],
                "review_codes": ["CANDIDATES_REVIEWED"],
            }
        elif schema_version == CANDIDATE_SELECTION_SCHEMA_VERSION:
            parsed = {
                "selected_candidate_code": "RECOVERY_FOCUSED",
                "accepted_adjustment_ids": [],
                "decision_codes": ["CROSS_REVIEW_CONSIDERED"],
            }
        else:
            raise AssertionError(schema_version)
        raw = AIMessage(
            content="",
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        )
        return {"raw": raw, "parsed": parsed, "parsing_error": None}


@dataclass(frozen=True)
class _Runnable:
    model: _ExperimentalChatModel

    async def ainvoke(self, messages: list[BaseMessage], **_: object) -> dict[str, object]:
        return self.model.answer(messages)


def _training_payload(*, duplicate: bool = False) -> tuple[dict[str, object], Scenario]:
    scenario = build_scenario(GRAPH_CASES[0])
    base = compose_prescriptions(scenario.constraint_envelope, scenario.exercise_pool)
    first, *remaining = base
    alternative = (
        first.model_copy(update={"rest_seconds_between_sets": first.rest_seconds_between_sets + 1}),
        *remaining,
    )
    if duplicate:
        alternative = base
    return (
        {
            "candidates": [
                {
                    "candidate_code": "GOAL_FOCUSED",
                    "objective_code": "GOAL_PRESERVATION",
                    "exercise_prescriptions": [item.model_dump(mode="json") for item in base],
                },
                {
                    "candidate_code": "RECOVERY_FOCUSED",
                    "objective_code": "RECOVERY_LOAD",
                    "exercise_prescriptions": [
                        item.model_dump(mode="json") for item in alternative
                    ],
                },
            ]
        },
        scenario,
    )


def test_provider_adapter_executes_generate_review_select_without_plan_rewrite() -> None:
    payload, scenario = _training_payload()
    model = _ExperimentalChatModel(training_payload=payload)
    adapter = CandidateReviewProviderAdapter(
        invoker=StructuredChatInvoker(
            chat_model=cast(Any, model),
            model_code="eval-candidate-scripted-v1",
            max_attempts=1,
        )
    )

    async def execute() -> tuple[
        CandidateSet, tuple[CandidateReview, CandidateReview], CandidateSelection | None
    ]:
        generated = await adapter.generate_candidates(
            envelope=scenario.constraint_envelope, pool=scenario.exercise_pool
        )
        assert generated.output is not None
        review_results = await adapter.review_both(
            envelope=scenario.constraint_envelope,
            pool=scenario.exercise_pool,
            candidate_set=generated.output,
        )
        recovery = review_results[0].output
        feasibility = review_results[1].output
        assert recovery is not None
        assert feasibility is not None
        reviews = (recovery, feasibility)
        selected = await adapter.select_candidate(candidate_set=generated.output, reviews=reviews)
        return generated.output, reviews, selected.output

    candidate_set, reviews, selection = asyncio.run(execute())
    assert selection is not None
    production_run = asyncio.run(MultiAgentRunner().run_scenario(scenario, Script()))
    coordinator_input = CoordinatorInput(
        constraint_envelope=scenario.constraint_envelope,
        exercise_pool=scenario.exercise_pool,
        proposals=production_run.graph_result.round_one_proposals,
        repair_attempt=0,
        repair_violation_codes=(),
    )
    outcome = materialize_selection(
        candidate_set=candidate_set,
        reviews=reviews,
        selection=selection,
        coordinator_input=coordinator_input,
    )
    chosen = next(
        item
        for item in candidate_set.candidates
        if item.candidate_code == selection.selected_candidate_code
    )

    assert outcome.plan_spec.exercise_prescriptions == chosen.exercise_prescriptions
    assert model.calls == [
        CANDIDATE_GENERATION_SCHEMA_VERSION,
        CANDIDATE_REVIEW_SCHEMA_VERSION,
        CANDIDATE_REVIEW_SCHEMA_VERSION,
        CANDIDATE_SELECTION_SCHEMA_VERSION,
    ]


def test_provider_adapter_rejects_duplicate_candidate_prescriptions() -> None:
    payload, scenario = _training_payload(duplicate=True)
    adapter = CandidateReviewProviderAdapter(
        invoker=StructuredChatInvoker(
            chat_model=cast(Any, _ExperimentalChatModel(training_payload=payload)),
            model_code="eval-candidate-scripted-v1",
            max_attempts=1,
        )
    )

    result = asyncio.run(
        adapter.generate_candidates(
            envelope=scenario.constraint_envelope, pool=scenario.exercise_pool
        )
    )

    assert result.output is None
    assert result.failure is not None


def test_candidate_review_runner_records_intervention_and_uses_common_gate() -> None:
    payload, scenario = _training_payload()
    model = _ExperimentalChatModel(training_payload=payload)

    result = asyncio.run(CandidateReviewRunner(chat_model=model).run_scenario(scenario))

    assert result.base_run.has_plan is True
    assert result.base_run.used_fallback is False
    assert result.selection_changed is True
    assert result.applied_adjustment_count == 0
    assert [audit.phase_code for audit in result.base_run.graph_result.invocation_audits] == [
        "CANDIDATE_GENERATION",
        "CROSS_REVIEW",
        "CROSS_REVIEW",
        "SELECTION",
    ]
    assert len(model.calls) == 4


def test_runner_retries_only_training_when_first_candidate_fails_common_gate() -> None:
    valid, scenario = _training_payload()
    invalid = json.loads(json.dumps(valid))
    invalid["candidates"][0]["exercise_prescriptions"][0]["exercise_id"] = str(uuid4())
    model = _ExperimentalChatModel(
        training_payload=valid,
        training_payloads=[invalid, valid],
    )

    result = asyncio.run(
        CandidateReviewRunner(chat_model=model, max_attempts=2).run_scenario(scenario)
    )

    assert result.base_run.used_fallback is False
    assert model.calls == [
        CANDIDATE_GENERATION_SCHEMA_VERSION,
        CANDIDATE_GENERATION_SCHEMA_VERSION,
        CANDIDATE_REVIEW_SCHEMA_VERSION,
        CANDIDATE_REVIEW_SCHEMA_VERSION,
        CANDIDATE_SELECTION_SCHEMA_VERSION,
    ]
    assert result.base_run.graph_result.invocation_audits[0].attempt_count == 2


def test_runner_stops_before_reviews_when_both_training_attempts_are_invalid() -> None:
    valid, scenario = _training_payload()
    invalid = json.loads(json.dumps(valid))
    invalid["candidates"][0]["exercise_prescriptions"][0]["exercise_id"] = str(uuid4())
    model = _ExperimentalChatModel(
        training_payload=invalid,
        training_payloads=[invalid, invalid],
    )

    result = asyncio.run(
        CandidateReviewRunner(chat_model=model, max_attempts=2).run_scenario(scenario)
    )

    assert result.base_run.used_fallback is True
    assert model.calls == [
        CANDIDATE_GENERATION_SCHEMA_VERSION,
        CANDIDATE_GENERATION_SCHEMA_VERSION,
    ]
    assert len(result.base_run.graph_result.invocation_audits) == 1
    assert result.base_run.graph_result.invocation_audits[0].attempt_count == 2
