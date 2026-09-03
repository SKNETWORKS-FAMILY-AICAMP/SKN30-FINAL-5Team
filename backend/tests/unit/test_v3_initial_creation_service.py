from __future__ import annotations

import asyncio
from copy import copy
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, SafetyRequiredActionCode
from backend.app.modules.decisions.schemas import DecisionCreateRequest, DecisionResponse
from backend.app.modules.decisions.service import IdempotencyKeyReusedError
from backend.app.modules.decisions.v3_creation import (
    V3CreationIdempotencyRecord,
    V3CreationSource,
    V3InitialCreationService,
    V3ProviderExecutionError,
    V3StructuredOutputError,
)
from backend.tests.unit.test_v3_persistence_service import make_bundle


def response(decision_id=None) -> DecisionResponse:
    return DecisionResponse(
        decision_id=decision_id or uuid4(),
        local_date=date(2026, 8, 26),
        status_code="COMPLETED",
        safety_status_code="PASS",
        action_code="KEEP",
        requested_duration_minutes=10,
        duration_adjustment_source_code="PROFILE_DEFAULT",
        final_plan=None,
        options=[],
        reason_codes=[],
        summary="safe deterministic result",
        created_at=datetime(2026, 8, 26, tzinfo=UTC),
    )


def command_request() -> DecisionCreateRequest:
    return DecisionCreateRequest(
        local_date=date(2026, 8, 26), daily_context_id=uuid4(), expected_context_version=1
    )


class Repository:
    def __init__(self, source, projected) -> None:
        self.source = source
        self.projected = projected
        self.idempotency = {}
        self.proposals = []
        self.finals = []
        self.terminals = []
        self.fail_persist = False

    def acquire_lock(self, **kwargs):
        del kwargs

    def get_idempotency(self, *, user_id, idempotency_key):
        return self.idempotency.get((user_id, idempotency_key))

    def load_source(self, **kwargs):
        del kwargs
        return self.source

    def persist_terminal(self, **kwargs):
        self.terminals.append(kwargs)

    def persist_success(self, *, bundle, response, **kwargs):
        del kwargs
        self.proposals.extend(bundle.agent_proposals)
        if self.fail_persist:
            raise RuntimeError("database write failed")
        self.finals.append((bundle.final_plan, response))

    def save_idempotency(self, *, user_id, idempotency_key, request_hash, response):
        self.idempotency[(user_id, idempotency_key)] = V3CreationIdempotencyRecord(
            request_hash=request_hash, response=response
        )


class UnitOfWork:
    def __init__(self, decisions) -> None:
        self.decisions = decisions

    def __enter__(self):
        self.before = (
            copy(self.decisions.idempotency),
            copy(self.decisions.proposals),
            copy(self.decisions.finals),
            copy(self.decisions.terminals),
        )
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc, traceback
        if exc_type is not None:
            (
                self.decisions.idempotency,
                self.decisions.proposals,
                self.decisions.finals,
                self.decisions.terminals,
            ) = self.before
        return False


class Safety:
    def __init__(self, envelope) -> None:
        self.envelope = envelope

    def evaluate(self, source):
        del source
        return self.envelope


class Pool:
    def __init__(self, root) -> None:
        self.root = root
        self.calls = 0

    def load(self, **kwargs):
        del kwargs
        self.calls += 1
        return self.root


class Runtime:
    def __init__(self, bundle, error=None) -> None:
        self.bundle = bundle
        self.error = error
        self.calls = 0

    async def create(self, **kwargs):
        del kwargs
        self.calls += 1
        if self.error:
            raise self.error
        return self.bundle


class Fallback:
    def __init__(self, bundle) -> None:
        self.bundle = bundle.model_copy(update={"fallback_used": True})
        self.codes = []

    def create(self, *, root_snapshot, failure_code):
        self.codes.append(failure_code)
        return self.bundle.model_copy(update={"root_snapshot": root_snapshot})


