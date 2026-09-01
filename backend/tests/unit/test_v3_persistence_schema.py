import ast
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from backend.app.db.base import Base
from backend.app.db.models import (  # noqa: F401 -- registers all metadata
    DecisionConstraintEnvelopeRecord,
    DecisionCoordinationAttemptRecord,
    DecisionExercisePoolRecord,
    DecisionExerciseRetrievalRecord,
    PlanIntegrityValidationRecord,
)
from backend.app.db.repositories.v3_decision import (
    AgentProposalWrite,
    ConstraintEnvelopeWrite,
    CoordinationAttemptWrite,
    ExercisePoolWrite,
    ExerciseRetrievalWrite,
    IntegrityValidationWrite,
    RootArtifactsWrite,
    _validate_payload,
)


def test_v3_persistence_tables_and_additive_columns_are_registered() -> None:
    assert {
        "decision_constraint_envelopes",
        "decision_exercise_pools",
        "decision_exercise_retrievals",
        "decision_coordination_attempts",
        "plan_integrity_validations",
    }.issubset(Base.metadata.tables)
    decision_columns = Base.metadata.tables["decision_runs"].c
    proposal_columns = Base.metadata.tables["agent_proposals"].c
    assert {
        "root_decision_run_id",
        "parent_decision_run_id",
        "generation_mode_code",
        "regeneration_sequence",
        "decision_engine_code",
        "langchain_contract_version",
        "langgraph_contract_version",
    }.issubset(decision_columns.keys())
    assert all(
        decision_columns[name].nullable
        for name in decision_columns.keys()
        if name
        in {
            "root_decision_run_id",
            "parent_decision_run_id",
            "generation_mode_code",
            "regeneration_sequence",
            "decision_engine_code",
            "langchain_contract_version",
            "langgraph_contract_version",
        }
    )
    assert {
        "proposal_hash",
        "prompt_version",
        "provider_code",
        "model_code",
        "output_schema_version",
        "attempt_number",
        "invocation_status_code",
        "latency_ms",
    }.issubset(proposal_columns.keys())
    assert proposal_columns["proposal_hash"].nullable


def test_legacy_deliberation_tables_remain_but_v3_repository_does_not_write_them() -> None:
    legacy_tables = {
        "decision_deliberations",
        "agent_review_events",
        "agent_proposal_revisions",
    }
    assert legacy_tables.issubset(Base.metadata.tables)

    repository_source = Path("backend/app/db/repositories/v3_decision.py").read_text(
        encoding="utf-8"
    )
    assert all(table_name not in repository_source for table_name in legacy_tables)


def test_v3_validation_has_composite_coordination_identity_fk() -> None:
    table = Base.metadata.tables["plan_integrity_validations"]
    constraint = next(
        item
        for item in table.foreign_key_constraints
        if item.name == "fk_v3_validation_coordination_identity"
    )
    assert tuple(element.parent.name for element in constraint.elements) == (
        "coordination_attempt_id",
        "decision_run_id",
        "coordination_attempt_number",
    )
    assert constraint.ondelete == "CASCADE"


@pytest.mark.parametrize(
    "payload",
    [
        {"pain_intensity_score": 7},
        {"nested": {"raw_health": {"value": "forbidden"}}},
        {"items": [{"provider_exception": "secret detail"}]},
        {"prompt": "hidden prompt"},
        {"email": "direct identifier"},
        {"wearable_data": [1, 2, 3]},
    ],
)
def test_v3_persistence_payload_guard_rejects_sensitive_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="forbidden field"):
        _validate_payload(payload, path="snapshot")


def test_v3_persistence_payload_guard_accepts_versioned_machine_data() -> None:
    _validate_payload(
        {
            "schema_version": "constraint-envelope-v3",
            "goal_code": "GENERAL_FITNESS",
            "requested_duration_minutes": 30,
            "exercise_ids": ["00000000-0000-0000-0000-000000000001"],
        },
        path="snapshot",
    )


def test_v3_write_contracts_are_framework_independent_frozen_dataclasses() -> None:
    contracts = (
        ConstraintEnvelopeWrite,
        ExercisePoolWrite,
        ExerciseRetrievalWrite,
        RootArtifactsWrite,
        AgentProposalWrite,
        CoordinationAttemptWrite,
        IntegrityValidationWrite,
    )
    for contract in contracts:
        assert is_dataclass(contract)
        assert contract.__dataclass_params__.frozen
        assert all("sqlalchemy" not in str(field.type).lower() for field in fields(contract))


def test_v3_repository_does_not_depend_on_graph_or_provider_sdk() -> None:
    source = Path("backend/app/db/repositories/v3_decision.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    forbidden_imports = (
        "langgraph",
        "langchain",
        "qdrant_client",
        "backend.app.integrations",
    )
    assert not any(
        module == value or module.startswith(f"{value}.")
        for module in imported_modules
        for value in forbidden_imports
    )
