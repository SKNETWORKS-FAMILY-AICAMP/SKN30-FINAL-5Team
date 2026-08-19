from datetime import date, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.catalog import Exercise
from backend.app.db.models.decision import DecisionRun, PlanCandidate, PlanItem
from backend.app.db.models.profile import MutationIdempotencyRecord
from backend.app.db.models.workout import (
    DecisionSelection,
    WorkoutAdditionalActivity,
    WorkoutFeedback,
    WorkoutFeedbackAdverseReaction,
    WorkoutFeedbackDiscomfort,
    WorkoutSafetyEvent,
    WorkoutSafetyEventAdverseReaction,
    WorkoutSafetyEventDiscomfort,
    WorkoutSession,
    WorkoutSessionItem,
    WorkoutSkipFeedback,
    WorkoutTimerEvent,
)
from backend.app.domain.rules.safety import EMERGENCY_REACTION_CODES
from backend.app.modules.workouts.codes import WORKOUT_RESPONSE_SCHEMA_VERSION
from backend.app.modules.workouts.ports import (
    IdempotencyRecord,
    ReturnHistory,
    SelectionSource,
    SessionState,
    WorkoutLogCursor,
    WorkoutLogDetail,
    WorkoutLogFeedback,
    WorkoutLogItem,
    WorkoutLogSummary,
)


