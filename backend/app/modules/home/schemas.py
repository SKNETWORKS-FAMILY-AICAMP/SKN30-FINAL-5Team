from datetime import date

from pydantic import BaseModel

from backend.app.modules.decisions.schemas import DecisionPlan, DecisionResponse
from backend.app.modules.workouts.schemas import WorkoutSessionDetailResponse


class HomeStateResponse(BaseModel):
    """Everything the home screen needs to restore itself after a restart.

    Both members are optional and independently absent: a user who has not checked in
    yet has neither, one who has a routine but has not selected it has a decision and no
    session. The client renders the state it is given rather than inferring one from a
    404 on each of two calls.

    Composition only. Every field is the same contract the dedicated endpoints return,
    so a client can keep using those and this stays a convenience.
    """

    local_date: date
    decision: DecisionResponse | None = None
    final_plan: DecisionPlan | None = None
    workout_session: WorkoutSessionDetailResponse | None = None


__all__ = ["HomeStateResponse"]
