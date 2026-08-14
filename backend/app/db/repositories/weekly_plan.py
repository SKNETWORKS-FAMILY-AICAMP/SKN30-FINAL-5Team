from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.catalog import ExerciseEquipment, ExerciseLocation
from backend.app.db.models.decision import DecisionRun, SafetyReview
from backend.app.db.models.profile import (
    MutationIdempotencyRecord,
    UserAvailableLocation,
    UserEquipment,
    UserProfile,
)
from backend.app.db.models.routine import Routine, RoutineDay
from backend.app.db.models.weekly_report import UserWeek, WeeklyPlanRevision, WeeklyReport
from backend.app.modules.weekly_plans.codes import WEEKLY_PLAN_RESPONSE_SCHEMA_VERSION
from backend.app.modules.weekly_plans.ports import (
    LatestPlanRevision,
    PlanContext,
    PlanIdempotencyRecord,
    PlanRevisionValues,
    RoutinePlanEvidence,
)


class WeeklyPlanRepository:
    def acquire_week_lock(self, session: Session, user_id: UUID, week_start: date) -> None:
        lock_key = int.from_bytes(
            sha256(f"weekly-plan:{user_id}:{week_start.isoformat()}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def acquire_idempotency_lock(
        self, session: Session, user_id: UUID, endpoint_code: str, key: UUID
    ) -> None:
        lock_key = int.from_bytes(
            sha256(f"{user_id}:{endpoint_code}:{key}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def get_idempotency_record(
        self, session: Session, user_id: UUID, endpoint_code: str, key: UUID
    ) -> PlanIdempotencyRecord | None:
        row = session.scalar(
            select(MutationIdempotencyRecord).where(
                MutationIdempotencyRecord.user_id == user_id,
                MutationIdempotencyRecord.endpoint_code == endpoint_code,
                MutationIdempotencyRecord.idempotency_key == key,
            )
        )
        if row is None:
            return None
        return PlanIdempotencyRecord(row.request_hash, row.response_payload)

    def save_idempotency_record(
        self,
        session: Session,
        *,
        user_id: UUID,
        endpoint_code: str,
        key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        now: datetime,
    ) -> None:
        session.add(
            MutationIdempotencyRecord(
                id=uuid4(),
                user_id=user_id,
                endpoint_code=endpoint_code,
                idempotency_key=key,
                request_hash=request_hash,
                response_payload=response_payload,
                response_schema_version=WEEKLY_PLAN_RESPONSE_SCHEMA_VERSION,
                created_at=now,
            )
        )
        session.flush()

    def get_plan_context(
        self, session: Session, user_id: UUID, week_id: UUID, week_start: date
    ) -> PlanContext | None:
        week = session.scalar(
            select(UserWeek).where(UserWeek.id == week_id, UserWeek.user_id == user_id)
        )
        profile = session.get(UserProfile, user_id)
        if week is None or profile is None:
            return None

        source_report = session.scalar(
            select(WeeklyReport)
            .join(UserWeek, UserWeek.id == WeeklyReport.user_week_id)
            .where(
                UserWeek.user_id == user_id,
                UserWeek.week_start_local_date == week_start - timedelta(days=7),
            )
        )
        has_prior_week = (
            session.scalar(
                select(UserWeek.id)
                .where(
                    UserWeek.user_id == user_id,
                    UserWeek.week_start_local_date < week_start,
                )
                .limit(1)
            )
            is not None
        )
        allowed_locations = tuple(
            sorted(
                session.scalars(
                    select(UserAvailableLocation.location_code).where(
                        UserAvailableLocation.user_id == user_id
                    )
                ).all()
            )
        ) or (profile.preferred_location_code,)
        equipment = tuple(
            sorted(
                session.scalars(
                    select(UserEquipment.equipment_code).where(UserEquipment.user_id == user_id)
                ).all()
            )
        )
        safety_result = session.execute(
            select(DecisionRun, SafetyReview)
            .outerjoin(SafetyReview, SafetyReview.decision_run_id == DecisionRun.id)
            .where(DecisionRun.user_id == user_id, DecisionRun.local_date < week_start)
            .order_by(DecisionRun.local_date.desc(), DecisionRun.created_at.desc())
            .limit(1)
        ).one_or_none()
        if safety_result is None:
            safety_status_code = "PASS"
            safety_opinion_codes: tuple[str, ...] = ()
            excluded_exercise_ids: tuple[UUID, ...] = ()
        else:
            decision, safety_review = safety_result
            safety_status_code = decision.safety_status_code
            safety_opinion_codes = (
                tuple(sorted(set(safety_review.reason_codes)))
                if safety_review is not None and safety_status_code == "REVISE"
                else ()
            )
            excluded_exercise_ids = (
                tuple(
                    sorted(
                        (UUID(value) for value in safety_review.excluded_exercise_ids),
                        key=str,
                    )
                )
                if safety_review is not None
                else ()
            )
        current_routine_id = session.scalar(
            select(Routine.id)
            .where(
                Routine.user_id == user_id,
                Routine.status_code == "ACTIVE",
                Routine.effective_from <= week_start,
                (Routine.effective_to.is_(None)) | (Routine.effective_to >= week_start),
            )
            .order_by(Routine.version.desc())
            .limit(1)
        )
        return PlanContext(
            week_id=week.id,
            week_start=week.week_start_local_date,
            week_end=week.week_end_local_date,
            is_first_user_week=not has_prior_week and safety_result is None,
            cold_start_applied=week.cold_start_applied,
            source_weekly_report_id=None if source_report is None else source_report.id,
            previous_report_status_code=(
                None if source_report is None else source_report.status_code
            ),
            requested_duration_minutes=profile.default_requested_duration_minutes,
            preferred_location_code=profile.preferred_location_code,
            allowed_location_codes=allowed_locations,
            available_equipment_codes=equipment,
            safety_status_code=safety_status_code,
            safety_opinion_codes=safety_opinion_codes,
            excluded_exercise_ids=excluded_exercise_ids,
            current_routine_id=current_routine_id,
        )

    def get_routine_evidence(
        self, session: Session, user_id: UUID, routine_id: UUID
    ) -> RoutinePlanEvidence | None:
        routine = session.scalar(
            select(Routine)
            .options(selectinload(Routine.days).selectinload(RoutineDay.items))
            .where(Routine.id == routine_id, Routine.user_id == user_id)
        )
        if routine is None or not routine.days:
            return None
        durations = {day.requested_duration_minutes for day in routine.days}
        if len(durations) != 1:
            raise RuntimeError("routine days do not share one requested duration")
        exercise_ids = tuple(
            sorted({item.exercise_id for day in routine.days for item in day.items}, key=str)
        )
        location_rows = session.execute(
            select(ExerciseLocation.exercise_id, ExerciseLocation.location_code).where(
                ExerciseLocation.exercise_id.in_(exercise_ids)
            )
        ).all()
        locations_by_exercise: dict[UUID, set[str]] = {
            exercise_id: set() for exercise_id in exercise_ids
        }
        for exercise_id, location_code in location_rows:
            locations_by_exercise[exercise_id].add(location_code)
        supported_locations = (
            set.intersection(*(locations_by_exercise[value] for value in exercise_ids))
            if exercise_ids
            else set()
        )
        equipment = tuple(
            sorted(
                set(
                    session.scalars(
                        select(ExerciseEquipment.equipment_code).where(
                            ExerciseEquipment.exercise_id.in_(exercise_ids)
                        )
                    ).all()
                )
            )
        )
        return RoutinePlanEvidence(
            routine_id=routine.id,
            routine_version=routine.version,
            requested_duration_minutes=durations.pop(),
            supported_location_codes=tuple(sorted(supported_locations)),
            required_equipment_codes=equipment,
            exercise_ids=exercise_ids,
        )

    def get_latest_revision(self, session: Session, week_id: UUID) -> LatestPlanRevision | None:
        row = session.scalar(
            select(WeeklyPlanRevision)
            .where(WeeklyPlanRevision.target_user_week_id == week_id)
            .order_by(WeeklyPlanRevision.revision_sequence.desc())
            .limit(1)
        )
        if row is None:
            return None
        ai_count = session.scalar(
            select(func.max(WeeklyPlanRevision.ai_revision_number)).where(
                WeeklyPlanRevision.target_user_week_id == week_id
            )
        )
        return LatestPlanRevision(
            revision_id=row.id,
            revision_sequence=row.revision_sequence,
            successful_ai_revision_count=ai_count or 0,
            routine_id=row.routine_id,
        )

    def create_revision(self, session: Session, values: PlanRevisionValues) -> PlanRevisionValues:
        session.add(
            WeeklyPlanRevision(
                id=values.revision_id,
                target_user_week_id=values.target_user_week_id,
                source_weekly_report_id=values.source_weekly_report_id,
                revision_sequence=values.revision_sequence,
                ai_revision_number=values.ai_revision_number,
                revision_source_code=values.revision_source_code,
                routine_id=values.routine_id,
                selected_location_code=values.selected_location_code,
                safety_status_code=values.safety_status_code,
                input_schema_version=values.input_schema_version,
                input_snapshot=values.input_snapshot,
                input_hash=values.input_hash,
                weekly_plan_policy_version=values.weekly_plan_policy_version,
                revision_reason_codes=values.revision_reason_codes,
                finalization_reason_codes=values.finalization_reason_codes,
                finalized_at=values.finalized_at,
                created_at=values.created_at,
            )
        )
        session.flush()
        return values


__all__ = ["WeeklyPlanRepository"]