class Projector:
    def __init__(self, projected) -> None:
        self.projected = projected

    def project_terminal(self, **kwargs):
        del kwargs
        return SimpleNamespace(
            response=self.projected.model_copy(
                update={"action_code": "REST", "safety_status_code": "BLOCKED"}
            ),
            explanation=object(),
        )

    def project_success(self, **kwargs):
        del kwargs
        return SimpleNamespace(response=self.projected, explanation=object())


def build(*, envelope=None, runtime_error=None, fail_persist=False):
    bundle = make_bundle()
    source = V3CreationSource(
        local_date=date(2026, 8, 26),
        context_version=1,
        normalized_values={"fatigue_code": "LOW", "goal_code": "STRENGTH"},
    )
    repository = Repository(source, response(bundle.decision_execution_id))
    repository.fail_persist = fail_persist
    runtime = Runtime(bundle, runtime_error)
    fallback = Fallback(bundle)
    service = V3InitialCreationService(
        unit_of_work_factory=lambda session: UnitOfWork(repository),
        safety_policy=Safety(envelope or bundle.root_snapshot.constraint_envelope),
        exercise_pool_loader=Pool(bundle.root_snapshot),
        graph_runtime=runtime,
        fallback=fallback,
        projector=Projector(repository.projected),
    )
    return service, repository, runtime, fallback, bundle


def test_safety_veto_never_calls_provider() -> None:
    base = make_bundle().root_snapshot.constraint_envelope
    veto = ConstraintEnvelope.create(
        **base.model_dump(
            exclude={
                "schema_version",
                "envelope_hash",
                "plan_generation_allowed",
                "safety_required_action_code",
            }
        ),
        plan_generation_allowed=False,
        safety_required_action_code=SafetyRequiredActionCode.REST,
    )
    service, repository, runtime, _, _ = build(envelope=veto)
    result = asyncio.run(service.create(object(), uuid4(), command_request(), uuid4()))
    assert result.action_code == "REST"
    assert runtime.calls == 0
    assert len(repository.terminals) == 1


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TimeoutError(), "PROVIDER_TIMEOUT"),
        (V3ProviderExecutionError(), "PROVIDER_UNAVAILABLE"),
        (V3StructuredOutputError(), "STRUCTURED_OUTPUT_INVALID"),
    ],
)
def test_provider_failures_use_deterministic_fallback(error, code) -> None:
    service, repository, _, fallback, bundle = build(runtime_error=error)
    result = asyncio.run(service.create(object(), uuid4(), command_request(), uuid4()))
    assert result.decision_id == bundle.decision_execution_id
    assert fallback.codes == [code]
    assert len(repository.proposals) == 3
    assert len(repository.finals) == 1


def test_proposals_and_final_are_separate_and_transaction_rolls_back() -> None:
    service, repository, _, _, _ = build(fail_persist=True)
    with pytest.raises(RuntimeError, match="database write failed"):
        asyncio.run(service.create(object(), uuid4(), command_request(), uuid4()))
    assert repository.proposals == []
    assert repository.finals == []
    assert repository.idempotency == {}


def test_creation_idempotency_replays_and_rejects_changed_request() -> None:
    service, _, runtime, _, _ = build()
    user_id, key = uuid4(), uuid4()
    request = command_request()
    first = asyncio.run(service.create(object(), user_id, request, key))
    second = asyncio.run(service.create(object(), user_id, request, key))
    assert second == first
    assert runtime.calls == 1
    changed = request.model_copy(update={"daily_context_id": uuid4()})
    with pytest.raises(IdempotencyKeyReusedError):
        asyncio.run(service.create(object(), user_id, changed, key))


def test_creation_source_rejects_identifiers_and_raw_health_fields() -> None:
    for field in ("email", "full_name", "auth_token", "raw_health_data", "calendar_text"):
        with pytest.raises(ValidationError, match="forbidden privacy field"):
            V3CreationSource(
                local_date=date(2026, 8, 26),
                context_version=1,
                normalized_values={field: "not-allowed"},
            )
