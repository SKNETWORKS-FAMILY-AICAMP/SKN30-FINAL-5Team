from contextlib import nullcontext
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.modules.checkins.ports import DailyContextValues, IdempotencyRecord
from backend.app.modules.checkins.schemas import DailyContextUpsertRequest
from backend.app.modules.checkins.service import (
    AvailabilitySlotOutOfRangeError,
    DailyContextNotFoundError,
    DailyContextService,
    IdempotencyKeyReusedError,
    ProfileTimezoneMissingError,
    StaleContextError,
)
from backend.app.modules.decisions.daily_adjustment import DailyAdjustmentLimitReachedError

NOW = datetime(2026, 8, 14, 3, 0, tzinfo=UTC)
LOCAL_DATE = date(2026, 8, 14)


class FakeSession:
    def begin(self):
        return nullcontext()


class FakeDailyContextRepository:
    def __init__(self, timezone_name: str | None = "Asia/Seoul") -> None:
        self.contexts: dict[tuple[UUID, date], dict[str, Any]] = {}
        self.idempotency: dict[tuple[UUID, UUID], IdempotencyRecord] = {}
        self.timezone_name = timezone_name
        self.persistent_pains: dict[UUID, tuple[tuple[str, int], ...]] = {}
        self.successful_regenerations = 0

    def acquire_mutation_lock(self, session: FakeSession, user_id: UUID, local_date: date) -> None:
        del session, user_id, local_date

    def get_user_timezone(self, session: FakeSession, user_id: UUID) -> str | None:
        del session, user_id
        return self.timezone_name

    def get_persistent_pain_defaults(
        self, session: FakeSession, user_id: UUID
    ) -> tuple[tuple[str, int], ...]:
        del session
        return self.persistent_pains.get(user_id, ())

    def count_daily_adjustments(
        self, session: FakeSession, user_id: UUID, local_date: date
    ) -> int:
        del session
        context = self.contexts.get((user_id, local_date))
        return max((context or {}).get("context_version", 1) - 1, 0) + (
            self.successful_regenerations
        )

    def get_context_version(
        self, session: FakeSession, user_id: UUID, local_date: date
    ) -> int | None:
        del session
        context = self.contexts.get((user_id, local_date))
        return None if context is None else int(context["context_version"])

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
            "sleep_source_code": values.sleep_source_code,
            "available_time_minutes": values.available_time_minutes,
            "pain_present": values.pain_present,
            "red_flag_present": values.red_flag_present,
            "fasting_state_code": values.fasting_state_code,
            "hydration_state_code": values.hydration_state_code,
            "discomforts": [
                {"body_area_code": body, "severity_code": severity}
                for body, severity in values.discomforts
            ],
            "pains": [
                {
                    "body_area_code": body,
                    "intensity_score": intensity,
                    "severity_code": severity,
                    "policy_version": policy_version,
                }
                for body, intensity, severity, policy_version in values.pains
            ],
            "adverse_reaction_codes": list(values.adverse_reaction_codes),
            "available_slots": (
                None
                if values.availability_source_code == "ROUTINE_DEFAULT"
                else [
                    {"start_at": start_at, "end_at": end_at}
                    for start_at, end_at in values.available_slots
                ]
            ),
            "availability_source_code": values.availability_source_code,
            "context_version": current["context_version"] + 1 if current else 1,
            "created_at": current["created_at"] if current else now,
            "updated_at": now,
        }
        self.contexts[key] = payload
        return payload


def request(
    *,
    fatigue: str = "MODERATE",
    discomforts: list[dict[str, str]] | None = None,
    available_slots: list[dict[str, str]] | None = None,
):
    payload: dict[str, Any] = {
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
    if available_slots is not None:
        payload["available_slots"] = available_slots
    return DailyContextUpsertRequest.model_validate(payload)


def test_persistent_pains_are_exposed_only_as_editable_checkin_defaults() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)
    user_id = uuid4()
    repository.persistent_pains[user_id] = (("KNEE", 4), ("SHOULDER", 2))

    defaults = service.defaults(FakeSession(), user_id, LOCAL_DATE)

    assert defaults.local_date == LOCAL_DATE
    assert [(pain.body_area_code.value, pain.intensity_score) for pain in defaults.pains] == [
        ("KNEE", 4),
        ("SHOULDER", 2),
    ]


def slot(start_hour: int, end_hour: int) -> dict[str, str]:
    """A same-day KST window for LOCAL_DATE."""

    return {
        "start_at": f"2026-08-14T{start_hour:02d}:00:00+09:00",
        "end_at": f"2026-08-14T{end_hour:02d}:00:00+09:00",
    }


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


def test_nrs_pain_and_safety_inputs_round_trip_with_the_policy_version() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)
    payload = DailyContextUpsertRequest.model_validate(
        {
            "fatigue_level_code": "HIGH",
            "available_time_minutes": 30,
            "location_code": "HOME",
            "sleep_minutes": 330,
            "sleep_source_code": "MANUAL",
            "pain_present": True,
            "red_flag_present": True,
            "pains": [{"body_area_code": "KNEE", "intensity_score": 6}],
            "adverse_reaction_codes": [],
        }
    )

    response = service.replace(FakeSession(), uuid4(), LOCAL_DATE, payload, uuid4(), None)

    assert response.requested_duration_minutes == 30
    assert response.available_time_minutes == 30
    assert response.sleep_source_code.value == "MANUAL"
    assert response.pain_present is True
    assert response.red_flag_present is True
    assert response.pains[0].intensity_score == 6
    assert response.pains[0].severity_code.value == "MODERATE"
    assert response.pains[0].policy_version == "pain-intensity-action-v2"


