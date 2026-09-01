from backend.app.modules.decisions.ports import NarrationCompletion, NarrationPrompt
from backend.app.modules.weekly_reports.narration import WeeklyReportNarrationAgent
from backend.app.modules.weekly_reports.ports import WeeklyReportNarrationInput


class RecordingProvider:
    def __init__(self, completion: NarrationCompletion) -> None:
        self.completion = completion
        self.prompts: list[NarrationPrompt] = []

    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        self.prompts.append(prompt)
        return self.completion


class FailingProvider:
    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        del prompt
        raise TimeoutError


def _report() -> WeeklyReportNarrationInput:
    return WeeklyReportNarrationInput(
        input_snapshot={
            "official_outcome_counts": {
                "completed": 1,
                "partial": 1,
                "not_completed": 1,
                "stopped_for_safety": 1,
            },
            "not_completed_reason_counts": {"TIME_SHORTAGE": 1},
        },
        objective_metrics={
            "completion_rate": 0.25,
            "persistence_rate": 0.5,
            "negotiation_success_rate": 0.5,
        },
        template_summary="template summary",
        template_decision_summary="template decision",
        template_next_action="template action",
    )


def test_valid_provider_result_is_used_without_an_external_call() -> None:
    provider = RecordingProvider(
        NarrationCompletion(
            model_code="test-model",
            sentences={
                "SUMMARY": "이번 주 기록의 흐름을 차분히 살펴보았어요.",
                "DECISION_SUMMARY": "조정과 미완료 사유를 함께 반영했어요.",
                "NEXT_ACTION": "다음 주에는 가능한 일정부터 가볍게 이어가 보세요.",
            },
        )
    )

    result = WeeklyReportNarrationAgent(provider).interpret(_report())

    assert result.source_code == "LLM"
    assert result.model_code == "test-model"
    assert result.summary == "이번 주 기록의 흐름을 차분히 살펴보았어요."
    assert len(provider.prompts) == 1
    assert provider.prompts[0].payload == {
        "input_snapshot": _report().input_snapshot,
        "objective_metrics": _report().objective_metrics,
    }
    assert "user_id" not in str(provider.prompts[0].payload)


def test_numeric_or_incomplete_provider_output_uses_template_fallback() -> None:
    provider = RecordingProvider(
        NarrationCompletion(
            model_code="test-model",
            sentences={
                "SUMMARY": "이번 주에 4회를 완료했어요.",
                "DECISION_SUMMARY": "조정 결과를 반영했어요.",
                "NEXT_ACTION": "가능한 시간부터 시작해 보세요.",
            },
        )
    )

    result = WeeklyReportNarrationAgent(provider).interpret(_report())

    assert result.source_code == "TEMPLATE"
    assert result.fallback_reason_code == "LLM_OUTPUT_REJECTED"
    assert result.summary == "template summary"


def test_provider_timeout_uses_template_fallback() -> None:
    result = WeeklyReportNarrationAgent(FailingProvider()).interpret(_report())

    assert result.source_code == "TEMPLATE"
    assert result.fallback_reason_code == "LLM_PROVIDER_FAILED"
    assert result.summary == "template summary"
