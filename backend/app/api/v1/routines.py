from datetime import date
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_routine_repository,
)
from backend.app.core.errors import AppError
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.routines.ports import RoutineRepositoryPort
from backend.app.modules.routines.schemas import RoutineCreateRequest, RoutineResponse
from backend.app.modules.routines.service import (
    ApprovedCatalogUnavailableError,
    IdempotencyKeyReusedError,
    RoutineContentUnavailableError,
    RoutineDurationUnavailableError,
    RoutineNotFoundError,
    RoutineService,
)

router = APIRouter(prefix="/routines", tags=["routines"])


def _translate_error(exc: Exception) -> AppError:
    if isinstance(exc, IdempotencyKeyReusedError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="IDEMPOTENCY_KEY_REUSED",
            message="동일한 멱등성 키를 다른 요청에 사용할 수 없습니다.",
        )
    if isinstance(exc, RoutineNotFoundError):
        return AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="ROUTINE_NOT_FOUND",
            message="해당 날짜에 활성 루틴이 없습니다.",
        )
    if isinstance(exc, RoutineDurationUnavailableError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="ROUTINE_DURATION_UNAVAILABLE",
            message="승인된 운동으로 요청 시간을 정확히 구성할 수 없습니다.",
        )
    if isinstance(exc, RoutineContentUnavailableError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="ROUTINE_CONTENT_UNAVAILABLE",
            message="승인된 준비·본운동·마무리 구성을 만들 수 없습니다.",
        )
    if isinstance(exc, ApprovedCatalogUnavailableError):
        return AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="APPROVED_CATALOG_UNAVAILABLE",
            message="운영 승인된 운동 카탈로그를 사용할 수 없습니다.",
        )
    if isinstance(exc, IntegrityError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="ROUTINE_VERSION_CONFLICT",
            message="루틴 버전이 변경되었습니다. 다시 시도해주세요.",
        )
    return AppError(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="데이터베이스를 일시적으로 사용할 수 없습니다.",
    )


@router.post("", response_model=RoutineResponse, status_code=HTTPStatus.CREATED)
def create_routine(
    payload: RoutineCreateRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[RoutineRepositoryPort, Depends(get_routine_repository)],
) -> RoutineResponse:
    try:
        return RoutineService(repository).create(
            session, current_user.user_id, payload, idempotency_key
        )
    except (
        IdempotencyKeyReusedError,
        ApprovedCatalogUnavailableError,
        RoutineContentUnavailableError,
        RoutineDurationUnavailableError,
        IntegrityError,
        SQLAlchemyError,
    ) as exc:
        raise _translate_error(exc) from None


@router.get("/current", response_model=RoutineResponse)
def get_current_routine(
    local_date: Annotated[date, Query()],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[RoutineRepositoryPort, Depends(get_routine_repository)],
) -> RoutineResponse:
    try:
        return RoutineService(repository).get_current(session, current_user.user_id, local_date)
    except (RoutineNotFoundError, SQLAlchemyError) as exc:
        raise _translate_error(exc) from None


__all__ = ["router"]
