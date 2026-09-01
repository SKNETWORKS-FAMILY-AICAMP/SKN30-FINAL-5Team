"""Database-backed identity provider for a shared V3 demo runtime."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.decision import DecisionRun
from backend.app.db.models.v3_decision import DecisionConstraintEnvelopeRecord
from backend.app.domain.agents.v3_contracts import RegenerationContext
from backend.app.domain.agents.v3_persistence import V3RootSnapshotPersistence
from backend.app.integrations.langgraph.demo_runtime import (
    V3DemoDecisionIdentity,
    V3DemoRuntimeError,
)


class SqlAlchemyV3DemoIdentityProvider:
    """Resolve lineage from persisted root artifacts without graph identifiers."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def initial(self) -> V3DemoDecisionIdentity:
        decision_id = uuid4()
        return V3DemoDecisionIdentity(decision_id, decision_id)

    def regeneration(
        self,
        root_snapshot: V3RootSnapshotPersistence,
        regeneration_context: RegenerationContext,
    ) -> V3DemoDecisionIdentity:
        with self._session_factory() as session:
            envelope = session.scalar(
                select(DecisionConstraintEnvelopeRecord).where(
                    DecisionConstraintEnvelopeRecord.envelope_hash
                    == root_snapshot.constraint_envelope.envelope_hash
                )
            )
            if envelope is None:
                raise V3DemoRuntimeError("V3_REGENERATION_LINEAGE_REQUIRED")
            parent = session.scalar(
                select(DecisionRun).where(
                    DecisionRun.root_decision_run_id == envelope.root_decision_run_id,
                    DecisionRun.regeneration_sequence
                    == regeneration_context.generation_sequence - 1,
                    DecisionRun.status_code == "COMPLETED",
                )
            )
            if parent is None:
                raise V3DemoRuntimeError("V3_REGENERATION_LINEAGE_REQUIRED")
            return V3DemoDecisionIdentity(
                decision_execution_id=uuid4(),
                root_decision_execution_id=envelope.root_decision_run_id,
                parent_decision_execution_id=parent.id,
            )


__all__ = ["SqlAlchemyV3DemoIdentityProvider"]
