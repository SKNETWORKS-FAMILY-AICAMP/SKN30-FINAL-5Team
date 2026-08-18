from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_decision_repository,
    get_narration_provider,
)
from backend.app.core.errors import AppError
from backend.app.modules.decisions.ports import DecisionRepositoryPort, NarrationProviderPort
from backend.app.modules.decisions.schemas import DecisionCreateRequest, DecisionResponse
from backend.app.modules.decisions.service import (
    DecisionContextNotFoundError,
    DecisionFailedError,
    DecisionInputUnavailableError,
    DecisionNotFoundError,
    DecisionService,
    IdempotencyKeyReusedError,
    StaleDecisionContextError,
)
from backend.app.modules.identity.service import CurrentUser

router = APIRouter(prefix="/decisions", tags=["decisions"])


def _error(exc: Exception) -> AppError:
    if isinstance(exc, DecisionNotFoundError):
        return AppError(
            status_code=404, code="DECISION_NOT_FOUND", message="결정 기록을 찾을 수 없습니다."
        )
    if isinstance(exc, DecisionContextNotFoundError):
        return AppError(
            status_code=404,
            code="DAILY_CONTEXT_NOT_FOUND",
            message="요청한 일일 체크인 또는 활성 루틴을 찾을 수 없습니다.",
        )
    if isinstance(exc, StaleDecisionContextError):
        return AppError(
            status_code=409,
            code="STALE_CONTEXT",
            message="체크인 정보가 변경되었습니다. 최신 버전으로 다시 요청해 주세요.",
        )
    if isinstance(exc, IdempotencyKeyReusedError):
        return AppError(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="같은 멱등성 키를 다른 요청에 사용할 수 없습니다.",
        )
    if isinstance(exc, DecisionInputUnavailableError):
        return AppError(
            status_code=422,
            code="NEEDS_INPUT",
            message="안전한 결정을 위해 추가 입력이 필요합니다.",
        )
    if isinstance(exc, DecisionFailedError):
        return AppError(
            status_code=503,
            code="DECISION_FAILED",
            message="안전한 운동 계획을 생성하지 못했습니다.",
        )
    if isinstance(exc, IntegrityError):
        return AppError(
            status_code=409,
            code="DECISION_CONFLICT",
            message="동시에 처리된 결정 요청과 충돌했습니다.",
        )
    return AppError(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="결정 저장소를 일시적으로 사용할 수 없습니다.",
    )


@router.post("", response_model=DecisionResponse, status_code=201)
def create_decision(
    payload: DecisionCreateRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[DecisionRepositoryPort, Depends(get_decision_repository)],
    narration_provider: Annotated[NarrationProviderPort, Depends(get_narration_provider)],
) -> DecisionResponse:
    # The route never calls a provider itself; narration stays inside the service.
    try:
        return DecisionService(repository, narration_provider=narration_provider).create(
            session, current_user.user_id, payload, idempotency_key
        )
    except (
        DecisionContextNotFoundError,
        StaleDecisionContextError,
        DecisionInputUnavailableError,
        DecisionFailedError,
        IdempotencyKeyReusedError,
        IntegrityError,
        SQLAlchemyError,
    ) as exc:
        raise _error(exc) from None


@router.get("/{decision_id}", response_model=DecisionResponse)
def get_decision(
    decision_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[DecisionRepositoryPort, Depends(get_decision_repository)],
) -> DecisionResponse:
    try:
        return DecisionService(repository).get(session, current_user.user_id, decision_id)
    except (DecisionNotFoundError, SQLAlchemyError) as exc:
        raise _error(exc) from None


__all__ = ["router"]
