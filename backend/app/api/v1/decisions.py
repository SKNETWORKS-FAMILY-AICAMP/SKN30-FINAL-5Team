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
    get_decision_creation_service,
    get_decision_repository,
    get_plan_revision_repository,
    get_v3_regeneration_service,
)
from backend.app.core.errors import AppError
from backend.app.domain.agents.v3_orchestration import RegenerationDifferenceCode
from backend.app.modules.decisions.execution_profile import (
    DecisionCreationServicePort,
    V3CompositionUnavailableError,
)
from backend.app.modules.decisions.plan_revision import (
    PlanRevisionError,
    PlanRevisionFailureCode,
)
from backend.app.modules.decisions.plan_revision_service import (
    PlanNotFoundError,
    PlanRevisionIdempotencyKeyReusedError,
    PlanRevisionService,
    PlanRevisionStaleError,
)
from backend.app.modules.decisions.ports import DecisionRepositoryPort, PlanRevisionRepositoryPort
from backend.app.modules.decisions.schemas import (
    DecisionCreateRequest,
    DecisionRegenerationRequest,
    DecisionResponse,
    PlanItemOrderRequest,
    PlanItemSetRepetitionRequest,
    PlanRevisionResponse,
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
    V3RegenerationFailureCode.V3_COMPOSITION_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
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
    V3RegenerationFailureCode.V3_COMPOSITION_UNAVAILABLE: ("V3 실행 구성이 준비되지 않았습니다."),
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


@router.post("", response_model=DecisionResponse, status_code=201)
async def create_decision(
    payload: DecisionCreateRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[DecisionCreationServicePort, Depends(get_decision_creation_service)],
) -> DecisionResponse:
    # Profile selection, business rules, provider calls and transactions all
    # stay behind the application-service boundary.
    try:
        return await service.create(session, current_user.user_id, payload, idempotency_key)
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
    except V3CompositionUnavailableError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="V3_COMPOSITION_UNAVAILABLE",
            message="V3 실행 구성이 준비되지 않았습니다.",
        ) from None


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


_PLAN_REVISION_STATUS = {
    PlanRevisionFailureCode.PLAN_ITEM_NOT_FOUND: HTTPStatus.NOT_FOUND,
    PlanRevisionFailureCode.PLAN_NOT_EDITABLE: HTTPStatus.CONFLICT,
    PlanRevisionFailureCode.COMPLETED_ITEM_NOT_REORDERABLE: HTTPStatus.CONFLICT,
    PlanRevisionFailureCode.REPETITIONS_NOT_APPLICABLE: HTTPStatus.UNPROCESSABLE_ENTITY,
    PlanRevisionFailureCode.REPETITIONS_REQUIRED: HTTPStatus.UNPROCESSABLE_ENTITY,
    PlanRevisionFailureCode.TIMING_BASIS_UNAVAILABLE: HTTPStatus.UNPROCESSABLE_ENTITY,
    PlanRevisionFailureCode.ORDER_ITEMS_MISMATCH: HTTPStatus.UNPROCESSABLE_ENTITY,
    PlanRevisionFailureCode.ORDER_CROSSES_PHASE: HTTPStatus.UNPROCESSABLE_ENTITY,
}

_PLAN_REVISION_MESSAGES = {
    PlanRevisionFailureCode.PLAN_ITEM_NOT_FOUND: "계획에 없는 운동입니다.",
    PlanRevisionFailureCode.PLAN_NOT_EDITABLE: "종료된 운동의 계획은 수정할 수 없습니다.",
    PlanRevisionFailureCode.COMPLETED_ITEM_NOT_REORDERABLE: (
        "이미 완료한 운동은 순서나 내용을 바꿀 수 없습니다."
    ),
    PlanRevisionFailureCode.REPETITIONS_NOT_APPLICABLE: (
        "시간으로 수행하는 운동에는 반복 횟수를 지정할 수 없습니다."
    ),
    PlanRevisionFailureCode.REPETITIONS_REQUIRED: "반복 횟수를 함께 보내주세요.",
    PlanRevisionFailureCode.TIMING_BASIS_UNAVAILABLE: (
        "승인된 운동 시간 기준이 없어 계획을 다시 계산할 수 없습니다."
    ),
    PlanRevisionFailureCode.ORDER_ITEMS_MISMATCH: (
        "순서를 바꿀 수 있는 운동 전체를 한 번에 보내주세요."
    ),
    PlanRevisionFailureCode.ORDER_CROSSES_PHASE: (
        "준비·본운동·마무리 구간을 넘어서는 이동은 할 수 없습니다."
    ),
}


def _plan_revision_error(exc: Exception) -> AppError:
    if isinstance(exc, PlanNotFoundError):
        return AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="PLAN_NOT_FOUND",
            message="오늘 수정할 수 있는 운동 계획이 없습니다.",
        )
    if isinstance(exc, PlanRevisionStaleError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="PLAN_REVISION_STALE",
            message="운동 계획이 변경되었습니다. 최신 계획으로 다시 시도해주세요.",
        )
    if isinstance(exc, PlanRevisionIdempotencyKeyReusedError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="IDEMPOTENCY_KEY_REUSED",
            message="같은 멱등성 키를 다른 요청에 사용할 수 없습니다.",
        )
    if isinstance(exc, PlanRevisionError):
        return AppError(
            status_code=_PLAN_REVISION_STATUS[exc.code],
            code=exc.code.value,
            message=_PLAN_REVISION_MESSAGES[exc.code],
        )
    if isinstance(exc, IntegrityError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="PLAN_REVISION_STALE",
            message="운동 계획이 변경되었습니다. 최신 계획으로 다시 시도해주세요.",
        )
    return AppError(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="결정 저장소를 일시적으로 사용할 수 없습니다.",
    )


@router.patch(
    "/{decision_id}/plan-items/{plan_item_id}",
    response_model=PlanRevisionResponse,
)
def edit_plan_item_sets_and_repetitions(
    decision_id: UUID,
    plan_item_id: UUID,
    payload: PlanItemSetRepetitionRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[PlanRevisionRepositoryPort, Depends(get_plan_revision_repository)],
) -> PlanRevisionResponse:
    """Replace one item's set and repetition counts and return the updated plan.

    This does not spend the day's re-recommendation budget: the user is rewriting their
    own plan, not asking for a different one.
    """

    try:
        return PlanRevisionService(repository).edit_sets_and_repetitions(
            session, current_user.user_id, decision_id, plan_item_id, payload, idempotency_key
        )
    except (
        PlanNotFoundError,
        PlanRevisionStaleError,
        PlanRevisionIdempotencyKeyReusedError,
        PlanRevisionError,
        IntegrityError,
        SQLAlchemyError,
    ) as exc:
        raise _plan_revision_error(exc) from None


@router.put(
    "/{decision_id}/plan-item-order",
    response_model=PlanRevisionResponse,
)
def edit_plan_item_order(
    decision_id: UUID,
    payload: PlanItemOrderRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[PlanRevisionRepositoryPort, Depends(get_plan_revision_repository)],
) -> PlanRevisionResponse:
    """Reorder the plan inside its phases and return it renumbered from 1."""

    try:
        return PlanRevisionService(repository).edit_order(
            session, current_user.user_id, decision_id, payload, idempotency_key
        )
    except (
        PlanNotFoundError,
        PlanRevisionStaleError,
        PlanRevisionIdempotencyKeyReusedError,
        PlanRevisionError,
        IntegrityError,
        SQLAlchemyError,
    ) as exc:
        raise _plan_revision_error(exc) from None


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
