"""Turn one evaluation case into the frozen graph boundary objects.

The V3 graph takes a `ConstraintEnvelope` and an `ExercisePoolSnapshot` and
nothing else -- no database handle, no identifiers (`langgraph/state.py`).  That
is what lets this harness exercise the real graph offline, so this module is the
whole bridge between a JSON case and a runnable input.

Envelope construction is itself a check.  A case with a missing or malformed
input is expected to fail here, exactly as the application would fail before
reaching the graph, so the failure is captured as a structured outcome rather
than allowed to escape as an exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from pydantic import ValidationError

from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExercisePoolSnapshot,
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    RetrievalFailureCode,
    RetrievalMetadata,
    RetrievalModeCode,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, RecoveryCeiling
from backend.app.domain.agents.v3_duration import pool_size_for_duration
from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.app.integrations.qdrant.snapshot_loader import QdrantExercisePoolSnapshotLoader
from backend.tests.evaluation.catalog_source import CatalogSource
from backend.tests.evaluation.dataset import (
    FIXED_TIME,
    EvaluationCase,
    RequiredActionExpectation,
)

POLICY_VERSION: Final = "eval-decision-policy-v1"
SAFETY_RULE_VERSION: Final = "eval-safety-rules-v1"
RECOVERY_POLICY_VERSION: Final = "eval-recovery-policy-v1"
QUERY_HASH: Final = "0" * 64

_ACTION_BY_EXPECTATION: Final[dict[RequiredActionExpectation, SafetyRequiredActionCode | None]] = {
    RequiredActionExpectation.NONE: None,
    RequiredActionExpectation.REST: SafetyRequiredActionCode.REST,
    RequiredActionExpectation.STOP_AND_SEEK_HELP: SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
}


class ScenarioBuildError(ValueError):
    """Raised with a stable code when a case cannot produce a graph input."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class Scenario:
    """A case rendered as the exact objects the graph consumes."""

    case: EvaluationCase
    constraint_envelope: ConstraintEnvelope
    exercise_pool: ExercisePoolSnapshot

    @property
    def excluded_exercise_ids(self) -> frozenset[str]:
        return frozenset(str(value) for value in self.constraint_envelope.excluded_exercise_ids)


def build_envelope(case: EvaluationCase) -> ConstraintEnvelope:
    """Build the frozen constraint envelope a case describes.

    Raises `ScenarioBuildError` with a stable code when the case deliberately
    omits or corrupts a required input; that outcome is the assertion for the
    `missing_input` and `invalid_input` categories.
    """

    source: CatalogSource = case.catalog
    expected = case.expected_constraints
    duration = expected.requested_duration_minutes
    if duration is None:
        raise ScenarioBuildError("REQUIRED_INPUT_MISSING_DURATION")
    if expected.primary_goal_code is None:
        raise ScenarioBuildError("REQUIRED_INPUT_MISSING_GOAL")
    if not expected.allowed_location_codes:
        raise ScenarioBuildError("REQUIRED_INPUT_MISSING_LOCATION")

    action_code = _ACTION_BY_EXPECTATION[case.expected_safety_result.required_action_code]
    try:
        return ConstraintEnvelope.create(
            requested_duration_minutes=duration,
            primary_goal_code=expected.primary_goal_code,
            allowed_location_codes=tuple(sorted(set(expected.allowed_location_codes))),
            allowed_equipment_codes=tuple(sorted(set(expected.allowed_equipment_codes))),
            excluded_exercise_ids=source.ids_for(expected.excluded_exercise_codes),
            mandatory_exercise_ids=source.ids_for(expected.mandatory_exercise_codes),
            recovery_ceiling=RecoveryCeiling(
                policy_version=RECOVERY_POLICY_VERSION,
                allowed_intensity_codes=tuple(sorted(set(expected.allowed_intensity_codes))),
                allowed_load_codes=tuple(sorted(set(expected.allowed_load_codes))),
                maximum_sets_per_exercise=expected.maximum_sets_per_exercise,
                maximum_repetitions_per_set=expected.maximum_repetitions_per_set,
                maximum_work_seconds_per_set=None,
                minimum_rest_seconds_between_sets=expected.minimum_rest_seconds_between_sets,
            ),
            plan_generation_allowed=expected.plan_generation_allowed,
            safety_required_action_code=action_code,
            policy_version=POLICY_VERSION,
            catalog_version=source.catalog_version,
            safety_rule_version=SAFETY_RULE_VERSION,
        )
    except (ValidationError, ValueError) as error:
        raise ScenarioBuildError("INVALID_INPUT_ENVELOPE_REJECTED") from error


def _retrieval_metadata(*, retrieval_failed: bool) -> RetrievalMetadata:
    """Describe the retrieval that produced the pool.

    A failed vector search is not a failed pool: PostgreSQL already established
    eligibility and the deterministic fallback supplies the ordering, so the
    metadata records a degraded ranking rather than a missing candidate set.
    """

    if not retrieval_failed:
        return RetrievalMetadata(
            collection_name="eval-exercise-catalog-v1",
            vector_index_version="eval-vector-index-v1",
            embedding_model_version="eval-embedding-v1",
            query_hash=QUERY_HASH,
            retrieval_status_code=RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
            deterministic_pool_fallback_used=False,
        )
    return RetrievalMetadata(
        collection_name="eval-exercise-catalog-v1",
        vector_index_version="eval-vector-index-v1",
        embedding_model_version="eval-embedding-v1",
        query_hash=QUERY_HASH,
        retrieval_status_code=RetrievalStatusCode.VECTOR_SEARCH_TIMEOUT,
        retrieval_failure_codes=(RetrievalFailureCode.VECTOR_SEARCH_TIMEOUT,),
        deterministic_fallback_version="eval-retrieval-fallback-v1",
        deterministic_pool_fallback_used=True,
    )


