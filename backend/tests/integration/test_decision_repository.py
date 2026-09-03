import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, selectinload

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import (
    CatalogVersion,
    Exercise,
    ExerciseAlternative,
    ExerciseLocation,
    ExerciseSafetyRule,
)
from backend.app.db.models.decision import (
    AgentProposalRecord,
    AgentProposalRevisionRecord,
    AgentReviewEventRecord,
    DecisionDeliberationRecord,
    DecisionExplanationRecord,
    DecisionOption,
    DecisionRun,
    PlanCandidate,
    SafetyReview,
)
from backend.app.db.models.identity import User
from backend.app.db.models.profile import (
    UserAttentionArea,
    UserAvailableLocation,
    UserEquipment,
    UserProfile,
)
from backend.app.db.models.routine import Routine, RoutineDay
from backend.app.db.repositories.checkin import DailyContextRepository
from backend.app.db.repositories.decision import DecisionRepository
from backend.app.db.repositories.deliberation import (
    DeliberationRepository,
    ProposalReferenceWrite,
    ReviewEventWrite,
    RevisedProposalWrite,
    canonical_payload_hash,
)
from backend.app.db.repositories.profile import ProfileRepository
from backend.app.db.repositories.routine import RoutineRepository
from backend.app.domain.agents.contracts import (
    AGENT_PROPOSAL_SCHEMA_VERSION,
    AgentProposal,
    RecommendedActionCode,
)
from backend.app.domain.agents.coordinator import (
    COORDINATOR_VERSION,
    CoordinatorCandidate,
    CoordinatorInput,
    CoordinatorResult,
    DownshiftAdjustmentCode,
    coordinate,
)
from backend.app.domain.rules.duration import (
    DURATION_RULE_VERSION,
    DurationAdjustmentSourceCode,
    DurationPlan,
    PlanItemDuration,
)
from backend.app.modules.checkins.schemas import DailyContextUpsertRequest
from backend.app.modules.checkins.service import DailyContextService
from backend.app.modules.decisions.codes import (
    DECISION_GRAPH_VERSION,
    DECISION_INPUT_SCHEMA_VERSION,
    DECISION_POLICY_VERSION,
)
from backend.app.modules.decisions.schemas import DecisionCreateRequest
from backend.app.modules.decisions.service import DecisionFailedError, DecisionService
from backend.app.modules.profiles.schemas import ProfileSettingsUpdateRequest
from backend.app.modules.profiles.service import ProfileService
from backend.app.modules.routines.schemas import RoutineCreateRequest
from backend.app.modules.routines.service import RoutineService
from backend.scripts.demo_seed import seed_catalog

ALEMBIC_CONFIG = Path("backend/alembic.ini")
NOW = datetime(2026, 8, 17, 3, 0, tzinfo=UTC)
LOCAL_DATE = date(2026, 8, 17)


class FailingDecisionRepository(DecisionRepository):
    def persist(self, session: Session, **values: Any) -> UUID:
        super().persist(session, **values)
        session.flush()
        raise RuntimeError("synthetic persist failure")


@pytest.fixture
def postgres_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    test_database_url = os.getenv("TEST_DATABASE_URL", "")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not (make_url(test_database_url).database or "").endswith("_test"):
        pytest.fail("Decision repository tests require a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")

    engine: Engine = create_engine(test_database_url)
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


def _add_user(
    session: Session,
    *,
    attention_areas: tuple[tuple[str, bool], ...],
) -> UUID:
    user_id = uuid4()
    with session.begin():
        session.add(
            User(
                id=user_id,
                status_code="ACTIVE",
                code_set_version="identity-mvp-v1",
                last_active_at=NOW,
                ai_trial_started_at=NOW,
                ai_trial_ends_at=NOW + timedelta(days=7),
                premium_status_code="NOT_AVAILABLE",
            )
        )
        session.add(
            UserProfile(
                user_id=user_id,
                protected_birthdate="synthetic-protected-value",
                nickname="합성 사용자",
                primary_goal_code="GENERAL_FITNESS",
                experience_level_code="BEGINNER",
                timezone="Asia/Seoul",
                preferred_location_code="HOME",
                default_requested_duration_minutes=30,
                desired_weekly_workout_count=3,
                coaching_style_code="SUPPORTIVE",
                height_cm=175.0,
                weight_kg=70.0,
                sex_code="PREFER_NOT_TO_SAY",
                code_set_version="profile-mvp-v1",
                profile_version=1,
            )
        )
        session.add(UserAvailableLocation(user_id=user_id, location_code="HOME"))
        session.add_all(
            UserEquipment(user_id=user_id, equipment_code=code)
            for code in ("BODYWEIGHT", "MAT", "RESISTANCE_BAND")
        )
        session.add_all(
            UserAttentionArea(
                user_id=user_id,
                body_area_code=body_area_code,
                is_active=is_active,
            )
            for body_area_code, is_active in attention_areas
        )
    return user_id


