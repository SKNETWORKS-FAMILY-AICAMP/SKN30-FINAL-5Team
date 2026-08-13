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
