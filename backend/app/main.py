import base64
import binascii
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.v1.router import api_router
from backend.app.core.catalog_guard import validate_catalog_manifests
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import register_exception_handlers
from backend.app.core.logging import configure_logging
from backend.app.core.middleware import RequestContextMiddleware
from backend.app.db.session import DatabaseManager
from backend.app.integrations.birthdate_crypto import (
    AwsKmsBirthdateCipher,
    KmsClient,
    LocalAesGcmBirthdateCipher,
)
from backend.app.integrations.firebase_auth import build_firebase_token_verifier
from backend.app.integrations.llm_provider import build_narration_provider
from backend.app.integrations.s3.exercise_media import build_exercise_media_url_provider
from backend.app.integrations.s3.profile_image import build_s3_profile_image_adapter
from backend.app.integrations.v3_application_composition import (
    V3ApplicationCompositionError,
    compose_v3_application_services,
)
from backend.app.integrations.v3_demo_factory import build_optional_v3_demo_runtime
from backend.app.integrations.v3_demo_identity import SqlAlchemyV3DemoIdentityProvider
from backend.app.modules.catalog.service import ExerciseMediaUrlPort
from backend.app.modules.decisions.execution_profile import (
    DecisionCreationServicePort,
    LegacyDecisionCreationService,
    ProfiledDecisionCreationService,
    StaticV3ProductionPromotionGate,
    V3ExecutionProfile,
    V3ProductionPromotionGatePort,
    V3ShadowCreationPort,
)
from backend.app.modules.decisions.ports import DecisionRepositoryPort, NarrationProviderPort
from backend.app.modules.decisions.service import DecisionService
from backend.app.modules.decisions.v3_regeneration import V3RegenerationServicePort
from backend.app.modules.identity.ports import FirebaseTokenVerifier
from backend.app.modules.profiles.ports import BirthdateCipher
from backend.app.modules.weekly_reports.narration import WeeklyReportNarrationAgent


def _build_birthdate_cipher(
    settings: Settings,
    *,
    kms_client: KmsClient | None = None,
) -> BirthdateCipher | None:
    configured_key = settings.birthdate_encryption_key_base64
    if settings.app_env in {"staging", "production"}:
        if settings.birthdate_kms_key_id is None:
            return None
        if kms_client is None:
            import boto3

            kms_client = cast(
                KmsClient,
                boto3.client("kms", region_name=settings.aws_region),
            )
        return AwsKmsBirthdateCipher(
            kms_client,
            key_id=settings.birthdate_kms_key_id,
        )
    if configured_key is None:
        return None
    try:
        key = base64.b64decode(configured_key.get_secret_value(), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("BIRTHDATE_ENCRYPTION_KEY_BASE64 is invalid") from exc
    return LocalAesGcmBirthdateCipher(
        key,
        key_id=settings.birthdate_encryption_key_id,
        app_env=settings.app_env,
    )


def create_app(
    *,
    settings: Settings | None = None,
    readiness_probe: Callable[[], None] | None = None,
    firebase_token_verifier: FirebaseTokenVerifier | None = None,
    birthdate_cipher: BirthdateCipher | None = None,
    narration_provider: NarrationProviderPort | None = None,
    exercise_media_url_provider: ExerciseMediaUrlPort | None = None,
    profile_image_storage: object | None = None,
    v3_creation_service: DecisionCreationServicePort | None = None,
    v3_shadow_service: V3ShadowCreationPort | None = None,
    v3_promotion_gate: V3ProductionPromotionGatePort | None = None,
    v3_regeneration_service: V3RegenerationServicePort | None = None,
    v3_service_composer: Callable[
        [Settings, DatabaseManager, object],
        tuple[DecisionCreationServicePort, V3RegenerationServicePort],
    ]
    | None = None,
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
        else build_firebase_token_verifier(
            resolved_settings.firebase_project_id,
            resolved_settings.firebase_clock_skew_seconds,
            resolved_settings.google_application_credentials,
        )
    )
    application.state.birthdate_cipher = (
        birthdate_cipher
        if birthdate_cipher is not None
        else _build_birthdate_cipher(resolved_settings)
    )
    application.state.narration_provider = (
        narration_provider
        if narration_provider is not None
        else build_narration_provider(resolved_settings)
    )
    application.state.weekly_report_narration_agent = WeeklyReportNarrationAgent(
        application.state.narration_provider
    )
    application.state.exercise_media_url_provider = (
        exercise_media_url_provider
        if exercise_media_url_provider is not None
        else build_exercise_media_url_provider(resolved_settings)
    )
    application.state.profile_image_storage = (
        profile_image_storage
        if profile_image_storage is not None
        else build_s3_profile_image_adapter(resolved_settings)
    )
    promotion_gate = (
        v3_promotion_gate
        if v3_promotion_gate is not None
        else StaticV3ProductionPromotionGate(resolved_settings.v3_production_promotion_approved)
    )
    profile = V3ExecutionProfile(resolved_settings.v3_execution_profile)
    authoritative_v3 = profile is V3ExecutionProfile.DEMO or (
        profile is V3ExecutionProfile.PRODUCTION and promotion_gate.allows_v3()
    )
    application.state.v3_authoritative_enabled = authoritative_v3
    runtime = None
    if authoritative_v3 and v3_creation_service is None and v3_regeneration_service is None:
        runtime = build_optional_v3_demo_runtime(
            resolved_settings,
            identity_provider=SqlAlchemyV3DemoIdentityProvider(database_manager.new_session),
            production_promotion_approved=promotion_gate.allows_v3(),
        )
    application.state.v3_demo_runtime = runtime
    composer = v3_service_composer or compose_v3_application_services
    if runtime is not None:
        try:
            composition_settings = resolved_settings.model_copy(
                update={"v3_production_promotion_approved": authoritative_v3}
            )
            automatic_creation, automatic_regeneration = composer(
                composition_settings, database_manager, runtime
            )
        except (SQLAlchemyError, V3ApplicationCompositionError):
            # The request path returns the stable V3_COMPOSITION_UNAVAILABLE code.
            # Do not log DB/provider exception details or fall back to legacy.
            automatic_creation = None
            automatic_regeneration = None
        if v3_creation_service is None and automatic_creation is not None:
            v3_creation_service = automatic_creation
        if v3_regeneration_service is None and automatic_regeneration is not None:
            v3_regeneration_service = automatic_regeneration

    def build_decision_creation_service(
        repository: DecisionRepositoryPort,
    ) -> DecisionCreationServicePort:
        legacy_creation_service = LegacyDecisionCreationService(
            DecisionService(
                repository,
                narration_provider=application.state.narration_provider,
            )
        )
        return ProfiledDecisionCreationService(
            profile=profile,
            legacy=legacy_creation_service,
            v3=v3_creation_service,
            shadow=v3_shadow_service,
            promotion_gate=promotion_gate,
        )

    application.state.decision_creation_service_factory = build_decision_creation_service
    application.state.v3_regeneration_service = v3_regeneration_service
    if resolved_settings.cors_allowed_origins:
        # Only the listed origins, and only the headers the client actually
        # sends. Needed for the browser-based demo; native builds send no
        # Origin header and leave this unset.
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_settings.cors_allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "If-Match"],
            expose_headers=["X-Request-ID"],
        )
    application.add_middleware(RequestContextMiddleware)
    register_exception_handlers(application)
    application.include_router(api_router, prefix=resolved_settings.api_v1_prefix)
    return application


app = create_app()
