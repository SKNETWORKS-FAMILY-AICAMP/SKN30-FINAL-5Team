import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings


def test_database_url_is_masked_in_settings_representation() -> None:
    secret = "postgresql+psycopg://user:secret@localhost:5432/app"
    settings = Settings(database_url=secret)

    assert secret not in repr(settings)
    assert settings.database_url.get_secret_value() == secret


def test_api_prefix_cannot_drift_from_contract() -> None:
    with pytest.raises(ValidationError, match="must remain /api/v1"):
        Settings(api_v1_prefix="/api/v2")


def test_blank_firebase_project_id_is_treated_as_unconfigured() -> None:
    settings = Settings(firebase_project_id="   ")

    assert settings.firebase_project_id is None


def test_onboarding_deployment_configuration_loads_json_code_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ONBOARDING_PRIMARY_GOAL_CODES", '["GENERAL_FITNESS"]')
    monkeypatch.setenv("ONBOARDING_EXPERIENCE_LEVEL_CODES", '["BEGINNER"]')
    monkeypatch.setenv("BIRTHDATE_ENCRYPTION_KEY_BASE64", "")

    settings = Settings(_env_file=None)

    assert settings.onboarding_primary_goal_codes == ("GENERAL_FITNESS",)
    assert settings.onboarding_experience_level_codes == ("BEGINNER",)
    assert settings.birthdate_encryption_key_base64 is None


def test_blank_onboarding_deployment_configuration_stays_unconfigured() -> None:
    settings = Settings(
        _env_file=None,
        consent_policy_version="   ",
        onboarding_primary_goal_codes="[]",
        onboarding_experience_level_codes='["  "]',
    )

    assert settings.consent_policy_version is None
    assert settings.onboarding_primary_goal_codes == ()
    assert settings.onboarding_experience_level_codes == ()


def test_blank_kms_configuration_is_treated_as_unconfigured() -> None:
    settings = Settings(
        _env_file=None,
        birthdate_kms_key_id="   ",
        aws_region="   ",
    )

    assert settings.birthdate_kms_key_id is None
    assert settings.aws_region is None


def test_exercise_media_s3_configuration_is_bounded() -> None:
    settings = Settings(
        _env_file=None,
        exercise_media_s3_bucket="exercise-app-media-test",
        exercise_media_s3_region="ap-northeast-2",
        exercise_media_url_expiry_seconds=60,
    )
    assert settings.exercise_media_s3_prefix == "videos/"
    assert settings.exercise_media_url_expiry_seconds == 60

    with pytest.raises(ValidationError, match="must remain videos"):
        Settings(_env_file=None, exercise_media_s3_prefix="images/")
    with pytest.raises(ValidationError, match=r"within \[60, 900\]"):
        Settings(_env_file=None, exercise_media_url_expiry_seconds=901)
    with pytest.raises(ValidationError, match="must be configured together"):
        Settings(_env_file=None, exercise_media_s3_bucket="exercise-app-media-test")


def test_cors_allowed_origins_defaults_to_disabled() -> None:
    # Asserted on the declared default rather than an instance, because
    # Settings() also reads the ambient environment and a shell that exports
    # CORS_ALLOWED_ORIGINS would otherwise make this pass or fail by accident.
    assert Settings.model_fields["cors_allowed_origins"].default == ()


def test_cors_allowed_origins_parses_comma_separated_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost/test",
        cors_allowed_origins="http://localhost:8081, http://127.0.0.1:8081",
    )
    assert settings.cors_allowed_origins == (
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    )


def test_cors_allowed_origins_rejects_wildcard() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg://test:test@localhost/test",
            cors_allowed_origins="*",
        )


def test_tuple_settings_accept_comma_separated_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ONBOARDING_PRIMARY_GOAL_CODES", "GENERAL_FITNESS,STRENGTH")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:8081, http://127.0.0.1:8081")
    settings = Settings(database_url="postgresql+psycopg://test:test@localhost/test")
    assert settings.onboarding_primary_goal_codes == ("GENERAL_FITNESS", "STRENGTH")
    assert settings.cors_allowed_origins == (
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    )


