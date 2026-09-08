from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_7_beginner_prescription_derivation.py"
_spec = importlib.util.spec_from_file_location("beginner_derivation", SCRIPT)
assert _spec and _spec.loader
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)

ROOT = Path(__file__).resolve().parents[3]


def _profile(code, level, goal, phase="MAIN", **overrides):
    row = {
        "catalog_version_code": "exercise-catalog-v2.0.7-final",
        "exercise_stable_code": code,
        "experience_level_code": level,
        "goal_code": goal,
        "intensity_code": "MODERATE",
        "phase_code": phase,
        "prescription_version": "prescription-set-v2.0.7-normalized-1.0.0",
        "reps": 10,
        "rest_seconds_per_set": 75,
        "review_status_code": "DOMAIN_APPROVED",
        "sets": 3,
        "work_seconds_per_set": None,
    }
    row.update(overrides)
    return row


def test_learns_the_transformation_from_exercises_carrying_both_levels() -> None:
    profiles = [
        _profile("teacher", "INTERMEDIATE", "STRENGTH"),
        _profile("teacher", "BEGINNER", "STRENGTH", sets=2, rest_seconds_per_set=60),
    ]

    mapping = builder.learn_mapping(profiles)

    assert mapping[(3, 10, 75, None, "MODERATE")] == (2, 10, 60, None, "MODERATE")


def test_contradictory_precedents_are_refused_rather_than_resolved() -> None:
    """Two identical inputs with different outcomes mean there is no rule to apply."""

    profiles = [
        _profile("a", "INTERMEDIATE", "STRENGTH"),
        _profile("a", "BEGINNER", "STRENGTH", sets=2, rest_seconds_per_set=60),
        _profile("b", "INTERMEDIATE", "STRENGTH"),
        _profile("b", "BEGINNER", "STRENGTH", sets=2, rest_seconds_per_set=45),
    ]

    with pytest.raises(ValueError, match="not a function"):
        builder.learn_mapping(profiles)


def test_an_input_the_corpus_never_showed_is_left_to_a_reviewer(tmp_path: Path) -> None:
    """The generator must not extrapolate past what the reviewed rows demonstrate."""

    profiles = [
        _profile("teacher", "INTERMEDIATE", "STRENGTH"),
        _profile("teacher", "BEGINNER", "STRENGTH", sets=2, rest_seconds_per_set=60),
        # Same target, but a set/rep shape no precedent covers.
        _profile("target", "INTERMEDIATE", "STRENGTH", reps=20, rest_seconds_per_set=90),
    ]
    catalog = {
        "teacher": {"stable_code": "teacher", "difficulty_code": "BEGINNER"},
        "target": {"stable_code": "target", "difficulty_code": "BEGINNER"},
    }

    derived, undecidable = builder.derive(profiles, catalog, builder.learn_mapping(profiles))

    assert derived == []
    assert len(undecidable) == 1 and "target" in undecidable[0]


def test_real_derivation_covers_every_target_and_invents_nothing() -> None:
    """Against the pinned bundle: 24 exercises, 72 rows, nothing outside the rule."""

    payload = builder.build(report=ROOT / "data/reports/.derivation-check.json")
    try:
        assert payload["summary"] == {
            "exercises": 24,
            "derived_rows": 72,
            "rows_outside_the_rule": 0,
        }
        assert payload["derivation"]["ambiguous_inputs"] == 0
        # Every derived row is a BEGINNER row whose source was INTERMEDIATE.
        assert {row["experience_level_code"] for row in payload["rows"]} == {"BEGINNER"}
        # The status must stay honest: these are not reviewed rows yet.
        assert payload["status"] == "DERIVED_PENDING_REVIEW"
    finally:
        (ROOT / "data/reports/.derivation-check.json").unlink(missing_ok=True)


def test_derived_reps_stay_inside_the_approved_beginner_fitt_range() -> None:
    """An independent check: the reviewed FITT policy never contradicts the rule."""

    from backend.app.domain.rules.fitt import context_for_exercise

    report = (
        ROOT / "data/reports/integrated_catalog_v2_0_7_final/beginner_prescription_derivation.json"
    )
    rows = json.loads(report.read_text(encoding="utf-8"))["rows"]
    checked = 0
    for row in rows:
        if row["reps"] is None:
            continue
        volume = context_for_exercise(
            stable_code=row["exercise_stable_code"],
            experience_level_code="BEGINNER",
            timing_mode_code="REPS",
        ).volume
        if volume is None:
            continue
        checked += 1
        assert volume.min_sets <= row["sets"] <= volume.max_sets
        assert volume.min_reps <= row["reps"] <= volume.max_reps
    assert checked, "the cross-check must actually exercise the approved ranges"