class WorkoutRepository:
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
    ) -> IdempotencyRecord | None:
        row = session.scalar(
            select(MutationIdempotencyRecord).where(
                MutationIdempotencyRecord.user_id == user_id,
                MutationIdempotencyRecord.endpoint_code == endpoint_code,
                MutationIdempotencyRecord.idempotency_key == key,
            )
        )
        if row is None:
            return None
        return IdempotencyRecord(row.request_hash, row.response_payload)

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
                response_schema_version=WORKOUT_RESPONSE_SCHEMA_VERSION,
                created_at=now,
            )
        )

    def get_selection_source(
        self, session: Session, user_id: UUID, decision_id: UUID, option_id: UUID
    ) -> SelectionSource | None:
        run = session.scalar(
            select(DecisionRun)
            .options(
                selectinload(DecisionRun.options),
                selectinload(DecisionRun.candidates).selectinload(PlanCandidate.items),
                selectinload(DecisionRun.safety_reviews),
            )
            .where(DecisionRun.id == decision_id, DecisionRun.user_id == user_id)
            .with_for_update()
        )
        if run is None:
            return None
        option = next((value for value in run.options if value.id == option_id), None)
        if option is None:
            return None
        candidate = next((value for value in run.candidates if value.selected), None)
        safety = run.safety_reviews[0] if run.safety_reviews else None
        existing_selection = session.scalar(
            select(DecisionSelection.id).where(DecisionSelection.decision_run_id == run.id)
        )
        return SelectionSource(
            decision_id=run.id,
            option_id=option.id,
            option_code=option.option_code,
            option_action_code=option.action_code,
            option_selectable=option.selectable,
            option_plan_candidate_id=option.plan_candidate_id,
            decision_status_code=run.status_code,
            decision_safety_status_code=run.safety_status_code,
            recommended_action_code=run.recommended_action_code,
            selected_candidate_id=None if candidate is None else candidate.id,
            selected_candidate_action_code=None if candidate is None else candidate.action_code,
            safety_candidate_id=None if safety is None else safety.plan_candidate_id,
            safety_status_code=None if safety is None else safety.safety_status_code,
            safety_vetoed=None if safety is None else safety.vetoed,
            plan_item_ids=()
            if candidate is None
            else tuple(
                item.id for item in sorted(candidate.items, key=lambda value: value.sequence)
            ),
            estimated_calories_burned=None
            if candidate is None
            else candidate.estimated_calories_burned,
            already_selected=existing_selection is not None,
        )

    def create_selection(
        self,
        session: Session,
        *,
        source: SelectionSource,
        user_id: UUID,
        selection_id: UUID,
        workout_session_id: UUID | None,
        idempotency_key: UUID,
        now: datetime,
    ) -> None:
        selection = DecisionSelection(
            id=selection_id,
            decision_run_id=source.decision_id,
            decision_option_id=source.option_id,
            selected_action_code=source.option_action_code,
            idempotency_key=idempotency_key,
            selected_at=now,
        )
        session.add(selection)
        if workout_session_id is None:
            session.flush()
            return
        if source.selected_candidate_id is None:
            raise ValueError("workout selection requires a selected plan candidate")
        workout = WorkoutSession(
            id=workout_session_id,
            user_id=user_id,
            decision_selection_id=selection_id,
            plan_candidate_id=source.selected_candidate_id,
            scheduled_workout_id=None,
            status_code="PLANNED",
            started_at=None,
            ended_at=None,
            actual_elapsed_seconds=None,
            estimated_calories_burned=source.estimated_calories_burned,
            idempotency_key=idempotency_key,
            created_at=now,
        )
        session.add(workout)
        session.add_all(
            [
                WorkoutSessionItem(
                    id=uuid4(),
                    workout_session_id=workout_session_id,
                    plan_item_id=plan_item_id,
                    status_code="PENDING",
                    completed_at=None,
                    updated_at=now,
                )
                for plan_item_id in source.plan_item_ids
            ]
        )
        session.flush()

    def get_session_state(
        self, session: Session, user_id: UUID, session_id: UUID
    ) -> SessionState | None:
        workout = session.scalar(
            select(WorkoutSession)
            .where(WorkoutSession.id == session_id, WorkoutSession.user_id == user_id)
            .with_for_update()
        )
        if workout is None:
            return None
        items = session.execute(
            select(
                WorkoutSessionItem.plan_item_id,
                WorkoutSessionItem.status_code,
                WorkoutSessionItem.completed_at,
            )
            .join(PlanItem, PlanItem.id == WorkoutSessionItem.plan_item_id)
            .where(WorkoutSessionItem.workout_session_id == workout.id)
            .order_by(PlanItem.sequence)
        ).all()
        return SessionState(
            workout.id,
            workout.status_code,
            workout.started_at,
            workout.ended_at,
            tuple(
                (plan_item_id, status, completed_at) for plan_item_id, status, completed_at in items
            ),
            workout.estimated_calories_burned,
        )

    def start_session(
        self, session: Session, session_id: UUID, started_at: datetime
    ) -> SessionState:
        workout = session.get(WorkoutSession, session_id)
        if workout is None:
            raise LookupError("locked workout session disappeared")
        workout.status_code = "IN_PROGRESS"
        workout.started_at = started_at
        session.flush()
        state = self.get_session_state(session, workout.user_id, workout.id)
        if state is None:
            raise LookupError("started workout session cannot be read")
        return state

    def update_session_item(
        self,
        session: Session,
        session_id: UUID,
        plan_item_id: UUID,
        status_code: str,
        now: datetime,
    ) -> SessionState | None:
        item = session.scalar(
            select(WorkoutSessionItem)
            .where(
                WorkoutSessionItem.workout_session_id == session_id,
                WorkoutSessionItem.plan_item_id == plan_item_id,
            )
            .with_for_update()
        )
        if item is None:
            return None
        item.status_code = status_code
        item.completed_at = now if status_code == "COMPLETED" else None
        item.updated_at = now
        session.flush()
        workout = session.get(WorkoutSession, session_id)
        if workout is None:
            raise LookupError("workout session disappeared while updating an item")
        return self.get_session_state(session, workout.user_id, workout.id)

    def create_timer_event(
        self,
        session: Session,
        *,
        event_id: UUID,
        session_id: UUID,
        event_code: str,
        occurred_at: datetime,
        client_recorded_at: datetime,
        now: datetime,
    ) -> None:
        session.add(
            WorkoutTimerEvent(
                id=event_id,
                workout_session_id=session_id,
                event_code=event_code,
                occurred_at=occurred_at,
                client_recorded_at=client_recorded_at,
                created_at=now,
            )
        )
        session.flush()

    def create_additional_activity(
        self,
        session: Session,
        *,
        activity_id: UUID,
        session_id: UUID,
        activity_type_code: str,
        duration_seconds: int,
        intensity_code: str | None,
        note: str | None,
        now: datetime,
    ) -> None:
        session.add(
            WorkoutAdditionalActivity(
                id=activity_id,
                workout_session_id=session_id,
                activity_type_code=activity_type_code,
                duration_seconds=duration_seconds,
                intensity_code=intensity_code,
                note=note,
                created_at=now,
            )
        )
        session.flush()

    def create_safety_event(
        self,
        session: Session,
        *,
        event_id: UUID,
        session_id: UUID,
        occurred_at: datetime,
        instruction_code: str,
        resulting_action_code: str | None,
        session_status_code: str,
        guidance_code: str,
        reason_code: str,
        rule_version: str,
        discomforts: tuple[tuple[str, str], ...],
        adverse_reaction_codes: tuple[str, ...],
        now: datetime,
    ) -> None:
        session.add(
            WorkoutSafetyEvent(
                id=event_id,
                workout_session_id=session_id,
                occurred_at=occurred_at,
                instruction_code=instruction_code,
                resulting_action_code=resulting_action_code,
                guidance_code=guidance_code,
                reason_code=reason_code,
                rule_version=rule_version,
                created_at=now,
            )
        )
        session.add_all(
            [
                WorkoutSafetyEventDiscomfort(
                    id=uuid4(),
                    workout_safety_event_id=event_id,
                    body_area_code=body_area_code,
                    severity_code=severity_code,
                )
                for body_area_code, severity_code in discomforts
            ]
        )
        session.add_all(
            [
                WorkoutSafetyEventAdverseReaction(
                    workout_safety_event_id=event_id, reaction_code=reaction_code
                )
                for reaction_code in adverse_reaction_codes
            ]
        )
        if session_status_code == "STOPPED_FOR_SAFETY":
            self.finish_session(
                session,
                session_id=session_id,
                status_code=session_status_code,
                ended_at=occurred_at,
                actual_elapsed_seconds=None,
            )
        session.flush()

    def finish_session(
        self,
        session: Session,
        *,
        session_id: UUID,
        status_code: str,
        ended_at: datetime,
        actual_elapsed_seconds: int | None,
    ) -> None:
        workout = session.get(WorkoutSession, session_id)
        if workout is None:
            raise LookupError("locked workout session disappeared")
        workout.status_code = status_code
        workout.ended_at = ended_at
        workout.actual_elapsed_seconds = actual_elapsed_seconds
        session.flush()

    def create_skip_feedback(
        self,
        session: Session,
        *,
        session_id: UUID,
        reason_code: str,
        now: datetime,
    ) -> None:
        session.add(
            WorkoutSkipFeedback(
                workout_session_id=session_id,
                reason_code=reason_code,
                created_at=now,
            )
        )
        session.flush()

    def feedback_exists(self, session: Session, session_id: UUID) -> bool:
        return (
            session.scalar(
                select(WorkoutFeedback.workout_session_id).where(
                    WorkoutFeedback.workout_session_id == session_id
                )
            )
            is not None
        )

    def create_feedback(
        self,
        session: Session,
        *,
        session_id: UUID,
        difficulty_code: str,
        fatigue_code: str | None,
        satisfaction_code: str | None,
        pain_occurred: bool,
        discomforts: tuple[tuple[str, str], ...],
        adverse_reaction_codes: tuple[str, ...],
        now: datetime,
    ) -> None:
        session.add(
            WorkoutFeedback(
                workout_session_id=session_id,
                difficulty_code=difficulty_code,
                fatigue_code=fatigue_code,
                satisfaction_code=satisfaction_code,
                pain_occurred=pain_occurred,
                created_at=now,
            )
        )
        session.add_all(
            [
                WorkoutFeedbackDiscomfort(
                    id=uuid4(),
                    workout_session_id=session_id,
                    body_area_code=body_area_code,
                    severity_code=severity_code,
                )
                for body_area_code, severity_code in discomforts
            ]
        )
        session.add_all(
            [
                WorkoutFeedbackAdverseReaction(
                    workout_session_id=session_id, reaction_code=reaction_code
                )
                for reaction_code in adverse_reaction_codes
            ]
        )
        session.flush()

    def get_return_history(
        self, session: Session, user_id: UUID, before_local_date: date
    ) -> ReturnHistory:
        base = (
            select(WorkoutSession.status_code, DecisionRun.local_date)
            .join(
                DecisionSelection,
                DecisionSelection.id == WorkoutSession.decision_selection_id,
            )
            .join(DecisionRun, DecisionRun.id == DecisionSelection.decision_run_id)
            .where(
                WorkoutSession.user_id == user_id,
                DecisionRun.local_date < before_local_date,
            )
            .subquery()
        )
        last_completed = session.scalar(
            select(func.max(base.c.local_date)).where(base.c.status_code == "COMPLETED")
        )
        not_completed_count = session.scalar(
            select(func.count()).select_from(base).where(base.c.status_code == "NOT_COMPLETED")
        )
        return ReturnHistory(
            last_completed_local_date=last_completed,
            not_completed_history_count=int(not_completed_count or 0),
        )

    def is_pressure_notification_suppressed(
        self, session: Session, user_id: UUID, local_date: date
    ) -> bool:
        rest_selected = session.scalar(
            select(DecisionSelection.id)
            .join(DecisionRun, DecisionRun.id == DecisionSelection.decision_run_id)
            .where(
                DecisionRun.user_id == user_id,
                DecisionRun.local_date == local_date,
                DecisionSelection.selected_action_code == "REST",
            )
            .limit(1)
        )
        if rest_selected is not None:
            return True
        stop_action = session.scalar(
            select(WorkoutSafetyEvent.id)
            .join(WorkoutSession, WorkoutSession.id == WorkoutSafetyEvent.workout_session_id)
            .join(
                DecisionSelection,
                DecisionSelection.id == WorkoutSession.decision_selection_id,
            )
            .join(DecisionRun, DecisionRun.id == DecisionSelection.decision_run_id)
            .where(
                WorkoutSession.user_id == user_id,
                DecisionRun.local_date == local_date,
                WorkoutSafetyEvent.resulting_action_code.in_({"REST", "STOP_AND_SEEK_HELP"}),
            )
            .limit(1)
        )
        if stop_action is not None:
            return True
        emergency_codes = tuple(code.value for code in EMERGENCY_REACTION_CODES)
        return (
            session.scalar(
                select(WorkoutFeedbackAdverseReaction.workout_session_id)
                .join(
                    WorkoutSession,
                    WorkoutSession.id == WorkoutFeedbackAdverseReaction.workout_session_id,
                )
                .join(
                    DecisionSelection,
                    DecisionSelection.id == WorkoutSession.decision_selection_id,
                )
                .join(DecisionRun, DecisionRun.id == DecisionSelection.decision_run_id)
                .where(
                    WorkoutSession.user_id == user_id,
                    DecisionRun.local_date == local_date,
                    WorkoutFeedbackAdverseReaction.reaction_code.in_(emergency_codes),
                )
                .limit(1)
            )
            is not None
        )

    def list_workout_logs(
        self,
        session: Session,
        user_id: UUID,
        *,
        from_local_date: date | None,
        to_local_date: date | None,
        status_code: str | None,
        cursor: WorkoutLogCursor | None,
        limit: int,
    ) -> tuple[WorkoutLogSummary, ...]:
        completed_count = (
            select(func.count())
            .select_from(WorkoutSessionItem)
            .where(
                WorkoutSessionItem.workout_session_id == WorkoutSession.id,
                WorkoutSessionItem.status_code == "COMPLETED",
            )
            .correlate(WorkoutSession)
            .scalar_subquery()
        )
        total_count = (
            select(func.count())
            .select_from(WorkoutSessionItem)
            .where(WorkoutSessionItem.workout_session_id == WorkoutSession.id)
            .correlate(WorkoutSession)
            .scalar_subquery()
        )
        not_completed_reason = (
            select(WorkoutSkipFeedback.reason_code)
            .where(WorkoutSkipFeedback.workout_session_id == WorkoutSession.id)
            .correlate(WorkoutSession)
            .scalar_subquery()
        )
        statement = (
            select(
                WorkoutSession.id,
                DecisionRun.local_date,
                WorkoutSession.status_code,
                completed_count,
                total_count,
                PlanCandidate.requested_duration_minutes,
                PlanCandidate.training_type_code,
                not_completed_reason,
                WorkoutSession.started_at,
                WorkoutSession.ended_at,
            )
            .join(PlanCandidate, PlanCandidate.id == WorkoutSession.plan_candidate_id)
            .join(DecisionRun, DecisionRun.id == PlanCandidate.decision_run_id)
            .where(WorkoutSession.user_id == user_id)
        )
        if from_local_date is not None:
            statement = statement.where(DecisionRun.local_date >= from_local_date)
        if to_local_date is not None:
            statement = statement.where(DecisionRun.local_date <= to_local_date)
        if status_code is not None:
            statement = statement.where(WorkoutSession.status_code == status_code)
        if cursor is not None:
            statement = statement.where(
                or_(
                    DecisionRun.local_date < cursor.local_date,
                    and_(
                        DecisionRun.local_date == cursor.local_date,
                        WorkoutSession.id < cursor.session_id,
                    ),
                )
            )
        rows = session.execute(
            statement.order_by(DecisionRun.local_date.desc(), WorkoutSession.id.desc()).limit(limit)
        ).all()
        return tuple(
            WorkoutLogSummary(
                session_id=row[0],
                local_date=row[1],
                status_code=row[2],
                completed_item_count=int(row[3]),
                total_item_count=int(row[4]),
                requested_duration_minutes=row[5],
                training_type_code=row[6],
                not_completed_reason_code=row[7],
                started_at=row[8],
                finished_at=row[9],
            )
            for row in rows
        )

    def get_workout_log_detail(
        self, session: Session, user_id: UUID, session_id: UUID
    ) -> WorkoutLogDetail | None:
        row = session.execute(
            select(
                WorkoutSession.id,
                DecisionRun.local_date,
                WorkoutSession.status_code,
                PlanCandidate.requested_duration_minutes,
                WorkoutSkipFeedback.reason_code,
                WorkoutSession.started_at,
                WorkoutSession.ended_at,
                WorkoutFeedback.difficulty_code,
                WorkoutFeedback.pain_occurred,
            )
            .join(PlanCandidate, PlanCandidate.id == WorkoutSession.plan_candidate_id)
            .join(DecisionRun, DecisionRun.id == PlanCandidate.decision_run_id)
            .outerjoin(
                WorkoutSkipFeedback,
                WorkoutSkipFeedback.workout_session_id == WorkoutSession.id,
            )
            .outerjoin(
                WorkoutFeedback,
                WorkoutFeedback.workout_session_id == WorkoutSession.id,
            )
            .where(WorkoutSession.id == session_id, WorkoutSession.user_id == user_id)
        ).one_or_none()
        if row is None:
            return None
        item_rows = session.execute(
            select(
                WorkoutSessionItem.plan_item_id,
                PlanItem.exercise_id,
                Exercise.name_ko,
                WorkoutSessionItem.status_code,
                PlanItem.sets,
                PlanItem.reps,
                PlanItem.work_seconds_per_set,
                WorkoutSessionItem.completed_at,
            )
            .join(PlanItem, PlanItem.id == WorkoutSessionItem.plan_item_id)
            .join(Exercise, Exercise.id == PlanItem.exercise_id)
            .where(WorkoutSessionItem.workout_session_id == session_id)
            .order_by(PlanItem.sequence)
        ).all()
        items = tuple(
            WorkoutLogItem(
                plan_item_id=item[0],
                exercise_id=item[1],
                exercise_name=item[2],
                status_code=item[3],
                sets=item[4],
                reps=item[5],
                work_seconds_per_set=item[6],
                completed_at=item[7],
            )
            for item in item_rows
        )
        feedback = None
        if row[7] is not None:
            feedback = WorkoutLogFeedback(
                perceived_difficulty_code=row[7],
                post_workout_discomfort_reported=bool(row[8]),
            )
        return WorkoutLogDetail(
            session_id=row[0],
            local_date=row[1],
            status_code=row[2],
            requested_duration_minutes=row[3],
            items=items,
            feedback=feedback,
            not_completed_reason_code=row[4],
            started_at=row[5],
            finished_at=row[6],
        )


__all__ = ["WorkoutRepository"]
