from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_db_session, get_reward_repository
from backend.app.core.errors import AppError
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.rewards.ports import RewardRepositoryPort
from backend.app.modules.rewards.schemas import (
    BananaSpendRequest,
    BananaSpendResponse,
    BananaWalletResponse,
    DailyRewardClaimResponse,
)
from backend.app.modules.rewards.service import (
    InsufficientBananaBalanceError,
    InvalidBananaSpendError,
    RewardProfileNotFoundError,
    RewardService,
)

router = APIRouter(prefix="/rewards", tags=["rewards"])


def _error(exc: Exception) -> AppError:
    if isinstance(exc, RewardProfileNotFoundError):
        return AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code="PROFILE_NOT_FOUND",
            message="프로필을 먼저 완료해 주세요.",
        )
    if isinstance(exc, InsufficientBananaBalanceError):
        return AppError(
            status_code=HTTPStatus.CONFLICT,
            code="INSUFFICIENT_BANANA_BALANCE",
            message="바나나가 부족합니다.",
        )
    if isinstance(exc, InvalidBananaSpendError):
        return AppError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="INVALID_BANANA_SPEND",
            message="바나나 사용 요청이 올바르지 않습니다.",
        )
    if isinstance(exc, SQLAlchemyError):
        return AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="DATABASE_UNAVAILABLE",
            message="바나나 정보를 일시적으로 사용할 수 없습니다.",
        )
    return AppError(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="REWARD_OPERATION_FAILED",
        message="바나나 요청을 처리하지 못했습니다.",
    )


@router.get("", response_model=BananaWalletResponse)
def get_rewards(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[RewardRepositoryPort, Depends(get_reward_repository)],
) -> BananaWalletResponse:
    try:
        return RewardService(repository).get_wallet(session, current_user.user_id)
    except (RewardProfileNotFoundError, SQLAlchemyError) as exc:
        raise _error(exc) from None


@router.post("/daily-reward/claim", response_model=DailyRewardClaimResponse)
def claim_daily_reward(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[RewardRepositoryPort, Depends(get_reward_repository)],
) -> DailyRewardClaimResponse:
    try:
        return RewardService(repository).claim_daily_reward(session, current_user.user_id)
    except (RewardProfileNotFoundError, SQLAlchemyError) as exc:
        raise _error(exc) from None


@router.post("/spend", response_model=BananaSpendResponse)
def spend_bananas(
    payload: BananaSpendRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[RewardRepositoryPort, Depends(get_reward_repository)],
) -> BananaSpendResponse:
    try:
        return RewardService(repository).spend(
            session, current_user.user_id, payload, idempotency_key
        )
    except (
        RewardProfileNotFoundError,
        InsufficientBananaBalanceError,
        InvalidBananaSpendError,
        SQLAlchemyError,
    ) as exc:
        raise _error(exc) from None


__all__ = ["router"]
