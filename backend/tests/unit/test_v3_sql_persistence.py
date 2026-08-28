from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from backend.app.db.repositories.v3_decision import V3DecisionRepository
from backend.app.domain.agents.v3_persistence import (
    V3PersistenceError,
    V3PersistenceFailureCode,
)
from backend.app.modules.decisions.v3_application import resolve_vector_index_registry_id
from backend.app.modules.decisions.v3_sql_persistence import (
    V3InvocationSqlMetadata,
    V3PersistenceSqlMapper,
    V3SqlAlchemyPersistenceAdapter,
    V3SqlPersistenceMetadata,
)
from backend.tests.unit.test_v3_persistence_service import (
    VECTOR_COLLECTION_NAME,
    VECTOR_EMBEDDING_MODEL_VERSION,
    VECTOR_INDEX_VERSION,
    make_bundle,
)

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _metadata(vector_index_registry_id: UUID | None = None) -> V3SqlPersistenceMetadata:
    invocation = V3InvocationSqlMetadata(
        provider_code="TEST_PROVIDER",
        model_code="model-v1",
        attempt_number=0,
        invocation_status_code="SUCCEEDED",
        latency_ms=1,
    )
    return V3SqlPersistenceMetadata(
        now=NOW,
        root_snapshot_expires_at=NOW + timedelta(hours=1),
        proposal_invocations=(invocation, invocation, invocation),
        coordinator_provider_code="TEST_PROVIDER",
        plan_candidate_ids=(uuid4(),),
        vector_index_registry_id=vector_index_registry_id,
    )


def _run() -> SimpleNamespace:
    return SimpleNamespace(
        input_hash="a" * 64,
        policy_version_id=uuid4(),
        catalog_version_id=uuid4(),
        duration_rule_version="duration-rule-v1",
    )


def test_sql_mapper_preserves_succeeded_retrieval_index_lineage() -> None:
    # A succeeded retrieval has to reach persistence with its registry ID. The
    # repository rejects the artifact otherwise, which surfaced only once a
    # matching vector index existed and retrieval stopped falling back.
    bundle = make_bundle(vector_retrieval_succeeded=True)
    run = _run()
    registry_id = uuid4()

    artifacts = V3PersistenceSqlMapper().map_root(bundle, run, _metadata(registry_id))

    V3DecisionRepository._validate_root_artifacts(run, artifacts)
    assert artifacts.retrieval.fallback_used is False
    assert artifacts.retrieval.vector_index_registry_id == registry_id
    assert artifacts.retrieval.collection_name == VECTOR_COLLECTION_NAME
    assert artifacts.retrieval.vector_index_version == VECTOR_INDEX_VERSION
    assert artifacts.retrieval.embedding_model_version == VECTOR_EMBEDDING_MODEL_VERSION


def test_sql_mapper_rejects_succeeded_retrieval_without_registry_id() -> None:
    # Guards the regression directly: dropping the registry ID must fail loudly
    # rather than persist a decision whose index lineage cannot be reproduced.
    bundle = make_bundle(vector_retrieval_succeeded=True)
    run = _run()

    artifacts = V3PersistenceSqlMapper().map_root(bundle, run, _metadata(None))

    with pytest.raises(ValueError, match="index lineage"):
        V3DecisionRepository._validate_root_artifacts(run, artifacts)


def test_sql_mapper_preserves_explicit_failed_retrieval_lineage() -> None:
    bundle = make_bundle()
    run = SimpleNamespace(
        input_hash="a" * 64,
        policy_version_id=uuid4(),
        catalog_version_id=uuid4(),
        duration_rule_version="duration-rule-v1",
    )

    artifacts = V3PersistenceSqlMapper().map_root(bundle, run, _metadata())

    V3DecisionRepository._validate_root_artifacts(run, artifacts)
    assert artifacts.retrieval.fallback_used is True
    assert artifacts.retrieval.fallback_policy_version == "deterministic-pool-v1"
    assert artifacts.retrieval.retrieval_failure_codes == ("VECTOR_INDEX_UNAVAILABLE",)


def test_sql_adapter_replays_strict_bundle_through_json_mode() -> None:
    bundle = make_bundle()
    run = SimpleNamespace(
        coordinator_result={"v3_persistence_bundle": bundle.model_dump(mode="json")}
    )
    session = SimpleNamespace(get=lambda _model, _identity: run)
    adapter = V3SqlAlchemyPersistenceAdapter(
        session,  # type: ignore[arg-type]
        lambda _session, _bundle: _metadata(),
    )

    assert adapter.get(bundle.decision_execution_id) == bundle


