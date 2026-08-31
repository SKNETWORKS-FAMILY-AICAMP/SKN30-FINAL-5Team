import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, delete, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import (
    BodyFocus,
    CatalogVersion,
    Exercise,
    ExerciseGoalTagLink,
    ExerciseLocation,
    ExercisePrescriptionProfile,
    Location,
    MovementPattern,
    TrainingType,
)
from backend.app.db.models.identity import User
from backend.app.db.models.profile import UserAvailableLocation, UserProfile
from backend.app.db.repositories.routine import RoutineRepository
from backend.app.modules.routines.schemas import RoutineCreateRequest
from backend.app.modules.routines.service import RoutineService

ALEMBIC_CONFIG = Path("backend/alembic.ini")
NOW = datetime(2026, 8, 13, 6, 0, tzinfo=UTC)


def _database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL", "")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(database_url).database.endswith("_test"):
        pytest.fail("Routine repository tests require a dedicated *_test database")
    return database_url


def _add_user(session: Session, *, experience_level_code: str = "BEGINNER") -> UUID:
    user_id = uuid4()
    session.add(
        User(
            id=user_id,
            status_code="ACTIVE",
            code_set_version="identity-mvp-v1",
            last_active_at=NOW,
            ai_trial_started_at=NOW,
            ai_trial_ends_at=NOW + timedelta(days=14),
            premium_status_code="NOT_AVAILABLE",
        )
    )
    session.add(
        UserProfile(
            user_id=user_id,
            protected_birthdate="synthetic-protected-value",
            nickname="합성 사용자",
            primary_goal_code="GENERAL_FITNESS",
            experience_level_code=experience_level_code,
            timezone="Asia/Seoul",
            preferred_location_code="HOME",
            default_requested_duration_minutes=10,
            desired_weekly_workout_count=2,
            coaching_style_code="SUPPORTIVE",
            height_cm=None,
            weight_kg=None,
            sex_code=None,
            code_set_version="profile-mvp-v1",
            profile_version=1,
        )
    )
    session.add(UserAvailableLocation(user_id=user_id, location_code="HOME"))
    session.add(UserAvailableLocation(user_id=user_id, location_code="GYM"))
    return user_id


def _add_exercise(
    session: Session,
    catalog: CatalogVersion,
    *,
    name: str,
    phase: str,
    seconds: int,
    tier: str,
    difficulty_code: str = "BEGINNER",
) -> None:
    exercise = Exercise(
        id=uuid4(),
        catalog_version_id=catalog.id,
        stable_code=f"synthetic-{difficulty_code.lower()}-{phase.lower()}",
        name_ko=f"{difficulty_code} {name}",
        name_en=None,
        training_type_code="STRENGTH" if phase == "MAIN" else "MOBILITY",
        body_focus_code="FULL_BODY",
        primary_movement_pattern_code=("CORE_BRACE" if phase == "MAIN" else "MOBILITY_STRETCH"),
        difficulty_code=difficulty_code,
        # Deliberately opposite for BEGINNER records: recommendation must use
        # difficulty_code only while this legacy DB column still exists.
        beginner_suitable=difficulty_code == "INTERMEDIATE",
        timing_mode_code="DURATION",
        default_seconds_per_rep=None,
        default_work_seconds=seconds - 10,
        default_rest_seconds=0,
        default_transition_seconds=10,
        recovery_eligible=phase != "MAIN",
        instruction_summary_ko="합성 테스트 설명",
        form_cues_ko=[],
        instruction_content_version="synthetic-v1",
        review_status_code="DOMAIN_APPROVED",
        source_track_code="kspo",
        source_identity=f"synthetic-{difficulty_code.lower()}-{phase.lower()}",
    )
    session.add(exercise)
    session.add(ExerciseLocation(exercise_id=exercise.id, location_code="HOME"))
    session.add(
        ExerciseGoalTagLink(
            exercise_id=exercise.id,
            goal_code="GENERAL_FITNESS",
            role_eligibility_code=tier,
            review_status_code="DOMAIN_APPROVED",
        )
    )
    prescription_levels = (
        ("BEGINNER", "INTERMEDIATE") if difficulty_code == "BEGINNER" else ("INTERMEDIATE",)
    )
    for experience_level_code in prescription_levels:
        session.add(
            ExercisePrescriptionProfile(
                id=uuid4(),
                exercise_id=exercise.id,
                goal_code="GENERAL_FITNESS",
                experience_level_code=experience_level_code,
                phase_code=phase,
                sets=1,
                reps=None,
                work_seconds_per_set=seconds - 10,
                rest_seconds_per_set=0,
                intensity_code=("LOW" if experience_level_code == "BEGINNER" else "MODERATE"),
                prescription_version="synthetic-v1",
                review_status_code="DOMAIN_APPROVED",
            )
        )


