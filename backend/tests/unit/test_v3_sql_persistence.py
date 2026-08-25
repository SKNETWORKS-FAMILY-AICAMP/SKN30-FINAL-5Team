from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from backend.app.db.repositories.v3_decision import V3DecisionRepository
from backend.app.modules.decisions.v3_sql_persistence import (
    V3InvocationSqlMetadata,
    V3PersistenceSqlMapper,
    V3SqlAlchemyPersistenceAdapter,
    V3SqlPersistenceMetadata,
)
from backend.tests.unit.test_v3_persistence_service import make_bundle

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _metadata() -> V3SqlPersistenceMetadata:
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
    )


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