def _prepare_decision_inputs(
    session: Session,
    user_id: UUID,
    *,
    fatigue_level_code: str = "LOW",
    discomforts: list[dict[str, str]] | None = None,
) -> UUID:
    RoutineService(RoutineRepository(), clock=lambda: NOW).create(
        session,
        user_id,
        RoutineCreateRequest(effective_from=LOCAL_DATE, goal_code="GENERAL_FITNESS"),
        uuid4(),
    )
    context = DailyContextService(DailyContextRepository(), clock=lambda: NOW).replace(
        session,
        user_id,
        LOCAL_DATE,
        DailyContextUpsertRequest.model_validate(
            {
                "fatigue_level_code": fatigue_level_code,
                "requested_duration_minutes": 30,
                "duration_adjustment_source_code": "PROFILE",
                "location_code": "HOME",
                "discomforts": discomforts or [],
                "adverse_reaction_codes": [],
            }
        ),
        uuid4(),
        None,
    )
    return context.id


def _install_synthetic_safety_data(
    session: Session,
    user_id: UUID,
    *,
    severity_code: str,
    effect_code: str,
    with_alternative: bool = False,
) -> tuple[UUID, UUID | None]:
    routine = session.scalar(
        select(Routine)
        .options(selectinload(Routine.days).selectinload(RoutineDay.items))
        .where(Routine.user_id == user_id, Routine.status_code == "ACTIVE")
    )
    assert routine is not None
    day = routine.days[
        (LOCAL_DATE.toordinal() - routine.effective_from.toordinal()) % len(routine.days)
    ]
    source_item = next(item for item in day.items if item.phase_code == "MAIN")
    source_id = source_item.exercise_id
    rule_set_version = f"golden-integration-{severity_code.lower()}-{effect_code.lower()}"
    session.add(
        ExerciseSafetyRule(
            catalog_version_id=routine.catalog_version_id,
            exercise_id=source_id,
            movement_pattern_code=None,
            body_area_code="KNEE",
            body_part_role_code="PRIMARY",
            minimum_severity_code=severity_code,
            maximum_severity_code=severity_code,
            effect_code=effect_code,
            reason_code="DIRECT_JOINT_LOAD",
            review_status_code="DOMAIN_APPROVED",
            rule_version="golden-integration-v1",
            rule_set_version_code=rule_set_version,
            production_eligible=True,
            source_manifest_hash="0" * 64,
            source_metadata={"synthetic": True, "scope": "integration-test"},
            created_at=NOW,
            updated_at=NOW,
        )
    )
    if not with_alternative:
        session.flush()
        session.commit()
        return source_id, None

    existing_ids = {item.exercise_id for item in day.items}
    alternative = session.scalar(
        select(Exercise)
        .join(ExerciseLocation, ExerciseLocation.exercise_id == Exercise.id)
        .where(
            Exercise.catalog_version_id == routine.catalog_version_id,
            Exercise.review_status_code == "DOMAIN_APPROVED",
            Exercise.id.not_in(existing_ids),
            ExerciseLocation.location_code == "HOME",
        )
        .order_by(Exercise.stable_code)
    )
    assert alternative is not None
    alternative_id = alternative.id
    session.add(
        ExerciseAlternative(
            source_exercise_id=source_id,
            alternative_exercise_id=alternative_id,
            reason_code="DISCOMFORT",
            goal_preservation_code="GENERAL_FITNESS",
            difficulty_delta=0,
            review_status_code="DOMAIN_APPROVED",
            rule_version="golden-integration-v1",
            alternative_set_version_code="golden-integration-alternatives-v1",
            production_eligible=True,
            source_manifest_hash="1" * 64,
            source_metadata={"synthetic": True, "scope": "integration-test"},
            created_at=NOW,
        )
    )
    session.flush()
    session.commit()
    return source_id, alternative_id


