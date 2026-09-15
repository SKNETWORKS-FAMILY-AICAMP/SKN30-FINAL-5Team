"""Structural, provider-boundary, and no-regression checks for architecture E."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, BaseMessage

from backend.app.integrations.llm_agents.models import LlmAgentRoleCode
from backend.tests.evaluation.dataset import EvaluationCase, load_dataset
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.runners.fake_chat import (
    Script,
    ScriptedChatModel,
    register_prompt_role,
)
from backend.tests.evaluation.runners.payloads import SingleAgentPayloadBuilder
from backend.tests.evaluation.runners.single_agent import (
    SINGLE_AGENT_RAG_PROMPT_VERSION,
    SingleAgentRunner,
)
from backend.tests.evaluation.runners.single_draft_review import SingleDraftReviewRunner
from backend.tests.evaluation.scenario import build_scenario
from backend.tests.evaluation.single_draft_review_provider import (
    FEASIBILITY_PROMPT_VERSION,
    PATCH_DECISION_SCHEMA_VERSION,
    RECOVERY_PROMPT_VERSION,
    REVIEW_SCHEMA_VERSION,
)

ReviewMode = Literal[
    "NO_CHANGE",
    "VALID_PATCH",
    "INVALID_FINAL_PATCH",
    "RECOVERY_FAILURE",
    "INVENTED_DECISION",
    "BOUNDARY_FAILURE",
]


@dataclass
class _ReviewChatModel:
    mode: ReviewMode = "NO_CHANGE"
    calls: list[str] = field(default_factory=list)

    def with_structured_output(self, schema: object, **_: object) -> _Runnable:
        del schema
        if self.mode == "BOUNDARY_FAILURE":
            raise RuntimeError("scripted critic boundary failure")
        return _Runnable(self)

    def answer(self, messages: list[BaseMessage]) -> dict[str, object]:
        content = messages[-1].content
        assert isinstance(content, str)
        body = json.loads(content)
        schema_version = body["output_schema_version"]
        prompt_version = body["prompt_version"]
        payload = body["input"]
        self.calls.append(prompt_version)
        parsing_error: str | None = None
        if schema_version == REVIEW_SCHEMA_VERSION:
            if self.mode == "RECOVERY_FAILURE" and prompt_version == RECOVERY_PROMPT_VERSION:
                parsed: dict[str, object] | None = None
                parsing_error = "scripted parse failure"
            elif self.mode in {"VALID_PATCH", "INVALID_FINAL_PATCH", "INVENTED_DECISION"} and (
                prompt_version == RECOVERY_PROMPT_VERSION
            ):
                prescriptions = payload["draft"]["exercise_prescriptions"]
                first = next(item for item in prescriptions if item["sets"] > 1)
                increase = 100000 if self.mode == "INVALID_FINAL_PATCH" else 1
                parsed = {
                    "adjustments": [
                        {
                            "adjustment_id": "RECOVERY_REST_01",
                            "prescription_sequence": first["sequence"],
                            "adjustment_code": "INCREASE_REST",
                            "value": first["rest_seconds_between_sets"] + increase,
                        }
                    ],
                    "review_codes": ["RECOVERY_CHANGE_RECOMMENDED"],
                }
            else:
                parsed = {"adjustments": [], "review_codes": ["NO_CHANGE"]}
        elif schema_version == PATCH_DECISION_SCHEMA_VERSION:
            submitted = payload["submitted_adjustment_ids"]
            accepted = list(submitted)
            if self.mode == "INVENTED_DECISION":
                accepted.append("INVENTED_PATCH")
            parsed = {
                "accepted_adjustment_ids": accepted,
                "rejected_adjustment_ids": [],
                "decision_codes": ["PATCHES_DECIDED"],
            }
        else:
            raise AssertionError(schema_version)
        raw = AIMessage(
            content="",
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        )
        return {"raw": raw, "parsed": parsed, "parsing_error": parsing_error}


@dataclass(frozen=True)
class _Runnable:
    model: _ReviewChatModel

    async def ainvoke(self, messages: list[BaseMessage], **_: object) -> dict[str, object]:
        return self.model.answer(messages)


def _runner(
    mode: ReviewMode = "NO_CHANGE", case: EvaluationCase = GRAPH_CASES[0]
) -> tuple[SingleDraftReviewRunner, _ReviewChatModel]:
    scenario = build_scenario(case)
    register_prompt_role(SINGLE_AGENT_RAG_PROMPT_VERSION, LlmAgentRoleCode.COORDINATOR)
    training = ScriptedChatModel(
        script=Script(),
        payload_builder=SingleAgentPayloadBuilder(
            envelope=scenario.constraint_envelope, pool=scenario.exercise_pool
        ),
    )
    reviews = _ReviewChatModel(mode=mode)
    return (
        SingleDraftReviewRunner(
            training_chat_model=cast(Any, training), review_chat_model=cast(Any, reviews)
        ),
        reviews,
    )


def test_no_change_reviews_preserve_valid_direct_draft() -> None:
    runner, model = _runner()
    scenario = build_scenario(GRAPH_CASES[0])

    result = asyncio.run(runner.run_scenario(scenario))

    assert result.base_run.has_plan is True
    assert result.base_run.used_fallback is False
    assert result.review_completed is True
    assert result.changed is False
    assert result.base_run.plan_spec == result.original_run.plan_spec
    assert result.preservation_codes == ("NO_CHANGE_KEEP_DRAFT",)
    assert model.calls == [RECOVERY_PROMPT_VERSION, FEASIBILITY_PROMPT_VERSION]


def test_valid_review_patch_passes_final_gate() -> None:
    runner, _ = _runner("VALID_PATCH")
    scenario = build_scenario(GRAPH_CASES[0])

    result = asyncio.run(runner.run_scenario(scenario))

    assert result.changed is True
    assert result.original_preserved is False
    assert result.applied_adjustment_count == 1
    assert result.base_run.used_fallback is False


def test_critic_failure_keeps_original_and_skips_coordinator() -> None:
    runner, model = _runner("RECOVERY_FAILURE")
    scenario = build_scenario(GRAPH_CASES[0])

    result = asyncio.run(runner.run_scenario(scenario))

    assert result.original_preserved is True
    assert result.preservation_codes == ("CRITIC_FAILED_KEEP_DRAFT",)
    assert result.base_run.plan_spec == result.original_run.plan_spec
    assert result.base_run.used_fallback is False
    assert model.calls == [RECOVERY_PROMPT_VERSION, FEASIBILITY_PROMPT_VERSION]


def test_coordinator_cannot_invent_patch_and_original_survives() -> None:
    runner, _ = _runner("INVENTED_DECISION")
    scenario = build_scenario(GRAPH_CASES[0])

    result = asyncio.run(runner.run_scenario(scenario))

    assert result.original_preserved is True
    assert result.preservation_codes == ("COORDINATOR_FAILED_KEEP_DRAFT",)
    assert result.base_run.plan_spec == result.original_run.plan_spec
    assert result.base_run.used_fallback is False


def test_patch_that_fails_final_duration_gate_cannot_degrade_original() -> None:
    runner, _ = _runner("INVALID_FINAL_PATCH")
    scenario = build_scenario(GRAPH_CASES[0])

    result = asyncio.run(runner.run_scenario(scenario))

    assert result.original_preserved is True
    assert result.preservation_codes == ("PATCH_FAILED_FINAL_GATE",)
    assert result.base_run.plan_spec == result.original_run.plan_spec
    assert result.base_run.used_fallback is False


def test_shared_baseline_draft_is_not_generated_twice() -> None:
    runner, _ = _runner()
    scenario = build_scenario(GRAPH_CASES[0])
    training_model = cast(ScriptedChatModel, runner.training_chat_model)
    original = asyncio.run(
        SingleAgentRunner(chat_model=training_model).run_scenario(scenario, Script())
    )
    assert len(training_model.calls) == 1

    result = asyncio.run(runner.run_scenario(scenario, original_run=original))

    assert len(training_model.calls) == 1
    assert result.original_run is original


def test_local_critic_boundary_failure_keeps_original() -> None:
    runner, _ = _runner("BOUNDARY_FAILURE")
    scenario = build_scenario(GRAPH_CASES[0])

    result = asyncio.run(runner.run_scenario(scenario))

    assert result.original_preserved is True
    assert result.preservation_codes == ("CRITIC_FAILED_KEEP_DRAFT",)
    assert result.base_run.plan_spec == result.original_run.plan_spec


def test_catalog_body_focus_codes_pass_privacy_guard() -> None:
    case = next(
        item for item in load_dataset("heldout_cases_v2").cases if item.case_id == "SQ-HELD-001"
    )
    runner, _ = _runner(case=case)

    result = asyncio.run(runner.run_scenario(build_scenario(case)))

    assert result.base_run.has_plan is True
    assert result.review_completed is True
