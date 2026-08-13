from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.catalog import (
    CatalogVersion,
    Exercise,
    ExerciseEquipment,
    ExerciseGoalTagLink,
    ExerciseLocation,
    ExercisePrescriptionProfile,
)
from backend.app.db.models.profile import (
    MutationIdempotencyRecord,
    UserAvailableLocation,
    UserEquipment,
    UserProfile,
)
from backend.app.db.models.routine import Routine, RoutineDay, RoutineItem
from backend.app.modules.routines.codes import (
    ROUTINE_RESPONSE_SCHEMA_VERSION,
    RoutineStatusCode,
    ScheduleRuleCode,
)
from backend.app.modules.routines.ports import (
    RoutineCandidate,
    RoutineCreationContext,
    RoutineDayValues,
    RoutineIdempotencyRecord,
)

_ENDPOINT_CODE = "POST_ROUTINES"


class RoutineRepository:
    def acquire_creation_lock(self, session: Session, user_id: UUID) -> None:
        lock_key = int.from_bytes(sha256(str(user_id).encode()).digest()[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def get_idempotency_record(
        self, session: Session, user_id: UUID, idempotency_key: UUID
    ) -> RoutineIdempotencyRecord | None:
        record = session.scalar(
            select(MutationIdempotencyRecord).where(
                MutationIdempotencyRecord.user_id == user_id,
                MutationIdempotencyRecord.endpoint_code == _ENDPOINT_CODE,
                MutationIdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        if record is None:
            return None
        return RoutineIdempotencyRecord(
            request_hash=record.request_hash,
            response_payload=record.response_payload,
        )

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
                endpoint_code=_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_payload=response_payload,
                response_schema_version=ROUTINE_RESPONSE_SCHEMA_VERSION,
                created_at=now,
            )
        )

    def get_creation_context(
        self, session: Session, user_id: UUID, goal_code: str
    ) -> RoutineCreationContext | None:
        profile = session.get(UserProfile, user_id)
        catalogs = session.scalars(
            select(CatalogVersion).where(
                CatalogVersion.status_code == "ACTIVE",
                CatalogVersion.review_status_code == "DOMAIN_APPROVED",
                CatalogVersion.review_method_code == "DOMAIN_REVIEWER",
                CatalogVersion.status_interpretation_code == "PRODUCTION_APPROVED",
                CatalogVersion.production_eligible.is_(True),
                CatalogVersion.activated_at.is_not(None),
            )
        ).all()
        if profile is None or len(catalogs) != 1:
            return None
        catalog = catalogs[0]
        locations = tuple(
            session.scalars(
                select(UserAvailableLocation.location_code).where(
                    UserAvailableLocation.user_id == user_id
                )
            ).all()
        ) or (profile.preferred_location_code,)
        equipment = tuple(
            session.scalars(
                select(UserEquipment.equipment_code).where(UserEquipment.user_id == user_id)
            ).all()
        )
        rows = session.execute(
            select(ExercisePrescriptionProfile, Exercise, ExerciseGoalTagLink)
            .join(Exercise, Exercise.id == ExercisePrescriptionProfile.exercise_id)
            .join(
                ExerciseGoalTagLink,
                (ExerciseGoalTagLink.exercise_id == Exercise.id)
                & (ExerciseGoalTagLink.goal_code == ExercisePrescriptionProfile.goal_code),
            )
            .where(
                Exercise.catalog_version_id == catalog.id,
                Exercise.review_status_code == "DOMAIN_APPROVED",
                Exercise.beginner_suitable.is_(True),
                ExercisePrescriptionProfile.goal_code == goal_code,
                ExercisePrescriptionProfile.experience_level_code == profile.experience_level_code,
                ExercisePrescriptionProfile.review_status_code == "DOMAIN_APPROVED",
                ExerciseGoalTagLink.review_status_code == "DOMAIN_APPROVED",
            )
        ).all()
        exercise_ids = {exercise.id for _, exercise, _ in rows}
        location_map: dict[UUID, set[str]] = {exercise_id: set() for exercise_id in exercise_ids}
        equipment_map: dict[UUID, set[str]] = {exercise_id: set() for exercise_id in exercise_ids}
        if exercise_ids:
            for exercise_id, location_code in session.execute(
                select(ExerciseLocation.exercise_id, ExerciseLocation.location_code).where(
                    ExerciseLocation.exercise_id.in_(exercise_ids)
                )
            ):
                location_map[exercise_id].add(location_code)
            for exercise_id, equipment_code in session.execute(
                select(ExerciseEquipment.exercise_id, ExerciseEquipment.equipment_code).where(
                    ExerciseEquipment.exercise_id.in_(exercise_ids)
                )
            ):
                equipment_map[exercise_id].add(equipment_code)
        location_set = set(locations)
        equipment_set = set(equipment)
        candidates = tuple(
            RoutineCandidate(
                exercise_id=exercise.id,
                exercise_name=exercise.name_ko,
                training_type_code=exercise.training_type_code,
                body_focus_code=exercise.body_focus_code,
                timing_mode_code=exercise.timing_mode_code,
                seconds_per_rep=exercise.default_seconds_per_rep,
                transition_seconds=exercise.default_transition_seconds,
                phase_code=prescription.phase_code,
                tier_code=goal_link.role_eligibility_code,
                sets=prescription.sets,
                reps=prescription.reps,
                work_seconds_per_set=prescription.work_seconds_per_set,
                rest_seconds_per_set=prescription.rest_seconds_per_set,
                intensity_code=prescription.intensity_code,
            )
            for prescription, exercise, goal_link in rows
            if location_map[exercise.id] & location_set
            and equipment_map[exercise.id].issubset(equipment_set)
        )
        return RoutineCreationContext(
            profile_duration_minutes=profile.default_requested_duration_minutes,
            desired_weekly_workout_count=profile.desired_weekly_workout_count,
            experience_level_code=profile.experience_level_code,
            available_location_codes=locations,
            equipment_codes=equipment,
            catalog_version_id=catalog.id,
            catalog_version_code=catalog.version_code,
            candidates=candidates,
        )

    def create_routine(
        self,
        session: Session,
        user_id: UUID,
        goal_code: str,
        effective_from: date,
        catalog_version_id: UUID,
        days: tuple[RoutineDayValues, ...],
        now: datetime,
    ) -> UUID:
        version = (
            session.scalar(select(func.max(Routine.version)).where(Routine.user_id == user_id)) or 0
        ) + 1
        active = session.scalars(
            select(Routine).where(
                Routine.user_id == user_id,
                Routine.status_code == RoutineStatusCode.ACTIVE,
                (Routine.effective_to.is_(None)) | (Routine.effective_to >= effective_from),
            )
        ).all()
        for existing in active:
            if existing.effective_from < effective_from:
                existing.effective_to = effective_from - timedelta(days=1)
            else:
                existing.status_code = RoutineStatusCode.ARCHIVED
        routine = Routine(
            id=uuid4(),
            user_id=user_id,
            version=version,
            goal_code=goal_code,
            status_code=RoutineStatusCode.ACTIVE,
            effective_from=effective_from,
            effective_to=None,
            catalog_version_id=catalog_version_id,
            created_at=now,
        )
        for day_values in days:
            day = RoutineDay(
                id=uuid4(),
                sequence=day_values.sequence,
                schedule_rule=ScheduleRuleCode.ROTATION,
                title=day_values.title,
                training_type_code=day_values.training_type_code,
                body_focus_code=day_values.body_focus_code,
                requested_duration_minutes=day_values.requested_duration_minutes,
                estimated_duration_seconds=day_values.estimated_duration_seconds,
                setup_seconds=day_values.setup_seconds,
                estimated_calories_burned=None,
                items=[
                    RoutineItem(
                        id=uuid4(),
                        exercise_id=item.exercise_id,
                        sequence=item.sequence,
                        phase_code=item.phase_code,
                        tier_code=item.tier_code,
                        sets=item.sets,
                        reps=item.reps,
                        work_seconds_per_set=item.work_seconds_per_set,
                        rest_seconds_per_set=item.rest_seconds_per_set,
                        intensity_code=item.intensity_code,
                    )
                    for item in day_values.items
                ],
            )
            routine.days.append(day)
        session.add(routine)
        session.flush()
        return routine.id

    def _response_payload(self, session: Session, routine: Routine) -> dict[str, Any]:
        catalog = session.get(CatalogVersion, routine.catalog_version_id)
        exercise_ids = {item.exercise_id for day in routine.days for item in day.items}
        exercises = {
            exercise.id: exercise
            for exercise in session.scalars(
                select(Exercise).where(Exercise.id.in_(exercise_ids))
            ).all()
        }
        if catalog is None or len(exercises) != len(exercise_ids):
            raise RuntimeError("routine references missing catalog content")
        return {
            "id": routine.id,
            "version": routine.version,
            "goal_code": routine.goal_code,
            "status_code": routine.status_code,
            "effective_from": routine.effective_from,
            "catalog_version": catalog.version_code,
            "days": [
                {
                    "id": day.id,
                    "sequence": day.sequence,
                    "title": day.title,
                    "training_type_code": day.training_type_code,
                    "body_focus_code": day.body_focus_code,
                    "requested_duration_minutes": day.requested_duration_minutes,
                    "estimated_duration_seconds": day.estimated_duration_seconds,
                    "estimated_calories_burned": day.estimated_calories_burned,
                    "items": [
                        {
                            "id": item.id,
                            "exercise_id": item.exercise_id,
                            "exercise_name": exercises[item.exercise_id].name_ko,
                            "sequence": item.sequence,
                            "phase_code": item.phase_code,
                            "tier_code": item.tier_code,
                            "sets": item.sets,
                            "reps": item.reps,
                            "work_seconds_per_set": item.work_seconds_per_set,
                            "rest_seconds_per_set": item.rest_seconds_per_set,
                            "instruction_available": bool(
                                exercises[item.exercise_id].instruction_summary_ko
                            ),
                        }
                        for item in day.items
                    ],
                }
                for day in routine.days
            ],
            "created_at": routine.created_at,
        }

    def get_routine_response_payload(
        self, session: Session, user_id: UUID, routine_id: UUID
    ) -> dict[str, Any] | None:
        routine = session.scalar(
            select(Routine)
            .options(selectinload(Routine.days).selectinload(RoutineDay.items))
            .where(Routine.id == routine_id, Routine.user_id == user_id)
        )
        return None if routine is None else self._response_payload(session, routine)

    def get_current_routine_payload(
        self, session: Session, user_id: UUID, local_date: date
    ) -> dict[str, Any] | None:
        routines = session.scalars(
            select(Routine)
            .options(selectinload(Routine.days).selectinload(RoutineDay.items))
            .where(
                Routine.user_id == user_id,
                Routine.status_code == RoutineStatusCode.ACTIVE,
                Routine.effective_from <= local_date,
                (Routine.effective_to.is_(None)) | (Routine.effective_to >= local_date),
            )
            .order_by(Routine.version.desc())
        ).all()
        if not routines:
            return None
        if len(routines) != 1:
            raise RuntimeError("multiple active routines overlap")
        return self._response_payload(session, routines[0])


__all__ = ["RoutineRepository"]
