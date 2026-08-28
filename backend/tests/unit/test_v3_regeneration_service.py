from __future__ import annotations

import asyncio
from copy import copy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.app.domain.agents.v3_orchestration import GraphTerminalStatusCode
from backend.app.domain.agents.v3_persistence import (
    V3DecisionPersistenceBundle,
    V3PersistenceError,
    V3PersistenceFailureCode,
)
from backend.app.modules.decisions.v3_regeneration import (
    V3DecisionEngineCode,
    V3DecisionNotFoundError,
    V3EngineDisabledError,
    V3IdempotencyKeyReusedError,
    V3NoAlternativeAvailableError,
    V3RegenerationCommand,
    V3RegenerationContextStaleError,
    V3RegenerationIdempotencyRecord,
    V3RegenerationLimitReachedError,
    V3RegenerationService,
    V3RegenerationVersionSnapshot,
    V3StaleRegenerationError,
    V3StoredRegenerationSource,
)
from backend.tests.unit.test_v3_persistence_service import make_bundle

NOW = datetime(2026, 8, 25, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000001")
PLAN_ID = UUID("00000000-0000-0000-0000-000000000002")
VERSIONS = V3RegenerationVersionSnapshot(
    catalog_version="catalog-v1",
    policy_version="policy-v1",
    safety_rule_version="safety-rule-v1",
)


def source(*, sequence: int = 0) -> V3StoredRegenerationSource:
    bundle = make_bundle()
    root_id = bundle.root_decision_execution_id
    decision_id = root_id if sequence == 0 else uuid4()
    envelope = bundle.root_snapshot.constraint_envelope
    versions = V3RegenerationVersionSnapshot(
        catalog_version=envelope.catalog_version,
        policy_version=envelope.policy_version,
        safety_rule_version=envelope.safety_rule_version,
    )
    return V3StoredRegenerationSource(
        decision_id=decision_id,
        root_decision_id=root_id,
        parent_decision_id=None if sequence == 0 else root_id,
        plan_id=PLAN_ID,
        regeneration_sequence=sequence,
        successful_regeneration_count=sequence,
        generation_mode_code="ORIGINAL" if sequence == 0 else "REGENERATED",
        decision_engine_code=V3DecisionEngineCode.LLM_MULTI_AGENT,
        terminal_status_code=GraphTerminalStatusCode.COMPLETED,
        root_snapshot=bundle.root_snapshot,
        final_plan=bundle.final_plan,
        snapshot_expires_at=NOW + timedelta(hours=1),
        versions=versions,
    )


class FakeRuntime:
    def __init__(self, current: V3StoredRegenerationSource, *, duplicate: bool = False) -> None:
        self.current = current
        self.duplicate = duplicate
        self.calls = 0
        self.contexts = []

    async def regenerate(self, *, root_snapshot, regeneration_context):
        self.calls += 1
        self.contexts.append(regeneration_context)
        base = make_bundle()
        previous = self.current.final_plan
        plan = previous
        if not self.duplicate:
            first = previous.exercises[0]
            changed_prescription = first.prescription.model_copy(
                update={"sets": first.prescription.sets + 1}
            )
            changed_exercise = first.model_copy(update={"prescription": changed_prescription})
            plan = previous.model_copy(
                update={"exercises": (changed_exercise, *previous.exercises[1:])}
            )
        return base.model_copy(
            update={
                "decision_execution_id": uuid4(),
                "root_decision_execution_id": self.current.root_decision_id,
                "parent_decision_execution_id": self.current.decision_id,
                "root_snapshot": root_snapshot,
                "final_plan": plan,
            }
        )


class FakePersistence:
    def __init__(self, current: V3StoredRegenerationSource | None) -> None:
        self.current = current
        self.idempotency = {}
        self.persisted: list[V3DecisionPersistenceBundle] = []

    def lock_regeneration_source(self, *, user_id, decision_id):
        if self.current is None or user_id != USER_ID or decision_id != self.current.decision_id:
            return None
        return self.current

    def get_idempotency_result(self, *, user_id, idempotency_key):
        return self.idempotency.get((user_id, idempotency_key))

    def persist_regeneration(self, *, bundle, result, user_id, idempotency_key, request_hash):
        self.persisted.append(bundle)
        self.idempotency[(user_id, idempotency_key)] = V3RegenerationIdempotencyRecord(
            request_hash=request_hash, result=result
        )


class FakeUnitOfWork:
    def __init__(self, decisions: FakePersistence) -> None:
        self.decisions = decisions
        self.before = None

    def __enter__(self):
        self.before = (copy(self.decisions.idempotency), copy(self.decisions.persisted))
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is not None and self.before is not None:
            self.decisions.idempotency, self.decisions.persisted = self.before
        return False


def service(current, runtime, persistence, *, enabled=True):
    return V3RegenerationService(
        unit_of_work=FakeUnitOfWork(persistence),
        graph_runtime=runtime,
        current_versions=current.versions if current is not None else VERSIONS,
        enabled=enabled,
        clock=lambda: NOW,
    )


def command(current, *, key=None, plan_id=PLAN_ID, sequence=None, user_id=USER_ID):
    return V3RegenerationCommand(
        user_id=user_id,
        decision_id=current.decision_id,
        idempotency_key=key or uuid4(),
        expected_plan_id=plan_id,
        expected_regeneration_sequence=(
            current.regeneration_sequence if sequence is None else sequence
        ),
    )


@pytest.mark.parametrize("sequence", [0, 1])
def test_regeneration_sequences_reuse_root_snapshot_and_persist_atomically(sequence):
    current = source(sequence=sequence)
    persistence = FakePersistence(current)
    runtime = FakeRuntime(current)

    result = asyncio.run(service(current, runtime, persistence).regenerate(command(current)))

    assert result.regeneration_sequence == sequence + 1
    assert result.root_decision_id == current.root_decision_id
    assert result.parent_decision_id == current.decision_id
    assert runtime.contexts[0].generation_sequence == sequence + 1
    assert persistence.persisted[0].root_snapshot == current.root_snapshot


def test_disabled_limit_stale_and_ownership_fail_before_graph_execution():
    current = source(sequence=0)
    persistence = FakePersistence(current)
    runtime = FakeRuntime(current)
    with pytest.raises(V3EngineDisabledError):
        asyncio.run(
            service(current, runtime, persistence, enabled=False).regenerate(command(current))
        )

    limited = source(sequence=2)
    with pytest.raises(V3RegenerationLimitReachedError):
        asyncio.run(
            service(limited, FakeRuntime(limited), FakePersistence(limited)).regenerate(
                command(limited, sequence=2)
            )
        )
    with pytest.raises(V3StaleRegenerationError):
        asyncio.run(
            service(current, runtime, persistence).regenerate(command(current, plan_id=uuid4()))
        )
    with pytest.raises(V3DecisionNotFoundError):
        asyncio.run(
            service(current, runtime, persistence).regenerate(command(current, user_id=uuid4()))
        )
    assert runtime.calls == 0


def test_idempotency_reuses_same_result_and_rejects_changed_body():
    current = source()
    persistence = FakePersistence(current)
    runtime = FakeRuntime(current)
    app = service(current, runtime, persistence)
    key = uuid4()
    first = asyncio.run(app.regenerate(command(current, key=key)))
    second = asyncio.run(app.regenerate(command(current, key=key)))
    assert second == first
    assert runtime.calls == 1
    with pytest.raises(V3IdempotencyKeyReusedError):
        asyncio.run(app.regenerate(command(current, key=key, plan_id=uuid4())))


def test_exact_duplicate_is_rejected_without_partial_persistence():
    current = source()
    persistence = FakePersistence(current)
    runtime = FakeRuntime(current, duplicate=True)
    with pytest.raises(V3NoAlternativeAvailableError):
        asyncio.run(service(current, runtime, persistence).regenerate(command(current)))
    assert persistence.persisted == []
    assert persistence.idempotency == {}


class _LegacyBundlePersistence(FakePersistence):
    """A store whose bundle predates the current persistence schema."""

    def lock_regeneration_source(self, *, user_id, decision_id):
        raise V3PersistenceError(V3PersistenceFailureCode.UNSUPPORTED_SCHEMA_VERSION)


def test_a_decision_stored_under_an_older_schema_reports_a_stale_context() -> None:
    # Removing fields from the bundle without moving its schema version made
    # every earlier decision unreadable, and the resulting error escaped the
    # service as an unhandled RuntimeError instead of an API failure code.
    current = source()
    regeneration = service(current, FakeRuntime(current), _LegacyBundlePersistence(current))

    with pytest.raises(V3RegenerationContextStaleError):
        asyncio.run(regeneration.regenerate(command(current)))
