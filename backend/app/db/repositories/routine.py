from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.catalog import (
    CatalogVersion,
    Exercise,
    ExerciseGoalTagLink,
    ExercisePrescriptionProfile,
)
from backend.app.db.models.decision import PlanCandidate
from backend.app.db.models.profile import (
    MutationIdempotencyRecord,
    UserAvailableLocation,
    UserEquipment,
    UserProfile,
)
from backend.app.db.models.routine import Routine, RoutineDay, RoutineItem
from backend.app.db.models.workout import WorkoutSession
from backend.app.domain.rules.training_level import allowed_exercise_difficulty_codes
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
        allowed_difficulties = allowed_exercise_difficulty_codes(profile.experience_level_code)
        if not allowed_difficulties:
            return None
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
                Exercise.difficulty_code.in_(allowed_difficulties),
                ExercisePrescriptionProfile.goal_code == goal_code,
                ExercisePrescriptionProfile.experience_level_code == profile.experience_level_code,
                ExercisePrescriptionProfile.review_status_code == "DOMAIN_APPROVED",
                ExerciseGoalTagLink.review_status_code == "DOMAIN_APPROVED",
            )
        ).all()
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
            # Neither equipment nor location gates the base routine. Equipment left
            # onboarding on 2026-08-27; ADR-0017 does the same for location because the
            # base routine is a weekly template and the day's location only arrives with
            # the check-in. The daily Safety-approved Pool applies that constraint, and
            # the variant lookup tells the user how to work around missing kit.
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

    def has_any_routine(self, session: Session, user_id: UUID) -> bool:
        """Return whether the user already has a base-routine version.

        Automatic onboarding creation is initial provisioning, not a profile
        revision mechanism. Archived versions count too, so this path cannot
        bypass the explicit routine version policy.
        """

        return (
            session.scalar(select(Routine.id).where(Routine.user_id == user_id).limit(1))
            is not None
        )

    def get_recent_performed_body_focus_codes(
        self, session: Session, user_id: UUID, local_date: date
    ) -> tuple[str, ...]:
        """Return seven local days of actual COMPLETED/PARTIAL body-focus history."""

        profile = session.get(UserProfile, user_id)
        if profile is None:
            return ()
        ended_local_date = func.date(func.timezone(profile.timezone, WorkoutSession.ended_at))
        values = session.scalars(
            select(PlanCandidate.body_focus_code)
            .join(WorkoutSession, WorkoutSession.plan_candidate_id == PlanCandidate.id)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status_code.in_(("COMPLETED", "PARTIAL")),
                WorkoutSession.ended_at.is_not(None),
                PlanCandidate.body_focus_code.is_not(None),
                ended_local_date >= local_date - timedelta(days=6),
                ended_local_date <= local_date,
            )
            .order_by(WorkoutSession.ended_at.desc(), WorkoutSession.id.desc())
        ).all()
        return tuple(value for value in values if value is not None)

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

    def archive_routines_with_other_duration(
        self,
        session: Session,
        user_id: UUID,
        *,
        requested_duration_minutes: int,
    ) -> int:
        """Archive this user's active routines built to a different duration.

        Scoped to the caller's own user id and to routines whose stored target
        no longer matches, so a profile edit that does not move the duration
        archives nothing.
        """

        stale_ids = session.scalars(
            select(Routine.id)
            .join(RoutineDay, RoutineDay.routine_id == Routine.id)
            .where(
                Routine.user_id == user_id,
                Routine.status_code == "ACTIVE",
                RoutineDay.requested_duration_minutes != requested_duration_minutes,
            )
            .distinct()
        ).all()
        if not stale_ids:
            return 0
        session.execute(
            update(Routine).where(Routine.id.in_(stale_ids)).values(status_code="ARCHIVED")
        )
        return len(stale_ids)

    def get_current_routine_payload(
        self, session: Session, user_id: UUID, local_date: date
    ) -> dict[str, Any] | None:
        routines = session.scalars(
            select(Routine)
            .join(CatalogVersion, CatalogVersion.id == Routine.catalog_version_id)
            .options(selectinload(Routine.days).selectinload(RoutineDay.items))
            .where(
                Routine.user_id == user_id,
                Routine.status_code == RoutineStatusCode.ACTIVE,
                Routine.effective_from <= local_date,
                (Routine.effective_to.is_(None)) | (Routine.effective_to >= local_date),
                CatalogVersion.status_code == "ACTIVE",
                CatalogVersion.review_status_code == "DOMAIN_APPROVED",
                CatalogVersion.review_method_code == "DOMAIN_REVIEWER",
                CatalogVersion.status_interpretation_code == "PRODUCTION_APPROVED",
                CatalogVersion.production_eligible.is_(True),
                CatalogVersion.activated_at.is_not(None),
            )
            .order_by(Routine.version.desc())
        ).all()
        if not routines:
            return None
        if len(routines) != 1:
            raise RuntimeError("multiple active routines overlap")
        return self._response_payload(session, routines[0])


__all__ = ["RoutineRepository"]