def test_tuple_settings_still_accept_json_array_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ONBOARDING_PRIMARY_GOAL_CODES", '["GENERAL_FITNESS"]')
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:8081"]')
    settings = Settings(database_url="postgresql+psycopg://test:test@localhost/test")
    assert settings.onboarding_primary_goal_codes == ("GENERAL_FITNESS",)
    assert settings.cors_allowed_origins == ("http://localhost:8081",)


def test_clock_skew_defaults_to_a_tolerant_window() -> None:
    # Zero tolerance makes a server clock that trails Google's by a second
    # reject fresh tokens, so the default is not the SDK's.
    assert Settings().firebase_clock_skew_seconds == 60


@pytest.mark.parametrize("value", [-1, 61])
def test_clock_skew_outside_the_sdk_range_is_refused_at_startup(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(firebase_clock_skew_seconds=value)


def test_qdrant_is_disabled_and_secret_is_masked_by_default() -> None:
    settings = Settings(qdrant_api_key="synthetic-secret")

    assert settings.qdrant_enabled is False
    assert "synthetic-secret" not in repr(settings)


def test_embedding_input_schema_defaults_to_recommendation_level_contract() -> None:
    assert Settings.model_fields["embedding_input_schema_version"].default == (
        "exercise-embedding-input-v2"
    )


def test_v3_regeneration_requires_its_own_server_side_flag() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="synthetic-secret",
        llm_agents_enabled=True,
        v3_langgraph_enabled=True,
    )

    assert settings.v3_regeneration_enabled is False


def test_qdrant_enabled_requires_an_explicit_embedding_contract() -> None:
    with pytest.raises(ValidationError, match="approved embedding contract"):
        Settings(qdrant_enabled=True)


def test_qdrant_url_rejects_embedded_credentials() -> None:
    with pytest.raises(ValidationError, match="must not contain credentials"):
        Settings(qdrant_url="https://user:secret@qdrant.example")


def test_production_qdrant_requires_tls_and_api_key() -> None:
    common = {
        "app_env": "production",
        "qdrant_enabled": True,
        "embedding_provider_code": "APPROVED_PROVIDER",
        "embedding_model_version": "approved-model-v1",
        "embedding_vector_dimension": 4,
    }
    with pytest.raises(ValidationError, match="requires QDRANT_API_KEY"):
        Settings(
            **common,
            qdrant_url="https://qdrant.example",
            qdrant_tls_enabled=True,
        )
    with pytest.raises(ValidationError, match="must agree"):
        Settings(
            **common,
            qdrant_url="http://qdrant.example",
            qdrant_tls_enabled=True,
            qdrant_api_key="synthetic-secret",
        )


def test_embedding_timeout_is_bounded() -> None:
    assert Settings(_env_file=None).embedding_timeout_seconds == 30.0
    with pytest.raises(ValidationError, match="EMBEDDING_TIMEOUT_SECONDS"):
        Settings(_env_file=None, embedding_timeout_seconds=0)
    with pytest.raises(ValidationError, match="EMBEDDING_TIMEOUT_SECONDS"):
        Settings(_env_file=None, embedding_timeout_seconds=121)


def test_agent_timeout_covers_a_measured_reasoning_model_call() -> None:
    # The bound is also handed to the provider client, so it has to cover a
    # whole call. Staging measured 17.2-23.5s for the slowest specialist against
    # a 38-exercise pool, and a 30s ceiling left no room for ordinary variance.
    assert Settings(llm_agents_timeout_seconds=45.0).llm_agents_timeout_seconds == 45.0
    assert Settings(llm_agents_timeout_seconds=60.0).llm_agents_timeout_seconds == 60.0


def test_agent_timeout_still_has_an_upper_bound() -> None:
    with pytest.raises(ValidationError, match=r"must be within \(0, 60\]"):
        Settings(llm_agents_timeout_seconds=61.0)
    with pytest.raises(ValidationError, match=r"must be within \(0, 60\]"):
        Settings(llm_agents_timeout_seconds=0)