def _replay_stored_decision(session: Session, run: DecisionRun) -> CoordinatorResult:
    catalog = session.get(CatalogVersion, run.catalog_version_id)
    assert catalog is not None
    proposals = tuple(
        AgentProposal.model_validate_json(json.dumps(record.proposal_payload))
        for record in sorted(run.proposals, key=lambda value: value.agent_type_code)
    )
    candidates = tuple(
        CoordinatorCandidate(
            candidate_id=candidate.candidate_code,
            action_code=RecommendedActionCode(candidate.action_code),
            exercise_ids=tuple(sorted({str(item.exercise_id) for item in candidate.items})),
            goal_tags=tuple(candidate.goal_tags),
            downshift_adjustment_codes=(
                (DownshiftAdjustmentCode.INTENSITY_REDUCED,)
                if candidate.action_code == "DOWNSHIFT"
                else ()
            ),
            catalog_version=catalog.version_code,
            duration_plan=DurationPlan(
                setup_seconds=candidate.setup_seconds,
                warmup_seconds=candidate.warmup_seconds,
                items=tuple(
                    PlanItemDuration(
                        item.work_seconds,
                        item.rest_seconds,
                        item.transition_seconds,
                    )
                    for item in candidate.items
                    if item.phase_code == "MAIN"
                ),
                cooldown_seconds=candidate.cooldown_seconds,
            ),
        )
        for candidate in sorted(run.candidates, key=lambda value: value.candidate_code)
    )
    snapshot = run.input_snapshot
    return coordinate(
        CoordinatorInput(
            proposals=proposals,
            candidates=candidates,
            profile_duration_minutes=snapshot["profile"]["default_requested_duration_minutes"],
            requested_duration_minutes=snapshot["requested_duration_minutes"],
            duration_adjustment_source_code=DurationAdjustmentSourceCode(
                snapshot["duration_adjustment_source_code"]
            ),
            policy_version=proposals[0].policy_version,
            catalog_version=catalog.version_code,
            catalog_status_code="ACTIVE",
            catalog_review_status_code="DOMAIN_APPROVED",
            catalog_production_eligible=True,
            catalog_activated=True,
            safety_rule_version=run.safety_rule_version,
            duration_rule_version=run.duration_rule_version,
            coordinator_version=run.coordinator_version,
        )
    )


def _request(daily_context_id: UUID) -> DecisionCreateRequest:
    return DecisionCreateRequest(
        local_date=LOCAL_DATE,
        daily_context_id=daily_context_id,
        expected_context_version=1,
    )


def _stored_run(session: Session, user_id: UUID) -> DecisionRun:
    run = session.scalar(
        select(DecisionRun)
        .options(
            selectinload(DecisionRun.proposals),
            selectinload(DecisionRun.candidates).selectinload(PlanCandidate.items),
            selectinload(DecisionRun.safety_reviews),
            selectinload(DecisionRun.options),
        )
        .where(DecisionRun.user_id == user_id)
    )
    assert run is not None
    return run


def _decision_record_counts(session: Session) -> tuple[int, int, int, int, int, int]:
    return tuple(
        int(session.scalar(select(func.count()).select_from(model)) or 0)
        for model in (
            DecisionRun,
            AgentProposalRecord,
            PlanCandidate,
            SafetyReview,
            DecisionOption,
            DecisionExplanationRecord,
        )
    )  # type: ignore[return-value]


@pytest.mark.integration
def test_completed_decision_is_reused_for_an_identical_context_input(
    postgres_session: Session,
) -> None:
    user_id = _add_user(postgres_session, attention_areas=())
    context_id = _prepare_decision_inputs(postgres_session, user_id)
    service = DecisionService(DecisionRepository(), clock=lambda: NOW)

    first = service.create(postgres_session, user_id, _request(context_id), uuid4())
    repeated = service.create(postgres_session, user_id, _request(context_id), uuid4())

    assert repeated.decision_id == first.decision_id
    assert (
        postgres_session.scalar(
            select(func.count()).select_from(DecisionRun).where(DecisionRun.user_id == user_id)
        )
        == 1
    )


