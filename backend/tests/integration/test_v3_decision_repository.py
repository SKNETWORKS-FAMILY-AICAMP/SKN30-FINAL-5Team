import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import CatalogVersion, Exercise
from backend.app.db.models.checkin import DailyContext
from backend.app.db.models.decision import (
    AgentProposalRecord,
    DecisionPolicyVersion,
    DecisionRun,
    PlanCandidate,
)
from backend.app.db.models.identity import User
from backend.app.db.models.routine import Routine
from backend.app.db.models.v3_decision import (
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
    V3DecisionRepository,
    V3PersistenceConflictError,
)
from backend.scripts.demo_seed import seed_catalog

ALEMBIC_CONFIG = Path("backend/alembic.ini")
NOW = datetime(2026, 8, 25, 3, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
HASH_F = "f" * 64


@pytest.fixture
def postgres_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    database_url = os.getenv("TEST_DATABASE_URL", "")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not (make_url(database_url).database or "").endswith("_test"):
        pytest.fail("V3 repository tests require a dedicated *_test database")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")
    engine: Engine = create_engine(database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        with session.begin():
            seed_catalog(session, NOW)
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()
        get_settings.cache_clear()


def _new_run(session: Session, *, user_id: UUID | None = None) -> tuple[DecisionRun, Exercise]:
    catalog = session.scalar(select(CatalogVersion).where(CatalogVersion.status_code == "ACTIVE"))
    policy = session.scalar(
        select(DecisionPolicyVersion).where(
            DecisionPolicyVersion.version_code == "decision-policy-v3"
        )
    )
    assert catalog is not None and policy is not None
    exercise = session.scalar(select(Exercise).where(Exercise.catalog_version_id == catalog.id))
    assert exercise is not None
    actual_user_id = user_id or uuid4()
    if user_id is None:
        session.add(
            User(
                id=actual_user_id,
                status_code="ACTIVE",
                code_set_version="identity-mvp-v1",
                last_active_at=NOW,
                ai_trial_started_at=NOW,
                ai_trial_ends_at=NOW + timedelta(days=14),
                premium_status_code="NOT_AVAILABLE",
            )
        )
    context = session.scalar(select(DailyContext).where(DailyContext.user_id == actual_user_id))
    routine = session.scalar(select(Routine).where(Routine.user_id == actual_user_id))
    if context is None:
        context = DailyContext(
            id=uuid4(),
            user_id=actual_user_id,
            local_date=date(2026, 8, 25),
            fatigue_level_code="LOW",
            requested_duration_minutes=30,
            duration_adjustment_source_code="PROFILE",
            location_code="HOME",
            availability_source_code="ROUTINE_DEFAULT",
            context_version=1,
        )
        session.add(context)
    if routine is None:
        routine = Routine(
            id=uuid4(),
            user_id=actual_user_id,
            version=1,
            goal_code="GENERAL_FITNESS",
            status_code="ACTIVE",
            effective_from=date(2026, 8, 25),
            catalog_version_id=catalog.id,
        )
        session.add(routine)
    # Raw FK-only fixture objects have no ORM relationship dependency, so
    # establish their rows before the DecisionRun references them.
    session.flush()
    run = DecisionRun(
        id=uuid4(),
        user_id=actual_user_id,
        local_date=date(2026, 8, 25),
        daily_context_id=context.id,
        daily_context_version=1,
        base_routine_id=routine.id,
        input_schema_version="decision-input-v4",
        input_snapshot={"requested_duration_minutes": 30},
        input_hash=HASH_A,
        catalog_version_id=catalog.id,
        policy_version_id=policy.id,
        safety_rule_version="safety-policy-v1",
        duration_rule_version="duration-rule-v1",
        graph_version="v3-graph-v1",
        coordinator_version="v3-coordinator-v1",
        status_code="RUNNING",
        safety_status_code="PASS",
        coordinator_result={},
    )
    session.add(run)
    session.flush()
    return run, exercise


def _artifacts(run: DecisionRun, exercise: Exercise) -> RootArtifactsWrite:
    exercise_id = exercise.id
    return RootArtifactsWrite(
        envelope=ConstraintEnvelopeWrite(
            input_hash=HASH_A,
            envelope_schema_version="constraint-envelope-v3",
            safety_policy_version="safety-policy-v1",
            policy_version_id=run.policy_version_id,
            safety_rule_version="safety-policy-v1",
            duration_rule_version="duration-rule-v1",
            plan_generation_allowed=True,
            required_action_code=None,
            veto=False,
            envelope_payload={
                "schema_version": "constraint-envelope-v3",
                "requested_duration_minutes": 30,
                "goal_code": "GENERAL_FITNESS",
            },
            envelope_hash=HASH_B,
            expires_at=NOW + timedelta(hours=1),
        ),
        pool=ExercisePoolWrite(
            catalog_version_id=run.catalog_version_id,
            pool_schema_version="exercise-pool-snapshot-v5",
            filter_codes=("PRODUCTION_APPROVED",),
            constraint_envelope_hash=HASH_B,
            exercise_payload=(
                {
                    "exercise_id": str(exercise_id),
                    "stable_code": exercise.stable_code,
                    "catalog_version": "merged-mvp-v0.4.0",
                    "content_version": exercise.instruction_content_version,
                },
            ),
            mandatory_exercise_ids=(exercise_id,),
            vector_ranked_exercise_ids=(),
            retrieval_metadata={
                "request_schema_version": "exercise-retrieval-request-v1",
                "result_schema_version": "exercise-retrieval-result-v1",
                "query_hash": HASH_C,
                "retrieval_status_code": "VECTOR_INDEX_UNAVAILABLE",
                "fallback_used": True,
            },
            pool_hash=HASH_D,
        ),
        retrieval=ExerciseRetrievalWrite(
            vector_index_registry_id=None,
            request_schema_version="exercise-retrieval-request-v1",
            request_hash=HASH_E,
            eligible_exercise_ids_hash=HASH_A,
            mandatory_exercise_ids_hash=HASH_B,
            normalized_query_codes_hash=HASH_C,
            retrieval_mode_code="VECTOR_RANKED",
            requested_limit=8,
            result_schema_version="exercise-retrieval-result-v1",
            collection_name=None,
            vector_index_version=None,
            embedding_model_version=None,
            query_hash=HASH_C,
            retrieval_status_code="VECTOR_INDEX_UNAVAILABLE",
            retrieval_failure_codes=("VECTOR_INDEX_UNAVAILABLE",),
            returned_ranked_ids_and_scores=(),
            revalidated_ranked_exercise_ids=(),
            fallback_used=True,
            fallback_policy_version="deterministic-pool-fallback-v1",
            retrieval_latency_ms=10,
            result_hash=HASH_F,
        ),
    )


def _proposals(exercise_id: UUID) -> tuple[AgentProposalWrite, ...]:
    return tuple(
        AgentProposalWrite(
            agent_type_code=role,
            proposal_status_code="READY",
            proposal_schema_version="specialist-agent-proposal-v1",
            proposal_payload={
                "schema_version": "specialist-agent-proposal-v1",
                "agent_type_code": role,
                "exercise_ids": [str(exercise_id)],
            },
            proposal_hash=hash_value,
            invocation_metadata_schema_version="llm-invocation-metadata-v1",
            prompt_version="v3-specialist-prompt-v1",
            provider_code="TEST_PROVIDER",
            model_code="TEST_MODEL_V1",
            output_schema_version="specialist-agent-proposal-v1",
            attempt_number=0,
            invocation_status_code="SUCCEEDED",
            latency_ms=25,
        )
        for role, hash_value in zip(
            ("TRAINING", "RECOVERY", "FEASIBILITY"),
            (HASH_A, HASH_B, HASH_C),
            strict=True,
        )
    )


def _configure_root(repo: V3DecisionRepository, session: Session, run: DecisionRun) -> None:
    repo.configure_lineage(
        session,
        decision_run_id=run.id,
        root_decision_run_id=run.id,
        parent_decision_run_id=None,
        generation_mode_code="ORIGINAL",
        regeneration_sequence=0,
        decision_engine_code="LLM_MULTI_AGENT",
        langchain_contract_version="langchain-v3-adapter-v1",
        langgraph_contract_version="v3-graph-state-v1",
    )


@pytest.mark.integration
def test_v3_root_round_trip_idempotency_and_regeneration_reuse(
    postgres_session: Session,
) -> None:
    repo = V3DecisionRepository()
    with postgres_session.begin():
        root, exercise = _new_run(postgres_session)
        _configure_root(repo, postgres_session, root)
        artifacts = _artifacts(root, exercise)
        first = repo.save_root_artifacts(
            postgres_session, root_decision_run_id=root.id, artifacts=artifacts, now=NOW
        )
        retry = repo.save_root_artifacts(
            postgres_session, root_decision_run_id=root.id, artifacts=artifacts, now=NOW
        )
        assert retry == first

        regenerated, _ = _new_run(postgres_session, user_id=root.user_id)
        repo.configure_lineage(
            postgres_session,
            decision_run_id=regenerated.id,
            root_decision_run_id=root.id,
            parent_decision_run_id=root.id,
            generation_mode_code="REGENERATED",
            regeneration_sequence=1,
            decision_engine_code="LLM_MULTI_AGENT",
            langchain_contract_version="langchain-v3-adapter-v1",
            langgraph_contract_version="v3-graph-state-v1",
        )
        bundle = repo.get_audit_bundle(postgres_session, regenerated.id)
        assert bundle.root_decision_run_id == root.id
        assert bundle.envelope["envelope_hash"] == HASH_B
        assert bundle.pool["pool_hash"] == HASH_D
        assert bundle.retrieval["request_hash"] == HASH_E
        assert bundle.retrieval["result_hash"] == HASH_F
        assert postgres_session.scalar(select(func.count(DecisionConstraintEnvelopeRecord.id))) == 1
        assert postgres_session.scalar(select(func.count(DecisionExercisePoolRecord.id))) == 1
        assert postgres_session.scalar(select(func.count(DecisionExerciseRetrievalRecord.id))) == 1


@pytest.mark.integration
def test_v3_proposals_coordination_validation_and_v1_v2_compatibility(
    postgres_session: Session,
) -> None:
    repo = V3DecisionRepository()
    with postgres_session.begin():
        run, exercise = _new_run(postgres_session)
        _configure_root(repo, postgres_session, run)
        repo.save_root_artifacts(
            postgres_session,
            root_decision_run_id=run.id,
            artifacts=_artifacts(run, exercise),
            now=NOW,
        )
        proposal_ids = repo.save_agent_proposals(
            postgres_session,
            decision_run_id=run.id,
            proposals=_proposals(exercise.id),
            now=NOW,
        )
        assert len(proposal_ids) == 3
        assert (
            repo.save_agent_proposals(
                postgres_session,
                decision_run_id=run.id,
                proposals=_proposals(exercise.id),
                now=NOW,
            )
            == proposal_ids
        )

        attempt = CoordinationAttemptWrite(
            attempt_number=0,
            status_code="READY",
            input_hash=HASH_A,
            coordinator_schema_version="plan-spec-v1",
            model_provider_code="TEST_PROVIDER",
            model_code="TEST_MODEL_V1",
            prompt_version="v3-coordinator-prompt-v1",
            plan_spec={"schema_version": "plan-spec-v1", "plan_hash": HASH_B},
            output_hash=HASH_B,
            repair_violation_codes=None,
            failure_code=None,
        )
        attempt_id = repo.save_coordination_attempt(
            postgres_session, decision_run_id=run.id, attempt=attempt, now=NOW
        )
        assert (
            repo.save_coordination_attempt(
                postgres_session, decision_run_id=run.id, attempt=attempt, now=NOW
            )
            == attempt_id
        )
        candidate = PlanCandidate(
            id=uuid4(),
            decision_run_id=run.id,
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
        postgres_session.add(candidate)
        postgres_session.flush()
        validation = IntegrityValidationWrite(
            coordination_attempt_number=0,
            plan_candidate_id=candidate.id,
            compiler_version="v3-plan-compiler-v1",
            validator_version="v3-integrity-validator-v1",
            status_code="PASS",
            violation_codes=(),
            meaningful_difference_codes=None,
            validation_hash=HASH_C,
        )
        repo.save_integrity_validation(
            postgres_session, decision_run_id=run.id, validation=validation, now=NOW
        )
        bundle = repo.get_audit_bundle(postgres_session, run.id)
        assert [item["agent_type_code"] for item in bundle.proposals] == [
            "TRAINING",
            "RECOVERY",
            "FEASIBILITY",
        ]
        assert bundle.integrity_validations[0]["plan_candidate_id"] == candidate.id

        legacy, _ = _new_run(postgres_session)
        legacy_proposal = AgentProposalRecord(
            id=uuid4(),
            decision_run_id=legacy.id,
            agent_type_code="SAFETY",
            proposal_status_code="READY",
            schema_version="agent-proposal-v1",
            proposal_payload={"recommended_action_code": "KEEP"},
            created_at=NOW,
        )
        postgres_session.add(legacy_proposal)
        postgres_session.flush()
        assert legacy_proposal.proposal_hash is None
        assert legacy_proposal.provider_code is None


@pytest.mark.integration
def test_v3_rejects_conflicts_constraints_privacy_and_partial_writes(
    postgres_session: Session,
) -> None:
    repo = V3DecisionRepository()
    with postgres_session.begin():
        run, exercise = _new_run(postgres_session)
        _configure_root(repo, postgres_session, run)
        artifacts = _artifacts(run, exercise)
        invalid = RootArtifactsWrite(
            envelope=ConstraintEnvelopeWrite(
                **{
                    **artifacts.envelope.__dict__,
                    "envelope_payload": {"pain_intensity_score": 7},
                }
            ),
            pool=artifacts.pool,
            retrieval=artifacts.retrieval,
        )
        with pytest.raises(ValueError, match="forbidden field"):
            repo.save_root_artifacts(
                postgres_session,
                root_decision_run_id=run.id,
                artifacts=invalid,
                now=NOW,
            )
        assert postgres_session.scalar(select(func.count(DecisionConstraintEnvelopeRecord.id))) == 0

        repo.save_root_artifacts(
            postgres_session,
            root_decision_run_id=run.id,
            artifacts=artifacts,
            now=NOW,
        )
        changed = RootArtifactsWrite(
            envelope=artifacts.envelope,
            pool=ExercisePoolWrite(**{**artifacts.pool.__dict__, "pool_hash": HASH_E}),
            retrieval=artifacts.retrieval,
        )
        with pytest.raises(V3PersistenceConflictError):
            repo.save_root_artifacts(
                postgres_session,
                root_decision_run_id=run.id,
                artifacts=changed,
                now=NOW,
            )
        with pytest.raises(ValueError, match="0 or 1"):
            repo.save_coordination_attempt(
                postgres_session,
                decision_run_id=run.id,
                attempt=CoordinationAttemptWrite(
                    attempt_number=2,
                    status_code="FAILED",
                    input_hash=HASH_A,
                    coordinator_schema_version="plan-spec-v1",
                    model_provider_code="TEST_PROVIDER",
                    model_code="TEST_MODEL_V1",
                    prompt_version="v3-coordinator-prompt-v1",
                    plan_spec=None,
                    output_hash=None,
                    repair_violation_codes=None,
                    failure_code="COORDINATOR_FAILED",
                ),
                now=NOW,
            )


@pytest.mark.integration
def test_v3_account_delete_cascades_all_user_linked_audit_rows(
    postgres_session: Session,
) -> None:
    repo = V3DecisionRepository()
    with postgres_session.begin():
        run, exercise = _new_run(postgres_session)
        user_id = run.user_id
        _configure_root(repo, postgres_session, run)
        repo.save_root_artifacts(
            postgres_session,
            root_decision_run_id=run.id,
            artifacts=_artifacts(run, exercise),
            now=NOW,
        )
        repo.save_agent_proposals(
            postgres_session,
            decision_run_id=run.id,
            proposals=_proposals(exercise.id),
            now=NOW,
        )
        postgres_session.delete(postgres_session.get(User, user_id))
        postgres_session.flush()
        assert postgres_session.scalar(select(func.count(DecisionRun.id))) == 0
        assert postgres_session.scalar(select(func.count(DecisionConstraintEnvelopeRecord.id))) == 0
        assert postgres_session.scalar(select(func.count(DecisionExercisePoolRecord.id))) == 0
        assert postgres_session.scalar(select(func.count(DecisionExerciseRetrievalRecord.id))) == 0
        assert postgres_session.scalar(select(func.count(AgentProposalRecord.id))) == 0


@pytest.mark.integration
def test_v3_failed_caller_transaction_leaves_no_partial_root_artifacts(
    postgres_session: Session,
) -> None:
    repo = V3DecisionRepository()
    with postgres_session.begin():
        run, exercise = _new_run(postgres_session)
        _configure_root(repo, postgres_session, run)
    with pytest.raises(RuntimeError, match="synthetic transaction failure"):
        with postgres_session.begin():
            repo.save_root_artifacts(
                postgres_session,
                root_decision_run_id=run.id,
                artifacts=_artifacts(run, exercise),
                now=NOW,
            )
            raise RuntimeError("synthetic transaction failure")
    assert postgres_session.scalar(select(func.count(DecisionConstraintEnvelopeRecord.id))) == 0
    assert postgres_session.scalar(select(func.count(DecisionExercisePoolRecord.id))) == 0
    assert postgres_session.scalar(select(func.count(DecisionExerciseRetrievalRecord.id))) == 0
    assert postgres_session.scalar(select(func.count(DecisionCoordinationAttemptRecord.id))) == 0
    assert postgres_session.scalar(select(func.count(PlanIntegrityValidationRecord.id))) == 0


@pytest.mark.integration
def test_v3_physical_unique_check_and_coordination_validation_fk_constraints(
    postgres_session: Session,
) -> None:
    repo = V3DecisionRepository()
    with postgres_session.begin():
        run, exercise = _new_run(postgres_session)
        _configure_root(repo, postgres_session, run)
        repo.save_root_artifacts(
            postgres_session,
            root_decision_run_id=run.id,
            artifacts=_artifacts(run, exercise),
            now=NOW,
        )
        with pytest.raises(IntegrityError), postgres_session.begin_nested():
            postgres_session.add(
                DecisionConstraintEnvelopeRecord(
                    id=uuid4(),
                    root_decision_run_id=run.id,
                    input_hash=HASH_A,
                    envelope_schema_version="constraint-envelope-v3",
                    safety_policy_version="safety-policy-v1",
                    policy_version_id=run.policy_version_id,
                    safety_rule_version="safety-policy-v1",
                    duration_rule_version="duration-rule-v1",
                    plan_generation_allowed=True,
                    required_action_code=None,
                    veto=False,
                    envelope_payload={"schema_version": "constraint-envelope-v3"},
                    envelope_hash=HASH_B,
                    expires_at=NOW + timedelta(hours=1),
                    created_at=NOW,
                )
            )
            postgres_session.flush()

        with pytest.raises(IntegrityError), postgres_session.begin_nested():
            postgres_session.add(
                DecisionCoordinationAttemptRecord(
                    id=uuid4(),
                    decision_run_id=run.id,
                    attempt_number=2,
                    status_code="FAILED",
                    input_hash=HASH_A,
                    coordinator_schema_version="plan-spec-v1",
                    model_provider_code="TEST_PROVIDER",
                    model_code="TEST_MODEL_V1",
                    prompt_version="v3-coordinator-prompt-v1",
                    plan_spec=None,
                    output_hash=None,
                    repair_violation_codes=[],
                    failure_code="COORDINATOR_FAILED",
                    created_at=NOW,
                )
            )
            postgres_session.flush()

        attempt_id = repo.save_coordination_attempt(
            postgres_session,
            decision_run_id=run.id,
            attempt=CoordinationAttemptWrite(
                attempt_number=0,
                status_code="FAILED",
                input_hash=HASH_A,
                coordinator_schema_version="plan-spec-v1",
                model_provider_code="TEST_PROVIDER",
                model_code="TEST_MODEL_V1",
                prompt_version="v3-coordinator-prompt-v1",
                plan_spec=None,
                output_hash=None,
                repair_violation_codes=None,
                failure_code="COORDINATOR_FAILED",
            ),
            now=NOW,
        )
        with pytest.raises(IntegrityError), postgres_session.begin_nested():
            postgres_session.add(
                PlanIntegrityValidationRecord(
                    id=uuid4(),
                    decision_run_id=run.id,
                    coordination_attempt_id=attempt_id,
                    coordination_attempt_number=1,
                    plan_candidate_id=None,
                    compiler_version="v3-plan-compiler-v1",
                    validator_version="v3-integrity-validator-v1",
                    status_code="FAILED",
                    violation_codes=["REPAIR_ATTEMPT_EXHAUSTED"],
                    meaningful_difference_codes=None,
                    validation_hash=HASH_C,
                    created_at=NOW,
                )
            )
            postgres_session.flush()
