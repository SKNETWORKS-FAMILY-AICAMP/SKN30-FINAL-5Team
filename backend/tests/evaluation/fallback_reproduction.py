"""D-2 re-read: does the fallback still leave the user with no plan on the real catalog?

D-2 recorded a deterministic fallback that could not fill the requested duration
in 8 of 15 planning cases, and classified it SERVICE while explicitly deferring
the question this module answers: the measurement was taken against an
18-exercise catalog written for tests, and the finding said it had to be re-read
against the catalog that ships.

Nothing here calls a provider. The fallback, the compiler and the integrity
validator are deterministic, so the whole comparison costs nothing and repeats
exactly.

**What is held fixed and what is replaced.** Each case keeps the constraint that
drives the finding -- requested duration, goal, allowed locations and, above all,
the recovery ceiling -- and only the catalog underneath changes. The exclusion
list cannot carry over, because a case names synthetic exercises that do not
exist in the shipped catalog. Exclusions are therefore reapplied *by count*:
the same number of eligible candidates is removed, taken from the front of the
goal-matched ordering, which is the pessimistic choice because a safety
exclusion tends to remove exactly the movements most relevant to the goal.

**What this cannot reproduce.** Which candidates Qdrant would rank into the
pool. Eligibility is PostgreSQL's and is faithful here; the ordering is not,
because there is no index to ask. Each case is therefore replayed over several
deterministic slices of the eligible set, and the result reports how many of
them produced a plan. A conclusion that held for only one slice is reported as
exactly that.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Final
from uuid import UUID

from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExercisePoolSnapshot,
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    RetrievalModeCode,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_compiler import CompiledPlan, compile_plan
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope
from backend.app.domain.agents.v3_duration import pool_size_for_duration
from backend.app.domain.agents.v3_orchestration import FallbackRequest
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationContext,
    IntegrityValidationStatusCode,
    validate_plan_integrity,
)
from backend.app.domain.rules.training_level import is_exercise_allowed_for_user
from backend.app.integrations.langgraph.demo_runtime import V3DemoRuntimeVersions
from backend.app.integrations.langgraph.fallback import DeterministicGraphFallbackProvider
from backend.app.integrations.qdrant.snapshot_loader import QdrantExercisePoolSnapshotLoader
from backend.tests.evaluation.dataset import EvaluationCase
from backend.tests.evaluation.production_catalog import (
    PRODUCTION_CATALOG_VERSION,
    load_production_records,
)
from backend.tests.evaluation.scenario import FIXED_TIME, build_envelope, build_scenario

# How many deterministic slices of the eligible set each case is replayed over.
# One slice would let a lucky ordering decide the finding.
DEFAULT_SLICE_COUNT: Final = 5

# The experience level the replay assumes. BEGINNER is the product's stated
# audience and the stricter gate: it admits fewer exercises than INTERMEDIATE.
DEFAULT_EXPERIENCE_LEVEL: Final = "BEGINNER"

_VERSIONS: Final = V3DemoRuntimeVersions()


@dataclass(frozen=True, slots=True)
class ReplayOutcome:
    """One case, one catalog, one pool slice."""

    case_id: str
    category: str
    catalog_label: str
    slice_index: int
    pool_size: int
    main_candidates: int
    produced_plan: bool
    failure_reason: str | None
    estimated_duration_seconds: int | None
    requested_duration_seconds: int

    def to_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "catalog": self.catalog_label,
            "slice": self.slice_index,
            "pool_size": self.pool_size,
            "main_candidates": self.main_candidates,
            "produced_plan": self.produced_plan,
            "failure_reason": self.failure_reason,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "requested_duration_seconds": self.requested_duration_seconds,
        }


@dataclass
class CatalogReplay:
    """Every outcome for one catalog, and the rates D-2 is stated in."""

    catalog_label: str
    outcomes: list[ReplayOutcome] = field(default_factory=list)

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.case_id for item in self.outcomes))

    @property
    def slice_success_rate(self) -> float | None:
        if not self.outcomes:
            return None
        return round(sum(1 for item in self.outcomes if item.produced_plan) / len(self.outcomes), 4)

    def cases_by_reliability(self) -> dict[str, list[str]]:
        """Split cases into always / sometimes / never produced a plan.

        The middle bucket is the one D-2 is about: an intermittent failure is
        what a user experiences as "sometimes I get nothing", and averaging it
        away into a single rate is what makes such a finding easy to dismiss.
        """

        buckets: dict[str, list[str]] = {"always": [], "sometimes": [], "never": []}
        for case_id in self.case_ids:
            rows = [item for item in self.outcomes if item.case_id == case_id]
            produced = sum(1 for item in rows if item.produced_plan)
            if produced == len(rows):
                buckets["always"].append(case_id)
            elif produced == 0:
                buckets["never"].append(case_id)
            else:
                buckets["sometimes"].append(case_id)
        return buckets

    @property
    def case_failure_rate(self) -> float | None:
        """Share of cases that failed on at least one slice."""

        if not self.case_ids:
            return None
        buckets = self.cases_by_reliability()
        failing = len(buckets["sometimes"]) + len(buckets["never"])
        return round(failing / len(self.case_ids), 4)

    def to_json(self) -> dict[str, object]:
        return {
            "catalog": self.catalog_label,
            "cases": len(self.case_ids),
            "replays": len(self.outcomes),
            "slice_success_rate": self.slice_success_rate,
            "case_failure_rate": self.case_failure_rate,
            "cases_by_reliability": self.cases_by_reliability(),
            "outcomes": [item.to_json() for item in self.outcomes],
        }


def _eligible(
    records: tuple[ExercisePoolExerciseRecord, ...],
    *,
    envelope: ConstraintEnvelope,
    experience_level_code: str,
) -> tuple[ExercisePoolExerciseRecord, ...]:
    """The deterministic pre-retrieval gates, in production's own order.

    Mirrors `_eligible_pool_exercises` followed by the goal preference in
    `PostgreSQLV3ExercisePoolSource.load_eligible`. Equipment is deliberately
    not a gate (2026-08-27 approval).
    """

    allowed_locations = set(envelope.allowed_location_codes)
    excluded = set(envelope.excluded_exercise_ids)
    eligible = tuple(
        item
        for item in records
        if item.exercise_id not in excluded
        and is_exercise_allowed_for_user(
            exercise_difficulty_code=item.difficulty_code,
            user_experience_level_code=experience_level_code,
        )
        and bool(set(item.location_codes) & allowed_locations)
    )
    goal_matched = tuple(item for item in eligible if envelope.primary_goal_code in item.goal_codes)
    return goal_matched or eligible


def _compose_pool(
    eligible: tuple[ExercisePoolExerciseRecord, ...],
    *,
    envelope: ConstraintEnvelope,
    requested_limit: int,
    ranking_offset: int,
) -> tuple[ExercisePoolExerciseRecord, ...]:
    """Compose the pool the way the shipped snapshot loader composes it.

    The selection is `QdrantExercisePoolSnapshotLoader._selected_ids`, called
    directly, so the phase and role reservation that production applies on top
    of the ranking applies here too. A first version of this replay took a plain
    window of the ranked list instead, and every case then failed on the slices
    that happened to be MAIN-heavy -- a harness artefact, because the reserved
    warmup and cooldown candidates were never taken.

    Only the ranking is simulated, by rotating the eligible list; that is the
    one input there is no index to ask for.
    """

    if not eligible:
        return ()
    rotation = ranking_offset % len(eligible)
    ranked = eligible[rotation:] + eligible[:rotation]
    request = ExerciseRetrievalRequest(
        catalog_version=envelope.catalog_version,
        constraint_envelope_hash=envelope.envelope_hash,
        eligible_exercise_ids=tuple(sorted((item.exercise_id for item in eligible), key=str)),
        mandatory_exercise_ids=envelope.mandatory_exercise_ids,
        normalized_query_codes=(envelope.primary_goal_code,),
        retrieval_mode=RetrievalModeCode.VECTOR_RANKED,
        requested_limit=requested_limit,
    )
    result = ExerciseRetrievalResult(
        ranked_exercise_ids=tuple(item.exercise_id for item in ranked),
        # A successful retrieval must score every ranked id. The values carry
        # no information here -- the selection reads the order, never the
        # score -- so they are a strictly descending series consistent with it.
        similarity_scores=tuple(
            round(1.0 - index / (len(ranked) + 1), 6) for index in range(len(ranked))
        ),
        collection_name="eval-production-replay-v1",
        vector_index_version="eval-production-replay-v1",
        embedding_model_version="eval-production-replay-v1",
        query_hash=envelope.envelope_hash,
        retrieval_status_code=RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
        fallback_used=False,
    )
    selected = QdrantExercisePoolSnapshotLoader._selected_ids(request, result, eligible)
    by_id = {item.exercise_id: item for item in eligible}
    # Keep the ranking order the loader keeps; the snapshot sorts separately.
    return tuple(by_id[item] for item in selected if item in by_id)


def _production_envelope(
    case: EvaluationCase,
    *,
    eligible_for_exclusion: tuple[ExercisePoolExerciseRecord, ...],
    exclusion_count: int,
) -> ConstraintEnvelope:
    """Rebuild the case's envelope against production exercise identities.

    Duration, goal, locations and the recovery ceiling are the case's own. Only
    the exclusion and mandatory lists are re-pointed, because the synthetic ids
    they name do not exist in the shipped catalog.
    """

    source = build_envelope(case)
    excluded: tuple[UUID, ...] = tuple(
        sorted(
            (item.exercise_id for item in eligible_for_exclusion[:exclusion_count]),
            key=str,
        )
    )
    return ConstraintEnvelope.create(
        requested_duration_minutes=source.requested_duration_minutes,
        primary_goal_code=source.primary_goal_code,
        allowed_location_codes=source.allowed_location_codes,
        allowed_equipment_codes=source.allowed_equipment_codes,
        excluded_exercise_ids=excluded,
        # Mandatory exercises are dropped rather than re-pointed: forcing an
        # arbitrary production exercise into the plan would be inventing a
        # constraint the case never made.
        mandatory_exercise_ids=(),
        recovery_ceiling=source.recovery_ceiling,
        plan_generation_allowed=source.plan_generation_allowed,
        safety_required_action_code=source.safety_required_action_code,
        policy_version=source.policy_version,
        catalog_version=PRODUCTION_CATALOG_VERSION,
        safety_rule_version=source.safety_rule_version,
    )


def _snapshot(
    envelope: ConstraintEnvelope, records: tuple[ExercisePoolExerciseRecord, ...]
) -> ExercisePoolSnapshot:
    from backend.tests.evaluation.scenario import _retrieval_metadata

    # The snapshot stores exercises in canonical UUID order and keeps the
    # ranking separately, exactly as `revalidate` hands them over. The window's
    # own order is the ranking, and the fallback reads it from there
    # (`fallback._ordered_ids`), so it must not be lost in the sort.
    return ExercisePoolSnapshot.create(
        catalog_version=envelope.catalog_version,
        constraint_envelope_hash=envelope.envelope_hash,
        exercises=tuple(sorted(records, key=lambda item: str(item.exercise_id))),
        mandatory_exercise_ids=envelope.mandatory_exercise_ids,
        vector_ranked_exercise_ids=tuple(item.exercise_id for item in records),
        retrieval_metadata=_retrieval_metadata(retrieval_failed=False),
        created_at=FIXED_TIME,
    )


def _run_fallback(
    *, envelope: ConstraintEnvelope, pool: ExercisePoolSnapshot
) -> tuple[CompiledPlan | None, str | None]:
    """The shipped fallback, compiler and validator, in the graph's own order."""

    provider = DeterministicGraphFallbackProvider(fallback_version=_VERSIONS.fallback_version)
    request = FallbackRequest.create(
        constraint_envelope=envelope,
        exercise_pool=pool,
        fallback_version=_VERSIONS.fallback_version,
    )
    spec = provider.generate(request)
    if spec is None:
        return None, "V3_FALLBACK_PLAN_UNAVAILABLE"
    try:
        compiled = compile_plan(
            spec,
            envelope=envelope,
            pool=pool,
            compiler_version=_VERSIONS.compiler_version,
        )
    except Exception:  # noqa: BLE001 -- mirrors nodes.compile_plan
        return None, "V3_COMPILATION_FAILED"
    result = validate_plan_integrity(
        compiled,
        envelope=envelope,
        pool=pool,
        repair_attempt=0,
        validator_version=_VERSIONS.validator_version,
        context=IntegrityValidationContext(fallback_plan_validation=True),
    )
    if result.status_code is not IntegrityValidationStatusCode.PASS:
        codes = ",".join(item.code.value for item in result.violations)
        return None, codes or "INTEGRITY_VALIDATION_FAILED"
    return compiled, None