def _seed(engine: Engine) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    with Session(engine) as session, session.begin():
        for model, code in (
            (TrainingType, "STRENGTH"),
            (TrainingType, "MOBILITY"),
            (BodyFocus, "FULL_BODY"),
            (MovementPattern, "CORE_BRACE"),
            (MovementPattern, "MOBILITY_STRETCH"),
            (Location, "HOME"),
            (Location, "GYM"),
        ):
            if session.get(model, code) is None:
                session.add(model(code=code, code_set_version="mvp-v1", display_name_ko=None))
        session.execute(
            update(CatalogVersion)
            .where(CatalogVersion.status_code == "ACTIVE")
            .values(
                status_code="DEPRECATED",
                production_eligible=False,
                activated_at=None,
            )
        )
        catalog = CatalogVersion(
            id=uuid4(),
            version_code=f"synthetic-approved-{uuid4()}",
            status_code="ACTIVE",
            manifest_schema_version="1.0",
            generator_version="synthetic-v1",
            code_set_version="mvp-v1",
            source_manifest_hash="a" * 64,
            source_track_code="kspo",
            review_status_code="DOMAIN_APPROVED",
            review_method_code="DOMAIN_REVIEWER",
            status_interpretation_code="PRODUCTION_APPROVED",
            production_eligible=True,
            exercise_record_count=6,
            manifest_metadata={"synthetic": True},
            activated_at=NOW,
        )
        session.add(catalog)
        session.flush()
        _add_exercise(
            session, catalog, name="준비 스트레칭", phase="WARMUP", seconds=60, tier="SUPPORT"
        )
        _add_exercise(session, catalog, name="본 운동", phase="MAIN", seconds=490, tier="CORE")
        _add_exercise(
            session,
            catalog,
            name="마무리 스트레칭",
            phase="COOLDOWN",
            seconds=45,
            tier="SUPPORT",
        )
        _add_exercise(
            session,
            catalog,
            name="준비 스트레칭",
            phase="WARMUP",
            seconds=60,
            tier="SUPPORT",
            difficulty_code="INTERMEDIATE",
        )
        _add_exercise(
            session,
            catalog,
            name="본 운동",
            phase="MAIN",
            seconds=490,
            tier="CORE",
            difficulty_code="INTERMEDIATE",
        )
        _add_exercise(
            session,
            catalog,
            name="마무리 스트레칭",
            phase="COOLDOWN",
            seconds=45,
            tier="SUPPORT",
            difficulty_code="INTERMEDIATE",
        )
        return (
            _add_user(session),
            _add_user(session),
            _add_user(session),
            _add_user(session, experience_level_code="INTERMEDIATE"),
            catalog.id,
        )


@pytest.mark.integration
def test_postgresql_routine_repository_version_ownership_and_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _database_url()
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")
    engine = create_engine(database_url)
    owner_id, other_id, concurrent_id, intermediate_id, catalog_id = _seed(engine)
    request = RoutineCreateRequest(effective_from=date(2026, 8, 14), goal_code="GENERAL_FITNESS")

    with Session(engine) as session:
        beginner_context = RoutineRepository().get_creation_context(
            session, owner_id, "GENERAL_FITNESS"
        )
        intermediate_context = RoutineRepository().get_creation_context(
            session, intermediate_id, "GENERAL_FITNESS"
        )
        assert beginner_context is not None and intermediate_context is not None
        assert all(
            candidate.exercise_name.startswith("BEGINNER ")
            for candidate in beginner_context.candidates
        )
        assert {
            candidate.exercise_name.split()[0] for candidate in intermediate_context.candidates
        } == {
            "BEGINNER",
            "INTERMEDIATE",
        }
        assert all(candidate.intensity_code == "LOW" for candidate in beginner_context.candidates)
        assert all(
            candidate.intensity_code == "MODERATE" for candidate in intermediate_context.candidates
        )

    with Session(engine) as session:
        first = RoutineService(RoutineRepository(), clock=lambda: NOW).create(
            session, owner_id, request, uuid4()
        )
        second = RoutineService(RoutineRepository(), clock=lambda: NOW).create(
            session,
            owner_id,
            request.model_copy(update={"effective_from": date(2026, 8, 15)}),
            uuid4(),
        )
        assert (first.version, second.version) == (1, 2)
        first_day_payload = RoutineRepository().get_current_routine_payload(
            session, owner_id, date(2026, 8, 14)
        )
        second_day_payload = RoutineRepository().get_current_routine_payload(
            session, owner_id, date(2026, 8, 15)
        )
        assert first_day_payload is not None and first_day_payload["version"] == 1
        assert second_day_payload is not None and second_day_payload["version"] == 2
        assert (
            RoutineRepository().get_current_routine_payload(session, other_id, date(2026, 8, 15))
            is None
        )

    def create_concurrently(_: int) -> int:
        with Session(engine) as session:
            response = RoutineService(RoutineRepository(), clock=lambda: NOW).create(
                session, concurrent_id, request, uuid4()
            )
            return response.version

    with ThreadPoolExecutor(max_workers=2) as executor:
        versions = sorted(executor.map(create_concurrently, range(2)))

    assert versions == [1, 2]
    with Session(engine) as session, session.begin():
        session.execute(
            update(CatalogVersion)
            .where(CatalogVersion.id == catalog_id)
            .values(
                status_code="DEPRECATED",
                production_eligible=False,
                activated_at=None,
            )
        )
    with Session(engine) as session:
        assert (
            RoutineRepository().get_creation_context(session, other_id, "GENERAL_FITNESS") is None
        )
        assert (
            RoutineRepository().get_current_routine_payload(session, owner_id, date(2026, 8, 15))
            is None
        )
        historical = RoutineRepository().get_routine_response_payload(session, owner_id, second.id)
        assert historical is not None
        assert historical["catalog_version"] == second.catalog_version
    with Session(engine) as session, session.begin():
        session.execute(
            update(CatalogVersion)
            .where(CatalogVersion.id == catalog_id)
            .values(
                status_code="ACTIVE",
                production_eligible=True,
                activated_at=NOW,
            )
        )
    with Session(engine) as session, session.begin():
        session.execute(
            delete(User).where(User.id.in_((owner_id, other_id, concurrent_id, intermediate_id)))
        )
        session.execute(delete(CatalogVersion).where(CatalogVersion.id == catalog_id))
    engine.dispose()
    get_settings.cache_clear()
