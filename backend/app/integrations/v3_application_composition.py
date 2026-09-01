"""Authoritative V3 application composition kept outside API and domain layers."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db.models.catalog import CatalogVersion, ExerciseSafetyRule
from backend.app.db.session import DatabaseManager
from backend.app.domain.rules.safety import SAFETY_ENGINE_VERSION
from backend.app.integrations.qdrant.snapshot_loader import QdrantExercisePoolSnapshotLoader
from backend.app.integrations.v3_demo_factory import V3DemoRuntimePort
from backend.app.integrations.v3_demo_retrieval import DatabaseBoundQdrantExerciseRetriever
from backend.app.modules.decisions.codes import DECISION_POLICY_VERSION
from backend.app.modules.decisions.execution_profile import DecisionCreationServicePort
from backend.app.modules.decisions.v3_application import (
    DeterministicV3SafetyPolicyAdapter,
    FailClosedV3ApplicationFallback,
    PostgreSQLV3ExercisePoolSource,
    SqlAlchemyV3CreationUnitOfWork,
    SqlAlchemyV3RegenerationUnitOfWork,
    V3DecisionResponseProjector,
)
from backend.app.modules.decisions.v3_creation import (
    V3CreationUnitOfWork,
    V3InitialCreationService,
)
from backend.app.modules.decisions.v3_regeneration import (
    V3RegenerationService,
    V3RegenerationServicePort,
    V3RegenerationUnitOfWork,
    V3RegenerationVersionSnapshot,
)


class V3ApplicationCompositionError(RuntimeError):
    pass


def _current_versions(database: DatabaseManager) -> V3RegenerationVersionSnapshot:
    with database.new_session() as session:
        catalog = session.scalar(
            select(CatalogVersion)
            .where(
                CatalogVersion.status_code == "ACTIVE",
                CatalogVersion.activated_at.is_not(None),
            )
            .order_by(CatalogVersion.activated_at.desc())
            .limit(1)
        )
        if catalog is None:
            raise V3ApplicationCompositionError("V3_ACTIVE_CATALOG_UNAVAILABLE")
        safety_version = session.scalar(
            select(ExerciseSafetyRule.rule_set_version_code)
            .where(ExerciseSafetyRule.catalog_version_id == catalog.id)
            .order_by(ExerciseSafetyRule.rule_set_version_code.desc())
            .limit(1)
        )
        return V3RegenerationVersionSnapshot(
            catalog_version=catalog.version_code,
            policy_version=DECISION_POLICY_VERSION,
            safety_rule_version=safety_version or SAFETY_ENGINE_VERSION,
        )


def compose_v3_application_services(
    settings: Settings,
    database: DatabaseManager,
    runtime: object,
) -> tuple[DecisionCreationServicePort, V3RegenerationServicePort]:
    if not callable(getattr(runtime, "create", None)) or not callable(
        getattr(runtime, "regenerate", None)
    ):
        raise V3ApplicationCompositionError("V3_RUNTIME_CONTRACT_UNAVAILABLE")
    graph_runtime = cast(V3DemoRuntimePort, runtime)
    catalog = PostgreSQLV3ExercisePoolSource()
    retriever = DatabaseBoundQdrantExerciseRetriever(settings, database.new_session)
    pool_loader = QdrantExercisePoolSnapshotLoader(catalog=catalog, retriever=retriever)
    versions = _current_versions(database)
    creation = V3InitialCreationService(
        unit_of_work_factory=cast(
            Callable[[Session], V3CreationUnitOfWork], SqlAlchemyV3CreationUnitOfWork
        ),
        safety_policy=DeterministicV3SafetyPolicyAdapter(),
        exercise_pool_loader=pool_loader,
        graph_runtime=graph_runtime,
        fallback=FailClosedV3ApplicationFallback(),
        projector=V3DecisionResponseProjector(),
    )
    regeneration = V3RegenerationService(
        unit_of_work=cast(
            V3RegenerationUnitOfWork,
            SqlAlchemyV3RegenerationUnitOfWork(database.new_session, current_versions=versions),
        ),
        graph_runtime=graph_runtime,
        current_versions=versions,
        enabled=(
            settings.v3_execution_profile == "DEMO"
            or (
                settings.v3_execution_profile == "PRODUCTION"
                and settings.v3_production_promotion_approved
            )
        ),
    )
    return creation, regeneration


__all__ = [
    "V3ApplicationCompositionError",
    "compose_v3_application_services",
]
