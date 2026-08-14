import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import BodyArea, Location
from backend.app.db.models.checkin import (
    DailyContext,
    DailyContextAdverseReaction,
    DailyContextDiscomfort,
)
from backend.app.db.models.identity import User
from backend.app.db.repositories.checkin import DailyContextRepository
from backend.app.modules.checkins.schemas import DailyContextUpsertRequest
from backend.app.modules.checkins.service import DailyContextService, StaleContextError
from backend.app.modules.identity.codes import (
    IDENTITY_CODE_SET_VERSION,
    PremiumStatusCode,
    UserStatusCode,
)

ALEMBIC_CONFIG = Path("backend/alembic.ini")
NOW = datetime(2026, 8, 14, 3, 0, tzinfo=UTC)
LOCAL_DATE = date(2026, 8, 14)


@pytest.fixture
def postgres_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(test_database_url).database.endswith("_test"):
        pytest.fail("Daily context tests require a dedicated *_test database")
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")
    engine: Engine = create_engine(test_database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()
        get_settings.cache_clear()


def _request(*, discomforts: list[dict[str, str]]) -> DailyContextUpsertRequest:
    return DailyContextUpsertRequest.model_validate(
        {
            "fatigue_level_code": "MODERATE",
            "requested_duration_minutes": 40,
            "duration_adjustment_source_code": "PROFILE",
            "location_code": "HOME",
            "sleep_minutes": None,
            "fasting_state_code": None,
            "hydration_state_code": None,
            "discomforts": discomforts,
            "adverse_reaction_codes": ["CHEST_DISCOMFORT"] if discomforts else [],
        }
    )


@pytest.mark.integration
def test_daily_context_persists_replaces_relations_and_locks_version(
    postgres_session: Session,
) -> None:
    user_id = uuid4()
    postgres_session.add_all(
        [
            User(
                id=user_id,
                status_code=UserStatusCode.ACTIVE,
                code_set_version=IDENTITY_CODE_SET_VERSION,
                last_active_at=NOW,
                created_at=NOW,
                updated_at=NOW,
                ai_trial_started_at=NOW,
                ai_trial_ends_at=NOW + timedelta(days=7),
                premium_status_code=PremiumStatusCode.NOT_AVAILABLE,
            ),
            Location(code="HOME", code_set_version="mvp-v1"),
            BodyArea(code="KNEE", code_set_version="mvp-v1"),
        ]
    )
    postgres_session.flush()
    postgres_session.commit()
    service = DailyContextService(DailyContextRepository(), clock=lambda: NOW)
    first = service.replace(
        postgres_session,
        user_id,
        LOCAL_DATE,
        _request(discomforts=[{"body_area_code": "KNEE", "severity_code": "MILD"}]),
        uuid4(),
        None,
    )
    second = service.replace(
        postgres_session, user_id, LOCAL_DATE, _request(discomforts=[]), uuid4(), 1
    )

    assert first.id == second.id
    assert second.context_version == 2
    with pytest.raises(StaleContextError):
        service.replace(postgres_session, user_id, LOCAL_DATE, _request(discomforts=[]), uuid4(), 1)
    assert postgres_session.scalar(select(func.count()).select_from(DailyContext)) == 1
    assert postgres_session.scalar(select(func.count()).select_from(DailyContextDiscomfort)) == 0
    assert (
        postgres_session.scalar(select(func.count()).select_from(DailyContextAdverseReaction)) == 0
    )
