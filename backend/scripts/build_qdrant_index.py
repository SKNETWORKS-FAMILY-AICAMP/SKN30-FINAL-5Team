"""Build and atomically activate one approved staging exercise vector index."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime

from backend.app.core.config import Settings
from backend.app.db.repositories.vector_index import VectorIndexRepository
from backend.app.db.session import DatabaseManager
from backend.app.integrations.qdrant.client import OfficialQdrantClientAdapter
from backend.app.integrations.qdrant.collection_manager import QdrantCollectionManager
from backend.app.integrations.qdrant.index_builder import ExerciseVectorIndexBuilder
from backend.app.integrations.qdrant.openai_embedding import build_openai_embedding_adapter

_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


def staging_index_gate_failure(settings: Settings, *, allow_provider_calls: bool) -> str | None:
    if not allow_provider_calls:
        return "OPT_IN_REQUIRED"
    if settings.app_env != "staging":
        return "ENVIRONMENT_NOT_STAGING"
    if settings.v3_production_promotion_approved:
        return "PRODUCTION_PROMOTION_FORBIDDEN"
    if not settings.qdrant_enabled:
        return "QDRANT_DISABLED"
    if settings.embedding_provider_code != "OPENAI":
        return "EMBEDDING_PROVIDER_NOT_APPROVED"
    if settings.embedding_model_version == "unconfigured":
        return "EMBEDDING_MODEL_NOT_APPROVED"
    if settings.embedding_vector_dimension <= 0:
        return "EMBEDDING_CONTRACT_INVALID"
    if settings.openai_api_key is None:
        return "CREDENTIAL_MISSING"
    return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-version", required=True)
    parser.add_argument("--vector-index-version", required=True)
    parser.add_argument("--allow-provider-calls", action="store_true")
    return parser


def main(argv: list[str] | None = None, *, settings: Settings | None = None) -> int:
    args = _parser().parse_args(argv)
    if not _VERSION_PATTERN.fullmatch(args.catalog_version) or not _VERSION_PATTERN.fullmatch(
        args.vector_index_version
    ):
        print("INDEX_VERSION_INVALID", file=sys.stderr)
        return 2
    try:
        current_settings = settings or Settings(_env_file=None)  # type: ignore[call-arg]
    except Exception:
        print("SETTINGS_INVALID", file=sys.stderr)
        return 2
    gate_failure = staging_index_gate_failure(
        current_settings, allow_provider_calls=args.allow_provider_calls
    )
    if gate_failure is not None:
        print(gate_failure, file=sys.stderr)
        return 2

    database = DatabaseManager(current_settings.database_url.get_secret_value())
    try:
        gateway = OfficialQdrantClientAdapter.from_settings(current_settings)
        manager = QdrantCollectionManager(
            gateway=gateway,
            alias_name=current_settings.qdrant_collection_alias,
            batch_size=current_settings.qdrant_batch_size,
        )
        builder = ExerciseVectorIndexBuilder(
            repository=VectorIndexRepository(),
            collection_manager=manager,
            embedding=build_openai_embedding_adapter(current_settings),
            collection_prefix=current_settings.qdrant_collection_prefix,
            environment=current_settings.app_env,
        )
        with database.new_session() as session, session.begin():
            result = builder.build_and_activate(
                session,
                catalog_version=args.catalog_version,
                vector_index_version=args.vector_index_version,
                now=datetime.now(UTC),
            )
    except Exception:
        print("QDRANT_INDEX_BUILD_FAILED", file=sys.stderr)
        return 2
    finally:
        database.dispose()

    print(
        json.dumps(
            {
                "alias_changed": result.alias_changed,
                "build_hash": result.build_hash,
                "collection_name": result.collection_name,
                "point_count": result.point_count,
                "vector_index_version": result.vector_index_version,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["main", "staging_index_gate_failure"]
