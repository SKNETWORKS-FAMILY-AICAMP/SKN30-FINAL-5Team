"""Which catalog a dataset's exercise codes refer to.

The tuning dataset is written against an 18-exercise synthetic catalog: small,
fully controlled, and good for asserting that a named fault is caught. It is a
poor basis for a headline number, because a pool that thin reaches shapes the
deployed catalog never produces -- that is how D-2 was first reported as a
service defect and had to be retracted.

The round 2 held-out set is therefore written against the catalog the service
deploys. Both have to load through the same scenario builder, so the catalog
stops being a module-level import and becomes a named source a dataset declares.

`DEPLOYED` follows `production_catalog.py`, which tracks the version with a
deployment path rather than the newest one in the approval registry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Final
from uuid import UUID

from backend.app.domain.agents.retrieval import ExercisePoolExerciseRecord
from backend.tests.evaluation import catalog as synthetic_catalog
from backend.tests.evaluation.production_catalog import (
    PRODUCTION_CATALOG_VERSION,
    load_production_records,
)

SYNTHETIC_SOURCE: Final = "eval-synthetic"
DEPLOYED_SOURCE: Final = "deployed"

# The user level the deployed pool is projected for. BEGINNER is the product's
# stated audience and the stricter gate: it admits fewer exercises than
# INTERMEDIATE, so a case written against it stays valid for both.
DEPLOYED_EXPERIENCE_LEVEL: Final = "BEGINNER"


class UnknownCatalogSourceError(KeyError):
    """Raised when a dataset names a catalog this harness does not carry."""


@dataclass(frozen=True, slots=True)
class CatalogSource:
    """One catalog, addressed by stable code.

    Deliberately the same surface `catalog.py` already exposed, so the scenario
    builder reads identically whichever source it was handed.
    """

    name: str
    catalog_version: str
    records: Mapping[str, ExercisePoolExerciseRecord]

    def __contains__(self, stable_code: object) -> bool:
        return stable_code in self.records

    def records_for(self, stable_codes: tuple[str, ...]) -> tuple[ExercisePoolExerciseRecord, ...]:
        """Return the named records in canonical UUID order, as the pool requires."""

        unknown = tuple(code for code in stable_codes if code not in self.records)
        if unknown:
            raise KeyError(f"unknown {self.name} exercise codes: {unknown}")
        selected = [self.records[code] for code in dict.fromkeys(stable_codes)]
        return tuple(sorted(selected, key=lambda record: str(record.exercise_id)))

    def ids_for(self, stable_codes: tuple[str, ...]) -> tuple[UUID, ...]:
        return tuple(record.exercise_id for record in self.records_for(stable_codes))

    def codes_in_phase(self, phase_code: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                code for code, record in self.records.items() if phase_code in record.phase_codes
            )
        )


@lru_cache(maxsize=4)
def _synthetic() -> CatalogSource:
    return CatalogSource(
        name=SYNTHETIC_SOURCE,
        catalog_version=synthetic_catalog.CATALOG_VERSION,
        records=dict(synthetic_catalog.CATALOG),
    )


@lru_cache(maxsize=4)
def _deployed() -> CatalogSource:
    records = load_production_records(DEPLOYED_EXPERIENCE_LEVEL)
    return CatalogSource(
        name=DEPLOYED_SOURCE,
        catalog_version=PRODUCTION_CATALOG_VERSION,
        records={record.stable_code: record for record in records},
    )


def source_for(name: str) -> CatalogSource:
    """Resolve a dataset's declared catalog, or refuse by name.

    Loading is lazy: the deployed bundle is several files on disk, and a run
    that only touches the tuning dataset should not pay to read it.
    """

    if name == SYNTHETIC_SOURCE:
        return _synthetic()
    if name == DEPLOYED_SOURCE:
        return _deployed()
    raise UnknownCatalogSourceError(
        f"unknown catalog source {name!r}; expected one of "
        f"{SYNTHETIC_SOURCE!r} or {DEPLOYED_SOURCE!r}"
    )


__all__ = [
    "DEPLOYED_EXPERIENCE_LEVEL",
    "DEPLOYED_SOURCE",
    "SYNTHETIC_SOURCE",
    "CatalogSource",
    "UnknownCatalogSourceError",
    "source_for",
]
