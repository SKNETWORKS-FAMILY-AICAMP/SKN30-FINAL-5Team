from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_db_session, get_workout_repository
from backend.app.core.errors import AppError
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.workouts.ports import WorkoutRepositoryPort
from backend.app.modules.workouts.schemas import (
    DecisionSelectionRequest,
    DecisionSelectionResponse,
    WorkoutAdditionalActivityRequest,
    WorkoutAdditionalActivityResponse,
    WorkoutFeedbackRequest,
    WorkoutFeedbackResponse,
    WorkoutSafetyEventRequest,
    WorkoutSafetyEventResponse,
    WorkoutSessionFinishRequest,
    WorkoutSessionFinishResponse,
    WorkoutSessionItemUpdateRequest,
    WorkoutSessionItemUpdateResponse,
    WorkoutSessionNotCompletedRequest,
    WorkoutSessionNotCompletedResponse,
    WorkoutSessionStartRequest,
    WorkoutSessionStartResponse,
    WorkoutTimerEventRequest,
    WorkoutTimerEventResponse,
)
from backend.app.modules.workouts.service import (
    DecisionAlreadySelectedError,
    FeedbackAlreadyExistsError,
    IdempotencyKeyReusedError,
    InvalidSafetyEventInputError,
    InvalidSessionStateError,
    NotCompletedReasonRequiredServiceError,
    OptionNotSelectableError,
    SessionEndedError,
    WorkoutResourceNotFoundError,
    WorkoutService,
)

selection_router = APIRouter(prefix="/decisions", tags=["decisions"])
router = APIRouter(prefix="/workout-sessions", tags=["workout-sessions"])


def _error(exc: Exception) -> AppError:
    if isinstance(exc, WorkoutResourceNotFoundError):
        return AppError(
            status_code=404,
            code="WORKOUT_RESOURCE_NOT_FOUND",
            message="요청한 선택 옵션, 운동 세션 또는 운동 블록을 찾을 수 없습니다.",
        )
    if isinstance(exc, OptionNotSelectableError):
        return AppError(
            status_code=409,
            code="OPTION_NOT_SELECTABLE",
            message="이 옵션은 선택할 수 없습니다.",
        )
    if isinstance(exc, DecisionAlreadySelectedError):
        return AppError(
            status_code=409,
            code="DECISION_ALREADY_SELECTED",
            message="이미 선택이 완료된 결정입니다.",
        )
    if isinstance(exc, SessionEndedError):
        return AppError(
            status_code=409,
            code="SESSION_ENDED",
            message="종료된 운동 세션은 수정할 수 없습니다.",
        )
    if isinstance(exc, InvalidSessionStateError):
        return AppError(
            status_code=409,
            code="INVALID_STATE_TRANSITION",
            message="현재 운동 세션 상태에서는 요청한 작업을 수행할 수 없습니다.",
        )
    if isinstance(exc, IdempotencyKeyReusedError):
        return AppError(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="같은 멱등성 키를 다른 요청에 사용할 수 없습니다.",
        )
    if isinstance(exc, NotCompletedReasonRequiredServiceError):
        return AppError(
            status_code=409,
            code="NOT_COMPLETED_REASON_REQUIRED",
            message="완료한 운동 블록이 없으면 미수행 사유와 함께 종료해야 합니다.",
        )
    if isinstance(exc, InvalidSafetyEventInputError):
        return AppError(
            status_code=422,
            code="INVALID_SAFETY_EVENT",
            message="불편 부위 또는 이상 반응을 한 가지 이상 입력해야 합니다.",
        )
    if isinstance(exc, FeedbackAlreadyExistsError):
        return AppError(
            status_code=409,
            code="FEEDBACK_ALREADY_EXISTS",
            message="이 운동 세션의 피드백이 이미 저장되었습니다.",
        )
    if isinstance(exc, IntegrityError):
        return AppError(
            status_code=409,
            code="WORKOUT_CONFLICT",
            message="동시에 처리된 운동 세션 요청과 충돌했습니다.",
        )
    return AppError(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="운동 세션 저장소를 일시적으로 사용할 수 없습니다.",
    )


_WORKOUT_ERRORS = (
    WorkoutResourceNotFoundError,
    OptionNotSelectableError,
    DecisionAlreadySelectedError,
    SessionEndedError,
    InvalidSessionStateError,
    IdempotencyKeyReusedError,
    NotCompletedReasonRequiredServiceError,
    InvalidSafetyEventInputError,
    FeedbackAlreadyExistsError,
    IntegrityError,
    SQLAlchemyError,
)


