from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_catalog_repository,
    get_current_user,
    get_db_session,
)
from backend.app.core.errors import AppError
from backend.app.modules.catalog.codes import (
    BodyAreaCode,
    DifficultyCode,
    EquipmentCode,
    TrainingTypeCode,
)
from backend.app.modules.catalog.schemas import (
    ExerciseDetailResponse,
    ExerciseListResponse,
    ExerciseVariantsResponse,
)
from backend.app.modules.catalog.service import (
    ExerciseCatalogUnavailableError,
    ExerciseNotFoundError,
    ExerciseReadRepositoryPort,
    ExerciseReadService,
    ExerciseVariantSetUnavailableError,
    InvalidExerciseListQueryError,
)
from backend.app.modules.identity.service import CurrentUser

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get("", response_model=ExerciseListResponse)
def list_exercises(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[ExerciseReadRepositoryPort, Depends(get_catalog_repository)],
    body_area_code: Annotated[BodyAreaCode | None, Query()] = None,
    equipment_code: Annotated[EquipmentCode | None, Query()] = None,
    training_type_code: Annotated[TrainingTypeCode | None, Query()] = None,
    difficulty_code: Annotated[DifficultyCode | None, Query()] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ExerciseListResponse:
    del current_user
    try:
        return ExerciseReadService(repository).list_exercises(
            session,
            body_area_code=body_area_code,
            equipment_code=equipment_code,
            training_type_code=training_type_code,
            difficulty_code=difficulty_code,
            cursor=cursor,
            limit=limit,
        )
    except InvalidExerciseListQueryError:
        raise AppError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="INVALID_REQUEST",
            message="조회 조건이 올바르지 않습니다.",
        ) from None
    except ExerciseCatalogUnavailableError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="APPROVED_CATALOG_UNAVAILABLE",
            message="운영 승인된 운동 카탈로그를 사용할 수 없습니다.",
        ) from None
    except SQLAlchemyError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="DATABASE_UNAVAILABLE",
            message="데이터베이스를 일시적으로 사용할 수 없습니다.",
        ) from None


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


@router.get("/{exercise_id}/variants", response_model=ExerciseVariantsResponse)
def get_exercise_variants(
    exercise_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[ExerciseReadRepositoryPort, Depends(get_catalog_repository)],
) -> ExerciseVariantsResponse:
    del current_user
    try:
        return ExerciseReadService(repository).get_equipment_variants(session, exercise_id)
    except ExerciseNotFoundError:
        raise AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            message="해당 운동 정보를 찾을 수 없습니다.",
        ) from None
    except (ExerciseCatalogUnavailableError, ExerciseVariantSetUnavailableError):
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="APPROVED_CATALOG_UNAVAILABLE",
            message="운영 승인된 운동 카탈로그를 사용할 수 없습니다.",
        ) from None
    except SQLAlchemyError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="DATABASE_UNAVAILABLE",
            message="데이터베이스를 일시적으로 사용할 수 없습니다.",
        ) from None


__all__ = ["router"]
