from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.v1.router import api_router
from backend.app.core.catalog_guard import validate_catalog_manifests
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import register_exception_handlers
from backend.app.core.logging import configure_logging
from backend.app.core.middleware import RequestContextMiddleware
from backend.app.db.session import DatabaseManager
from backend.app.integrations.firebase_auth import build_firebase_token_verifier
from backend.app.modules.identity.ports import FirebaseTokenVerifier


def create_app(
    *,
    settings: Settings | None = None,
    readiness_probe: Callable[[], None] | None = None,
    firebase_token_verifier: FirebaseTokenVerifier | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    database_manager = DatabaseManager(resolved_settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        validate_catalog_manifests(
            resolved_settings.app_env,
            resolved_settings.catalog_manifest_paths,
        )
        try:
            yield
        finally:
            database_manager.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.database_manager = database_manager
    application.state.readiness_probe = readiness_probe or database_manager.readiness_probe
    application.state.firebase_token_verifier = (
        firebase_token_verifier
        if firebase_token_verifier is not None
        else build_firebase_token_verifier(resolved_settings.firebase_project_id)
    )
    application.add_middleware(RequestContextMiddleware)
    register_exception_handlers(application)
    application.include_router(api_router, prefix=resolved_settings.api_v1_prefix)
    return application


app = create_app()
