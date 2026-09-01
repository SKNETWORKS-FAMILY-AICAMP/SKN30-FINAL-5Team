from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table

from backend.scripts.migrate_staging_database import (
    canonical_rows_hash,
    order_self_referencing_rows,
)


def test_canonical_rows_hash_is_order_independent() -> None:
    first = [{"id": 2, "value": "B"}, {"id": 1, "value": "A"}]
    second = [{"value": "A", "id": 1}, {"value": "B", "id": 2}]

    assert canonical_rows_hash(first) == canonical_rows_hash(second)


def test_self_referencing_rows_are_parent_first() -> None:
    metadata = MetaData()
    table = Table(
        "nodes",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey("nodes.id"), nullable=True),
        Column("value", String, nullable=False),
    )
    rows = [
        {"id": 3, "parent_id": 2, "value": "leaf"},
        {"id": 1, "parent_id": None, "value": "root"},
        {"id": 2, "parent_id": 1, "value": "child"},
    ]

    ordered = order_self_referencing_rows(table, rows)

    assert [row["id"] for row in ordered] == [1, 2, 3]
