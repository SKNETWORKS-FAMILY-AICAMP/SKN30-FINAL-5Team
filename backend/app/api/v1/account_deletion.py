from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_account_deletion_repository,
    get_db_session,
    get_deletion_lifecycle_user,
)
from backend.app.core.errors import AppError
from backend.app.modules.account_deletion.ports import AccountDeletionRepositoryPort
from backend.app.modules.account_deletion.schemas import AccountDeletionResponse
from backend.app.modules.account_deletion.service import (
    AccountDeletionService,
    AccountDeletionUnavailableError,
    IdempotencyKeyReusedError,
)
from backend.app.modules.identity.service import CurrentUser

router = APIRouter(prefix="/me", tags=["account-deletion"])


@router.delete(
    "",
    response_model=AccountDeletionResponse,
    status_code=HTTPStatus.ACCEPTED,
)
def request_account_deletion(
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    current_user: Annotated[CurrentUser, Depends(get_deletion_lifecycle_user)],
    session: Annotated[Session, Depends(get_db_session)],
    repository: Annotated[
        AccountDeletionRepositoryPort,
        Depends(get_account_deletion_repository),
    ],
) -> AccountDeletionResponse:
    try:
        return AccountDeletionService(repository).request_deletion(
            session,
            current_user.user_id,
            idempotency_key,
        )
    except IdempotencyKeyReusedError:
        raise AppError(
            status_code=HTTPStatus.CONFLICT,
            code="IDEMPOTENCY_KEY_REUSED",
            message="동일한 멱등성 키를 다른 요청에 사용할 수 없습니다.",
        ) from None
    except AccountDeletionUnavailableError:
        raise AppError(
            status_code=HTTPStatus.FORBIDDEN,
            code="ACCOUNT_DISABLED",
            message="현재 이 계정으로 접근할 수 없습니다.",
        ) from None
    except (IntegrityError, SQLAlchemyError):
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="DATABASE_UNAVAILABLE",
            message="계정 삭제 요청을 일시적으로 처리할 수 없습니다.",
        ) from None


__all__ = ["router"]
