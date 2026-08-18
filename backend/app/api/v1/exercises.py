from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_catalog_repository,
    get_current_user,
    get_db_session,
)
from backend.app.core.errors import AppError
from backend.app.modules.catalog.schemas import ExerciseDetailResponse
from backend.app.modules.catalog.service import (
    ExerciseNotFoundError,
    ExerciseReadRepositoryPort,
    ExerciseReadService,
)
from backend.app.modules.identity.service import CurrentUser

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get("/{exercise_id}", response_model=ExerciseDetailResponse)
def get_exercise_detail(
    exercise_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[ExerciseReadRepositoryPort, Depends(get_catalog_repository)],
) -> ExerciseDetailResponse:
    del current_user
    try:
        return ExerciseReadService(repository).get_detail(session, exercise_id)
    except ExerciseNotFoundError:
        raise AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            message="해당 운동 정보를 찾을 수 없습니다.",
        ) from None
    except SQLAlchemyError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="DATABASE_UNAVAILABLE",
            message="데이터베이스를 일시적으로 사용할 수 없습니다.",
        ) from None


__all__ = ["router"]
