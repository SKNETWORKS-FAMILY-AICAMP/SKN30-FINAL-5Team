"""Reviewed FITT-reference loading and deterministic strength volume bounds.

This module deliberately does not infer an exercise prescription from a name,
movement, or difficulty. It joins a catalog stable code through the reviewed
identity mapping to ``catalog_enrichment_v3_fitt.csv`` and its reviewed
template. Callers receive ``REVIEW_REQUIRED`` when any link is absent or
unapproved.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

FITT_CONTEXT_POLICY_VERSION = "fitt-context-policy-v2"
FITT_REFERENCE_SOURCE_CODE = "catalog-enrichment-v3-fitt"
DOMAIN_APPROVED = "DOMAIN_APPROVED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class FittVolumeRange:
    min_sets: int
    max_sets: int
    min_reps: int
    max_reps: int
    default_sets: int
    default_reps: int


@dataclass(frozen=True, slots=True)
class FittContext:
    source_code: str
    policy_version: str
    review_status_code: str
    template_id: str | None
    frequency_code: str | None
    intensity_code: str | None
    time_mode_code: str | None
    type_code: str | None
    volume: FittVolumeRange | None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_reference_path() -> Path:
    return _repo_root() / "data" / "normalized" / "catalog_enrichment_v3_fitt.csv"


def _default_template_path() -> Path:
    return _repo_root() / "data" / "normalized" / "fitt_template_v1.csv"


def _default_mapping_path() -> Path:
    return _repo_root() / "data" / "normalized" / "v2_0_7_fitt_stable_code_mapping.csv"


def review_required_context() -> FittContext:
    return FittContext(
        source_code=FITT_REFERENCE_SOURCE_CODE,
        policy_version=FITT_CONTEXT_POLICY_VERSION,
        review_status_code=REVIEW_REQUIRED,
        template_id=None,
        frequency_code=None,
        intensity_code=None,
        time_mode_code=None,
        type_code=None,
        volume=None,
    )


def _integer(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        result = int(value)
    except ValueError:
        return None
    return result if result > 0 else None


def _range_lower(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    first = value.split("-", maxsplit=1)[0].strip()
    return _integer(first)


def _keyed_rows(path: Path, key: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        result: dict[str, dict[str, str]] = {}
        for row in csv.DictReader(handle):
            value = row.get(key, "")
            if not value or value in result:
                raise ValueError(f"{path.name}: blank or duplicate {key}")
            result[value] = row
    return result


@lru_cache(maxsize=1)
def _rows() -> tuple[
    dict[str, dict[str, str]], dict[str, dict[str, str]], dict[str, dict[str, str]]
]:
    mappings = _keyed_rows(_default_mapping_path(), "exercise_stable_code")
    references = _keyed_rows(_default_reference_path(), "exercise_id")
    templates = _keyed_rows(_default_template_path(), "fitt_template_id")
    return mappings, references, templates


def _strength_volume(
    *,
    experience_level_code: str,
    template: dict[str, str],
) -> FittVolumeRange | None:
    category = template.get("training_category")
    if category not in {"COMPOUND_STRENGTH", "ISOLATION_STRENGTH"}:
        return None
    if experience_level_code not in {"BEGINNER", "INTERMEDIATE"}:
        return None
    min_sets, max_sets = (2, 3) if experience_level_code == "BEGINNER" else (2, 4)
    min_reps, max_reps = (8, 12) if category == "COMPOUND_STRENGTH" else (10, 15)
    default_sets = _integer(template.get("default_sets"))
    default_reps = _range_lower(template.get("default_reps"))
    if (
        default_sets is None
        or default_reps is None
        or not min_sets <= default_sets <= max_sets
        or not min_reps <= default_reps <= max_reps
    ):
        return None
    return FittVolumeRange(
        min_sets=min_sets,
        max_sets=max_sets,
        min_reps=min_reps,
        max_reps=max_reps,
        default_sets=default_sets,
        default_reps=default_reps,
    )


def context_for_exercise(
    *,
    stable_code: str,
    experience_level_code: str,
    timing_mode_code: str,
) -> FittContext:
    """Return reviewed agent context for one catalog stable code.

    FITT approval alone is not enough for a selectable repetitions range.  A
    strength range must also resolve to one of the explicitly approved template
    categories and to a supported experience level.
    """

    mappings, references, templates = _rows()
    mapping = mappings.get(stable_code)
    if mapping is None or mapping.get("review_status_code") != DOMAIN_APPROVED:
        return review_required_context()
    reference = references.get(mapping.get("exercise_id", ""))
    if (
        reference is None
        or reference.get("fitt_status") != "APPROVED"
        or mapping.get("fitt_template_id") != reference.get("fitt_template_id")
    ):
        return review_required_context()
    template_id = reference.get("fitt_template_id") or None
    template = templates.get(template_id or "")
    if template is None:
        return review_required_context()
    volume = (
        _strength_volume(experience_level_code=experience_level_code, template=template)
        if timing_mode_code == "REPS"
        else None
    )
    review_status = DOMAIN_APPROVED
    # A non-strength repetition mapping is still reviewed FITT context, but it
    # has no approved selectable range.  The compiler therefore refuses a
    # repetitions prescription instead of manufacturing one.
    return FittContext(
        source_code=FITT_REFERENCE_SOURCE_CODE,
        policy_version=FITT_CONTEXT_POLICY_VERSION,
        review_status_code=review_status,
        template_id=template_id,
        frequency_code="PER_SESSION",
        intensity_code=reference.get("default_intensity") or None,
        time_mode_code=reference.get("timing_mode_code") or None,
        type_code=reference.get("current_training_type") or None,
        volume=volume,
    )


__all__ = [
    "DOMAIN_APPROVED",
    "FITT_CONTEXT_POLICY_VERSION",
    "FITT_REFERENCE_SOURCE_CODE",
    "FittContext",
    "FittVolumeRange",
    "REVIEW_REQUIRED",
    "_default_mapping_path",
    "context_for_exercise",
    "review_required_context",
]
