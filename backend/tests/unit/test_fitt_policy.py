import pytest

from backend.app.domain.rules.fitt import REVIEW_REQUIRED, context_for_exercise


@pytest.mark.parametrize(
    ("stable_code", "experience_level_code", "template_id", "expected"),
    (
        ("NEX-000001", "BEGINNER", "FITT-COMPOUND-HINGE-V1", (2, 3, 8, 12, 3, 8)),
        ("NEX-000001", "INTERMEDIATE", "FITT-COMPOUND-HINGE-V1", (2, 4, 8, 12, 3, 8)),
        ("NEX-000004", "BEGINNER", "FITT-ISOLATION-STRENGTH-V1", (2, 3, 10, 15, 3, 10)),
        ("NEX-000004", "INTERMEDIATE", "FITT-ISOLATION-STRENGTH-V1", (2, 4, 10, 15, 3, 10)),
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
