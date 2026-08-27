"""Remap an approved staging Qdrant index to the canonical staging catalog UUIDs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime

from sqlalchemy.engine import URL, make_url

from backend.app.core.config import Settings
from backend.app.db.repositories.vector_index import (
    IndexableExerciseRecord,
    VectorIndexBuildWrite,
    VectorIndexRepository,
)
from backend.app.db.session import DatabaseManager
from backend.app.integrations.qdrant.client import OfficialQdrantClientAdapter, QdrantPoint
from backend.app.integrations.qdrant.collection_manager import (
    QdrantCollectionManager,
    immutable_collection_name,
)
from backend.app.integrations.qdrant.embedding import EmbeddingContract
from backend.app.integrations.qdrant.index_builder import (
    canonical_embedding_document,
    vector_index_build_hash,
)

SOURCE_DATABASE = "exercise_app"
TARGET_DATABASE = "helkki_staging"
CATALOG_VERSION = "exercise-catalog-v2.0.1-final"
VECTOR_INDEX_VERSION = "v201-openai-text-embedding-3-large-d3072-inputv1-cosine-r2-helkki-staging"
EXPECTED_POINT_COUNT = 102
EXPECTED_MODEL = "text-embedding-3-large"
EXPECTED_DIMENSION = 3072
EXPECTED_INPUT_SCHEMA = "exercise-embedding-input-v1"
EXPECTED_DISTANCE = "COSINE"


def _database_url(base_url: URL, database_name: str) -> str:
    return base_url.set(database=database_name).render_as_string(hide_password=False)


def _document_hash(record: IndexableExerciseRecord) -> str:
    return hashlib.sha256(canonical_embedding_document(record).encode()).hexdigest()


def remap_points(
    *,
    source_records: tuple[IndexableExerciseRecord, ...],
    old_records: tuple[IndexableExerciseRecord, ...],
    old_points: tuple[QdrantPoint, ...],
    vector_index_version: str,
    build_hash: str,
) -> tuple[QdrantPoint, ...]:
    """Map catalog-only vectors by stable code while verifying their source documents."""

    source_by_code = {record.stable_code: record for record in source_records}
    old_by_id = {record.exercise_id: record for record in old_records}
    if len(source_by_code) != len(source_records) or len(old_by_id) != len(old_records):
        raise ValueError("catalog exercise identity is not unique")
    if set(source_by_code) != {record.stable_code for record in old_records}:
        raise ValueError("source and old catalog stable-code sets differ")
    if {point.exercise_id for point in old_points} != set(old_by_id):
        raise ValueError("old Qdrant point UUID set differs from the old catalog")

    remapped: list[QdrantPoint] = []
    for old_point in old_points:
        old_record = old_by_id[old_point.exercise_id]
        source_record = source_by_code[old_record.stable_code]
        source_hash = _document_hash(source_record)
        if source_hash != _document_hash(old_record):
            raise ValueError("catalog embedding document changed during UUID remap")
        if old_point.payload.get("source_document_hash") != source_hash:
            raise ValueError("old Qdrant source document hash is not canonical")
        payload = dict(old_point.payload)
        payload.update(
            {
                "catalog_version_id": str(source_record.catalog_version_id),
                "vector_index_version": vector_index_version,
                "build_hash": build_hash,
            }
        )
        remapped.append(
            QdrantPoint(
                exercise_id=source_record.exercise_id,
                vector=old_point.vector,
                payload=payload,
            )
        )
    return tuple(sorted(remapped, key=lambda point: str(point.exercise_id)))


def _contract(settings: Settings) -> EmbeddingContract:
    expected = (
        "OPENAI",
        EXPECTED_MODEL,
        EXPECTED_INPUT_SCHEMA,
        EXPECTED_DIMENSION,
        EXPECTED_DISTANCE,
    )
    actual = (
        settings.embedding_provider_code,
        settings.embedding_model_version,
        settings.embedding_input_schema_version,
        settings.embedding_vector_dimension,
        settings.embedding_distance_metric_code,
    )
    if actual != expected:
        raise ValueError("embedding contract differs from the approved staging contract")
    return EmbeddingContract(
        provider_code=actual[0],
        model_version=actual[1],
        input_schema_version=actual[2],
        vector_dimension=actual[3],
        distance_metric_code=actual[4],
    )


def _manager(settings: Settings) -> tuple[OfficialQdrantClientAdapter, QdrantCollectionManager]:
    gateway = OfficialQdrantClientAdapter.from_settings(settings)
    return gateway, QdrantCollectionManager(
        gateway=gateway,
        alias_name=settings.qdrant_collection_alias,
        batch_size=settings.qdrant_batch_size,
    )


def prepare(settings: Settings) -> dict[str, object]:
    base_url = make_url(settings.database_url.get_secret_value())
    if base_url.database != SOURCE_DATABASE:
        raise ValueError("exercise_app DATABASE_URL is required for prepare")
    source_db = DatabaseManager(_database_url(base_url, SOURCE_DATABASE))
    target_db = DatabaseManager(_database_url(base_url, TARGET_DATABASE))
    repository = VectorIndexRepository()
    gateway, manager = _manager(settings)
    contract = _contract(settings)
    try:
        with source_db.new_session() as source_session:
            source_records = repository.list_indexable_exercises(source_session, CATALOG_VERSION)
        with target_db.new_session() as target_session:
            old_records = repository.list_indexable_exercises(target_session, CATALOG_VERSION)
            if not old_records:
                raise ValueError("old target catalog is not indexable")
            old_registry = repository.get_active_for_catalog(
                target_session, old_records[0].catalog_version_id
            )
            if old_registry is None:
                raise ValueError("old target registry has no ACTIVE row")
            old_collection = old_registry.collection_name
        if len(source_records) != EXPECTED_POINT_COUNT or len(old_records) != EXPECTED_POINT_COUNT:
            raise ValueError("catalog point count differs from the approved count")
        if gateway.aliases().get(settings.qdrant_collection_alias) != old_collection:
            raise ValueError("Qdrant alias and old ACTIVE registry differ")
        old_points = gateway.retrieve_points_with_vectors(
            collection_name=old_collection,
            exercise_ids=tuple(record.exercise_id for record in old_records),
        )
        source_hashes = tuple(_document_hash(record) for record in source_records)
        build_hash = vector_index_build_hash(
            records=source_records,
            source_document_hashes=source_hashes,
            vector_index_version=VECTOR_INDEX_VERSION,
            embedding_contract=contract,
        )
        new_collection = immutable_collection_name(
            prefix=settings.qdrant_collection_prefix,
            environment=settings.app_env,
            catalog_version=CATALOG_VERSION,
            embedding_model_version=contract.model_version,
            vector_index_version=VECTOR_INDEX_VERSION,
        )
        points = remap_points(
            source_records=source_records,
            old_records=old_records,
            old_points=old_points,
            vector_index_version=VECTOR_INDEX_VERSION,
            build_hash=build_hash,
        )
        manager.build(
            collection_name=new_collection,
            vector_dimension=contract.vector_dimension,
            distance_metric_code=contract.distance_metric_code,
            points=points,
            expected_build_hash=build_hash,
        )
        if gateway.aliases().get(settings.qdrant_collection_alias) != old_collection:
            raise ValueError("prepare changed the active Qdrant alias")
        return {
            "status": "VECTOR_REMAP_PREPARED",
            "vector_index_version": VECTOR_INDEX_VERSION,
            "collection_name": new_collection,
            "point_count": len(points),
            "build_hash": build_hash,
            "alias_changed": False,
        }
    finally:
        source_db.dispose()
        target_db.dispose()


def activate(settings: Settings) -> dict[str, object]:
    base_url = make_url(settings.database_url.get_secret_value())
    if base_url.database != TARGET_DATABASE:
        raise ValueError("helkki_staging DATABASE_URL is required for activate")
    database = DatabaseManager(_database_url(base_url, TARGET_DATABASE))
    repository = VectorIndexRepository()
    _, manager = _manager(settings)
    contract = _contract(settings)
    try:
        with database.new_session() as session:
            records = repository.list_indexable_exercises(session, CATALOG_VERSION)
        if len(records) != EXPECTED_POINT_COUNT:
            raise ValueError("canonical staging catalog point count is invalid")
        source_hashes = tuple(_document_hash(record) for record in records)
        build_hash = vector_index_build_hash(
            records=records,
            source_document_hashes=source_hashes,
            vector_index_version=VECTOR_INDEX_VERSION,
            embedding_contract=contract,
        )
        collection_name = immutable_collection_name(
            prefix=settings.qdrant_collection_prefix,
            environment=settings.app_env,
            catalog_version=CATALOG_VERSION,
            embedding_model_version=contract.model_version,
            vector_index_version=VECTOR_INDEX_VERSION,
        )
        manager.validate(
            collection_name=collection_name,
            expected_ids=tuple(record.exercise_id for record in records),
            expected_build_hash=build_hash,
        )
        now = datetime.now(UTC)
        with database.new_session() as session, session.begin():
            registry = repository.create_build(
                session,
                VectorIndexBuildWrite(
                    catalog_version_id=records[0].catalog_version_id,
                    collection_name=collection_name,
                    vector_index_version=VECTOR_INDEX_VERSION,
                    source_manifest_hash=records[0].catalog_manifest_hash,
                    embedding_model_version=contract.model_version,
                    embedding_input_schema_version=contract.input_schema_version,
                    distance_metric_code=contract.distance_metric_code,
                    vector_dimension=contract.vector_dimension,
                    build_hash=build_hash,
                ),
            )
            if registry.status_code != "ACTIVE":
                repository.mark_ready(session, registry, built_at=now)
        alias_changed = manager.activate(collection_name)
        with database.new_session() as session, session.begin():
            activated_registry = repository.get_by_version(session, VECTOR_INDEX_VERSION)
            if activated_registry is None:
                raise ValueError("prepared registry disappeared before activation")
            repository.activate(session, activated_registry, activated_at=now)
        return {
            "status": "VECTOR_REMAP_ACTIVATED",
            "vector_index_version": VECTOR_INDEX_VERSION,
            "collection_name": collection_name,
            "point_count": len(records),
            "build_hash": build_hash,
            "alias_changed": alias_changed,
        }
    finally:
        database.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "activate"))
    args = parser.parse_args(argv)
    try:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        if settings.app_env != "staging" or not settings.qdrant_enabled:
            raise ValueError("approved staging Qdrant settings are required")
        result = prepare(settings) if args.command == "prepare" else activate(settings)
    except Exception as exc:
        print(f"QDRANT_REMAP_FAILED:{type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["activate", "main", "prepare", "remap_points"]
