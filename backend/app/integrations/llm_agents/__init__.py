"""Provider-neutral LangChain adapters for V3 specialists and coordinator."""

from backend.app.integrations.llm_agents.coordinator import LangChainCoordinatorAdapter
from backend.app.integrations.llm_agents.models import (
    LlmAgentFailure,
    LlmAgentFailureCode,
    LlmAgentRoleCode,
    LlmInvocationTelemetry,
    StructuredAgentResult,
)
from backend.app.integrations.llm_agents.openai import (
    build_openai_demo_chat_model,
    build_openai_shadow_chat_model,
    openai_demo_gates_ready,
    openai_shadow_gates_ready,
)
from backend.app.integrations.llm_agents.provider import (
    StructuredChatInvoker,
    build_structured_chat_invoker,
)
from backend.app.integrations.llm_agents.specialists import (
    FeasibilityAgentAdapter,
    LangChainSpecialistAdapter,
    RecoveryAgentAdapter,
    TrainingAgentAdapter,
)

__all__ = [
    "FeasibilityAgentAdapter",
    "LangChainCoordinatorAdapter",
    "LangChainSpecialistAdapter",
    "LlmAgentFailure",
    "LlmAgentFailureCode",
    "LlmAgentRoleCode",
    "LlmInvocationTelemetry",
    "RecoveryAgentAdapter",
    "StructuredAgentResult",
    "StructuredChatInvoker",
    "TrainingAgentAdapter",
    "build_structured_chat_invoker",
    "build_openai_demo_chat_model",
    "build_openai_shadow_chat_model",
    "openai_demo_gates_ready",
    "openai_shadow_gates_ready",
]
