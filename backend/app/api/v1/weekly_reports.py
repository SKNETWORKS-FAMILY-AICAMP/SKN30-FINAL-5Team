from datetime import date
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_weekly_report_narration_agent,
    get_weekly_report_repository,
)
from backend.app.core.errors import AppError
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.weekly_reports.ports import (
    WeeklyReportNarrationAgentPort,
    WeeklyReportRepositoryPort,
)
from backend.app.modules.weekly_reports.schemas import (
    WeeklyReportAcknowledgementRequest,
    WeeklyReportCreateRequest,
    WeeklyReportResponse,
    WeekResponse,
)
from backend.app.modules.weekly_reports.service import (
    IdempotencyKeyReusedError,
    InvalidAcknowledgementTimeError,
    InvalidWeekStartError,
    InvalidWeekTimezoneError,
    ReportInputChangedError,
    WeeklyReportNotFoundError,
    WeeklyReportService,
    WeeklyReportUnavailableError,
    WeekNotClosedError,
    WeekOutcomeInconsistentError,
    WeekOutcomesIncompleteError,
    WeekProfileRequiredError,
)

weeks_router = APIRouter(prefix="/weeks", tags=["weekly-reports"])
router = APIRouter(prefix="/weekly-reports", tags=["weekly-reports"])


def _error(exc: Exception) -> AppError:
    if isinstance(exc, InvalidWeekStartError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="INVALID_WEEK_START",
            message="week_start는 사용자 시간대 기준 월요일이어야 합니다.",
        )
    if isinstance(exc, InvalidWeekTimezoneError):
        return AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="INVALID_WEEK_TIMEZONE",
            message="주간 경계에 사용할 시간대를 확인할 수 없습니다.",
        )
    if isinstance(exc, WeekProfileRequiredError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="PROFILE_REQUIRED",
            message="주간 정보를 만들기 전에 온보딩을 완료해야 합니다.",
        )
    if isinstance(exc, WeekNotClosedError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="WEEK_NOT_CLOSED",
            message="열린 주에는 최종 주간 리포트를 생성할 수 없습니다.",
        )
    if isinstance(exc, WeekOutcomesIncompleteError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="WEEK_OUTCOMES_INCOMPLETE",
            message="종료되지 않은 세션이나 미수행 이유가 없는 세션을 먼저 정리해야 합니다.",
        )
    if isinstance(exc, WeekOutcomeInconsistentError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="WEEK_OUTCOME_INCONSISTENT",
            message="계획 블록 체크와 저장된 세션 결과가 일치하지 않습니다.",
        )
    if isinstance(exc, ReportInputChangedError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="REPORT_INPUT_CHANGED",
            message="이미 생성된 주간 리포트의 입력 집계가 변경되었습니다.",
        )
    if isinstance(exc, WeeklyReportNotFoundError):
        return AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="WEEKLY_REPORT_NOT_FOUND",
            message="주간 리포트를 찾을 수 없습니다.",
        )
    if isinstance(exc, InvalidAcknowledgementTimeError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="INVALID_ACKNOWLEDGEMENT_TIME",
            message="리포트 생성 시각보다 이른 확인 시각은 사용할 수 없습니다.",
        )
    if isinstance(exc, IdempotencyKeyReusedError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="IDEMPOTENCY_KEY_REUSED",
            message="동일한 멱등성 키를 다른 요청에 사용할 수 없습니다.",
        )
    if isinstance(exc, IntegrityError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="WEEKLY_REPORT_CONFLICT",
            message="동시에 처리된 주간 리포트 요청과 충돌했습니다.",
        )
    if isinstance(exc, (WeeklyReportUnavailableError, SQLAlchemyError)):
        return AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="WEEKLY_REPORT_UNAVAILABLE",
            message="주간 리포트를 일시적으로 사용할 수 없습니다.",
        )
    return AppError(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="WEEKLY_REPORT_OPERATION_FAILED",
        message="주간 리포트 요청을 처리하지 못했습니다.",
    )


_ERRORS = (
    InvalidWeekStartError,
    InvalidWeekTimezoneError,
    WeekProfileRequiredError,
    WeekNotClosedError,
    WeekOutcomesIncompleteError,
    WeekOutcomeInconsistentError,
    ReportInputChangedError,
    WeeklyReportNotFoundError,
    InvalidAcknowledgementTimeError,
    IdempotencyKeyReusedError,
    WeeklyReportUnavailableError,
    IntegrityError,
    SQLAlchemyError,
)


@weeks_router.get("/{week_start}", response_model=WeekResponse)
def get_week(
    week_start: date,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WeeklyReportRepositoryPort, Depends(get_weekly_report_repository)],
) -> WeekResponse:
    try:
        return WeeklyReportService(repository).get_week(session, current_user.user_id, week_start)
    except _ERRORS as exc:
        raise _error(exc) from None


@weeks_router.post(
    "/{week_start}/report", response_model=WeeklyReportResponse, status_code=HTTPStatus.CREATED
)
def create_report(
    week_start: date,
    payload: WeeklyReportCreateRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WeeklyReportRepositoryPort, Depends(get_weekly_report_repository)],
    narration_agent: Annotated[
        WeeklyReportNarrationAgentPort, Depends(get_weekly_report_narration_agent)
    ],
) -> WeeklyReportResponse:
    try:
        return WeeklyReportService(repository, narration_agent=narration_agent).create_report(
            session, current_user.user_id, week_start, payload, idempotency_key
        )
    except _ERRORS as exc:
        raise _error(exc) from None


@router.get("/{report_id}", response_model=WeeklyReportResponse)
def get_report(
    report_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WeeklyReportRepositoryPort, Depends(get_weekly_report_repository)],
) -> WeeklyReportResponse:
    try:
        return WeeklyReportService(repository).get_report(session, current_user.user_id, report_id)
    except _ERRORS as exc:
        raise _error(exc) from None


@router.post("/{report_id}/acknowledgement", response_model=WeeklyReportResponse)
def acknowledge_report(
    report_id: UUID,
    payload: WeeklyReportAcknowledgementRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WeeklyReportRepositoryPort, Depends(get_weekly_report_repository)],
) -> WeeklyReportResponse:
    try:
        return WeeklyReportService(repository).acknowledge_report(
            session, current_user.user_id, report_id, payload, idempotency_key
        )
    except _ERRORS as exc:
        raise _error(exc) from None


__all__ = ["router", "weeks_router"]
