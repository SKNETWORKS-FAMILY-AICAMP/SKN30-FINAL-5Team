"""Atomic V3 persistence and provider-free replay application services."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from backend.app.domain.agents.v3_persistence import (
    V3DecisionPersistenceBundle,
    V3PersistenceError,
    V3PersistenceFailureCode,
    V3ReplayResult,
    V3RootSnapshotPersistence,
)


class V3DecisionPersistenceRepository(Protocol):
    """Stored-bundle access.

    ``get`` and ``get_root_snapshot`` return ``None`` only when no bundle is
    stored. A bundle written under an earlier schema is not "missing": an
    implementation must raise ``V3PersistenceError`` with
    ``UNSUPPORTED_SCHEMA_VERSION`` so callers do not mistake a record they
    cannot read for one that does not exist.
    """

    def add(self, bundle: V3DecisionPersistenceBundle) -> None: ...
    def get(self, decision_execution_id: UUID) -> V3DecisionPersistenceBundle | None: ...
    def get_root_snapshot(
        self, root_decision_execution_id: UUID
    ) -> V3RootSnapshotPersistence | None: ...


class V3DecisionUnitOfWork(Protocol):
    repository: V3DecisionPersistenceRepository

    def __enter__(self) -> V3DecisionUnitOfWork: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool | None: ...


class V3DecisionPersistenceService:
    def __init__(self, unit_of_work: V3DecisionUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    def persist(self, bundle: V3DecisionPersistenceBundle) -> None:
        try:
            with self._unit_of_work as work:
                if work.repository.get(bundle.decision_execution_id) is not None:
                    raise V3PersistenceError(V3PersistenceFailureCode.DUPLICATE_DECISION_EXECUTION)
                work.repository.add(bundle)
        except V3PersistenceError:
            raise
        except Exception as exc:
            raise V3PersistenceError(V3PersistenceFailureCode.TRANSACTION_FAILED) from exc

    def replay(self, decision_execution_id: UUID) -> V3ReplayResult:
        with self._unit_of_work as work:
            stored = work.repository.get(decision_execution_id)
        if stored is None:
            raise V3PersistenceError(V3PersistenceFailureCode.ROOT_SNAPSHOT_MISSING)
        # The schema check belongs to the repository, which sees the stored
        # payload. Once a bundle has been parsed its schema_version is a Literal
        # of the supported version, so re-checking it here could never fail and
        # read as though this path handled older records when it did not.
        try:
            verified = V3DecisionPersistenceBundle.model_validate_json(stored.model_dump_json())
        except ValidationError as exc:
            raise V3PersistenceError(V3PersistenceFailureCode.CANONICAL_HASH_MISMATCH) from exc
        return V3ReplayResult(
            decision_execution_id=verified.decision_execution_id,
            terminal_status_code=verified.terminal_status_code,
            final_plan=verified.final_plan,
            failure_codes=verified.failure_codes,
            graph_version=verified.graph_version,
            policy_version=verified.policy_version,
            prompt_version=verified.prompt_version,
            model_version=verified.model_version,
            catalog_version=verified.catalog_version,
            canonical_result_hash=verified.canonical_result_hash,
        )

    def load_regeneration_root(self, root_decision_execution_id: UUID) -> V3RootSnapshotPersistence:
        with self._unit_of_work as work:
            snapshot = work.repository.get_root_snapshot(root_decision_execution_id)
        if snapshot is None:
            raise V3PersistenceError(V3PersistenceFailureCode.ROOT_SNAPSHOT_MISSING)
        return snapshot


__all__ = [
    "V3DecisionPersistenceRepository",
    "V3DecisionPersistenceService",
    "V3DecisionUnitOfWork",
]