@selection_router.post(
    "/{decision_id}/selection", response_model=DecisionSelectionResponse, status_code=201
)
def select_decision(
    decision_id: UUID,
    payload: DecisionSelectionRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> DecisionSelectionResponse:
    try:
        return WorkoutService(repository).select_decision(
            session, current_user.user_id, decision_id, payload, idempotency_key
        )
    except _WORKOUT_ERRORS as exc:
        raise _error(exc) from None


@router.patch("/{session_id}/start", response_model=WorkoutSessionStartResponse)
def start_session(
    session_id: UUID,
    payload: WorkoutSessionStartRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> WorkoutSessionStartResponse:
    try:
        return WorkoutService(repository).start_session(
            session, current_user.user_id, session_id, payload, idempotency_key
        )
    except _WORKOUT_ERRORS as exc:
        raise _error(exc) from None


@router.patch("/{session_id}/items/{plan_item_id}", response_model=WorkoutSessionItemUpdateResponse)
def update_session_item(
    session_id: UUID,
    plan_item_id: UUID,
    payload: WorkoutSessionItemUpdateRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> WorkoutSessionItemUpdateResponse:
    try:
        return WorkoutService(repository).update_item(
            session,
            current_user.user_id,
            session_id,
            plan_item_id,
            payload,
            idempotency_key,
        )
    except _WORKOUT_ERRORS as exc:
        raise _error(exc) from None


@router.post(
    "/{session_id}/timer-events", response_model=WorkoutTimerEventResponse, status_code=201
)
def record_timer_event(
    session_id: UUID,
    payload: WorkoutTimerEventRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> WorkoutTimerEventResponse:
    try:
        return WorkoutService(repository).record_timer_event(
            session, current_user.user_id, session_id, payload, idempotency_key
        )
    except _WORKOUT_ERRORS as exc:
        raise _error(exc) from None


@router.post(
    "/{session_id}/additional-activities",
    response_model=WorkoutAdditionalActivityResponse,
    status_code=201,
)
def record_additional_activity(
    session_id: UUID,
    payload: WorkoutAdditionalActivityRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> WorkoutAdditionalActivityResponse:
    try:
        return WorkoutService(repository).record_additional_activity(
            session, current_user.user_id, session_id, payload, idempotency_key
        )
    except _WORKOUT_ERRORS as exc:
        raise _error(exc) from None


@router.post(
    "/{session_id}/safety-events", response_model=WorkoutSafetyEventResponse, status_code=201
)
def record_safety_event(
    session_id: UUID,
    payload: WorkoutSafetyEventRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> WorkoutSafetyEventResponse:
    try:
        return WorkoutService(repository).record_safety_event(
            session, current_user.user_id, session_id, payload, idempotency_key
        )
    except _WORKOUT_ERRORS as exc:
        raise _error(exc) from None


@router.patch("/{session_id}/finish", response_model=WorkoutSessionFinishResponse)
def finish_session(
    session_id: UUID,
    payload: WorkoutSessionFinishRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> WorkoutSessionFinishResponse:
    try:
        return WorkoutService(repository).finish_session(
            session, current_user.user_id, session_id, payload, idempotency_key
        )
    except _WORKOUT_ERRORS as exc:
        raise _error(exc) from None


@router.patch("/{session_id}/not-completed", response_model=WorkoutSessionNotCompletedResponse)
def mark_not_completed(
    session_id: UUID,
    payload: WorkoutSessionNotCompletedRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> WorkoutSessionNotCompletedResponse:
    try:
        return WorkoutService(repository).mark_not_completed(
            session, current_user.user_id, session_id, payload, idempotency_key
        )
    except _WORKOUT_ERRORS as exc:
        raise _error(exc) from None


@router.post("/{session_id}/feedback", response_model=WorkoutFeedbackResponse, status_code=201)
def record_feedback(
    session_id: UUID,
    payload: WorkoutFeedbackRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[WorkoutRepositoryPort, Depends(get_workout_repository)],
) -> WorkoutFeedbackResponse:
    try:
        return WorkoutService(repository).record_feedback(
            session, current_user.user_id, session_id, payload, idempotency_key
        )
    except _WORKOUT_ERRORS as exc:
        raise _error(exc) from None


__all__ = ["router", "selection_router"]
