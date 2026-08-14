import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("backend.error")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unavailable"))


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    body = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or [],
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(),
        headers={"X-Request-ID": request_id},
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    if any(error["loc"][-1:] == ("date_of_birth",) for error in exc.errors()):
        return _error_response(
            request,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="INVALID_DATE_OF_BIRTH",
            message="생년월일이 올바르지 않습니다.",
        )
    if any(
        error["loc"][-1:] == ("discomforts",)
        and "body_area_code must not be duplicated" in error["msg"]
        for error in exc.errors()
    ):
        return _error_response(
            request,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="DUPLICATE_BODY_AREA",
            message="불편 부위는 중복해서 선택할 수 없습니다.",
        )
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return _error_response(
        request,
        status_code=HTTPStatus.BAD_REQUEST,
        code="INVALID_REQUEST",
        message="요청 값이 올바르지 않습니다.",
        details=details,
    )


async def http_error_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if exc.status_code == HTTPStatus.NOT_FOUND:
        code = "RESOURCE_NOT_FOUND"
        message = "요청한 리소스를 찾을 수 없습니다."
    else:
        code = "HTTP_ERROR"
        message = "요청을 처리할 수 없습니다."
    return _error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_request_error",
        extra={
            "event_code": "UNHANDLED_REQUEST_ERROR",
            "request_id": _request_id(request),
            "path": request.url.path,
            "exception_type": type(exc).__name__,
        },
    )
    return _error_response(
        request,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        message="요청을 처리하지 못했습니다.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
