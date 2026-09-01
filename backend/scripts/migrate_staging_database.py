"""Clone one PostgreSQL application database into an empty staging database safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.sql.ddl import sort_tables

from backend.app.core.config import Settings

EXPECTED_SOURCE_DATABASE = "exercise_app"
EXPECTED_TARGET_DATABASE = "helkki_staging"
EXPECTED_CATALOG_VERSION = "exercise-catalog-v2.0.1-final"
EXPECTED_TARGET_CATALOG_ID_BEFORE = "04d726d5-ad3d-45f0-b400-bf4205113863"
CONFIRMED_SNAPSHOT = "database-1-pre-helkki-staging-migration-20260827-01"
LOCK_KEY = 1_501_027


def _json_default(value: object) -> object:
    if isinstance(value, (UUID, datetime, date, Decimal, Enum)):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def canonical_rows_hash(rows: Iterable[Mapping[str, object]]) -> str:
    canonical = [dict(sorted(row.items())) for row in rows]
    canonical.sort(
        key=lambda row: json.dumps(
            row,
            default=_json_default,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    payload = json.dumps(
        canonical,
        default=_json_default,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def order_self_referencing_rows(
    table: Table, rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    self_constraints = [
        constraint
        for constraint in table.foreign_key_constraints
        if constraint.referred_table is table
    ]
    if not self_constraints or not rows:
        return rows
    primary_keys = tuple(column.name for column in table.primary_key.columns)
    if not primary_keys:
        raise ValueError(f"self-referencing table {table.name} has no primary key")
    pending = list(rows)
    inserted: set[tuple[object, ...]] = set()
    ordered: list[dict[str, object]] = []
    while pending:
        ready: list[dict[str, object]] = []
        for row in pending:
            dependencies: list[tuple[object, ...]] = []
            for constraint in self_constraints:
                local_values = tuple(row[element.parent.name] for element in constraint.elements)
                if all(value is None for value in local_values):
                    continue
                remote_names = tuple(element.column.name for element in constraint.elements)
                dependency = tuple(local_values[remote_names.index(key)] for key in primary_keys)
                dependencies.append(dependency)
            if all(dependency in inserted for dependency in dependencies):
                ready.append(row)
        if not ready:
            raise ValueError(f"unresolvable self-reference in {table.name}")
        for row in ready:
            inserted.add(tuple(row[key] for key in primary_keys))
            ordered.append(row)
            pending.remove(row)
    return ordered


def _database_url(base_url: URL, database_name: str) -> URL:
    return base_url.set(database=database_name)


def _schema_signature(connection: Connection) -> tuple[tuple[object, ...], ...]:
    rows = connection.execute(
        text(
            """
            SELECT table_name, column_name, ordinal_position, data_type, udt_name,
                   is_nullable, coalesce(column_default, '')
            FROM information_schema.columns
            WHERE table_schema='public'
            ORDER BY table_name, ordinal_position
            """
        )
    ).all()
    return tuple(tuple(row) for row in rows)


def _active_catalog(connection: Connection) -> tuple[str, str, int]:
    return (
        connection.execute(
            text(
                """
            SELECT id::text, version_code, exercise_record_count
            FROM catalog_versions WHERE status_code='ACTIVE'
            """
            )
        )
        .one()
        ._tuple()
    )


def _revisions(connection: Connection) -> tuple[str, ...]:
    return tuple(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())


def _table_rows(connection: Connection, table: Table) -> list[dict[str, object]]:
    return [dict(row) for row in connection.execute(select(table)).mappings()]


def _print_summary(summary: Mapping[str, object]) -> None:
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def migrate(*, base_url: URL, allow_write: bool) -> int:
    source_engine = create_engine(_database_url(base_url, EXPECTED_SOURCE_DATABASE))
    target_engine = create_engine(_database_url(base_url, EXPECTED_TARGET_DATABASE))
    source = source_engine.connect().execution_options(isolation_level="REPEATABLE READ")
    target = target_engine.connect().execution_options(isolation_level="SERIALIZABLE")
    source_transaction = source.begin()
    target_transaction = target.begin()
    try:
        source.execute(text("SET TRANSACTION READ ONLY"))
        if (
            source.execute(text("SELECT current_database()")).scalar_one()
            != EXPECTED_SOURCE_DATABASE
        ):
            raise ValueError("source database mismatch")
        if (
            target.execute(text("SELECT current_database()")).scalar_one()
            != EXPECTED_TARGET_DATABASE
        ):
            raise ValueError("target database mismatch")
        target.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        if _schema_signature(source) != _schema_signature(target):
            raise ValueError("source and target schemas differ")
        if _revisions(source) != _revisions(target):
            raise ValueError("source and target Alembic revisions differ")
        source_catalog = _active_catalog(source)
        target_catalog = _active_catalog(target)
        if (
            source_catalog[1] != EXPECTED_CATALOG_VERSION
            or target_catalog[1] != EXPECTED_CATALOG_VERSION
        ):
            raise ValueError("active catalog version mismatch")
        if source_catalog[2] != 102 or target_catalog[2] != 102:
            raise ValueError("active catalog exercise count mismatch")
        target_registry_count = target.execute(
            text("SELECT count(*) FROM vector_index_registry")
        ).scalar_one()

        metadata = MetaData()
        metadata.reflect(bind=source, schema="public")
        tables = [table for table in metadata.tables.values() if table.name != "alembic_version"]
        source_rows = {table.name: _table_rows(source, table) for table in tables}
        source_hashes = {
            table.name: canonical_rows_hash(source_rows[table.name]) for table in tables
        }
        source_counts = {table.name: len(source_rows[table.name]) for table in tables}
        if not allow_write:
            replicated_tables = [table for table in tables if table.name != "vector_index_registry"]
            target_rows = {table.name: _table_rows(target, table) for table in replicated_tables}
            replicated_content_matches = all(
                source_counts[table.name] == len(target_rows[table.name])
                and source_hashes[table.name] == canonical_rows_hash(target_rows[table.name])
                for table in replicated_tables
            )
            target_transaction.rollback()
            source_transaction.rollback()
            _print_summary(
                {
                    "status": "DRY_RUN_OK",
                    "source_database": EXPECTED_SOURCE_DATABASE,
                    "target_database": EXPECTED_TARGET_DATABASE,
                    "table_count": len(tables),
                    "source_row_count": sum(source_counts.values()),
                    "source_active_catalog_id": source_catalog[0],
                    "target_active_catalog_id_before": target_catalog[0],
                    "replicated_table_count": len(replicated_tables),
                    "replicated_content_matches": replicated_content_matches,
                    "target_vector_index_registry_rows": target_registry_count,
                }
            )
            return 0

        if target_catalog[0] != EXPECTED_TARGET_CATALOG_ID_BEFORE:
            raise ValueError("target catalog identity changed after the approved preflight")
        if target_registry_count != 1:
            raise ValueError("target vector registry changed after the approved preflight")

        preparer = target.dialect.identifier_preparer
        quoted = ", ".join(
            f"{preparer.quote_schema('public')}.{preparer.quote(table.name)}" for table in tables
        )
        target.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
        for table in sort_tables(tables):
            rows = order_self_referencing_rows(table, source_rows[table.name])
            if rows:
                target.execute(table.insert(), rows)

        target_counts: dict[str, int] = {}
        target_hashes: dict[str, str] = {}
        for table in tables:
            rows = _table_rows(target, table)
            target_counts[table.name] = len(rows)
            target_hashes[table.name] = canonical_rows_hash(rows)
        if source_counts != target_counts:
            raise ValueError("target row counts differ before commit")
        if source_hashes != target_hashes:
            raise ValueError("target canonical hashes differ before commit")
        target_transaction.commit()
        source_transaction.rollback()
        _print_summary(
            {
                "status": "MIGRATION_COMMITTED",
                "source_database": EXPECTED_SOURCE_DATABASE,
                "target_database": EXPECTED_TARGET_DATABASE,
                "table_count": len(tables),
                "row_count": sum(source_counts.values()),
                "active_catalog_id": source_catalog[0],
                "vector_index_registry_rows": target_counts["vector_index_registry"],
                "counts_hash": hashlib.sha256(
                    json.dumps(source_counts, sort_keys=True).encode()
                ).hexdigest(),
                "content_hashes_hash": hashlib.sha256(
                    json.dumps(source_hashes, sort_keys=True).encode()
                ).hexdigest(),
            }
        )
        return 0
    except Exception:
        if target_transaction.is_active:
            target_transaction.rollback()
        if source_transaction.is_active:
            source_transaction.rollback()
        raise
    finally:
        source.close()
        target.close()
        source_engine.dispose()
        target_engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--confirmed-snapshot")
    args = parser.parse_args(argv)
    if args.allow_write and args.confirmed_snapshot != CONFIRMED_SNAPSHOT:
        print("CONFIRMED_SNAPSHOT_REQUIRED", file=sys.stderr)
        return 2
    settings = Settings()
    base_url = make_url(settings.database_url.get_secret_value())
    if base_url.database != EXPECTED_SOURCE_DATABASE:
        print("SOURCE_DATABASE_URL_REQUIRED", file=sys.stderr)
        return 2
    try:
        return migrate(base_url=base_url, allow_write=args.allow_write)
    except Exception as exc:
        print(f"MIGRATION_FAILED:{type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["canonical_rows_hash", "main", "migrate", "order_self_referencing_rows"]
