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
