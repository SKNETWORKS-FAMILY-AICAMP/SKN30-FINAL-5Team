from datetime import date, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from backend.app.db.models.checkin import (
    DailyContext,
    DailyContextAdverseReaction,
    DailyContextAvailabilitySlot,
    DailyContextDiscomfort,
    DailyContextPain,
)
from backend.app.db.models.profile import (
    MutationIdempotencyRecord,
    UserPersistentPain,
    UserProfile,
)
from backend.app.domain.rules.external_context import CalendarAvailabilitySourceCode
from backend.app.modules.checkins.codes import (
    DAILY_CONTEXT_ENDPOINT_CODE,
    DAILY_CONTEXT_RESPONSE_SCHEMA_VERSION,
)
from backend.app.modules.checkins.ports import DailyContextValues, IdempotencyRecord


class DailyContextRepository:
    def acquire_mutation_lock(self, session: Session, user_id: UUID, local_date: date) -> None:
        lock_input = f"{user_id}:{local_date.isoformat()}".encode()
        lock_key = int.from_bytes(sha256(lock_input).digest()[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def get_user_timezone(self, session: Session, user_id: UUID) -> str | None:
        return session.scalar(select(UserProfile.timezone).where(UserProfile.user_id == user_id))

    def get_persistent_pain_defaults(
        self, session: Session, user_id: UUID
    ) -> tuple[tuple[str, int], ...]:
        rows = session.execute(
            select(UserPersistentPain.body_area_code, UserPersistentPain.intensity_score)
            .where(UserPersistentPain.user_id == user_id)
            .order_by(UserPersistentPain.body_area_code)
        )
        return tuple(
            (str(body_area_code), int(intensity_score)) for body_area_code, intensity_score in rows
        )

    def get_idempotency_record(
        self, session: Session, user_id: UUID, idempotency_key: UUID
    ) -> IdempotencyRecord | None:
        row = session.scalar(
            select(MutationIdempotencyRecord).where(
                MutationIdempotencyRecord.user_id == user_id,
                MutationIdempotencyRecord.endpoint_code == DAILY_CONTEXT_ENDPOINT_CODE,
                MutationIdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        if row is None:
            return None
        return IdempotencyRecord(row.request_hash, row.response_payload)

    def save_idempotency_record(
        self,
        session: Session,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        now: datetime,
    ) -> None:
        session.add(
            MutationIdempotencyRecord(
                id=uuid4(),
                user_id=user_id,
                endpoint_code=DAILY_CONTEXT_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_payload=response_payload,
                response_schema_version=DAILY_CONTEXT_RESPONSE_SCHEMA_VERSION,
                created_at=now,
            )
        )

    def get_payload(
        self, session: Session, user_id: UUID, local_date: date
    ) -> dict[str, Any] | None:
        row = session.scalar(
            select(DailyContext).where(
                DailyContext.user_id == user_id, DailyContext.local_date == local_date
            )
        )
        return None if row is None else self._payload(session, row)

    def replace(
        self,
        session: Session,
        user_id: UUID,
        local_date: date,
        expected_version: int | None,
        values: DailyContextValues,
        now: datetime,
    ) -> dict[str, Any] | None:
        row = session.scalar(
            select(DailyContext).where(
                DailyContext.user_id == user_id, DailyContext.local_date == local_date
            )
        )
        if row is None:
            if expected_version is not None:
                return None
            row = DailyContext(
                id=uuid4(),
                user_id=user_id,
                local_date=local_date,
                context_version=1,
                created_at=now,
                updated_at=now,
                fatigue_level_code=values.fatigue_level_code,
                requested_duration_minutes=values.requested_duration_minutes,
                duration_adjustment_source_code=values.duration_adjustment_source_code,
                location_code=values.location_code,
                sleep_minutes=values.sleep_minutes,
                sleep_source_code=values.sleep_source_code,
                available_time_minutes=values.available_time_minutes,
                pain_present=values.pain_present,
                red_flag_present=values.red_flag_present,
                fasting_state_code=values.fasting_state_code,
                hydration_state_code=values.hydration_state_code,
                availability_source_code=values.availability_source_code,
            )
            session.add(row)
            session.flush()
        else:
            if expected_version is None or row.context_version != expected_version:
                return None
            row.fatigue_level_code = values.fatigue_level_code
            row.requested_duration_minutes = values.requested_duration_minutes
            row.duration_adjustment_source_code = values.duration_adjustment_source_code
            row.location_code = values.location_code
            row.sleep_minutes = values.sleep_minutes
            row.sleep_source_code = values.sleep_source_code
            row.available_time_minutes = values.available_time_minutes
            row.pain_present = values.pain_present
            row.red_flag_present = values.red_flag_present
            row.fasting_state_code = values.fasting_state_code
            row.hydration_state_code = values.hydration_state_code
            row.availability_source_code = values.availability_source_code
            row.context_version += 1
            row.updated_at = now
            session.execute(
                delete(DailyContextDiscomfort).where(
                    DailyContextDiscomfort.daily_context_id == row.id
                )
            )
            session.execute(
                delete(DailyContextPain).where(DailyContextPain.daily_context_id == row.id)
            )
            session.execute(
                delete(DailyContextAdverseReaction).where(
                    DailyContextAdverseReaction.daily_context_id == row.id
                )
            )
            session.execute(
                delete(DailyContextAvailabilitySlot).where(
                    DailyContextAvailabilitySlot.daily_context_id == row.id
                )
            )

        session.add_all(
            [
                DailyContextPain(
                    id=uuid4(),
                    daily_context_id=row.id,
                    body_area_code=body,
                    intensity_score=intensity_score,
                    severity_code=severity_code,
                    policy_version=policy_version,
                )
                for body, intensity_score, severity_code, policy_version in values.pains
            ]
            + [
                DailyContextAdverseReaction(daily_context_id=row.id, reaction_code=code)
                for code in values.adverse_reaction_codes
            ]
            + [
                DailyContextAvailabilitySlot(
                    id=uuid4(),
                    daily_context_id=row.id,
                    start_at=start_at,
                    end_at=end_at,
                    slot_order=index,
                )
                for index, (start_at, end_at) in enumerate(values.available_slots)
            ]
        )
        session.flush()
        return self._payload(session, row)

    @staticmethod
    def _payload(session: Session, row: DailyContext) -> dict[str, Any]:
        pains = session.execute(
            select(
                DailyContextPain.body_area_code,
                DailyContextPain.intensity_score,
                DailyContextPain.severity_code,
                DailyContextPain.policy_version,
            ).where(DailyContextPain.daily_context_id == row.id)
        ).all()
        legacy_discomforts = (
            session.execute(
                select(
                    DailyContextDiscomfort.body_area_code,
                    DailyContextDiscomfort.severity_code,
                ).where(DailyContextDiscomfort.daily_context_id == row.id)
            ).all()
            if not pains
            else ()
        )
        reactions = session.scalars(
            select(DailyContextAdverseReaction.reaction_code).where(
                DailyContextAdverseReaction.daily_context_id == row.id
            )
        ).all()
        slots = session.execute(
            select(
                DailyContextAvailabilitySlot.start_at,
                DailyContextAvailabilitySlot.end_at,
            )
            .where(DailyContextAvailabilitySlot.daily_context_id == row.id)
            .order_by(DailyContextAvailabilitySlot.slot_order)
        ).all()
        # ROUTINE_DEFAULT means the user never answered, so the field stays null.
        # MANUAL with no rows is an explicit "no time today" choice and stays [].
        available_slots = (
            None
            if row.availability_source_code == CalendarAvailabilitySourceCode.ROUTINE_DEFAULT
            else [{"start_at": start_at, "end_at": end_at} for start_at, end_at in slots]
        )
        return {
            "id": row.id,
            "local_date": row.local_date,
            "fatigue_level_code": row.fatigue_level_code,
            "requested_duration_minutes": row.requested_duration_minutes,
            "duration_adjustment_source_code": row.duration_adjustment_source_code,
            "location_code": row.location_code,
            "sleep_minutes": row.sleep_minutes,
            "sleep_source_code": row.sleep_source_code,
            "available_time_minutes": row.available_time_minutes,
            "pain_present": row.pain_present or bool(pains) or bool(legacy_discomforts),
            "red_flag_present": row.red_flag_present,
            "fasting_state_code": row.fasting_state_code,
            "hydration_state_code": row.hydration_state_code,
            "pains": [
                {
                    "body_area_code": body,
                    "intensity_score": intensity_score,
                    "severity_code": severity_code,
                    "policy_version": policy_version,
                }
                for body, intensity_score, severity_code, policy_version in sorted(pains)
            ],
            "discomforts": [
                {"body_area_code": body, "severity_code": severity_code}
                for body, _, severity_code, _ in sorted(pains)
            ]
            if pains
            else [
                {"body_area_code": body, "severity_code": severity_code}
                for body, severity_code in sorted(legacy_discomforts)
            ],
            "adverse_reaction_codes": sorted(reactions),
            "available_slots": available_slots,
            "availability_source_code": row.availability_source_code,
            "context_version": row.context_version,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


__all__ = ["DailyContextRepository"]
