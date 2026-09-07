"""Read only the reviewed MET source approved for workout calorie estimates."""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Final

from backend.app.domain.rules.calories import MET_MAPPING_SOURCE_VERSION

_MAPPING_FILE: Final = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "generated"
    / "exercise-met-mapping-v0.1.0"
    / "exercise_met_mapping_reviewed.csv"
)


def _normalized_name(value: str) -> str:
    return " ".join(value.casefold().split())


@lru_cache(maxsize=1)
def approved_met_values_by_exercise_name() -> dict[str, Decimal]:
    """Return only explicitly domain-approved, production-eligible MET rows.

    The reviewed file identifies its rows by the stable source exercise name, while
    a runtime catalog row has a database UUID.  Matching the approved source name
    is deliberate: unmapped catalog records stay unavailable rather than receiving
    a category-level or guessed MET value.
    """

    values: dict[str, Decimal] = {}
    with _MAPPING_FILE.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (
                row.get("review_status") != "DOMAIN_APPROVED"
                or row.get("production_eligible", "").casefold() != "true"
            ):
                continue
            name = _normalized_name(row.get("exercise_name", ""))
            try:
                met_value = Decimal(row.get("met_value", ""))
            except InvalidOperation as exc:
                raise ValueError("approved MET mapping has an invalid met_value") from exc
            if not name or met_value <= 0:
                raise ValueError("approved MET mapping has an invalid identity")
            existing = values.get(name)
            if existing is not None and existing != met_value:
                raise ValueError("approved MET mapping has an ambiguous identity")
            values[name] = met_value
    return values


def approved_met_value_for_exercise_name(name_en: str | None) -> Decimal | None:
    if not name_en:
        return None
    try:
        return approved_met_values_by_exercise_name().get(_normalized_name(name_en))
    except (OSError, ValueError):
        # Missing or invalid packaged mapping data must never block an official
        # session result or turn an estimate into an invented fallback value.
        return None


__all__ = [
    "MET_MAPPING_SOURCE_VERSION",
    "approved_met_value_for_exercise_name",
    "approved_met_values_by_exercise_name",
]