def test_stale_or_missing_version_cannot_replace_existing_context() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)
    user_id = uuid4()
    service.replace(FakeSession(), user_id, LOCAL_DATE, request(), uuid4(), None)

    with pytest.raises(StaleContextError):
        service.replace(FakeSession(), user_id, LOCAL_DATE, request(), uuid4(), None)
    with pytest.raises(StaleContextError):
        service.replace(FakeSession(), user_id, LOCAL_DATE, request(), uuid4(), 9)


def test_checkin_edit_and_regeneration_share_a_two_adjustment_daily_budget() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)
    user_id = uuid4()
    service.replace(FakeSession(), user_id, LOCAL_DATE, request(), uuid4(), None)
    repository.successful_regenerations = 1

    second = service.replace(
        FakeSession(), user_id, LOCAL_DATE, request(fatigue="HIGH"), uuid4(), 1
    )
    assert second.context_version == 2

    with pytest.raises(DailyAdjustmentLimitReachedError):
        service.replace(FakeSession(), user_id, LOCAL_DATE, request(), uuid4(), 2)


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


def test_missing_available_slots_is_routine_default_not_an_empty_manual_choice() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)

    response = service.replace(FakeSession(), uuid4(), LOCAL_DATE, request(), uuid4(), None)

    assert response.availability_source_code == "ROUTINE_DEFAULT"
    assert response.available_slots is None


def test_explicit_empty_choice_is_preserved_as_manual() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)

    response = service.replace(
        FakeSession(), uuid4(), LOCAL_DATE, request(available_slots=[]), uuid4(), None
    )

    assert response.availability_source_code == "MANUAL"
    assert response.available_slots == []


def test_manual_slots_are_stored_in_start_order() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)

    response = service.replace(
        FakeSession(),
        uuid4(),
        LOCAL_DATE,
        request(available_slots=[slot(19, 21), slot(7, 9)]),
        uuid4(),
        None,
    )

    assert response.availability_source_code == "MANUAL"
    assert [entry.start_at.hour for entry in response.available_slots or []] == [7, 19]


def test_slot_order_does_not_change_the_idempotency_key_meaning() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)
    user_id, key = uuid4(), uuid4()

    first = service.replace(
        FakeSession(),
        user_id,
        LOCAL_DATE,
        request(available_slots=[slot(7, 9), slot(19, 21)]),
        key,
        None,
    )
    retry = service.replace(
        FakeSession(),
        user_id,
        LOCAL_DATE,
        request(available_slots=[slot(19, 21), slot(7, 9)]),
        key,
        None,
    )

    assert retry == first


def test_slot_outside_the_local_date_is_rejected() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)

    with pytest.raises(AvailabilitySlotOutOfRangeError):
        service.replace(
            FakeSession(),
            uuid4(),
            LOCAL_DATE,
            request(
                available_slots=[
                    {
                        "start_at": "2026-08-15T09:00:00+09:00",
                        "end_at": "2026-08-15T11:00:00+09:00",
                    }
                ]
            ),
            uuid4(),
            None,
        )


def test_slot_may_close_on_the_next_local_midnight() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)

    response = service.replace(
        FakeSession(),
        uuid4(),
        LOCAL_DATE,
        request(
            available_slots=[
                {
                    "start_at": "2026-08-14T22:00:00+09:00",
                    "end_at": "2026-08-15T00:00:00+09:00",
                }
            ]
        ),
        uuid4(),
        None,
    )

    assert len(response.available_slots or []) == 1


def test_slots_need_a_profile_timezone() -> None:
    repository = FakeDailyContextRepository(timezone_name=None)
    service = DailyContextService(repository, clock=lambda: NOW)

    with pytest.raises(ProfileTimezoneMissingError):
        service.replace(
            FakeSession(), uuid4(), LOCAL_DATE, request(available_slots=[slot(7, 9)]), uuid4(), None
        )


def test_a_check_in_without_slots_still_needs_no_timezone_lookup() -> None:
    repository = FakeDailyContextRepository(timezone_name=None)
    service = DailyContextService(repository, clock=lambda: NOW)

    response = service.replace(FakeSession(), uuid4(), LOCAL_DATE, request(), uuid4(), None)

    assert response.availability_source_code == "ROUTINE_DEFAULT"


@pytest.mark.parametrize(
    "slots",
    [
        pytest.param([slot(7, 9), slot(8, 10)], id="overlapping"),
        pytest.param([slot(7, 9), slot(9, 11)], id="touching"),
        pytest.param(
            [
                {
                    "start_at": "2026-08-14T09:00:00+09:00",
                    "end_at": "2026-08-14T09:00:00+09:00",
                }
            ],
            id="empty-range",
        ),
        pytest.param(
            [{"start_at": "2026-08-14T09:00:00", "end_at": "2026-08-14T11:00:00"}],
            id="naive-datetime",
        ),
        pytest.param([slot(hour, hour + 1) for hour in range(0, 18, 2)], id="over-the-cap"),
    ],
)
def test_invalid_slot_shapes_are_rejected(slots: list[dict[str, str]]) -> None:
    with pytest.raises(ValueError):
        request(available_slots=slots)


def test_manual_slots_never_change_the_requested_duration() -> None:
    repository = FakeDailyContextRepository()
    service = DailyContextService(repository, clock=lambda: NOW)

    response = service.replace(
        FakeSession(),
        uuid4(),
        LOCAL_DATE,
        request(available_slots=[slot(7, 8)]),
        uuid4(),
        None,
    )

    assert response.requested_duration_minutes == 40
