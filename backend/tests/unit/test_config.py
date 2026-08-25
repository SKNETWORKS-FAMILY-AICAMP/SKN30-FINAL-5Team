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
