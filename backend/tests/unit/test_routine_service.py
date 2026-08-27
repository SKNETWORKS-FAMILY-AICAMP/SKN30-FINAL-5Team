from contextlib import nullcontext
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.modules.routines.ports import (
    RoutineCandidate,
    RoutineCreationContext,
    RoutineDayValues,
    RoutineIdempotencyRecord,
)
from backend.app.modules.routines.schemas import RoutineCreateRequest
from backend.app.modules.routines.service import (
    IdempotencyKeyReusedError,
    RoutineDurationUnavailableError,
    RoutineNotFoundError,
    RoutineService,
)

NOW = datetime(2026, 8, 13, 6, 0, tzinfo=UTC)


class FakeSession:
    def begin(self) -> nullcontext[None]:
        return nullcontext()


def _candidate(phase: str, seconds: int, *, tier: str = "SUPPORT") -> RoutineCandidate:
    return RoutineCandidate(
        exercise_id=uuid4(),
        exercise_name=f"{phase} 운동",
        training_type_code="STRENGTH" if phase == "MAIN" else "MOBILITY",
        body_focus_code="FULL_BODY",
        timing_mode_code="DURATION",
        seconds_per_rep=None,
        transition_seconds=10,
        phase_code=phase,
        tier_code=tier,
        sets=1,
        reps=None,
        work_seconds_per_set=seconds - 10,
        rest_seconds_per_set=0,
        intensity_code="LOW",
    )


class FakeRoutineRepository:
    def __init__(self, *, duration_minutes: int = 10) -> None:
        self.context = RoutineCreationContext(
            profile_duration_minutes=duration_minutes,
            desired_weekly_workout_count=2,
            experience_level_code="BEGINNER",
            available_location_codes=("HOME", "GYM"),
            equipment_codes=("BODYWEIGHT",),
            catalog_version_id=uuid4(),
            catalog_version_code="synthetic-approved-v1",
            candidates=(
                _candidate("WARMUP", 60),
                _candidate("MAIN", 490, tier="CORE"),
                _candidate("COOLDOWN", 45),
            ),
        )
        self.idempotency: dict[tuple[UUID, UUID], RoutineIdempotencyRecord] = {}
        self.payloads: dict[tuple[UUID, UUID], dict[str, Any]] = {}
        self.versions: dict[UUID, int] = {}
        self.current: dict[UUID, UUID] = {}
        self.days: tuple[RoutineDayValues, ...] = ()

    def acquire_creation_lock(self, session: FakeSession, user_id: UUID) -> None:
        del session, user_id

    def get_idempotency_record(
        self, session: FakeSession, user_id: UUID, idempotency_key: UUID
    ) -> RoutineIdempotencyRecord | None:
        del session
        return self.idempotency.get((user_id, idempotency_key))

    def save_idempotency_record(
        self,
        session: FakeSession,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        now: datetime,
    ) -> None:
        del session, now
        self.idempotency[(user_id, idempotency_key)] = RoutineIdempotencyRecord(
            request_hash=request_hash, response_payload=response_payload
        )

    def get_creation_context(
        self, session: FakeSession, user_id: UUID, goal_code: str
    ) -> RoutineCreationContext | None:
        del session, user_id
        return self.context if goal_code == "GENERAL_FITNESS" else None

    def create_routine(
        self,
        session: FakeSession,
        user_id: UUID,
        goal_code: str,
        effective_from: date,
        catalog_version_id: UUID,
        days: tuple[RoutineDayValues, ...],
        now: datetime,
    ) -> UUID:
        del session, catalog_version_id
        routine_id = uuid4()
        version = self.versions.get(user_id, 0) + 1
        self.versions[user_id] = version
        self.days = days
        exercise_names = {
            candidate.exercise_id: candidate.exercise_name for candidate in self.context.candidates
        }
        payload = {
            "id": routine_id,
            "version": version,
            "goal_code": goal_code,
            "status_code": "ACTIVE",
            "effective_from": effective_from,
            "catalog_version": self.context.catalog_version_code,
            "days": [
                {
                    "id": uuid4(),
                    "sequence": day.sequence,
                    "title": day.title,
                    "training_type_code": day.training_type_code,
                    "body_focus_code": day.body_focus_code,
                    "requested_duration_minutes": day.requested_duration_minutes,
                    "estimated_duration_seconds": day.estimated_duration_seconds,
                    "estimated_calories_burned": None,
                    "items": [
                        {
                            "id": uuid4(),
                            "exercise_id": item.exercise_id,
                            "exercise_name": exercise_names[item.exercise_id],
                            "sequence": item.sequence,
                            "phase_code": item.phase_code,
                            "tier_code": item.tier_code,
                            "sets": item.sets,
                            "reps": item.reps,
                            "work_seconds_per_set": item.work_seconds_per_set,
                            "rest_seconds_per_set": item.rest_seconds_per_set,
                            "instruction_available": True,
                        }
                        for item in day.items
                    ],
                }
                for day in days
            ],
            "created_at": now,
        }
        self.payloads[(user_id, routine_id)] = payload
        self.current[user_id] = routine_id
        return routine_id

    def get_routine_response_payload(
        self, session: FakeSession, user_id: UUID, routine_id: UUID
    ) -> dict[str, Any] | None:
        del session
        return self.payloads.get((user_id, routine_id))

    def get_current_routine_payload(
        self, session: FakeSession, user_id: UUID, local_date: date
    ) -> dict[str, Any] | None:
        del session, local_date
        routine_id = self.current.get(user_id)
        return None if routine_id is None else self.payloads.get((user_id, routine_id))


