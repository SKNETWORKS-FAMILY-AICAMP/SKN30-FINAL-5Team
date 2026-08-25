from __future__ import annotations

import ast
import inspect
import json
import socket
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    RecoveryCeiling,
    SpecialistAgentInput,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
)
from backend.app.integrations.llm_agents.coordinator import LangChainCoordinatorAdapter
from backend.app.integrations.llm_agents.payload import (
    assert_private_machine_payload,
    project_exercise_pool,
)
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.app.integrations.llm_agents.specialists import TrainingAgentAdapter
from backend.app.integrations.llm_provider import (
    UnavailableNarrationProvider,
    build_narration_provider,
)
from backend.tests.unit.llm_agent_test_support import (
    ToolCallingFakeChatModel,
    tool_response,
)
from backend.tests.unit.test_v3_agent_contracts import envelope, pool, proposal

FORBIDDEN_PROMPT_FIELDS = {
    "user_id",
    "email",
    "name",
    "date",
    "created_at",
    "check_in_text",
    "pain",
    "pain_area",
    "pain_intensity",
    "severity",
    "intensity_score",
    "raw_health",
    "raw_wearable",
    "calendar_text",
    "retrieval_metadata",
    "similarity_score",
    "similarity_scores",
    "vector_ranked_exercise_ids",
}


def _field_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            names.add(str(key).lower())
            names.update(_field_names(nested))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            names.update(_field_names(nested))
    return names


def _successful_training_adapter() -> tuple[TrainingAgentAdapter, ToolCallingFakeChatModel]:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    output = proposal(SpecialistAgentTypeCode.TRAINING, current_envelope, current_pool)
    model = ToolCallingFakeChatModel(responses=[tool_response(SpecialistAgentProposal, output, 1)])
    adapter = TrainingAgentAdapter(
        invoker=StructuredChatInvoker(chat_model=model, model_code="fake-model-v1")
    )
    return adapter, model


def test_prompt_payload_excludes_identifiers_raw_health_and_retrieval_lineage() -> None:
    adapter, model = _successful_training_adapter()
    current_envelope = envelope()

    result = adapter.propose(
        constraint_envelope=current_envelope,
        exercise_pool=pool(current_envelope),
    )

    assert result.succeeded
    human_message = next(
        message for message in model.seen_messages[0] if isinstance(message, HumanMessage)
    )
    assert isinstance(human_message.content, str)
    payload = json.loads(human_message.content)["input"]
    assert _field_names(payload).isdisjoint(FORBIDDEN_PROMPT_FIELDS)
    serialized = json.dumps(payload, sort_keys=True).lower()
    for forbidden in (
        "collection_name",
        "source_reference_codes",
        "review_reference_codes",
        "embedding_model_version",
        "query_hash",
    ):
        assert forbidden not in serialized
    assert payload["exercise_pool"]["exercise_id_allowlist"]


def test_actual_input_contracts_expose_no_direct_or_raw_sensitive_fields() -> None:
    field_names = {
        *ConstraintEnvelope.model_fields,
        *RecoveryCeiling.model_fields,
        *SpecialistAgentInput.model_fields,
    }
    assert field_names.isdisjoint(FORBIDDEN_PROMPT_FIELDS)


@pytest.mark.parametrize("sensitive_code", ("KNEE", "KNEE_PAIN", "SEVERITY_HIGH"))
def test_sensitive_health_machine_codes_are_rejected_outside_catalog_projection(
    sensitive_code: str,
) -> None:
    with pytest.raises(ValueError):
        assert_private_machine_payload({"reason_codes": [sensitive_code]})


def test_pool_projection_carries_id_allowlist_but_not_qdrant_ranking() -> None:
    current_envelope = envelope()
    projected = project_exercise_pool(pool(current_envelope))
    serialized = json.dumps(projected, sort_keys=True)

    assert projected["exercise_id_allowlist"] == [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000003",
    ]
    assert "vector_ranked_exercise_ids" not in serialized
    assert "similarity" not in serialized
    assert "retrieval_metadata" not in serialized


def test_fake_model_path_never_opens_a_network_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_network(*_: object, **__: object) -> object:
        raise AssertionError("network access is forbidden in adapter unit tests")

    monkeypatch.setattr(socket, "socket", reject_network)
    adapter, _ = _successful_training_adapter()
    current_envelope = envelope()

    assert adapter.propose(
        constraint_envelope=current_envelope,
        exercise_pool=pool(current_envelope),
    ).succeeded


def test_runtime_adapter_imports_and_constructors_have_no_operational_tools() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    integration_dir = backend_root / "app" / "integrations" / "llm_agents"
    forbidden_import_prefixes = (
        "backend.app.db",
        "backend.app.repositories",
        "sqlalchemy",
        "qdrant_client",
        "langgraph",
    )
    imported_modules: set[str] = set()
    for source_path in integration_dir.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)
    assert not any(
        module.startswith(prefix)
        for module in imported_modules
        for prefix in forbidden_import_prefixes
    )

    specialist_parameters = inspect.signature(TrainingAgentAdapter).parameters
    coordinator_parameters = inspect.signature(LangChainCoordinatorAdapter).parameters
    parameter_names = {name.lower() for name in (*specialist_parameters, *coordinator_parameters)}
    assert not parameter_names & {"db", "orm", "repository", "qdrant", "tools"}


def test_project_has_only_approved_base_langgraph_and_no_provider_sdk_dependency() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    project = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = tuple(project["project"]["dependencies"])

    assert "langchain-core==1.6.0" in dependencies
    assert "langgraph==1.2.11" in dependencies
    assert not any(
        dependency.lower().startswith(
            ("langgraph-cli", "langgraph-sdk", "langchain-openai", "openai")
        )
        for dependency in dependencies
    )


def test_agent_settings_default_disabled_and_bound_retry_count() -> None:
    assert Settings.model_fields["llm_agents_enabled"].default is False
    for invalid_attempts in (0, 3):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, llm_agents_max_attempts=invalid_attempts)


def test_agent_settings_do_not_change_disabled_narration_provider() -> None:
    settings = Settings(
        _env_file=None,
        llm_enabled=False,
        llm_agents_enabled=True,
        llm_agents_provider_code="UNCONFIGURED",
        llm_agents_model_code="unconfigured",
    )

    assert isinstance(build_narration_provider(settings), UnavailableNarrationProvider)