@pytest.mark.integration
def test_new_daily_context_version_creates_a_new_decision(
    postgres_session: Session,
) -> None:
    user_id = _add_user(postgres_session, attention_areas=())
    context_id = _prepare_decision_inputs(postgres_session, user_id)
    service = DecisionService(DecisionRepository(), clock=lambda: NOW)
    first = service.create(postgres_session, user_id, _request(context_id), uuid4())
    updated = DailyContextService(DailyContextRepository(), clock=lambda: NOW).replace(
        postgres_session,
        user_id,
        LOCAL_DATE,
        DailyContextUpsertRequest.model_validate(
            {
                "fatigue_level_code": "MODERATE",
                "requested_duration_minutes": 30,
                "duration_adjustment_source_code": "PROFILE",
                "location_code": "HOME",
                "discomforts": [],
                "adverse_reaction_codes": [],
            }
        ),
        uuid4(),
        1,
    )
    second = service.create(
        postgres_session,
        user_id,
        DecisionCreateRequest(
            local_date=LOCAL_DATE,
            daily_context_id=updated.id,
            expected_context_version=updated.context_version,
        ),
        uuid4(),
    )

    assert second.decision_id != first.decision_id
    assert (
        postgres_session.scalar(
            select(func.count()).select_from(DecisionRun).where(DecisionRun.user_id == user_id)
        )
        == 2
    )


