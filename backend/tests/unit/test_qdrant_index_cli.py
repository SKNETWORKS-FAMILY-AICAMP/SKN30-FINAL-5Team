from __future__ import annotations

from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.scripts import build_qdrant_index


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "staging",
        "qdrant_enabled": True,
        "qdrant_url": "https://qdrant.staging.example",
        "qdrant_api_key": SecretStr("qdrant-secret-sentinel"),
        "qdrant_tls_enabled": True,
        "embedding_provider_code": "OPENAI",
        "embedding_model_version": "text-embedding-test",
        "embedding_vector_dimension": 2,
        "openai_api_key": SecretStr("openai-secret-sentinel"),
        "v3_production_promotion_approved": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_every_staging_gate_is_required() -> None:
    assert (
        build_qdrant_index.staging_index_gate_failure(_settings(), allow_provider_calls=False)
        == "OPT_IN_REQUIRED"
    )
    assert (
        build_qdrant_index.staging_index_gate_failure(
            _settings(
                app_env="test",
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                qdrant_tls_enabled=False,
            ),
            allow_provider_calls=True,
        )
        == "ENVIRONMENT_NOT_STAGING"
    )
    assert (
        build_qdrant_index.staging_index_gate_failure(
            _settings(v3_production_promotion_approved=True), allow_provider_calls=True
        )
        == "PRODUCTION_PROMOTION_FORBIDDEN"
    )
    assert (
        build_qdrant_index.staging_index_gate_failure(
            _settings(qdrant_enabled=False), allow_provider_calls=True
        )
        == "QDRANT_DISABLED"
    )
    assert (
        build_qdrant_index.staging_index_gate_failure(
            _settings(embedding_provider_code="OTHER"), allow_provider_calls=True
        )
        == "EMBEDDING_PROVIDER_NOT_APPROVED"
    )
    assert (
        build_qdrant_index.staging_index_gate_failure(
            _settings(openai_api_key=None), allow_provider_calls=True
        )
        == "CREDENTIAL_MISSING"
    )
    assert (
        build_qdrant_index.staging_index_gate_failure(_settings(), allow_provider_calls=True)
        is None
    )


def test_cli_default_is_zero_call_and_reports_only_canonical_code(capsys) -> None:
    exit_code = build_qdrant_index.main(
        [
            "--catalog-version",
            "exercise-catalog-v2.0.1-final",
            "--vector-index-version",
            "staging-index-v1",
        ],
        settings=_settings(),
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "OPT_IN_REQUIRED"
    assert "sentinel" not in captured.err