def test_registry_id_is_resolved_for_a_succeeded_retrieval() -> None:
    # The wiring regression: persistence has to look the registry row up from
    # the index version the result names. Leaving it unresolved made every
    # decision fail once a matching index existed and retrieval stopped
    # falling back.
    bundle = make_bundle(vector_retrieval_succeeded=True)
    registry_id = uuid4()
    looked_up: list[str] = []

    class _Session:
        def scalar(self, statement: object) -> object:
            looked_up.append(str(statement))
            return SimpleNamespace(id=registry_id)

    resolved = resolve_vector_index_registry_id(
        cast(Session, _Session()), bundle.root_snapshot.retrieval_result
    )

    assert resolved == registry_id
    assert len(looked_up) == 1


def test_registry_id_stays_none_for_a_deterministic_fallback() -> None:
    bundle = make_bundle()

    class _Session:
        def scalar(self, statement: object) -> object:  # pragma: no cover - must not run
            raise AssertionError("a fallback retrieval must not query the registry")

    resolved = resolve_vector_index_registry_id(
        cast(Session, _Session()), bundle.root_snapshot.retrieval_result
    )

    assert resolved is None


def test_missing_registry_row_fails_loudly_instead_of_persisting_blank_lineage() -> None:
    bundle = make_bundle(vector_retrieval_succeeded=True)

    class _Session:
        def scalar(self, statement: object) -> object:
            return None

    with pytest.raises(RuntimeError, match="V3_VECTOR_INDEX_REGISTRY_MISSING"):
        resolve_vector_index_registry_id(
            cast(Session, _Session()), bundle.root_snapshot.retrieval_result
        )


def test_persist_bundle_passes_the_resolved_registry_id_into_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Covers the call site rather than the resolver: the id has to actually
    # reach V3SqlPersistenceMetadata. Leaving it off the constructor is what
    # made every vector-backed decision fail to persist.
    from backend.app.modules.decisions import v3_application

    bundle = make_bundle(vector_retrieval_succeeded=True)
    registry_id = uuid4()
    captured: list[V3SqlPersistenceMetadata] = []

    class _CapturingAdapter:
        def __init__(self, _session: object, metadata_factory: object) -> None:
            self._metadata_factory = metadata_factory

        def add(self, added_bundle: object) -> None:
            captured.append(self._metadata_factory(None, added_bundle))

    monkeypatch.setattr(
        v3_application, "resolve_vector_index_registry_id", lambda _s, _r: registry_id
    )
    monkeypatch.setattr(v3_application, "V3SqlAlchemyPersistenceAdapter", _CapturingAdapter)

    v3_application._persist_v3_bundle(
        cast(Session, SimpleNamespace()),
        cast(Any, SimpleNamespace(created_at=NOW)),
        cast(Any, SimpleNamespace(id=uuid4())),
        bundle,
    )

    assert len(captured) == 1
    assert captured[0].vector_index_registry_id == registry_id


def _stored_adapter(payload: object) -> V3SqlAlchemyPersistenceAdapter:
    run = SimpleNamespace(coordinator_result={"v3_persistence_bundle": payload})
    return V3SqlAlchemyPersistenceAdapter(
        cast(Session, SimpleNamespace(get=lambda _model, _identity: run)),
        lambda _session, _bundle: _metadata(),
    )


def _legacy_payload() -> dict[str, Any]:
    """A bundle as written before conflict detection and review were removed."""

    payload = make_bundle().model_dump(mode="json")
    payload["schema_version"] = "v3-decision-persistence-bundle-v1"
    payload["conflict_result"] = {"schema_version": "v3-conflict-detection-v1"}
    payload["review_results"] = []
    return payload


def test_a_bundle_from_an_earlier_schema_fails_with_its_documented_code() -> None:
    # Removing conflict_result and review_results without moving the schema
    # version left every stored bundle unreadable, and the extra-field
    # ValidationError escaped the repository instead of naming the cause.
    adapter = _stored_adapter(_legacy_payload())

    with pytest.raises(V3PersistenceError) as error:
        adapter.get(uuid4())

    assert error.value.code is V3PersistenceFailureCode.UNSUPPORTED_SCHEMA_VERSION


def test_an_unreadable_bundle_is_never_reported_as_a_missing_one() -> None:
    # persist() treats None as "no row yet" and writes. Reporting an older
    # bundle that way would let a duplicate execution through.
    adapter = _stored_adapter(_legacy_payload())

    with pytest.raises(V3PersistenceError):
        adapter.get(uuid4())


def test_a_bundle_written_under_the_current_schema_still_replays() -> None:
    bundle = make_bundle()
    adapter = _stored_adapter(bundle.model_dump(mode="json"))

    assert adapter.get(bundle.decision_execution_id) == bundle
