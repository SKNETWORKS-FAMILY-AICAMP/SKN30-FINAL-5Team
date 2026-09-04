from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_decision_repository,
    get_workout_repository,
)
from backend.app.core.errors import AppError
from backend.app.modules.decisions.ports import DecisionRepositoryPort
from backend.app.modules.home.schemas import HomeStateResponse
from backend.app.modules.home.service import HomeService
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.workouts.ports import WorkoutRepositoryPort

router = APIRouter(prefix="/home", tags=["home"])


@router.get("", response_model=HomeStateResponse, response_model_exclude_unset=True)
def get_home_state(
    local_date: Annotated[date, Query()],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    decisions: Annotated[DecisionRepositoryPort, Depends(get_decision_repository)],
    workouts: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> HomeStateResponse:
    """Return the day's decision, its plan, and the workout session in one read.

    A day with no check-in yet is an empty state, not an error: both members come back
    null and the client shows the check-in prompt.
    """

    try:
        return HomeService(decisions, workouts).get_state(session, current_user.user_id, local_date)
    except SQLAlchemyError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="DATABASE_UNAVAILABLE",
            message="데이터베이스를 일시적으로 사용할 수 없습니다.",
        ) from None


__all__ = ["router"]
