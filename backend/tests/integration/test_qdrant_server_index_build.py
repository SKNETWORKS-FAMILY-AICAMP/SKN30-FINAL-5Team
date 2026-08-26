from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from backend.app.core.config import Settings
from backend.app.db.repositories.vector_index import VectorIndexRepository
from backend.app.db.session import DatabaseManager
from backend.app.integrations.qdrant.client import OfficialQdrantClientAdapter
from backend.app.integrations.qdrant.collection_manager import QdrantCollectionManager
from backend.app.integrations.qdrant.embedding import (
    DeterministicFakeEmbeddingAdapter,
    EmbeddingContract,
)
from backend.app.integrations.qdrant.index_builder import ExerciseVectorIndexBuilder

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_QDRANT_INTEGRATION") != "true",
    reason="requires an explicitly provisioned PostgreSQL/Qdrant test environment",
)


def test_real_postgresql_catalog_builds_and_activates_idempotent_qdrant_index() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    database = DatabaseManager(settings.database_url.get_secret_value())
    gateway = OfficialQdrantClientAdapter.from_settings(settings)
    manager = QdrantCollectionManager(
        gateway=gateway,
        alias_name=settings.qdrant_collection_alias,
        batch_size=settings.qdrant_batch_size,
    )
    embedding = DeterministicFakeEmbeddingAdapter(
        EmbeddingContract(
            provider_code="DETERMINISTIC_TEST_ONLY",
            model_version="deterministic-qdrant-integration-v1",
            input_schema_version=settings.embedding_input_schema_version,
            vector_dimension=settings.embedding_vector_dimension,
            distance_metric_code=settings.embedding_distance_metric_code,
        )
    )
    builder = ExerciseVectorIndexBuilder(
        repository=VectorIndexRepository(),
        collection_manager=manager,
        embedding=embedding,
        collection_prefix=settings.qdrant_collection_prefix,
        environment=settings.app_env,
    )
    now = datetime.now(UTC)
    try:
        with database.new_session() as session, session.begin():
            first = builder.build_and_activate(
                session,
                catalog_version="exercise-catalog-v2.0.0-final",
                vector_index_version="qdrant-integration-test-v1",
                now=now,
            )
        with database.new_session() as session, session.begin():
            second = builder.build_and_activate(
                session,
                catalog_version="exercise-catalog-v2.0.0-final",
                vector_index_version="qdrant-integration-test-v1",
                now=now,
            )
    finally:
        database.dispose()

    assert first.point_count == second.point_count == 102
    assert len(first.build_hash) == 64
    assert first.build_hash == second.build_hash
    assert first.alias_changed is True
    assert second.alias_changed is False
    assert gateway.exact_count(first.collection_name) == 102
    assert gateway.aliases()[settings.qdrant_collection_alias] == first.collection_name
