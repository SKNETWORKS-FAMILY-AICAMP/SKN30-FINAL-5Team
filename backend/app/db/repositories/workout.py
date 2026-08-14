from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.decision import DecisionRun, PlanCandidate, PlanItem
from backend.app.db.models.profile import MutationIdempotencyRecord
from backend.app.db.models.workout import (
    DecisionSelection,
    WorkoutAdditionalActivity,
    WorkoutSession,
    WorkoutSessionItem,
    WorkoutTimerEvent,
)
from backend.app.modules.workouts.codes import WORKOUT_RESPONSE_SCHEMA_VERSION
from backend.app.modules.workouts.ports import IdempotencyRecord, SelectionSource, SessionState


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


__all__ = ["WorkoutRepository"]
