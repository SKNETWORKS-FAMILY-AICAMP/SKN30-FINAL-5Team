"""PostgreSQL registry for rebuildable Qdrant exercise indexes."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class VectorIndexRegistry(Base):
    __tablename__ = "vector_index_registry"
    __table_args__ = (
        CheckConstraint(
            "status_code IN ('BUILDING','READY','ACTIVE','STALE','FAILED','RETIRED')",
            name="ck_vector_index_registry_status",
        ),
        CheckConstraint("vector_dimension > 0", name="ck_vector_index_registry_dimension"),
        CheckConstraint(
            "distance_metric_code IN ('COSINE','DOT','EUCLID','MANHATTAN')",
            name="ck_vector_index_registry_distance",
        ),
        CheckConstraint(
            "source_manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_vector_index_registry_source_hash",
        ),
        CheckConstraint(
            "build_hash ~ '^[0-9a-f]{64}$'",
            name="ck_vector_index_registry_build_hash",
        ),
        CheckConstraint(
            "status_code NOT IN ('READY','ACTIVE') OR built_at IS NOT NULL",
            name="ck_vector_index_registry_built_at",
        ),
        CheckConstraint(
            "status_code <> 'ACTIVE' OR activated_at IS NOT NULL",
            name="ck_vector_index_registry_activated_at",
        ),
        UniqueConstraint("vector_index_version", name="uq_vector_index_registry_version"),
        Index(
            "ix_vector_index_registry_catalog_status",
            "catalog_version_id",
            "status_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    catalog_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("catalog_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    collection_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vector_index_version: Mapped[str] = mapped_column(String(128), nullable=False)
    source_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_input_schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    distance_metric_code: Mapped[str] = mapped_column(String(16), nullable=False)
    vector_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    build_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[str] = mapped_column(String(16), nullable=False)
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["VectorIndexRegistry"]
