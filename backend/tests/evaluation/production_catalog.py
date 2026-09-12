"""Load the shipped catalog bundle into the pool records production builds.

D-2 -- "tight constraints leave the user with no plan at all" -- was measured
against this harness's own 18-exercise synthetic catalog, and the finding said
so.  A failure rate read off a catalog written for tests is not yet a statement
about the service, so this module rebuilds the pool from the catalog the service
actually ships and lets the same deterministic fallback answer again.

**Nothing here re-implements a production rule.**  Phase assignment comes from
the prescription profiles through `is_exercise_prescription_compatible`, exactly
as `vector_index.py` derives it; the FITT volume comes from
`context_for_exercise`; difficulty and location eligibility come from
`is_exercise_allowed_for_user`; pool size comes from `pool_size_for_duration`.
This module only reads the reviewed files the database is seeded from.

**What it cannot reproduce: which candidates Qdrant would rank into the pool.**
PostgreSQL decides eligibility and Qdrant only orders, so the eligible *set* is
authoritative and faithful here. Which `pool_size_for_duration` slice of it a
live query would return is not, because there is no index to ask. Callers
therefore sample several deterministic slices rather than one, so a conclusion
cannot rest on a lucky ordering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final
from uuid import UUID, uuid5

from backend.app.domain.agents.retrieval import (
    ExerciseFittContext,
    ExerciseFittVolumeRange,
    ExercisePoolExerciseRecord,
)
from backend.app.domain.rules.fitt import context_for_exercise
from backend.app.domain.rules.training_level import is_exercise_prescription_compatible

# The catalog the service actually runs, which is not the same question as the
# highest version `approvals.py` carries. `approvals.py` is a registry of
# approved artifacts; deployment is decided by which promotion command was run,
# and `infra/deployment/README.md` documents only v2.0.7 as the release path
# (V2-0-7-PRODUCTION-APPROVAL-2026-09-08-R01). v2.0.8 is approved but not
# deployed. Two further checks agree: the shipped FITT reference is pinned to
# `v2_0_7_fitt_stable_code_mapping.csv`, and the deployment README has no v2.0.8
# section at all.
#
# An earlier version of this module pinned v2.0.8 by reading the registry alone.
# The two catalogs hold the same 237 exercises but differ on fields the
# deterministic fallback times a plan with -- `default_rest_seconds` on 14,
# `default_work_seconds` on 13, `family_code` on 12 -- so the choice is not
# cosmetic and the D-2 re-read had to be repeated against this one.
PRODUCTION_CATALOG_VERSION: Final = "exercise-catalog-v2.0.7-final"
PRODUCTION_BUNDLE_ROOT: Final = Path(
    "data/generated/integrated-catalog-v2.0.7-final/backend_bundle/catalog"
)

# Exercise identifiers are assigned by the database at seed time, so the bundle
# carries none. A uuid5 over the stable code gives every run the same ids
# without claiming they are the ids production assigned: the fallback only uses
# them for identity and family grouping, never to look anything up.
_EXERCISE_ID_NAMESPACE: Final = UUID("9c2f7f7c-4c8a-4a2e-9f1b-2d6a0d3f5e11")

_CONTENT_VERSION: Final = "production-catalog-replay-v1"
_REFERENCE_CODES: Final[tuple[str, ...]] = ("v2.0.7-final",)


class ProductionCatalogUnavailableError(RuntimeError):
    """Raised when the shipped bundle is not present in this checkout."""


def production_exercise_id(stable_code: str) -> UUID:
    return uuid5(_EXERCISE_ID_NAMESPACE, stable_code)


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.exists():
        raise ProductionCatalogUnavailableError(f"missing catalog bundle file: {path}")
    with path.open(encoding="utf-8") as handle:
        return tuple(json.loads(line) for line in handle if line.strip())


@dataclass(frozen=True, slots=True)
class CatalogCoverage:
    """What fraction of the catalog carries each thing the fallback needs.

    Recorded because it is the most likely explanation for any difference
    between the synthetic and production answers, and because a coverage gap is
    a data finding in its own right rather than a detail of this replay.
    """

    total: int
    with_phase_codes: int
    with_main_phase: int
    with_fitt_approved: int
    with_fitt_volume: int
    duration_mode: int

    def to_json(self) -> dict[str, object]:
        return {
            "exercises": self.total,
            "with_phase_codes": self.with_phase_codes,
            "with_main_phase": self.with_main_phase,
            "with_fitt_domain_approved": self.with_fitt_approved,
            "with_fitt_volume_range": self.with_fitt_volume,
            "duration_mode_exercises": self.duration_mode,
        }


def _fitt_context(
    *, stable_code: str, experience_level_code: str, timing_mode_code: str
) -> ExerciseFittContext:
    """Adapt the reviewed FITT reference the way `v3_application` adapts it."""

    context = context_for_exercise(
        stable_code=stable_code,
        experience_level_code=experience_level_code,
        timing_mode_code=timing_mode_code,
    )
    volume = (
        None
        if context.volume is None
        else ExerciseFittVolumeRange(
            min_sets=context.volume.min_sets,
            max_sets=context.volume.max_sets,
            min_reps=context.volume.min_reps,
            max_reps=context.volume.max_reps,
            default_sets=context.volume.default_sets,
            default_reps=context.volume.default_reps,
        )
    )
    return ExerciseFittContext(
        source_code=context.source_code,
        policy_version=context.policy_version,
        review_status_code=context.review_status_code,
        template_id=context.template_id,
        frequency_code=context.frequency_code,
        intensity_code=context.intensity_code,
        time_mode_code=context.time_mode_code,
        type_code=context.type_code,
        volume=volume,
    )


@lru_cache(maxsize=4)
def load_production_records(
    experience_level_code: str = "BEGINNER",
    *,
    root: Path = PRODUCTION_BUNDLE_ROOT,
) -> tuple[ExercisePoolExerciseRecord, ...]:
    """Project the shipped bundle into the records the agents would receive.

    `experience_level_code` is the user's level, and it decides two things the
    way production decides them: which prescription profiles contribute phase
    codes, and which FITT row applies.
    """

    exercises = _read_jsonl(root / "catalog" / "exercises.jsonl")
    profiles = _read_jsonl(root / "prescriptions" / "prescription_profiles.jsonl")
    goal_links = _read_jsonl(root / "prescriptions" / "goal_tag_links.jsonl")

    goals: dict[str, set[str]] = {}
    roles: dict[str, str] = {}
    for link in goal_links:
        if link.get("review_status_code") != "DOMAIN_APPROVED":
            continue
        code = str(link["exercise_stable_code"])
        goals.setdefault(code, set()).add(str(link["goal_code"]))
        role = link.get("role_eligibility_code")
        if role is not None:
            roles.setdefault(code, str(role))

    difficulty_by_code = {
        str(item["stable_code"]): str(item["difficulty_code"]) for item in exercises
    }
    phases: dict[str, set[str]] = {}
    for profile in profiles:
        if profile.get("review_status_code") != "DOMAIN_APPROVED":
            continue
        code = str(profile["exercise_stable_code"])
        difficulty = difficulty_by_code.get(code)
        if difficulty is None:
            continue
        # The same compatibility gate `vector_index.py` applies before a
        # prescription profile is allowed to contribute a phase.
        if not is_exercise_prescription_compatible(
            exercise_difficulty_code=difficulty,
            prescription_experience_level_code=str(profile["experience_level_code"]),
        ):
            continue
        phases.setdefault(code, set()).add(str(profile["phase_code"]))

    records: list[ExercisePoolExerciseRecord] = []
    for item in exercises:
        code = str(item["stable_code"])
        if item.get("review_status_code") != "DOMAIN_APPROVED":
            continue
        if not item.get("general_pool_included"):
            continue
        movement = item.get("primary_movement_pattern_code")
        records.append(
            ExercisePoolExerciseRecord(
                exercise_id=production_exercise_id(code),
                catalog_version=PRODUCTION_CATALOG_VERSION,
                content_version=_CONTENT_VERSION,
                stable_code=code,
                family_code=item.get("family_code"),
                training_type_code=str(item["training_type_code"]),
                body_focus_code=str(item["body_focus_code"]),
                movement_pattern_codes=(str(movement),) if movement else (),
                difficulty_code=str(item["difficulty_code"]),
                timing_mode_code=str(item["timing_mode_code"]),
                default_seconds_per_rep=item.get("default_seconds_per_rep"),
                default_work_seconds=item.get("default_work_seconds"),
                default_rest_seconds=int(item["default_rest_seconds"]),
                default_transition_seconds=int(item["default_transition_seconds"]),
                fitt_context=_fitt_context(
                    stable_code=code,
                    experience_level_code=experience_level_code,
                    timing_mode_code=str(item["timing_mode_code"]),
                ),
                recovery_eligible=bool(item["recovery_eligible"]),
                goal_codes=tuple(sorted(goals.get(code, set()))),
                phase_codes=tuple(sorted(phases.get(code, set()))),
                role_eligibility_code=roles.get(code),
                equipment_codes=tuple(sorted(str(value) for value in item["equipment_codes"])),
                location_codes=tuple(sorted(str(value) for value in item["location_codes"])),
                prescription_reference_codes=_REFERENCE_CODES,
                source_reference_codes=_REFERENCE_CODES,
                review_reference_codes=_REFERENCE_CODES,
            )
        )
    return tuple(sorted(records, key=lambda record: record.stable_code))


def coverage(records: tuple[ExercisePoolExerciseRecord, ...]) -> CatalogCoverage:
    return CatalogCoverage(
        total=len(records),
        with_phase_codes=sum(1 for item in records if item.phase_codes),
        with_main_phase=sum(1 for item in records if "MAIN" in item.phase_codes),
        with_fitt_approved=sum(
            1
            for item in records
            if item.fitt_context is not None
            and item.fitt_context.review_status_code == "DOMAIN_APPROVED"
        ),
        with_fitt_volume=sum(1 for item in records if item.approved_fitt_volume() is not None),
        duration_mode=sum(1 for item in records if item.timing_mode_code == "DURATION"),
    )


__all__ = [
    "PRODUCTION_BUNDLE_ROOT",
    "PRODUCTION_CATALOG_VERSION",
    "CatalogCoverage",
    "ProductionCatalogUnavailableError",
    "coverage",
    "load_production_records",
    "production_exercise_id",
]
