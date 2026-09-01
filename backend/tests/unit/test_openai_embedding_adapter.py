from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.integrations.qdrant import openai_embedding
from backend.app.integrations.qdrant.embedding import EmbeddingContract


class FakeEmbeddings:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}
        self.response: object = SimpleNamespace(
            data=(
                SimpleNamespace(index=1, embedding=(3.0, 4.0)),
                SimpleNamespace(index=0, embedding=(1.0, 2.0)),
            )
        )

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return self.response


def _contract() -> EmbeddingContract:
    return EmbeddingContract(
        provider_code="OPENAI",
        model_version="text-embedding-test",
        input_schema_version="exercise-embedding-input-v1",
        vector_dimension=2,
        distance_metric_code="COSINE",
    )


def test_adapter_orders_provider_rows_and_requests_the_approved_dimension() -> None:
    embeddings = FakeEmbeddings()
    adapter = openai_embedding.OpenAIEmbeddingAdapter(
        contract=_contract(), client=SimpleNamespace(embeddings=embeddings)
    )

    result = adapter.embed_documents(("reviewed-a", "reviewed-b"))

    assert result == ((1.0, 2.0), (3.0, 4.0))
    assert embeddings.kwargs == {
        "model": "text-embedding-test",
        "input": ["reviewed-a", "reviewed-b"],
        "dimensions": 2,
        "encoding_format": "float",
    }


def test_query_contains_only_schema_and_normalized_codes() -> None:
    embeddings = FakeEmbeddings()
    embeddings.response = SimpleNamespace(data=(SimpleNamespace(index=0, embedding=(1.0, 2.0)),))
    adapter = openai_embedding.OpenAIEmbeddingAdapter(
        contract=_contract(), client=SimpleNamespace(embeddings=embeddings)
    )

    assert adapter.embed_query(("GOAL_GENERAL", "HOME")) == (1.0, 2.0)
    assert embeddings.kwargs["input"] == [
        '{"normalized_query_codes":["GOAL_GENERAL","HOME"],'
        '"schema_version":"exercise-embedding-input-v1"}'
    ]


def test_provider_exception_is_sanitized() -> None:
    embeddings = FakeEmbeddings()
    embeddings.create = Mock(side_effect=RuntimeError("raw-provider-secret-sentinel"))
    adapter = openai_embedding.OpenAIEmbeddingAdapter(
        contract=_contract(), client=SimpleNamespace(embeddings=embeddings)
    )

    with pytest.raises(openai_embedding.EmbeddingProviderError) as error:
        adapter.embed_documents(("reviewed",))

    assert str(error.value) == "EMBEDDING_PROVIDER_FAILURE"
    assert error.value.__cause__ is None


def test_factory_uses_secret_without_exposing_it_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    constructor = Mock(return_value=SimpleNamespace(embeddings=FakeEmbeddings()))
    monkeypatch.setattr(openai_embedding, "OpenAI", constructor)
    settings = Settings(
        _env_file=None,
        embedding_provider_code="OPENAI",
        embedding_model_version="text-embedding-test",
        embedding_vector_dimension=2,
        openai_api_key=SecretStr("embedding-secret-sentinel"),
    )

    adapter = openai_embedding.build_openai_embedding_adapter(settings)

    assert adapter.contract.model_version == "text-embedding-test"
    assert "embedding-secret-sentinel" not in repr(adapter)
    assert constructor.call_args.kwargs["max_retries"] == 0
    assert constructor.call_args.kwargs["timeout"] == 30.0
