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
    get_routine_repository,
    get_weekly_plan_repository,
    get_weekly_report_repository,
)
from backend.app.core.errors import AppError
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.routines.ports import RoutineRepositoryPort
from backend.app.modules.weekly_plans.ports import WeeklyPlanRepositoryPort
from backend.app.modules.weekly_plans.schemas import (
    InitialWeeklyPlanRequest,
    WeeklyPlanRevisionRequest,
    WeeklyPlanRevisionResponse,
)
from backend.app.modules.weekly_plans.service import (
    AiRevisionLimitReachedError,
    IdempotencyKeyReusedError,
    InitialPlanAlreadyExistsError,
    InitialPlanRequiredError,
    PlanRevisionRejectedError,
    PreviousWeeklyReportRequiredError,
    StalePlanRevisionError,
    TargetWeekClosedError,
    WeeklyPlanContextUnavailableError,
    WeeklyPlanRoutineNotFoundError,
    WeeklyPlanService,
)
from backend.app.modules.weekly_reports.ports import WeeklyReportRepositoryPort
from backend.app.modules.weekly_reports.service import (
    InvalidWeekStartError,
    InvalidWeekTimezoneError,
    WeeklyReportService,
    WeekProfileRequiredError,
)

router = APIRouter(prefix="/weeks", tags=["weekly-plans"])


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
            message="주간 계획을 만들기 전에 온보딩을 완료해야 합니다.",
        )
    if isinstance(exc, TargetWeekClosedError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="TARGET_WEEK_CLOSED",
            message="이미 닫힌 주의 계획은 생성하거나 수정할 수 없습니다.",
        )
    if isinstance(exc, PreviousWeeklyReportRequiredError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="PREVIOUS_WEEKLY_REPORT_REQUIRED",
            message="다음 주 계획을 만들기 전에 닫힌 직전 주 리포트를 생성해야 합니다.",
        )
    if isinstance(exc, InitialPlanAlreadyExistsError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="INITIAL_PLAN_ALREADY_EXISTS",
            message="대상 주의 초기 계획이 이미 존재합니다.",
        )
    if isinstance(exc, InitialPlanRequiredError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="INITIAL_PLAN_REQUIRED",
            message="계획을 수정하기 전에 초기 계획을 생성해야 합니다.",
        )
    if isinstance(exc, StalePlanRevisionError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="STALE_PLAN_REVISION",
            message="계획 revision이 변경되었습니다. 최신 순서로 다시 시도해주세요.",
        )
    if isinstance(exc, AiRevisionLimitReachedError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="AI_REVISION_LIMIT_REACHED",
            message="AI 계획 수정은 최대 2회까지 가능합니다.",
        )
    if isinstance(exc, WeeklyPlanRoutineNotFoundError):
        return AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="WEEKLY_PLAN_ROUTINE_NOT_FOUND",
            message="사용할 수 있는 사용자 루틴 버전을 찾을 수 없습니다.",
        )
    if isinstance(exc, PlanRevisionRejectedError):
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="PLAN_REVISION_REJECTED",
            message="요청한 계획 수정이 시간·장소·장비 또는 안전 제약을 충족하지 않습니다.",
            details=[{"reason_code": code} for code in exc.reason_codes],
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
            code="WEEKLY_PLAN_CONFLICT",
            message="동시에 처리된 주간 계획 요청과 충돌했습니다.",
        )
    if isinstance(exc, (WeeklyPlanContextUnavailableError, SQLAlchemyError)):
        return AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="WEEKLY_PLAN_UNAVAILABLE",
            message="주간 계획을 일시적으로 사용할 수 없습니다.",
        )
    return AppError(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="WEEKLY_PLAN_OPERATION_FAILED",
        message="주간 계획 요청을 처리하지 못했습니다.",
    )


_ERRORS = (
    InvalidWeekStartError,
    InvalidWeekTimezoneError,
    WeekProfileRequiredError,
    TargetWeekClosedError,
    PreviousWeeklyReportRequiredError,
    InitialPlanAlreadyExistsError,
    InitialPlanRequiredError,
    StalePlanRevisionError,
    AiRevisionLimitReachedError,
    WeeklyPlanRoutineNotFoundError,
    PlanRevisionRejectedError,
    IdempotencyKeyReusedError,
    WeeklyPlanContextUnavailableError,
    IntegrityError,
    SQLAlchemyError,
)


def _service(
    repository: WeeklyPlanRepositoryPort,
    routine_repository: RoutineRepositoryPort,
    weekly_report_repository: WeeklyReportRepositoryPort,
) -> WeeklyPlanService:
    return WeeklyPlanService(
        repository,
        routine_repository,
        WeeklyReportService(weekly_report_repository),
    )


@router.post(
    "/{week_start}/plan",
    response_model=WeeklyPlanRevisionResponse,
    status_code=HTTPStatus.CREATED,
)
def create_initial_plan(
    week_start: date,
    payload: InitialWeeklyPlanRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WeeklyPlanRepositoryPort, Depends(get_weekly_plan_repository)],
    routine_repository: Annotated[RoutineRepositoryPort, Depends(get_routine_repository)],
    weekly_report_repository: Annotated[
        WeeklyReportRepositoryPort, Depends(get_weekly_report_repository)
    ],
) -> WeeklyPlanRevisionResponse:
    try:
        return _service(repository, routine_repository, weekly_report_repository).create_initial(
            session, current_user.user_id, week_start, payload, idempotency_key
        )
    except _ERRORS as exc:
        raise _error(exc) from None


@router.post(
    "/{week_start}/plan-revisions",
    response_model=WeeklyPlanRevisionResponse,
    status_code=HTTPStatus.CREATED,
)
def create_plan_revision(
    week_start: date,
    payload: WeeklyPlanRevisionRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WeeklyPlanRepositoryPort, Depends(get_weekly_plan_repository)],
    routine_repository: Annotated[RoutineRepositoryPort, Depends(get_routine_repository)],
    weekly_report_repository: Annotated[
        WeeklyReportRepositoryPort, Depends(get_weekly_report_repository)
    ],
) -> WeeklyPlanRevisionResponse:
    try:
        return _service(repository, routine_repository, weekly_report_repository).create_revision(
            session, current_user.user_id, week_start, payload, idempotency_key
        )
    except _ERRORS as exc:
        raise _error(exc) from None


__all__ = ["router"]
