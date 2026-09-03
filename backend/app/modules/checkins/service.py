import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from backend.app.domain.rules.external_context import CalendarAvailabilitySourceCode
from backend.app.domain.rules.safety import BodyAreaCode, severity_from_intensity_score
from backend.app.modules.checkins.codes import DAILY_PAIN_POLICY_VERSION
from backend.app.modules.checkins.ports import DailyContextRepositoryPort, DailyContextValues
from backend.app.modules.checkins.schemas import (
    DailyContextDefaultsResponse,
    DailyContextResponse,
    DailyContextUpsertRequest,
    PainInput,
)


class DailyContextNotFoundError(Exception):
    """The requested user-scoped context does not exist."""


class StaleContextError(Exception):
    """The supplied version cannot replace the current context."""


class IdempotencyKeyReusedError(Exception):
    """The same mutation key was used for a different request."""


class AvailabilitySlotOutOfRangeError(Exception):
    """A manual availability slot falls outside the check-in's local date."""


class ProfileTimezoneMissingError(Exception):
    """Availability slots need a verified profile timezone to be bounded."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request_hash(local_date: date, request: DailyContextUpsertRequest) -> str:
    value = {"local_date": local_date.isoformat(), **request.model_dump(mode="json")}
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _bounded_slots(
    request: DailyContextUpsertRequest,
    local_date: date,
    timezone_name: str,
) -> tuple[tuple[datetime, datetime], ...]:
    """Require every manual slot to sit inside local_date in the user's timezone."""

    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ProfileTimezoneMissingError from exc
    day_start = datetime.combine(local_date, time.min, tzinfo=zone)
    day_end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone)
    slots: list[tuple[datetime, datetime]] = []
    for slot in request.available_slots or ():
        # The next midnight is an allowed closing boundary but not an allowed start.
        if slot.start_at < day_start or slot.start_at >= day_end or slot.end_at > day_end:
            raise AvailabilitySlotOutOfRangeError
        slots.append((slot.start_at, slot.end_at))
    return tuple(slots)


class DailyContextService:
    def __init__(
        self,
        repository: DailyContextRepositoryPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def get(self, session: Session, user_id: UUID, local_date: date) -> DailyContextResponse:
        payload = self._repository.get_payload(session, user_id, local_date)
        if payload is None:
            raise DailyContextNotFoundError
        return DailyContextResponse.model_validate(payload)

    def defaults(
        self, session: Session, user_id: UUID, local_date: date
    ) -> DailyContextDefaultsResponse:
        """Project persistent pains only for editable check-in form initialization."""

        persistent_pains = self._repository.get_persistent_pain_defaults(session, user_id)
        return DailyContextDefaultsResponse(
            local_date=local_date,
            pains=[
                PainInput(
                    body_area_code=BodyAreaCode(body_area_code), intensity_score=intensity_score
                )
                for body_area_code, intensity_score in persistent_pains
            ],
        )

    def replace(
        self,
        session: Session,
        user_id: UUID,
        local_date: date,
        request: DailyContextUpsertRequest,
        idempotency_key: UUID,
        expected_version: int | None,
    ) -> DailyContextResponse:
        request_hash = _request_hash(local_date, request)
        now = self._clock()
        with session.begin():
            self._repository.acquire_mutation_lock(session, user_id, local_date)
            existing = self._repository.get_idempotency_record(session, user_id, idempotency_key)
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise IdempotencyKeyReusedError
                return DailyContextResponse.model_validate(existing.response_payload)

            if request.available_slots is None:
                availability_source_code = CalendarAvailabilitySourceCode.ROUTINE_DEFAULT
                available_slots: tuple[tuple[datetime, datetime], ...] = ()
            else:
                timezone_name = self._repository.get_user_timezone(session, user_id)
                if timezone_name is None:
                    raise ProfileTimezoneMissingError
                availability_source_code = CalendarAvailabilitySourceCode.MANUAL
                available_slots = _bounded_slots(request, local_date, timezone_name)

            assert request.requested_duration_minutes is not None
            assert request.available_time_minutes is not None
            assert request.pain_present is not None

            values = DailyContextValues(
                fatigue_level_code=request.fatigue_level_code,
                requested_duration_minutes=request.requested_duration_minutes,
                duration_adjustment_source_code=request.duration_adjustment_source_code,
                location_code=request.location_code,
                sleep_minutes=request.sleep_minutes,
                sleep_source_code=request.sleep_source_code,
                available_time_minutes=request.available_time_minutes,
                pain_present=request.pain_present,
                red_flag_present=request.red_flag_present,
                fasting_state_code=request.fasting_state_code,
                hydration_state_code=request.hydration_state_code,
                discomforts=tuple(
                    (item.body_area_code, item.severity_code) for item in request.discomforts
                ),
                pains=tuple(
                    (
                        str(item.body_area_code),
                        item.intensity_score,
                        severity_from_intensity_score(item.intensity_score).name,
                        DAILY_PAIN_POLICY_VERSION,
                    )
                    for item in request.pains
                ),
                adverse_reaction_codes=tuple(request.adverse_reaction_codes),
                availability_source_code=availability_source_code,
                available_slots=available_slots,
            )
            payload = self._repository.replace(
                session, user_id, local_date, expected_version, values, now
            )
            if payload is None:
                raise StaleContextError
            response = DailyContextResponse.model_validate(payload)
            self._repository.save_idempotency_record(
                session,
                user_id,
                idempotency_key,
                request_hash,
                response.model_dump(mode="json"),
                now,
            )
        return response


__all__ = [
    "AvailabilitySlotOutOfRangeError",
    "DailyContextNotFoundError",
    "DailyContextService",
    "IdempotencyKeyReusedError",
    "ProfileTimezoneMissingError",
    "StaleContextError",
]
