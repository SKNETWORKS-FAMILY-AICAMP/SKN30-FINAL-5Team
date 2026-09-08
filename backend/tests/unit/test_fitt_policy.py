import csv
import json
from pathlib import Path

import pytest

from backend.app.domain.rules.fitt import (
    REVIEW_REQUIRED,
    _default_mapping_path,
    _default_reference_path,
    _default_template_path,
    context_for_exercise,
)

# The catalog the API actually serves. Reading an older bundle here is what let
# a timing-mode conflict reach production unnoticed.
PROMOTED_CATALOG = Path(
    "data/generated/integrated-catalog-v2.0.7-final/backend_bundle/catalog/catalog/exercises.jsonl"
)

# Reviewed FITT rows whose timing mode contradicts the promoted catalog's. The
# join is by permanent source identity and is correct; the two sources simply
# disagree about whether the movement is counted in repetitions or held for
# time. The catalog owns that answer, so these carry no approved FITT context.
CATALOG_TIMING_CONFLICTS = {
    "bodyweight_crunch_core_brace_bodyweight",
    "bodyweight_reverse_crunch_core_brace_bodyweight",
    "dead_bug",
    "lower_back_curl_core_brace_bodyweight",
    "seated_side_crunch_wall",
}


def _promoted_exercises() -> list[dict[str, str]]:
    return [
        json.loads(line)
        for line in PROMOTED_CATALOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize(
    ("stable_code", "experience_level_code", "template_id", "expected"),
    (
        (
            "barbell_deadlift_hip_dominant_barbell",
            "BEGINNER",
            "FITT-COMPOUND-HINGE-V1",
            (2, 3, 8, 12, 3, 8),
        ),
        (
            "barbell_deadlift_hip_dominant_barbell",
            "INTERMEDIATE",
            "FITT-COMPOUND-HINGE-V1",
            (2, 4, 8, 12, 3, 8),
        ),
        (
            "barbell_front_raise_isolation_barbell",
            "BEGINNER",
            "FITT-ISOLATION-STRENGTH-V1",
            (2, 3, 10, 15, 3, 10),
        ),
        (
            "barbell_front_raise_isolation_barbell",
            "INTERMEDIATE",
            "FITT-ISOLATION-STRENGTH-V1",
            (2, 4, 10, 15, 3, 10),
        ),
    ),
)
def test_approved_strength_fitt_context_has_only_reviewed_level_ranges(
    stable_code: str,
    experience_level_code: str,
    template_id: str,
    expected: tuple[int, int, int, int, int, int],
) -> None:
    # The policy decision is based on the approved template, so both supported
    # experience levels can be checked without inventing a separate source row.
    context = context_for_exercise(
        stable_code=stable_code,
        experience_level_code=experience_level_code,
        timing_mode_code="REPS",
    )

    assert context.review_status_code == "DOMAIN_APPROVED"
    assert context.template_id == template_id
    assert context.volume is not None
    assert (
        context.volume.min_sets,
        context.volume.max_sets,
        context.volume.min_reps,
        context.volume.max_reps,
        context.volume.default_sets,
        context.volume.default_reps,
    ) == expected


def test_missing_fitt_mapping_is_review_required_and_has_no_inferred_range() -> None:
    context = context_for_exercise(
        stable_code="UNKNOWN-STABLE-CODE",
        experience_level_code="BEGINNER",
        timing_mode_code="REPS",
    )

    assert context.review_status_code == REVIEW_REQUIRED
    assert context.volume is None


def test_reviewed_fitt_references_are_copied_into_the_backend_image() -> None:
    """The module opens these on the V3 decision path, so the image must carry them.

    `_repo_root()` resolves against the container working directory. A reference
    the Dockerfile does not copy is a reference the API cannot read, and the
    failure surfaces as FileNotFoundError on every routine creation rather than
    as a missing-data code.
    """

    dockerfile = Path("backend/Dockerfile").read_text(encoding="utf-8")
    ignorefile = Path("backend/Dockerfile.dockerignore").read_text(encoding="utf-8")
    for path in (_default_mapping_path(), _default_reference_path(), _default_template_path()):
        assert path.is_file(), f"{path} is missing from the repository"
        relative = path.relative_to(Path.cwd()).as_posix()
        assert relative in dockerfile, f"{relative} is not copied into the image"
        assert f"!{relative}" in ignorefile, f"{relative} is excluded by the dockerignore"


def test_a_reference_contradicting_the_catalog_timing_mode_is_review_required() -> None:
    """A disagreement is withheld rather than resolved in favour of either source.

    `ExercisePoolExerciseRecord` refuses a record whose FITT timing mode differs
    from the catalog's, and the pool is built as one model validation, so a
    single contradicting row failed every routine creation instead of degrading
    that one exercise.
    """

    contradicting = sorted(CATALOG_TIMING_CONFLICTS)[0]
    catalog = {row["stable_code"]: row for row in _promoted_exercises()}
    assert catalog[contradicting]["timing_mode_code"] == "REPS"

    context = context_for_exercise(
        stable_code=contradicting,
        experience_level_code="BEGINNER",
        timing_mode_code="REPS",
    )

    assert context.review_status_code == REVIEW_REQUIRED
    assert context.time_mode_code is None
    assert context.volume is None


def test_no_promoted_exercise_yields_a_context_the_agent_snapshot_rejects() -> None:
    """The invariant `ExercisePoolExerciseRecord.validate_timing_basis` enforces.

    Checked against every exercise at its own timing mode. The earlier version of
    this test asked for "REPS" for all of them, which is why it agreed with a
    catalog it never actually matched.
    """

    for row in _promoted_exercises():
        for level in ("BEGINNER", "INTERMEDIATE"):
            context = context_for_exercise(
                stable_code=row["stable_code"],
                experience_level_code=level,
                timing_mode_code=row["timing_mode_code"],
            )
            assert context.time_mode_code in {None, row["timing_mode_code"]}, (
                f"{row['stable_code']} would fail the pool build"
            )


def test_promoted_catalog_uses_only_reviewed_fitt_mapping_coverage() -> None:
    catalog = _promoted_exercises()
    assert catalog, "the promoted catalog must not be empty"

    approved = {
        row["stable_code"]
        for row in catalog
        if context_for_exercise(
            stable_code=row["stable_code"],
            experience_level_code="BEGINNER",
            timing_mode_code=row["timing_mode_code"],
        ).review_status_code
        != REVIEW_REQUIRED
    }
    mapping_codes = {
        row["exercise_stable_code"]
        for row in csv.DictReader(_default_mapping_path().read_text(encoding="utf-8").splitlines())
    }

    assert len(mapping_codes) == 89
    # Approval is the mapping minus the rows the catalog contradicts. Pinning
    # the difference keeps a future catalog re-review from silently widening it.
    assert mapping_codes - approved == CATALOG_TIMING_CONFLICTS
    assert approved == mapping_codes - CATALOG_TIMING_CONFLICTS
    assert len(approved) == 84