def _reserved_ranking(
    *,
    envelope: ConstraintEnvelope,
    records: tuple[ExercisePoolExerciseRecord, ...],
    ranked: tuple[UUID, ...],
) -> tuple[UUID, ...]:
    """Select and order a case's pool the way the shipped snapshot loader does.

    Ranking alone can hand the agents a pool with no cooldown candidate in it,
    so production reserves a few candidates per phase and role before spending
    the rest on rank (`QdrantExercisePoolSnapshotLoader._selected_ids`). This
    harness declares each case's eligible set directly and used to skip that
    step, which made the deterministic fallback fail on pool shapes production
    never produces: D-2 was reported as a service defect on that basis and had
    to be retracted (`docs/test/TEST_RESULTS.md` 12절).

    The selection is production's own function rather than a copy of it, and it
    decides pool membership as well as order. On the synthetic catalog the two
    are nearly the same set -- a case declares about fifteen exercises and the
    loader would size the pool at fifteen -- so this mostly reorders. On the
    deployed catalog it does real work: 157 eligible beginner exercises become
    the roughly fifteen a live request would carry.
    """

    request = ExerciseRetrievalRequest(
        catalog_version=envelope.catalog_version,
        constraint_envelope_hash=envelope.envelope_hash,
        eligible_exercise_ids=tuple(sorted((item.exercise_id for item in records), key=str)),
        mandatory_exercise_ids=envelope.mandatory_exercise_ids,
        normalized_query_codes=(envelope.primary_goal_code,),
        retrieval_mode=RetrievalModeCode.VECTOR_RANKED,
        requested_limit=pool_size_for_duration(
            requested_duration_minutes=envelope.requested_duration_minutes,
            exercises=records,
        ),
    )
    # With no declared ranking this is the deterministic retrieval state, which
    # still goes through the same selection; only the stored ranking differs.
    succeeded = bool(ranked)
    result = ExerciseRetrievalResult(
        ranked_exercise_ids=ranked,
        # Scores carry no information here; the selection reads order only.
        similarity_scores=tuple(
            round(1.0 - index / (len(ranked) + 1), 6) for index in range(len(ranked))
        ),
        collection_name="eval-exercise-catalog-v1" if succeeded else None,
        vector_index_version="eval-vector-index-v1" if succeeded else None,
        embedding_model_version="eval-embedding-v1" if succeeded else None,
        query_hash=QUERY_HASH,
        retrieval_status_code=(
            RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
            if succeeded
            else RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE
        ),
        fallback_used=not succeeded,
    )
    carried = {item.exercise_id for item in records}
    selected = QdrantExercisePoolSnapshotLoader._selected_ids(request, result, records)
    # A snapshot may only name ranked exercises it actually carries.
    return tuple(item for item in selected if item in carried)


def build_pool(case: EvaluationCase, envelope: ConstraintEnvelope) -> ExercisePoolSnapshot:
    """Build the pool snapshot the agents receive.

    Eligibility comes from the case, mirroring production where PostgreSQL owns
    it; the vector ranking only reorders what is already eligible
    (`qdrant/snapshot_loader.py`), through the phase and role reservation that
    `_reserved_ranking` applies.
    """

    source = case.catalog
    eligible = source.records_for(case.pool.exercise_codes)
    retrieval_failed = case.pool.retrieval_failed
    declared = source.ids_for(case.pool.vector_ranked_exercise_codes)

    # Production stores the *selection*, not the whole eligible set: the loader
    # sizes a pool from the requested duration and reserves phase and role
    # coverage before spending the rest on rank, then revalidates only those ids
    # into the snapshot. A case declares eligibility, which is PostgreSQL's job;
    # the selection is the loader's, and the deployed catalog makes the
    # difference concrete -- 157 eligible beginner exercises against a pool the
    # service would size at roughly fifteen.
    selected = _reserved_ranking(envelope=envelope, records=eligible, ranked=declared)
    by_id = {item.exercise_id: item for item in eligible}
    records = tuple(sorted((by_id[item] for item in selected), key=lambda r: str(r.exercise_id)))

    # A case that declares no ranking is not a successful vector retrieval: the
    # contract refuses that combination, and production reaches the same state
    # through `deterministic_retrieval_fallback`, which stores no ranking on the
    # snapshot either.
    ranked: tuple[UUID, ...] = () if retrieval_failed or not declared else selected
    try:
        return ExercisePoolSnapshot.create(
            catalog_version=source.catalog_version,
            constraint_envelope_hash=envelope.envelope_hash,
            exercises=records,
            mandatory_exercise_ids=source.ids_for(
                case.expected_constraints.mandatory_exercise_codes
            ),
            vector_ranked_exercise_ids=ranked,
            retrieval_metadata=_retrieval_metadata(retrieval_failed=retrieval_failed),
            created_at=FIXED_TIME,
        )
    except (ValidationError, ValueError) as error:
        raise ScenarioBuildError("INVALID_INPUT_POOL_REJECTED") from error


def build_scenario(case: EvaluationCase) -> Scenario:
    """Render one case as graph input, or raise `ScenarioBuildError`."""

    envelope = build_envelope(case)
    return Scenario(
        case=case,
        constraint_envelope=envelope,
        exercise_pool=build_pool(case, envelope),
    )


__all__ = [
    "POLICY_VERSION",
    "RECOVERY_POLICY_VERSION",
    "SAFETY_RULE_VERSION",
    "Scenario",
    "ScenarioBuildError",
    "build_envelope",
    "build_pool",
    "build_scenario",
]
