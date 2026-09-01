from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models.decision import PlanCandidate
from backend.app.db.models.v3_decision import (
    DecisionConstraintEnvelopeRecord,
    DecisionCoordinationAttemptRecord,
    DecisionExercisePoolRecord,
    DecisionExerciseRetrievalRecord,
    PlanIntegrityValidationRecord,
)
from backend.app.domain.agents.v3_persistence import V3DecisionPersistenceBundle
from backend.app.modules.decisions.v3_sql_persistence import (
    V3InvocationSqlMetadata,
    V3SqlAlchemyPersistenceAdapter,
    V3SqlPersistenceMetadata,
)
from backend.tests.integration.test_v3_decision_repository import (
    NOW,
    _new_run,
    postgres_session,  # noqa: F401 - imported pytest fixture
)
from backend.tests.unit.test_v3_persistence_service import make_bundle


def _bundle_for(run_id):
    bundle = make_bundle()
    payload = bundle.model_dump(exclude={"canonical_result_hash"})
    payload.update(
        decision_execution_id=run_id,
        root_decision_execution_id=run_id,
        parent_decision_execution_id=None,
    )
    return V3DecisionPersistenceBundle.create(**payload)


def _candidate(session: Session, run_id):
    candidate = PlanCandidate(
        id=uuid4(),
        decision_run_id=run_id,
        candidate_code="FINAL",
        action_code="KEEP",
        training_type_code="STRENGTH",
        body_focus_code=None,
        requested_duration_minutes=30,
        duration_adjustment_source_code="PROFILE",
        estimated_duration_seconds=1800,
        estimated_calories_burned=None,
        setup_seconds=0,
        warmup_seconds=60,
        cooldown_seconds=60,
        goal_tags=["GENERAL_FITNESS"],
        duration_rule_version="duration-rule-v1",
        selected=True,
        created_at=NOW,
    )
    session.add(candidate)
    session.flush()
    return candidate


def _metadata(candidate_id):
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
        plan_candidate_ids=(candidate_id,),
    )


@pytest.mark.integration
def test_domain_bundle_sql_round_trip_replay_and_root_lookup(
    request: pytest.FixtureRequest,
) -> None:
    db_session: Session = request.getfixturevalue("postgres_session")
    with db_session.begin():
        run, _ = _new_run(db_session)
        candidate = _candidate(db_session, run.id)
        bundle = _bundle_for(run.id)
        adapter = V3SqlAlchemyPersistenceAdapter(
            db_session, lambda _session, _bundle: _metadata(candidate.id)
        )
        adapter.add(bundle)
        replayed = adapter.get(run.id)
        root = adapter.get_root_snapshot(run.id)

        assert replayed == bundle
        assert root == bundle.root_snapshot
        assert db_session.scalar(select(func.count(DecisionConstraintEnvelopeRecord.id))) == 1
        assert db_session.scalar(select(func.count(DecisionExercisePoolRecord.id))) == 1
        assert db_session.scalar(select(func.count(DecisionExerciseRetrievalRecord.id))) == 1
        assert db_session.scalar(select(func.count(DecisionCoordinationAttemptRecord.id))) == 1
        assert db_session.scalar(select(func.count(PlanIntegrityValidationRecord.id))) == 1


@pytest.mark.integration
def test_domain_bundle_sql_transaction_rolls_back_all_audit_rows(
    request: pytest.FixtureRequest,
) -> None:
    db_session: Session = request.getfixturevalue("postgres_session")
    with db_session.begin():
        run, _ = _new_run(db_session)
        run_id = run.id
        candidate = _candidate(db_session, run.id)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with db_session.begin():
            adapter = V3SqlAlchemyPersistenceAdapter(
                db_session, lambda _session, _bundle: _metadata(candidate.id)
            )
            adapter.add(_bundle_for(run_id))
            raise RuntimeError("synthetic failure")

    assert db_session.scalar(select(func.count(DecisionConstraintEnvelopeRecord.id))) == 0
    assert db_session.scalar(select(func.count(DecisionExercisePoolRecord.id))) == 0
    assert db_session.scalar(select(func.count(DecisionExerciseRetrievalRecord.id))) == 0
    assert db_session.scalar(select(func.count(DecisionCoordinationAttemptRecord.id))) == 0
    assert db_session.scalar(select(func.count(PlanIntegrityValidationRecord.id))) == 0
