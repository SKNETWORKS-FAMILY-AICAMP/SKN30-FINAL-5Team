"""Compose the day's decision and workout session into one home-screen read.

This service owns no rules. It reads the two existing projections and returns them
together, so a client restoring its screen makes one request instead of two and cannot
land on a state where the decision it just read is not the one the session belongs to.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.modules.decisions.ports import DecisionRepositoryPort
from backend.app.modules.decisions.schemas import DecisionResponse
from backend.app.modules.home.schemas import HomeStateResponse
from backend.app.modules.workouts.ports import WorkoutRepositoryPort
from backend.app.modules.workouts.service import WorkoutLogNotFoundError, WorkoutService


class HomeService:
    def __init__(
        self,
        decisions: DecisionRepositoryPort,
        workouts: WorkoutRepositoryPort,
    ) -> None:
        self._decisions = decisions
        self._workouts = workouts

    def get_state(self, session: Session, user_id: UUID, local_date: date) -> HomeStateResponse:
        stored = self._decisions.get_response_for_date(session, user_id, local_date)
        decision = None if stored is None else DecisionResponse.model_validate(stored)
        final_plan = None if decision is None else decision.final_plan

        workout_session = None
        record = (
            None
            if final_plan is None
            else self._workouts.get_workout_log_detail_for_plan(
                session, user_id, final_plan.plan_id
            )
        )
        if record is not None:
            try:
                workout_session = WorkoutService(self._workouts).get_workout_log_detail(
                    session, user_id, record.session_id
                )
            except WorkoutLogNotFoundError:  # pragma: no cover - lost between two reads
                workout_session = None

        return HomeStateResponse(
            local_date=local_date,
            decision=decision,
            final_plan=final_plan,
            workout_session=workout_session,
        )


__all__ = ["HomeService"]
