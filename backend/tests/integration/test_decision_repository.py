import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.decision import DecisionRun
from backend.app.db.models.identity import User
from backend.app.db.models.profile import (
    UserAttentionArea,
    UserAvailableLocation,
    UserEquipment,
    UserProfile,
)
from backend.app.db.repositories.checkin import DailyContextRepository
from backend.app.db.repositories.decision import DecisionRepository
from backend.app.db.repositories.profile import ProfileRepository
from backend.app.db.repositories.routine import RoutineRepository
from backend.app.modules.checkins.schemas import DailyContextUpsertRequest
from backend.app.modules.checkins.service import DailyContextService
from backend.app.modules.decisions.codes import DECISION_INPUT_SCHEMA_VERSION
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


def _prepare_decision_inputs(session: Session, user_id: UUID) -> UUID:
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
                "fatigue_level_code": "LOW",
                "requested_duration_minutes": 30,
                "duration_adjustment_source_code": "PROFILE",
                "location_code": "HOME",
                "discomforts": [],
                "adverse_reaction_codes": [],
            }
        ),
        uuid4(),
        None,
    )
    return context.id


def _request(daily_context_id: UUID) -> DecisionCreateRequest:
    return DecisionCreateRequest(
        local_date=LOCAL_DATE,
        daily_context_id=daily_context_id,
        expected_context_version=1,
    )


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
    assert stored.input_schema_version == DECISION_INPUT_SCHEMA_VERSION == "decision-input-v3"
    assert stored.input_snapshot["profile"]["attention_area_codes"] == ["KNEE", "SHOULDER"]
    assert tuple(stored.input_snapshot["profile"]["attention_area_codes"]) == (
        "KNEE",
        "SHOULDER",
    )
    assert stored.status_code == "FAILED"
    postgres_session.rollback()
    DecisionService(repository, clock=lambda: NOW).create(
        postgres_session,
        empty_owner_id,
        _request(empty_context_id),
        uuid4(),
    )
    run_count = postgres_session.scalar(
        select(func.count()).select_from(DecisionRun).where(DecisionRun.user_id == owner_id)
    )
    postgres_session.rollback()

    with pytest.raises(RuntimeError, match="synthetic persist failure"):
        DecisionService(FailingDecisionRepository(), clock=lambda: NOW).create(
            postgres_session,
            owner_id,
            _request(owner_context_id),
            uuid4(),
        )
    assert (
        postgres_session.scalar(
            select(func.count()).select_from(DecisionRun).where(DecisionRun.user_id == owner_id)
        )
        == run_count
    )


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
                "equipment_codes": ["MAT"],
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
    assert updated.context.equipment_codes == ("MAT",)
    assert updated.context.attention_area_codes == ("KNEE",)
    postgres_session.rollback()

    unchanged = postgres_session.scalar(select(DecisionRun).where(DecisionRun.user_id == owner_id))
    assert unchanged is not None
    assert unchanged.input_snapshot == old_snapshot