def replay_production(
    cases: tuple[EvaluationCase, ...],
    *,
    slice_count: int = DEFAULT_SLICE_COUNT,
    experience_level_code: str = DEFAULT_EXPERIENCE_LEVEL,
    exclusion_multiplier: int = 1,
) -> CatalogReplay:
    """Replay every case against the shipped catalog, over several orderings.

    `exclusion_multiplier` widens each case's safety exclusion beyond what the
    case declared. D-2 named shrinking MAIN candidates as one of its two drivers,
    so a replay that only reproduces the declared exclusions has not yet pushed
    on that driver.
    """

    records = load_production_records(experience_level_code)
    label = PRODUCTION_CATALOG_VERSION
    if exclusion_multiplier != 1:
        label = f"{label} (exclusions x{exclusion_multiplier})"
    replay = CatalogReplay(catalog_label=label)

    for case in cases:
        source = build_envelope(case)
        exclusion_count = len(source.excluded_exercise_ids) * exclusion_multiplier
        # Sizing needs an envelope, and the envelope needs the exclusions, so
        # eligibility is computed once with no exclusions to choose which
        # candidates the case's exclusion count removes.
        unfiltered = _eligible(
            records, envelope=source, experience_level_code=experience_level_code
        )
        envelope = _production_envelope(
            case, eligible_for_exclusion=unfiltered, exclusion_count=exclusion_count
        )
        eligible = _eligible(
            records, envelope=envelope, experience_level_code=experience_level_code
        )
        if not eligible:
            replay.outcomes.append(
                ReplayOutcome(
                    case_id=case.case_id,
                    category=case.category.value,
                    catalog_label=replay.catalog_label,
                    slice_index=0,
                    pool_size=0,
                    main_candidates=0,
                    produced_plan=False,
                    failure_reason="NO_ELIGIBLE_EXERCISE",
                    estimated_duration_seconds=None,
                    requested_duration_seconds=envelope.requested_duration_minutes * 60,
                )
            )
            continue

        size = pool_size_for_duration(
            requested_duration_minutes=envelope.requested_duration_minutes,
            exercises=eligible,
        )
        for index in range(slice_count):
            # Spread the windows across the eligible list rather than stepping
            # by one, so the slices are genuinely different candidate sets.
            offset = (index * max(1, len(eligible) // slice_count)) if slice_count else 0
            window = _compose_pool(
                eligible,
                envelope=envelope,
                requested_limit=size,
                ranking_offset=offset,
            )
            pool = _snapshot(envelope, window)
            compiled, reason = _run_fallback(envelope=envelope, pool=pool)
            replay.outcomes.append(
                ReplayOutcome(
                    case_id=case.case_id,
                    category=case.category.value,
                    catalog_label=replay.catalog_label,
                    slice_index=index,
                    pool_size=len(window),
                    main_candidates=sum(1 for item in window if "MAIN" in item.phase_codes),
                    produced_plan=compiled is not None,
                    failure_reason=reason,
                    estimated_duration_seconds=(
                        compiled.estimated_duration_seconds if compiled else None
                    ),
                    requested_duration_seconds=envelope.requested_duration_minutes * 60,
                )
            )
    return replay


def replay_synthetic(cases: tuple[EvaluationCase, ...]) -> CatalogReplay:
    """Replay the same cases against the harness catalog D-2 was measured on.

    One slice per case: the synthetic pool is the case's own, so there is no
    ranking to vary.
    """

    replay = CatalogReplay(catalog_label="eval-synthetic-catalog-v1")
    for case in cases:
        scenario = build_scenario(case)
        envelope = scenario.constraint_envelope
        pool = scenario.exercise_pool
        compiled, reason = _run_fallback(envelope=envelope, pool=pool)
        replay.outcomes.append(
            ReplayOutcome(
                case_id=case.case_id,
                category=case.category.value,
                catalog_label=replay.catalog_label,
                slice_index=0,
                pool_size=len(pool.exercises),
                main_candidates=sum(1 for item in pool.exercises if "MAIN" in item.phase_codes),
                produced_plan=compiled is not None,
                failure_reason=reason,
                estimated_duration_seconds=(
                    compiled.estimated_duration_seconds if compiled else None
                ),
                requested_duration_seconds=envelope.requested_duration_minutes * 60,
            )
        )
    return replay


def replay_synthetic_with_production_composition(
    cases: tuple[EvaluationCase, ...],
    *,
    slice_count: int = DEFAULT_SLICE_COUNT,
) -> CatalogReplay:
    """Hold the catalog fixed and change only how the pool is composed.

    Without this arm the comparison cannot say *why* the two catalogs differ.
    The harness declares each case's pool directly, so it never applies the
    phase and role reservation `QdrantExercisePoolSnapshotLoader._selected_ids`
    applies in production; this arm puts the synthetic catalog through that
    reservation so the catalog's size and the composition rule can be told
    apart.
    """

    from backend.tests.evaluation import catalog as synthetic_catalog

    records = tuple(
        sorted(synthetic_catalog.BY_ID.values(), key=lambda item: str(item.exercise_id))
    )
    replay = CatalogReplay(catalog_label="eval-synthetic-catalog-v1 (production composition)")
    for case in cases:
        envelope = build_envelope(case)
        excluded = set(envelope.excluded_exercise_ids)
        eligible = tuple(item for item in records if item.exercise_id not in excluded)
        if not eligible:
            continue
        size = pool_size_for_duration(
            requested_duration_minutes=envelope.requested_duration_minutes,
            exercises=eligible,
        )
        for index in range(slice_count):
            offset = (index * max(1, len(eligible) // slice_count)) if slice_count else 0
            window = _compose_pool(
                eligible,
                envelope=envelope,
                requested_limit=size,
                ranking_offset=offset,
            )
            compiled, reason = _run_fallback(envelope=envelope, pool=_snapshot(envelope, window))
            replay.outcomes.append(
                ReplayOutcome(
                    case_id=case.case_id,
                    category=case.category.value,
                    catalog_label=replay.catalog_label,
                    slice_index=index,
                    pool_size=len(window),
                    main_candidates=sum(1 for item in window if "MAIN" in item.phase_codes),
                    produced_plan=compiled is not None,
                    failure_reason=reason,
                    estimated_duration_seconds=(
                        compiled.estimated_duration_seconds if compiled else None
                    ),
                    requested_duration_seconds=envelope.requested_duration_minutes * 60,
                )
            )
    return replay


def report(production: CatalogReplay, synthetic: CatalogReplay) -> dict[str, object]:
    return {
        "finding": "D-2",
        "question": (
            "Does the deterministic fallback still fail to produce a plan when the "
            "shipped catalog replaces the harness catalog?"
        ),
        "llm_calls": 0,
        "synthetic": synthetic.to_json(),
        "production": production.to_json(),
    }


def dumps(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


__all__ = [
    "DEFAULT_EXPERIENCE_LEVEL",
    "DEFAULT_SLICE_COUNT",
    "CatalogReplay",
    "ReplayOutcome",
    "dumps",
    "replay_production",
    "replay_synthetic",
    "replay_synthetic_with_production_composition",
    "report",
]
