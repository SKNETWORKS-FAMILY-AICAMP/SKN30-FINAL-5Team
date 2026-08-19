from datetime import date
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_current_user,
    get_daily_context_repository,
    get_db_session,
)
from backend.app.core.errors import AppError
from backend.app.modules.checkins.ports import DailyContextRepositoryPort
from backend.app.modules.checkins.schemas import DailyContextResponse, DailyContextUpsertRequest
from backend.app.modules.checkins.service import (
    DailyContextNotFoundError,
    DailyContextService,
    IdempotencyKeyReusedError,
    StaleContextError,
)
from backend.app.modules.identity.service import CurrentUser

router = APIRouter(prefix="/daily-contexts", tags=["daily-contexts"])


def _expected_version(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    normalized = if_match.strip().removeprefix("W/").strip('"')
    try:
        value = int(normalized)
    except ValueError:
        raise AppError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="INVALID_REQUEST",
            message="If-Match는 현재 context_version이어야 합니다.",
        ) from None
    if value <= 0:
        raise AppError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="INVALID_REQUEST",
            message="If-Match는 현재 context_version이어야 합니다.",
        )
    return value


def _translate_error(exc: Exception) -> AppError:
    if isinstance(exc, DailyContextNotFoundError):
        return AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="DAILY_CONTEXT_NOT_FOUND",
            message="해당 날짜의 체크인을 찾을 수 없습니다.",
        )
    if isinstance(exc, StaleContextError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="STALE_CONTEXT",
            message="체크인 정보가 변경되었습니다. 최신 상태로 다시 시도해주세요.",
        )
    if isinstance(exc, IdempotencyKeyReusedError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="IDEMPOTENCY_KEY_REUSED",
            message="동일한 멱등성 키를 다른 요청에 사용할 수 없습니다.",
        )
    if isinstance(exc, IntegrityError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="INVALID_DOMAIN_CODE",
            message="체크인에 허용되지 않은 코드가 포함되어 있습니다.",
        )
    return AppError(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="데이터베이스를 일시적으로 사용할 수 없습니다.",
    )


@router.put("/{local_date}", response_model=DailyContextResponse)
def replace_daily_context(
    local_date: date,
    payload: DailyContextUpsertRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[DailyContextRepositoryPort, Depends(get_daily_context_repository)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> DailyContextResponse:
    try:
        return DailyContextService(repository).replace(
            session,
            current_user.user_id,
            local_date,
            payload,
            idempotency_key,
            _expected_version(if_match),
        )
    except (
        DailyContextNotFoundError,
        StaleContextError,
        IdempotencyKeyReusedError,
        IntegrityError,
        SQLAlchemyError,
    ) as exc:
        raise _translate_error(exc) from None


@router.get("/{local_date}", response_model=DailyContextResponse)
def get_daily_context(
    local_date: date,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[DailyContextRepositoryPort, Depends(get_daily_context_repository)],
) -> DailyContextResponse:
    try:
        return DailyContextService(repository).get(session, current_user.user_id, local_date)
    except (DailyContextNotFoundError, SQLAlchemyError) as exc:
        raise _translate_error(exc) from None


__all__ = ["router"]
