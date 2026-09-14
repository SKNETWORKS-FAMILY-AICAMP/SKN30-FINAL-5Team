import logging
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from backend.app.core.errors import unhandled_error_handler

logger = logging.getLogger("backend.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        started_at = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "event_code": "REQUEST_COMPLETED",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        return response


class ErrorEnvelopeMiddleware(BaseHTTPMiddleware):
    """Answer an unhandled exception from below the CORS layer.

    Starlette always installs `ServerErrorMiddleware` as the outermost layer, so
    the 500 it builds from the ``Exception`` handler never travels back through
    `CORSMiddleware` and reaches a browser with no `Access-Control-Allow-Origin`
    header. The browser then discards a correctly formed error envelope and the
    client sees a transport failure, so a server error is indistinguishable from
    a lost connection -- which is how a deterministic 500 on routine creation
    reached users as a connectivity message and stayed misdiagnosed.

    Installing this inside CORS keeps the envelope readable cross-origin. The
    handler registered on the application stays in place as the outer safety net
    for anything raised above this point.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 - the deliberate last resort
            return await unhandled_error_handler(request, exc)
