import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.modules.checkins.ports import DailyContextRepositoryPort, DailyContextValues
from backend.app.modules.checkins.schemas import DailyContextResponse, DailyContextUpsertRequest


class DailyContextNotFoundError(Exception):
    """The requested user-scoped context does not exist."""


class StaleContextError(Exception):
    """The supplied version cannot replace the current context."""


class IdempotencyKeyReusedError(Exception):
    """The same mutation key was used for a different request."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request_hash(local_date: date, request: DailyContextUpsertRequest) -> str:
    value = {"local_date": local_date.isoformat(), **request.model_dump(mode="json")}
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


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

            values = DailyContextValues(
                fatigue_level_code=request.fatigue_level_code,
                requested_duration_minutes=request.requested_duration_minutes,
                duration_adjustment_source_code=request.duration_adjustment_source_code,
                location_code=request.location_code,
                sleep_minutes=request.sleep_minutes,
                fasting_state_code=request.fasting_state_code,
                hydration_state_code=request.hydration_state_code,
                discomforts=tuple(
                    (item.body_area_code, item.severity_code) for item in request.discomforts
                ),
                adverse_reaction_codes=tuple(request.adverse_reaction_codes),
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
    "DailyContextNotFoundError",
    "DailyContextService",
    "IdempotencyKeyReusedError",
    "StaleContextError",
]
