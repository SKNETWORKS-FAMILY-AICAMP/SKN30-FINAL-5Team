from contextlib import nullcontext
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.modules.checkins.ports import DailyContextValues, IdempotencyRecord
from backend.app.modules.checkins.schemas import DailyContextUpsertRequest
from backend.app.modules.checkins.service import (
    DailyContextNotFoundError,
    DailyContextService,
    IdempotencyKeyReusedError,
    StaleContextError,
)

NOW = datetime(2026, 8, 14, 3, 0, tzinfo=UTC)
LOCAL_DATE = date(2026, 8, 14)


class FakeSession:
    def begin(self):
        return nullcontext()


class FakeDailyContextRepository:
    def __init__(self) -> None:
        self.contexts: dict[tuple[UUID, date], dict[str, Any]] = {}
        self.idempotency: dict[tuple[UUID, UUID], IdempotencyRecord] = {}

    def acquire_mutation_lock(self, session: FakeSession, user_id: UUID, local_date: date) -> None:
        del session, user_id, local_date

    def get_idempotency_record(
        self, session: FakeSession, user_id: UUID, idempotency_key: UUID
    ) -> IdempotencyRecord | None:
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
        self.idempotency[(user_id, idempotency_key)] = IdempotencyRecord(
            request_hash, response_payload
        )

    def get_payload(
        self, session: FakeSession, user_id: UUID, local_date: date
    ) -> dict[str, Any] | None:
        del session
        return self.contexts.get((user_id, local_date))

    def replace(
        self,
        session: FakeSession,
        user_id: UUID,
        local_date: date,
        expected_version: int | None,
        values: DailyContextValues,
        now: datetime,
    ) -> dict[str, Any] | None:
        del session
        key = (user_id, local_date)
        current = self.contexts.get(key)
        if current is None and expected_version is not None:
            return None
        if current is not None and (
            expected_version is None or current["context_version"] != expected_version
        ):
            return None
        payload = {
            "id": current["id"] if current else uuid4(),
            "local_date": local_date,
            "fatigue_level_code": values.fatigue_level_code,
            "requested_duration_minutes": values.requested_duration_minutes,
            "duration_adjustment_source_code": values.duration_adjustment_source_code,
            "location_code": values.location_code,
            "sleep_minutes": values.sleep_minutes,
            "fasting_state_code": values.fasting_state_code,
            "hydration_state_code": values.hydration_state_code,
            "discomforts": [
                {"body_area_code": body, "severity_code": severity}
                for body, severity in values.discomforts
            ],
            "adverse_reaction_codes": list(values.adverse_reaction_codes),
            "context_version": current["context_version"] + 1 if current else 1,
            "created_at": current["created_at"] if current else now,
            "updated_at": now,
        }
        self.contexts[key] = payload
        return payload


def request(*, fatigue: str = "MODERATE", discomforts: list[dict[str, str]] | None = None):
    return DailyContextUpsertRequest.model_validate(
        {
            "fatigue_level_code": fatigue,
            "requested_duration_minutes": 40,
            "duration_adjustment_source_code": "PROFILE",
            "location_code": "HOME",
            "sleep_minutes": None,
            "fasting_state_code": None,
            "hydration_state_code": None,
            "discomforts": discomforts or [],
            "adverse_reaction_codes": [],
        }
    )


def test_manual_create_get_and_versioned_full_replacement() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)
    user_id = uuid4()

    first = service.replace(
        FakeSession(),
        user_id,
        LOCAL_DATE,
        request(discomforts=[{"body_area_code": "KNEE", "severity_code": "MILD"}]),
        uuid4(),
        None,
    )
    second = service.replace(
        FakeSession(), user_id, LOCAL_DATE, request(fatigue="HIGH"), uuid4(), 1
    )

    assert first.context_version == 1
    assert second.context_version == 2
    assert second.discomforts == []
    assert service.get(FakeSession(), user_id, LOCAL_DATE) == second


def test_stale_or_missing_version_cannot_replace_existing_context() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)
    user_id = uuid4()
    service.replace(FakeSession(), user_id, LOCAL_DATE, request(), uuid4(), None)

    with pytest.raises(StaleContextError):
        service.replace(FakeSession(), user_id, LOCAL_DATE, request(), uuid4(), None)
    with pytest.raises(StaleContextError):
        service.replace(FakeSession(), user_id, LOCAL_DATE, request(), uuid4(), 9)


def test_idempotent_retry_does_not_increment_and_changed_payload_conflicts() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)
    user_id, key = uuid4(), uuid4()
    first = service.replace(FakeSession(), user_id, LOCAL_DATE, request(), key, None)
    retry = service.replace(FakeSession(), user_id, LOCAL_DATE, request(), key, None)
    assert retry == first

    with pytest.raises(IdempotencyKeyReusedError):
        service.replace(FakeSession(), user_id, LOCAL_DATE, request(fatigue="HIGH"), key, 1)


def test_user_scope_and_missing_context_are_isolated() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)
    service.replace(FakeSession(), uuid4(), LOCAL_DATE, request(), uuid4(), None)
    with pytest.raises(DailyContextNotFoundError):
        service.get(FakeSession(), uuid4(), LOCAL_DATE)


def test_duplicate_body_area_is_rejected_without_health_inference() -> None:
    with pytest.raises(ValueError):
        request(
            discomforts=[
                {"body_area_code": "KNEE", "severity_code": "MILD"},
                {"body_area_code": "KNEE", "severity_code": "MODERATE"},
            ]
        )
