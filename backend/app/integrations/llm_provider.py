"""Optional LLM narration adapters.

The adapter only rewrites approved decision codes into sentences. It never receives the
decision itself, never sees direct identifiers or raw health records, and any failure is
surfaced as an exception so the caller can use its reviewed template text.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Final, Protocol

from backend.app.core.config import Settings
from backend.app.modules.decisions.ports import (
    NarrationCompletion,
    NarrationPrompt,
    NarrationProviderFailedError,
    NarrationProviderPort,
    NarrationProviderUnavailableError,
)

logger = logging.getLogger("backend.integrations.llm")

_RESPONSES_PATH: Final = "/responses"
_MAX_RESPONSE_BYTES: Final = 32_768


class UnavailableNarrationProvider:
    """Null object used whenever narration is disabled or unconfigured."""

    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        del prompt
        raise NarrationProviderUnavailableError


class JsonHttpTransport(Protocol):
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class UrllibJsonTransport:
    """Standard-library JSON transport so the adapter adds no runtime dependency."""

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        request = urllib.request.Request(  # noqa: S310 - url is an https setting value
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # Provider error text can echo the request, so only the class name is kept.
            raise NarrationProviderFailedError(type(exc).__name__) from None
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise NarrationProviderFailedError("RESPONSE_TOO_LARGE")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise NarrationProviderFailedError("RESPONSE_NOT_JSON") from None
        if not isinstance(decoded, dict):
            raise NarrationProviderFailedError("RESPONSE_NOT_OBJECT")
        return decoded


def _output_text(payload: dict[str, Any]) -> str:
    """Read the model text from an OpenAI Responses payload without trusting its shape."""

    direct = payload.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    chunks: list[str] = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if not chunks:
        raise NarrationProviderFailedError("RESPONSE_TEXT_MISSING")
    return "".join(chunks)


@dataclass(frozen=True, slots=True)
class OpenAiNarrationProvider:
    """OpenAI Responses adapter for optional narration sentences.

    The request body carries the codes-only payload it is given. The API key is read from
    settings, is never logged, and no request or response content is written to logs.
    """

    api_key: str
    model_code: str
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 3.0
    max_output_tokens: int = 400
    transport: JsonHttpTransport = UrllibJsonTransport()

    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        body: dict[str, Any] = {
            "model": self.model_code,
            "max_output_tokens": self.max_output_tokens,
            "instructions": prompt.instruction,
            "input": json.dumps(
                {
                    "prompt_version": prompt.prompt_version,
                    "slot_codes": list(prompt.slot_codes),
                    "decision": prompt.payload,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "text": {"format": {"type": "json_object"}},
        }
        payload = self.transport.post_json(
            url=f"{self.base_url}{_RESPONSES_PATH}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            body=body,
            timeout_seconds=self.timeout_seconds,
        )
        try:
            content = json.loads(_output_text(payload))
        except json.JSONDecodeError:
            raise NarrationProviderFailedError("OUTPUT_NOT_JSON") from None
        if not isinstance(content, dict):
            raise NarrationProviderFailedError("OUTPUT_NOT_OBJECT")
        sentences = content.get("sentences")
        if not isinstance(sentences, dict):
            raise NarrationProviderFailedError("OUTPUT_SENTENCES_MISSING")
        returned_model = payload.get("model")
        return NarrationCompletion(
            model_code=returned_model if isinstance(returned_model, str) else self.model_code,
            sentences={
                str(key): value for key, value in sentences.items() if isinstance(value, str)
            },
        )


def build_narration_provider(
    settings: Settings,
    *,
    transport: JsonHttpTransport | None = None,
) -> NarrationProviderPort:
    """Return the configured provider, or the null object when narration is off."""

    if not settings.llm_enabled or settings.llm_provider_code != "OPENAI":
        return UnavailableNarrationProvider()
    api_key = settings.openai_api_key
    if api_key is None:
        # Settings validation blocks this combination; stay fail-closed if it is bypassed.
        logger.warning("llm_provider_disabled", extra={"reason_code": "API_KEY_MISSING"})
        return UnavailableNarrationProvider()
    return OpenAiNarrationProvider(
        api_key=api_key.get_secret_value(),
        model_code=settings.llm_model_code,
        base_url=settings.llm_api_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_output_tokens=settings.llm_max_output_tokens,
        transport=transport if transport is not None else UrllibJsonTransport(),
    )


__all__ = [
    "JsonHttpTransport",
    "OpenAiNarrationProvider",
    "UnavailableNarrationProvider",
    "UrllibJsonTransport",
    "build_narration_provider",
]
