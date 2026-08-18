import json
import logging
from typing import Any

import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.integrations.llm_provider import (
    OpenAiNarrationProvider,
    UnavailableNarrationProvider,
    build_narration_provider,
)
from backend.app.modules.decisions.ports import (
    NarrationPrompt,
    NarrationProviderFailedError,
    NarrationProviderUnavailableError,
)

API_KEY = "test-key-not-a-real-secret"
PROMPT = NarrationPrompt(
    prompt_version="decision-explanation-prompt-v1",
    instruction="안내 문구만 작성한다.",
    slot_codes=("SUMMARY",),
    payload={"action_code": "KEEP", "safety_status_code": "PASS"},
)


class RecordingTransport:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._payload = payload if payload is not None else _responses_payload()

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "body": body,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self._payload


class RaisingTransport:
    def post_json(self, **_: Any) -> dict[str, Any]:
        raise NarrationProviderFailedError("TIMEOUT")


def _responses_payload(sentences: dict[str, str] | None = None) -> dict[str, Any]:
    content = {"sentences": sentences if sentences is not None else {"SUMMARY": "좋습니다."}}
    return {
        "model": "gpt-test-1",
        "output": [{"content": [{"type": "output_text", "text": json.dumps(content)}]}],
    }


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "database_url": "postgresql+psycopg://test:test@localhost/test",
    }
    values.update(overrides)
    return Settings(**values)


def test_narration_is_unavailable_by_default() -> None:
    provider = build_narration_provider(_settings())

    assert isinstance(provider, UnavailableNarrationProvider)
    with pytest.raises(NarrationProviderUnavailableError):
        provider.narrate(PROMPT)


def test_enabling_openai_without_an_api_key_is_rejected_at_startup() -> None:
    with pytest.raises(ValidationError):
        _settings(llm_enabled=True, llm_provider_code="OPENAI")


def test_enabled_settings_build_the_openai_adapter() -> None:
    transport = RecordingTransport()
    provider = build_narration_provider(
        _settings(
            llm_enabled=True,
            llm_provider_code="OPENAI",
            openai_api_key=API_KEY,
            llm_model_code="gpt-test-1",
            llm_timeout_seconds=1.5,
        ),
        transport=transport,
    )

    assert isinstance(provider, OpenAiNarrationProvider)
    completion = provider.narrate(PROMPT)

    call = transport.calls[0]
    assert call["url"] == "https://api.openai.com/v1/responses"
    assert call["headers"]["Authorization"] == f"Bearer {API_KEY}"
    assert call["timeout_seconds"] == 1.5
    assert call["body"]["model"] == "gpt-test-1"
    assert completion.model_code == "gpt-test-1"
    assert completion.sentences == {"SUMMARY": "좋습니다."}


def test_request_body_carries_only_the_prompt_payload() -> None:
    transport = RecordingTransport()
    provider = OpenAiNarrationProvider(
        api_key=API_KEY, model_code="gpt-test-1", transport=transport
    )

    provider.narrate(PROMPT)

    body = transport.calls[0]["body"]
    sent = json.loads(body["input"])
    assert sent["decision"] == PROMPT.payload
    assert sent["prompt_version"] == PROMPT.prompt_version
    # 인증 정보는 헤더에만 있고 본문에는 남지 않는다.
    assert API_KEY not in json.dumps(body, ensure_ascii=False)


def test_transport_failure_is_raised_as_a_provider_failure() -> None:
    provider = OpenAiNarrationProvider(
        api_key=API_KEY, model_code="gpt-test-1", transport=RaisingTransport()
    )

    with pytest.raises(NarrationProviderFailedError):
        provider.narrate(PROMPT)


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "gpt-test-1", "output": []},
        {"model": "gpt-test-1", "output_text": "not json"},
        {"model": "gpt-test-1", "output_text": json.dumps({"unexpected": {}})},
        {"model": "gpt-test-1", "output_text": json.dumps(["array"])},
    ],
)
def test_unusable_provider_payloads_are_rejected(payload: dict[str, Any]) -> None:
    provider = OpenAiNarrationProvider(
        api_key=API_KEY,
        model_code="gpt-test-1",
        transport=RecordingTransport(payload=payload),
    )

    with pytest.raises(NarrationProviderFailedError):
        provider.narrate(PROMPT)


def test_non_string_sentences_are_dropped_before_validation() -> None:
    provider = OpenAiNarrationProvider(
        api_key=API_KEY,
        model_code="gpt-test-1",
        transport=RecordingTransport(
            payload={
                "model": "gpt-test-1",
                "output_text": json.dumps({"sentences": {"SUMMARY": "좋습니다.", "BAD": 12}}),
            }
        ),
    )

    completion = provider.narrate(PROMPT)

    assert completion.sentences == {"SUMMARY": "좋습니다."}


def test_missing_api_key_falls_back_to_the_null_provider_without_logging_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(
        llm_enabled=True, llm_provider_code="OPENAI", openai_api_key=API_KEY
    ).model_copy(update={"openai_api_key": None})

    with caplog.at_level(logging.WARNING):
        provider = build_narration_provider(settings)

    assert isinstance(provider, UnavailableNarrationProvider)
    assert API_KEY not in caplog.text
