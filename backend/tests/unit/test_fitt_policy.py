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

PROMOTED_CATALOG = Path(
    "data/generated/exercise-catalog-v2.0.6-final/backend_bundle/catalog/exercises.jsonl"
)


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


def test_promoted_catalog_uses_only_reviewed_fitt_mapping_coverage() -> None:

    stable_codes = [
        json.loads(line)["stable_code"]
        for line in PROMOTED_CATALOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert stable_codes, "the promoted catalog must not be empty"

    approved = {
        code
        for code in stable_codes
        if context_for_exercise(
            stable_code=code,
            experience_level_code="BEGINNER",
            timing_mode_code="REPS",
        ).review_status_code
        != REVIEW_REQUIRED
    }
    mapping_codes = {
        row["exercise_stable_code"]
        for row in __import__("csv").DictReader(
            _default_mapping_path().read_text(encoding="utf-8").splitlines()
        )
    }

    assert approved == mapping_codes
    assert len(approved) == 89
