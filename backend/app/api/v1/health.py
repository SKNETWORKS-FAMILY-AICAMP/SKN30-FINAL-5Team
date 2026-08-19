from collections.abc import Callable
from http import HTTPStatus

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.app.core.errors import AppError, ErrorEnvelope

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status_code: str


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status_code="OK")


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorEnvelope}},
)
def ready(request: Request) -> HealthResponse:
    probe: Callable[[], None] = request.app.state.readiness_probe
    try:
        probe()
    except Exception:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="DATABASE_UNAVAILABLE",
            message="서비스 준비 상태를 확인할 수 없습니다.",
        ) from None
    return HealthResponse(status_code="READY")
