from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_notification_repository,
    get_workout_repository,
)
from backend.app.core.errors import AppError
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.notifications.ports import NotificationRepositoryPort
from backend.app.modules.notifications.schemas import NotificationListResponse, NotificationResponse
from backend.app.modules.notifications.service import NotificationNotFoundError, NotificationService
from backend.app.modules.workouts.ports import WorkoutRepositoryPort

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _error(exc: Exception) -> AppError:
    if isinstance(exc, NotificationNotFoundError):
        return AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="NOTIFICATION_NOT_FOUND",
            message="알림을 찾을 수 없습니다.",
        )
    return AppError(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        code="NOTIFICATION_UNAVAILABLE",
        message="알림을 일시적으로 사용할 수 없습니다.",
    )


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[NotificationRepositoryPort, Depends(get_notification_repository)],
    workout_repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> NotificationListResponse:
    try:
        return NotificationService(repository, workout_repository).list_notifications(
            session,
            current_user.user_id,
            previous_last_active_at=current_user.previous_last_active_at,
        )
    except SQLAlchemyError as exc:
        raise _error(exc) from None


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[NotificationRepositoryPort, Depends(get_notification_repository)],
    workout_repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> NotificationResponse:
    try:
        return NotificationService(repository, workout_repository).mark_read(
            session, current_user.user_id, notification_id
        )
    except (NotificationNotFoundError, SQLAlchemyError) as exc:
        raise _error(exc) from None


__all__ = ["router"]
