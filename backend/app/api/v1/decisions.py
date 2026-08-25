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
    get_decision_repository,
    get_narration_provider,
    get_v3_regeneration_service,
)
from backend.app.core.errors import AppError
from backend.app.domain.agents.v3_orchestration import RegenerationDifferenceCode
from backend.app.modules.decisions.ports import DecisionRepositoryPort, NarrationProviderPort
from backend.app.modules.decisions.schemas import (
    DecisionCreateRequest,
    DecisionRegenerationRequest,
    DecisionResponse,
)
from backend.app.modules.decisions.service import (
    DecisionContextNotFoundError,
    DecisionFailedError,
    DecisionInputUnavailableError,
    DecisionNotFoundError,
    DecisionService,
    IdempotencyKeyReusedError,
    StaleDecisionContextError,
)
from backend.app.modules.decisions.v3_regeneration import (
    V3RegenerationCommand,
    V3RegenerationError,
    V3RegenerationFailureCode,
    V3RegenerationServicePort,
)
from backend.app.modules.identity.service import CurrentUser

router = APIRouter(prefix="/decisions", tags=["decisions"])

_REGENERATION_ERROR_STATUS = {
    V3RegenerationFailureCode.DECISION_NOT_FOUND: HTTPStatus.NOT_FOUND,
    V3RegenerationFailureCode.IDEMPOTENCY_KEY_REUSED: HTTPStatus.CONFLICT,
    V3RegenerationFailureCode.STALE_REGENERATION: HTTPStatus.CONFLICT,
    V3RegenerationFailureCode.REGENERATION_CONTEXT_STALE: HTTPStatus.CONFLICT,
    V3RegenerationFailureCode.REGENERATION_LIMIT_REACHED: HTTPStatus.CONFLICT,
    V3RegenerationFailureCode.REGENERATION_NOT_ALLOWED: HTTPStatus.CONFLICT,
    V3RegenerationFailureCode.NO_ALTERNATIVE_AVAILABLE: HTTPStatus.UNPROCESSABLE_ENTITY,
    V3RegenerationFailureCode.DECISION_FAILED: HTTPStatus.SERVICE_UNAVAILABLE,
    V3RegenerationFailureCode.V3_ENGINE_DISABLED: HTTPStatus.SERVICE_UNAVAILABLE,
}

_REGENERATION_ERROR_MESSAGES = {
    V3RegenerationFailureCode.DECISION_NOT_FOUND: "결정 기록을 찾을 수 없습니다.",
    V3RegenerationFailureCode.IDEMPOTENCY_KEY_REUSED: (
        "같은 멱등성 키를 다른 요청에 사용할 수 없습니다."
    ),
    V3RegenerationFailureCode.STALE_REGENERATION: (
        "운동 계획이 변경되었습니다. 최신 계획으로 다시 요청해 주세요."
    ),
    V3RegenerationFailureCode.REGENERATION_CONTEXT_STALE: (
        "재생성 기준 정보가 만료되었거나 변경되었습니다."
    ),
    V3RegenerationFailureCode.REGENERATION_LIMIT_REACHED: "재생성 가능 횟수를 초과했습니다.",
    V3RegenerationFailureCode.REGENERATION_NOT_ALLOWED: "이 결정은 재생성할 수 없습니다.",
    V3RegenerationFailureCode.NO_ALTERNATIVE_AVAILABLE: (
        "안전 조건과 운동 목표를 유지하는 다른 루틴을 만들 수 없습니다."
    ),
    V3RegenerationFailureCode.DECISION_FAILED: "안전한 운동 계획을 생성하지 못했습니다.",
    V3RegenerationFailureCode.V3_ENGINE_DISABLED: "루틴 재생성 기능을 사용할 수 없습니다.",
}

_DIFFERENCE_CODE_TO_API = {
    RegenerationDifferenceCode.CORE_EXERCISE_CHANGED: "CORE_EXERCISE_CHANGED",
    RegenerationDifferenceCode.SET_REPETITION_STRUCTURE_CHANGED: "SET_REP_STRUCTURE_CHANGED",
    RegenerationDifferenceCode.EXERCISE_SEQUENCE_CHANGED: "EXERCISE_ORDER_CHANGED",
    RegenerationDifferenceCode.ROUTINE_COMPOSITION_CHANGED: "ROUTINE_STRUCTURE_CHANGED",
}


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


def _regeneration_error(exc: V3RegenerationError) -> AppError:
    return AppError(
        status_code=_REGENERATION_ERROR_STATUS[exc.code],
        code=exc.code.value,
        message=_REGENERATION_ERROR_MESSAGES[exc.code],
    )


@router.post(
    "", response_model=DecisionResponse, response_model_exclude_unset=True, status_code=201
)
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


@router.get("", response_model=DecisionResponse, response_model_exclude_unset=True)
def get_decision_for_date(
    local_date: Annotated[date, Query()],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[DecisionRepositoryPort, Depends(get_decision_repository)],
) -> DecisionResponse:
    """Return the day's stored decision so a restarted client can resume it."""

    try:
        return DecisionService(repository).get_for_date(session, current_user.user_id, local_date)
    except (DecisionNotFoundError, SQLAlchemyError) as exc:
        raise _error(exc) from None


@router.post(
    "/{decision_id}/regenerations",
    response_model=DecisionResponse,
    response_model_exclude_unset=True,
    status_code=201,
)
async def regenerate_decision(
    decision_id: UUID,
    payload: DecisionRegenerationRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[DecisionRepositoryPort, Depends(get_decision_repository)],
    service: Annotated[V3RegenerationServicePort, Depends(get_v3_regeneration_service)],
) -> DecisionResponse:
    command = V3RegenerationCommand(
        user_id=current_user.user_id,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        expected_plan_id=payload.expected_plan_id,
        expected_regeneration_sequence=payload.expected_regeneration_sequence,
    )
    try:
        result = await service.regenerate(command)
    except V3RegenerationError as exc:
        raise _regeneration_error(exc) from None

    try:
        stored = DecisionService(repository).get(session, current_user.user_id, result.decision_id)
    except DecisionNotFoundError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code=V3RegenerationFailureCode.DECISION_FAILED.value,
            message=_REGENERATION_ERROR_MESSAGES[V3RegenerationFailureCode.DECISION_FAILED],
        ) from None
    except SQLAlchemyError as exc:
        raise _error(exc) from None

    return stored.model_copy(
        update={
            "generation_mode_code": result.generation_mode_code,
            "decision_engine_code": result.decision_engine_code.value,
            "root_decision_id": result.root_decision_id,
            "parent_decision_id": result.parent_decision_id,
            "regeneration_sequence": result.regeneration_sequence,
            "meaningful_difference_codes": [
                _DIFFERENCE_CODE_TO_API[code] for code in result.meaningful_difference_codes
            ],
        }
    )


@router.get("/{decision_id}", response_model=DecisionResponse, response_model_exclude_unset=True)
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
