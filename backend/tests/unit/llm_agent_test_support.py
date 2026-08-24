"""Network-free LangChain chat models for the approved V3 domain contracts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class ToolCallingFakeChatModel(FakeMessagesListChatModel):
    """Scripted fake that still uses BaseChatModel.with_structured_output parsing."""

    invocation_count: int = 0
    seen_messages: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tool_names: list[tuple[str, ...]] = Field(default_factory=list)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        self.bound_tool_names.append(tuple(_tool_name(tool) for tool in tools))
        return self.bind(tools=tools, tool_choice=tool_choice, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.invocation_count += 1
        self.seen_messages.append(messages)
        return super()._generate(
            messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs,
        )


class RaisingStructuredChatModel(FakeMessagesListChatModel):
    """Provider-neutral failure fake with no network behavior."""

    failure_kind: Literal["timeout", "unavailable"]
    raw_error_text: str
    invocation_count: int = 0

    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[Any, Any]:
        del schema, include_raw, kwargs

        def raise_error(_: object) -> object:
            self.invocation_count += 1
            if self.failure_kind == "timeout":
                raise TimeoutError(self.raw_error_text)
            raise ConnectionError(self.raw_error_text)

        return RunnableLambda(raise_error)


def _tool_name(tool: dict[str, Any] | type | Callable[..., Any] | BaseTool) -> str:
    if isinstance(tool, type):
        return tool.__name__
    if isinstance(tool, dict):
        title = tool.get("title") or tool.get("name")
        return title if isinstance(title, str) else "SCHEMA"
    return str(getattr(tool, "name", "SCHEMA"))


def tool_response(
    schema: type[BaseModel],
    output: BaseModel | dict[str, object],
    call_id: int,
) -> AIMessage:
    arguments = output.model_dump(mode="json") if isinstance(output, BaseModel) else output
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": schema.__name__,
                "args": arguments,
                "id": f"call-{call_id}",
                "type": "tool_call",
            }
        ],
    )


__all__ = [
    "RaisingStructuredChatModel",
    "ToolCallingFakeChatModel",
    "tool_response",
]
