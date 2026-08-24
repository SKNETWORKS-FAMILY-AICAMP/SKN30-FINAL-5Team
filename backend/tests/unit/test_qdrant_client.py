from typing import Any
from uuid import UUID

import pytest
from qdrant_client.http.exceptions import ResponseHandlingException

from backend.app.integrations.qdrant.client import (
    OfficialQdrantClientAdapter,
    QdrantProviderTimeoutError,
    QdrantProviderUnavailableError,
)


class BrokenClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def query_points(self, **_: Any) -> None:
        raise self.error


def _query(adapter: OfficialQdrantClientAdapter) -> None:
    adapter.query_exercises(
        collection_name="exercise_catalog_active",
        query_vector=(1.0, 0.0),
        eligible_exercise_ids=(UUID("00000000-0000-0000-0000-000000000001"),),
        excluded_exercise_ids=(),
        catalog_version="catalog-v1",
        vector_index_version="index-v1",
        embedding_model_version="embedding-v1",
        requested_limit=1,
    )


def test_provider_exception_text_and_api_key_never_cross_adapter_boundary(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "SECRET_API_KEY provider-url-with-credentials"
    adapter = OfficialQdrantClientAdapter(BrokenClient(RuntimeError(secret)), timeout_seconds=1)  # type: ignore[arg-type]

    with pytest.raises(QdrantProviderUnavailableError) as captured:
        _query(adapter)

    assert secret not in str(captured.value)
    assert secret not in caplog.text


def test_timeout_exception_is_mapped_without_provider_text() -> None:
    adapter = OfficialQdrantClientAdapter(
        BrokenClient(TimeoutError("raw timeout")),  # type: ignore[arg-type]
        timeout_seconds=1,
    )

    with pytest.raises(QdrantProviderTimeoutError, match="VECTOR_SEARCH_TIMEOUT"):
        _query(adapter)


def test_wrapped_http_timeout_maps_to_timeout() -> None:
    adapter = OfficialQdrantClientAdapter(
        BrokenClient(ResponseHandlingException(TimeoutError("raw timeout"))),  # type: ignore[arg-type]
        timeout_seconds=1,
    )

    with pytest.raises(QdrantProviderTimeoutError, match="VECTOR_SEARCH_TIMEOUT"):
        _query(adapter)