@pytest.mark.integration
def test_concurrent_identical_requests_create_one_completed_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_database_url = os.getenv("TEST_DATABASE_URL", "")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not (make_url(test_database_url).database or "").endswith("_test"):
        pytest.fail("Decision repository tests require a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")
    engine = create_engine(test_database_url)
    user_id: UUID | None = None
    try:
        with Session(engine) as setup_session:
            with setup_session.begin():
                seed_catalog(setup_session, NOW)
            user_id = _add_user(setup_session, attention_areas=())
            context_id = _prepare_decision_inputs(setup_session, user_id)

        request = _request(context_id)

        def create_in_worker(_: int) -> UUID:
            with Session(engine) as worker_session:
                return (
                    DecisionService(DecisionRepository(), clock=lambda: NOW)
                    .create(worker_session, user_id, request, uuid4())
                    .decision_id
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            decision_ids = list(executor.map(create_in_worker, range(2)))

        assert decision_ids[0] == decision_ids[1]
        with Session(engine) as verification_session:
            assert (
                verification_session.scalar(
                    select(func.count())
                    .select_from(DecisionRun)
                    .where(DecisionRun.user_id == user_id)
                )
                == 1
            )
    finally:
        if user_id is not None:
            with Session(engine) as cleanup_session:
                cleanup_session.execute(delete(User).where(User.id == user_id))
                cleanup_session.commit()
        engine.dispose()
        get_settings.cache_clear()


@pytest.mark.integration
def test_mild_caution_result_round_trips_with_four_proposals_and_replay(
    postgres_session: Session,
) -> None:
    owner_id = _add_user(postgres_session, attention_areas=())
    context_id = _prepare_decision_inputs(
        postgres_session,
        owner_id,
        discomforts=[{"body_area_code": "KNEE", "severity_code": "MILD"}],
    )
    source_id, _ = _install_synthetic_safety_data(
        postgres_session,
        owner_id,
        severity_code="MILD",
        effect_code="CAUTION",
    )

    response = DecisionService(DecisionRepository(), clock=lambda: NOW).create(
        postgres_session,
        owner_id,
        _request(context_id),
        uuid4(),
    )
    run = _stored_run(postgres_session, owner_id)
    safety = run.safety_reviews[0]
    selected = next(candidate for candidate in run.candidates if candidate.selected)

    assert response.action_code == "DOWNSHIFT"
    assert response.safety_status_code == "REVISE"
    assert response.requested_duration_minutes == 30
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 1800
    assert len(run.proposals) == 4
    assert run.input_schema_version == DECISION_INPUT_SCHEMA_VERSION
    assert run.graph_version == DECISION_GRAPH_VERSION
    assert run.coordinator_version == COORDINATOR_VERSION
    assert run.duration_rule_version == DURATION_RULE_VERSION
    assert run.safety_rule_version == "golden-integration-mild-caution"
    assert all(record.schema_version == AGENT_PROPOSAL_SCHEMA_VERSION for record in run.proposals)
    assert all(
        record.proposal_payload["policy_version"] == DECISION_POLICY_VERSION
        for record in run.proposals
    )
    assert "proposals" not in run.coordinator_result
    assert "date_of_birth" not in str(run.input_snapshot)
    assert "raw_health" not in str(run.input_snapshot)
    assert all(
        record.proposal_payload["requested_duration_minutes"] == 30 for record in run.proposals
    )
    assert all(
        record.proposal_payload["estimated_duration_seconds"] == 1800 for record in run.proposals
    )
    assert safety.safety_status_code == "REVISE"
    assert safety.vetoed is False
    assert safety.excluded_exercise_ids == []
    assert selected.action_code == "DOWNSHIFT"
    assert selected.estimated_duration_seconds == 1800
    assert str(source_id) in {str(item.exercise_id) for item in selected.items}
    assert (
        _replay_stored_decision(postgres_session, run).model_dump(mode="json")
        == run.coordinator_result
    )


@pytest.mark.integration
def test_moderate_approved_alternative_round_trips_without_reintroducing_exclusion(
    postgres_session: Session,
) -> None:
    owner_id = _add_user(postgres_session, attention_areas=())
    context_id = _prepare_decision_inputs(
        postgres_session,
        owner_id,
        discomforts=[{"body_area_code": "KNEE", "severity_code": "MODERATE"}],
    )
    source_id, alternative_id = _install_synthetic_safety_data(
        postgres_session,
        owner_id,
        severity_code="MODERATE",
        effect_code="EXCLUDE",
        with_alternative=True,
    )
    assert alternative_id is not None
    assert not postgres_session.in_transaction()

    response = DecisionService(DecisionRepository(), clock=lambda: NOW).create(
        postgres_session,
        owner_id,
        _request(context_id),
        uuid4(),
    )
    run = _stored_run(postgres_session, owner_id)
    safety = run.safety_reviews[0]
    selected = next(candidate for candidate in run.candidates if candidate.selected)
    selected_exercise_ids = {item.exercise_id for item in selected.items}
    relation = postgres_session.scalar(
        select(ExerciseAlternative).where(
            ExerciseAlternative.source_exercise_id == source_id,
            ExerciseAlternative.alternative_exercise_id == alternative_id,
        )
    )
    alternative = postgres_session.get(Exercise, alternative_id)

    assert relation is not None
    assert relation.reason_code == "DISCOMFORT"
    assert relation.review_status_code == "DOMAIN_APPROVED"
    assert relation.production_eligible is True
    assert alternative is not None
    assert alternative.review_status_code == "DOMAIN_APPROVED"
    assert response.action_code == "CHANGE"
    assert response.safety_status_code == "REVISE"
    assert response.requested_duration_minutes == 30
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 1800
    assert len(run.proposals) == 4
    assert safety.vetoed is True
    assert safety.excluded_exercise_ids == [str(source_id)]
    assert source_id not in selected_exercise_ids
    assert alternative_id in selected_exercise_ids
    assert selected.action_code == "CHANGE"
    assert selected.estimated_duration_seconds == 1800
    assert all(
        record.proposal_payload["requested_duration_minutes"] == 30 for record in run.proposals
    )
    assert all(
        record.proposal_payload["estimated_duration_seconds"] == 1800 for record in run.proposals
    )
    assert (
        _replay_stored_decision(postgres_session, run).model_dump(mode="json")
        == run.coordinator_result
    )


@pytest.mark.integration
def test_chronic_attention_snapshot_is_canonical_immutable_and_replayable(
    postgres_session: Session,
) -> None:
    owner_id = _add_user(
        postgres_session,
        attention_areas=(("KNEE", True),),
    )
    context_id = _prepare_decision_inputs(postgres_session, owner_id)
    _install_synthetic_safety_data(
        postgres_session,
        owner_id,
        severity_code="MILD",
        effect_code="CAUTION",
    )

    response = DecisionService(DecisionRepository(), clock=lambda: NOW).create(
        postgres_session,
        owner_id,
        _request(context_id),
        uuid4(),
    )
    run = _stored_run(postgres_session, owner_id)
    old_snapshot = json.loads(json.dumps(run.input_snapshot))

    assert response.action_code == "DOWNSHIFT"
    assert response.safety_status_code == "REVISE"
    assert response.requested_duration_minutes == 30
    assert response.final_plan is not None
    assert response.final_plan.estimated_duration_seconds == 1800
    assert run.input_snapshot["discomforts"] == []
    assert run.input_snapshot["profile"]["attention_area_codes"] == ["KNEE"]
    assert len(run.proposals) == 4
    assert run.safety_reviews[0].vetoed is False
    assert run.safety_reviews[0].excluded_exercise_ids == []
    assert (
        _replay_stored_decision(postgres_session, run).model_dump(mode="json")
        == run.coordinator_result
    )
    postgres_session.rollback()

    ProfileService(
        ProfileRepository(),
        None,
        primary_goal_codes=("GENERAL_FITNESS",),
        experience_level_codes=("BEGINNER",),
        consent_policy_version=None,
        clock=lambda: NOW,
    ).update_profile_settings(
        postgres_session,
        owner_id,
        ProfileSettingsUpdateRequest.model_validate({"attention_area_codes": []}),
        uuid4(),
        1,
    )
    unchanged = _stored_run(postgres_session, owner_id)

    assert unchanged.input_snapshot == old_snapshot
    assert unchanged.input_snapshot["profile"]["attention_area_codes"] == ["KNEE"]


@pytest.mark.integration
def test_decision_repository_assembles_and_persists_active_profile_attention_areas(
    postgres_session: Session,
) -> None:
    owner_id = _add_user(
        postgres_session,
        attention_areas=(("SHOULDER", True), ("LOWER_BACK", False), ("KNEE", True)),
    )
    empty_owner_id = _add_user(postgres_session, attention_areas=())
    _add_user(postgres_session, attention_areas=(("HIP", True),))
    owner_context_id = _prepare_decision_inputs(postgres_session, owner_id)
    empty_context_id = _prepare_decision_inputs(postgres_session, empty_owner_id)
    repository = DecisionRepository()

    assembly = repository.assemble(postgres_session, owner_id, owner_context_id)
    assert assembly is not None
    assert assembly.context.attention_area_codes == ("KNEE", "SHOULDER")
    assert assembly.context.profile_preferred_location_code == "HOME"
    assert assembly.context.snapshot()["profile"]["attention_area_codes"] == [
        "KNEE",
        "SHOULDER",
    ]
    postgres_session.rollback()

    empty_assembly = repository.assemble(postgres_session, empty_owner_id, empty_context_id)
    assert empty_assembly is not None
    assert empty_assembly.context.attention_area_codes == ()
    postgres_session.rollback()

    with pytest.raises(DecisionFailedError):
        DecisionService(repository, clock=lambda: NOW).create(
            postgres_session,
            owner_id,
            _request(owner_context_id),
            uuid4(),
        )
    stored = postgres_session.scalar(select(DecisionRun).where(DecisionRun.user_id == owner_id))
    assert stored is not None
    assert stored.input_schema_version == DECISION_INPUT_SCHEMA_VERSION == "decision-input-v5"
    assert stored.graph_version == DECISION_GRAPH_VERSION == "decision-graph-v2"
    assert stored.input_snapshot["profile"]["attention_area_codes"] == ["KNEE", "SHOULDER"]
    assert tuple(stored.input_snapshot["profile"]["attention_area_codes"]) == (
        "KNEE",
        "SHOULDER",
    )
    assert len(stored.proposals) == 4
    assert "proposals" not in stored.coordinator_result
    assert stored.status_code == "FAILED"
    postgres_session.rollback()
    DecisionService(repository, clock=lambda: NOW).create(
        postgres_session,
        empty_owner_id,
        _request(empty_context_id),
        uuid4(),
    )
    explanation = postgres_session.scalar(
        select(DecisionExplanationRecord)
        .join(DecisionRun, DecisionRun.id == DecisionExplanationRecord.decision_run_id)
        .where(DecisionRun.user_id == empty_owner_id)
    )
    assert explanation is not None
    # LLM 미설정 환경에서는 검수된 템플릿 문구와 폴백 사유만 남는다.
    assert explanation.source_code == "TEMPLATE"
    assert explanation.template_version == "decision-explanation-template-v1"
    assert explanation.prompt_version is None
    assert explanation.model_code is None
    assert explanation.fallback_reason_code == "LLM_DISABLED"
    assert explanation.coaching_style_code == "SUPPORTIVE"
    assert [summary["agent_type_code"] for summary in explanation.agent_summaries] == [
        "TRAINING",
        "RECOVERY",
        "SAFETY",
        "FEASIBILITY",
        "COORDINATOR",
    ]
    resumed = repository.get_response_for_date(postgres_session, empty_owner_id, LOCAL_DATE)
    assert resumed is not None
    assert resumed["status_code"] == "COMPLETED"
    assert repository.get_response_for_date(postgres_session, owner_id, LOCAL_DATE) is None
    record_counts = _decision_record_counts(postgres_session)
    postgres_session.rollback()

    with pytest.raises(RuntimeError, match="synthetic persist failure"):
        DecisionService(FailingDecisionRepository(), clock=lambda: NOW).create(
            postgres_session,
            owner_id,
            _request(owner_context_id),
            uuid4(),
        )
    assert _decision_record_counts(postgres_session) == record_counts


@pytest.mark.integration
def test_profile_update_changes_only_future_decision_context_snapshots(
    postgres_session: Session,
) -> None:
    owner_id = _add_user(postgres_session, attention_areas=())
    context_id = _prepare_decision_inputs(postgres_session, owner_id)
    repository = DecisionRepository()
    DecisionService(repository, clock=lambda: NOW).create(
        postgres_session,
        owner_id,
        _request(context_id),
        uuid4(),
    )
    stored = postgres_session.scalar(select(DecisionRun).where(DecisionRun.user_id == owner_id))
    assert stored is not None
    old_snapshot = stored.input_snapshot
    assert old_snapshot["profile"]["primary_goal_code"] == "GENERAL_FITNESS"
    assert old_snapshot["profile"]["preferred_location_code"] == "HOME"
    assert old_snapshot["profile"]["attention_area_codes"] == []
    postgres_session.rollback()

    ProfileService(
        ProfileRepository(),
        None,
        primary_goal_codes=("GENERAL_FITNESS", "MUSCLE_GAIN"),
        experience_level_codes=("BEGINNER",),
        consent_policy_version=None,
        clock=lambda: NOW,
    ).update_profile_settings(
        postgres_session,
        owner_id,
        ProfileSettingsUpdateRequest.model_validate(
            {
                "primary_goal_code": "MUSCLE_GAIN",
                "preferred_location_code": "GYM",
                "available_location_codes": ["GYM"],
                "attention_area_codes": ["KNEE"],
            }
        ),
        uuid4(),
        1,
    )

    updated = repository.assemble(postgres_session, owner_id, context_id)
    assert updated is not None
    assert updated.context.primary_goal_code == "MUSCLE_GAIN"
    assert updated.context.profile_preferred_location_code == "GYM"
    assert updated.context.equipment_codes == ("BODYWEIGHT", "MAT", "RESISTANCE_BAND")
    assert updated.context.attention_area_codes == ("KNEE",)
    postgres_session.rollback()

    unchanged = postgres_session.scalar(select(DecisionRun).where(DecisionRun.user_id == owner_id))
    assert unchanged is not None
    assert unchanged.input_snapshot == old_snapshot


@pytest.mark.integration
def test_deliberation_repository_separates_rounds_hashes_and_coordinator_result(
    postgres_session: Session,
) -> None:
    owner_id = _add_user(postgres_session, attention_areas=())
    context_id = _prepare_decision_inputs(postgres_session, owner_id)
    DecisionService(DecisionRepository(), clock=lambda: NOW).create(
        postgres_session,
        owner_id,
        _request(context_id),
        uuid4(),
    )
    run = _stored_run(postgres_session, owner_id)
    original_coordinator_result = json.loads(json.dumps(run.coordinator_result))
    proposals = {proposal.agent_type_code: proposal for proposal in run.proposals}
    proposal_hashes = {
        agent_type_code: canonical_payload_hash(proposal.proposal_payload)
        for agent_type_code, proposal in proposals.items()
    }
    references = tuple(
        ProposalReferenceWrite(agent_type_code, proposal_hashes[agent_type_code])
        for agent_type_code in sorted(proposal_hashes)
    )
    revised_training_payload = {
        **proposals["TRAINING"].proposal_payload,
        "preference_codes": ["PREFER_LOWER_IMPACT"],
    }
    reviews = tuple(
        ReviewEventWrite(
            agent_type_code=agent_type_code,
            review_status_code="READY" if agent_type_code == "TRAINING" else "NOT_REQUIRED",
            revision_status_code="REVISED" if agent_type_code == "TRAINING" else "NOT_REQUIRED",
            review_schema_version="agent-review-v0.1",
            reviewed_proposal_references=references,
            review_payload={
                "accepted_constraint_codes": ["RECOVERY_LOAD_CEILING"]
                if agent_type_code == "TRAINING"
                else [],
                "unresolved_conflict_codes": [],
            },
            revised_proposal=(
                RevisedProposalWrite(
                    proposal_status_code="READY",
                    proposal_schema_version="agent-proposal-v0.2",
                    proposal_payload=revised_training_payload,
                )
                if agent_type_code == "TRAINING"
                else None
            ),
        )
        for agent_type_code in ("TRAINING", "RECOVERY", "SAFETY", "FEASIBILITY")
    )

    deliberation_id = DeliberationRepository().persist(
        postgres_session,
        decision_run_id=run.id,
        deliberation_schema_version="decision-deliberation-v0.1",
        round_count=2,
        round_two_status_code="COMPLETED",
        conflict_detector_version="conflict-detector-v1",
        precedence_version="constraint-precedence-v1",
        conflict_codes=("TRAINING_RECOVERY_LOAD_CONFLICT",),
        reviews=reviews,
        now=NOW,
    )
    postgres_session.commit()

    deliberation = postgres_session.get(DecisionDeliberationRecord, deliberation_id)
    revisions = tuple(
        postgres_session.scalars(
            select(AgentProposalRevisionRecord)
            .where(AgentProposalRevisionRecord.decision_run_id == run.id)
            .order_by(
                AgentProposalRevisionRecord.round_number,
                AgentProposalRevisionRecord.agent_type_code,
            )
        )
    )
    events = tuple(
        postgres_session.scalars(
            select(AgentReviewEventRecord)
            .where(AgentReviewEventRecord.decision_run_id == run.id)
            .order_by(AgentReviewEventRecord.agent_type_code)
        )
    )
    stored_run = postgres_session.get(DecisionRun, run.id)

    assert deliberation is not None
    assert deliberation.graph_version == run.graph_version
    assert deliberation.policy_version_id == run.policy_version_id
    assert deliberation.deliberation_schema_version == "decision-deliberation-v0.1"
    assert len([revision for revision in revisions if revision.round_number == 1]) == 4
    assert len([revision for revision in revisions if revision.round_number == 2]) == 1
    assert len(events) == 4
    assert {event.review_status_code for event in events} == {"READY", "NOT_REQUIRED"}
    assert all(
        event.baseline_proposal_hash
        == next(
            revision.proposal_hash
            for revision in revisions
            if revision.round_number == 1 and revision.agent_type_code == event.agent_type_code
        )
        for event in events
    )
    assert stored_run is not None
    assert stored_run.coordinator_result == original_coordinator_result
    assert "review_payload" not in stored_run.coordinator_result

    with pytest.raises(ValueError, match="already exists"):
        DeliberationRepository().persist(
            postgres_session,
            decision_run_id=run.id,
            deliberation_schema_version="decision-deliberation-v0.1",
            round_count=2,
            round_two_status_code="COMPLETED",
            conflict_detector_version="conflict-detector-v1",
            precedence_version="constraint-precedence-v1",
            conflict_codes=("TRAINING_RECOVERY_LOAD_CONFLICT",),
            reviews=reviews,
            now=NOW,
        )