def _request(day: int = 14) -> RoutineCreateRequest:
    return RoutineCreateRequest(effective_from=date(2026, 8, day), goal_code="GENERAL_FITNESS")


def test_first_and_next_routine_versions_preserve_phase_order_and_duration() -> None:
    repository = FakeRoutineRepository()
    service = RoutineService(repository, clock=lambda: NOW)
    user_id = uuid4()

    first = service.create(FakeSession(), user_id, _request(), uuid4())  # type: ignore[arg-type]
    second = service.create(FakeSession(), user_id, _request(15), uuid4())  # type: ignore[arg-type]

    assert (first.version, second.version) == (1, 2)
    assert all(day.estimated_duration_seconds == 600 for day in second.days)
    assert [item.phase_code for item in second.days[0].items] == [
        "WARMUP",
        "MAIN",
        "COOLDOWN",
    ]
    assert second.days[0].items[1].tier_code == "CORE"


def test_idempotency_returns_same_response_and_rejects_changed_payload() -> None:
    repository = FakeRoutineRepository()
    service = RoutineService(repository, clock=lambda: NOW)
    user_id = uuid4()
    key = uuid4()

    first = service.create(FakeSession(), user_id, _request(), key)  # type: ignore[arg-type]
    repeated = service.create(FakeSession(), user_id, _request(), key)  # type: ignore[arg-type]

    assert repeated == first
    assert repository.versions[user_id] == 1
    with pytest.raises(IdempotencyKeyReusedError):
        service.create(FakeSession(), user_id, _request(15), key)  # type: ignore[arg-type]


def test_duration_within_tolerance_is_accepted() -> None:
    """A plan may land within five minutes of the request (2026-08-27 decision)."""
    repository = FakeRoutineRepository(duration_minutes=9)
    service = RoutineService(repository, clock=lambda: NOW)

    response = service.create(FakeSession(), uuid4(), _request(), uuid4())  # type: ignore[arg-type]

    assert response is not None


def test_duration_beyond_tolerance_still_fails() -> None:
    """The allowance is bounded; it never silently shortens an impossible request."""
    repository = FakeRoutineRepository(duration_minutes=180)
    service = RoutineService(repository, clock=lambda: NOW)

    with pytest.raises(RoutineDurationUnavailableError):
        service.create(FakeSession(), uuid4(), _request(), uuid4())  # type: ignore[arg-type]


def test_current_routine_is_scoped_to_authenticated_user() -> None:
    repository = FakeRoutineRepository()
    service = RoutineService(repository, clock=lambda: NOW)
    owner_id = uuid4()
    service.create(FakeSession(), owner_id, _request(), uuid4())  # type: ignore[arg-type]

    with pytest.raises(RoutineNotFoundError):
        service.get_current(FakeSession(), uuid4(), date(2026, 8, 14))  # type: ignore[arg-type]
