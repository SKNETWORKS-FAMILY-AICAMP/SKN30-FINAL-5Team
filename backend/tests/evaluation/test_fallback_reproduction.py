"""Pin the D-2 re-read, including the harness bug the first attempt had.

The conclusion -- that D-2 was a property of the harness rather than of the
service -- is only worth anything if the replay stays faithful. These tests hold
the two things that made it faithful: it uses production's own pool composition,
and the synthetic arm still reproduces the original failure, so the comparison
has something real on both sides.

Everything here is deterministic and costs nothing.
"""

from __future__ import annotations

import pytest

from backend.app.domain.agents.retrieval import ExercisePoolExerciseRecord
from backend.tests.evaluation.budget import planning_cases
from backend.tests.evaluation.fallback_reproduction import (
    _compose_pool,
    replay_production,
    replay_synthetic,
    replay_synthetic_with_production_composition,
)
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.production_catalog import (
    PRODUCTION_CATALOG_VERSION,
    coverage,
    load_production_records,
)
from backend.tests.evaluation.scenario import build_envelope

CASES = planning_cases(GRAPH_CASES)
SLICES = 5


@pytest.fixture(scope="module")
def production_records() -> tuple[ExercisePoolExerciseRecord, ...]:
    return load_production_records()


# -- the shipped bundle is what we think it is --------------------------


def test_production_catalog_loads_the_approved_bundle(
    production_records: tuple[ExercisePoolExerciseRecord, ...],
) -> None:
    """`approvals.py` records 237 records for this catalog version."""

    assert len(production_records) == 237
    assert all(item.catalog_version == PRODUCTION_CATALOG_VERSION for item in production_records)


def test_production_catalog_carries_every_phase(
    production_records: tuple[ExercisePoolExerciseRecord, ...],
) -> None:
    """A pool cannot build a session out of MAIN alone."""

    report = coverage(production_records)
    assert report.with_phase_codes == report.total
    for phase in ("WARMUP", "MAIN", "COOLDOWN"):
        assert sum(1 for item in production_records if phase in item.phase_codes) >= 4


def test_production_fitt_volume_coverage_is_recorded_not_assumed(
    production_records: tuple[ExercisePoolExerciseRecord, ...],
) -> None:
    """Most shipped exercises have no reviewed volume range, and that is fine.

    The fallback falls back to the Recovery ceiling when no range covers an
    exercise. Asserting the gap keeps it visible: if it silently closed or
    widened, the D-2 conclusion would rest on different data than it was drawn
    from. This is an observation, not a target.
    """

    report = coverage(production_records)
    assert report.with_fitt_volume < report.total
    assert report.with_fitt_volume > 0


# -- the replay uses production's own composition -----------------------


def test_compose_pool_reserves_every_phase(
    production_records: tuple[ExercisePoolExerciseRecord, ...],
) -> None:
    """Regression guard for the bug the first version of this replay had.

    A plain window of the ranked list skipped `_selected_ids`, so MAIN-heavy
    orderings produced pools with no warmup or cooldown candidate at all and
    every case "failed". That was the harness, not the service, and it would
    have been reported as confirming D-2.
    """

    envelope = build_envelope(CASES[0])
    eligible = tuple(
        item
        for item in production_records
        if envelope.primary_goal_code in item.goal_codes
        and set(item.location_codes) & set(envelope.allowed_location_codes)
    )
    # Order the input so the highest-ranked candidates are all MAIN-only: the
    # arrangement that broke the naive window.
    main_first = tuple(item for item in eligible if item.phase_codes == ("MAIN",)) + tuple(
        item for item in eligible if item.phase_codes != ("MAIN",)
    )
    window = _compose_pool(main_first, envelope=envelope, requested_limit=12, ranking_offset=0)

    for phase in ("WARMUP", "MAIN", "COOLDOWN"):
        assert any(phase in item.phase_codes for item in window), phase


# -- both sides of the comparison are real ------------------------------


def test_synthetic_arm_still_reproduces_the_original_failure() -> None:
    """The harness catalog must still fail, or the comparison proves nothing."""

    replay = replay_synthetic(CASES)
    buckets = replay.cases_by_reliability()
    assert buckets["never"], "D-2's original condition no longer reproduces at all"
    assert replay.slice_success_rate is not None
    assert replay.slice_success_rate < 1.0


def test_production_composition_alone_does_not_explain_the_whole_gap() -> None:
    """Both harness causes contribute, and the split is worth keeping visible.

    Composition lifts the synthetic catalog part of the way; catalog richness
    covers the rest. Reporting only one would misattribute the finding.
    """

    as_measured = replay_synthetic(CASES)
    composed = replay_synthetic_with_production_composition(CASES, slice_count=SLICES)
    assert as_measured.slice_success_rate is not None
    assert composed.slice_success_rate is not None
    assert composed.slice_success_rate > as_measured.slice_success_rate
    assert composed.slice_success_rate < 1.0


# -- the conclusion -----------------------------------------------------


@pytest.mark.parametrize("exclusion_multiplier", [1, 2, 4])
def test_shipped_catalog_always_produces_a_fallback_plan(exclusion_multiplier: int) -> None:
    """D-2's failure does not occur on the catalog the service ships.

    This is the finding: on the shipped catalog, composed the shipped way, the
    deterministic fallback produced a plan for every case and every ranking
    slice tested -- including the tight-recovery-ceiling cases D-2 named, and
    with the safety exclusions widened well past what any case declared.
    """

    replay = replay_production(CASES, slice_count=SLICES, exclusion_multiplier=exclusion_multiplier)
    buckets = replay.cases_by_reliability()
    assert buckets["never"] == []
    assert buckets["sometimes"] == []
    assert replay.slice_success_rate == 1.0


def test_tight_recovery_ceiling_cases_are_actually_covered() -> None:
    """The conclusion only counts if D-2's own condition was in the sample.

    D-2 named a tight recovery ceiling -- `maximum_sets_per_exercise=2` -- as a
    driver. A replay whose cases all carried a loose ceiling would have proved
    nothing about it.
    """

    tight = [
        case
        for case in CASES
        if (build_envelope(case).recovery_ceiling.maximum_sets_per_exercise or 99) <= 2
    ]
    assert len(tight) >= 3

    replay = replay_production(tuple(tight), slice_count=SLICES)
    assert replay.slice_success_rate == 1.0
