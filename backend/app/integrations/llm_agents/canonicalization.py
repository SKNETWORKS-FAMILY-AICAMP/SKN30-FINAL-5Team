"""Put provider output into the canonical order the V3 contracts require.

Code tuples in the domain contracts must be sorted and free of duplicates so
that proposal and plan hashes stay reproducible. That order carries no meaning
of its own: the codes are a set, and the contract sorts them only to have one
spelling of the same answer.

A model returns codes in the order it reasoned about them, so leaving the order
to the model rejects otherwise valid proposals over a property the server can
establish itself. This is the same reason ``proposal_hash`` and
``estimated_duration_seconds`` are withheld from the provider schema.

The domain contracts keep their strict ordering rule. Normalization belongs
here, at the boundary that adapts an external answer, rather than in the domain
that has to stay strict for everything already inside it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_PROPOSAL_CODE_FIELDS: tuple[str, ...] = (
    "adjustment_codes",
    "evidence_reference_codes",
    "hard_constraint_codes",
    "reason_codes",
)
_PLAN_CODE_FIELDS: tuple[str, ...] = ("decision_codes",)
_PRESCRIPTION_CODE_FIELDS: tuple[str, ...] = ("equipment_codes",)


def _canonical_codes(value: object) -> object:
    """Sort and de-duplicate a sequence of codes, leaving anything else untouched.

    The result stays a tuple because the domain contracts are strict and reject a
    list where they declare a tuple. Values that are not a plain sequence of
    strings are returned as they came so that malformed output still fails
    validation instead of being reshaped into something that passes.
    """

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return value
    if not all(isinstance(item, str) for item in value):
        return value
    return tuple(sorted(set(value)))


def _canonical_prescriptions(value: object) -> object:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return value
    prescriptions = []
    for item in value:
        if not isinstance(item, Mapping):
            return value
        prescriptions.append(
            {
                key: (_canonical_codes(nested) if key in _PRESCRIPTION_CODE_FIELDS else nested)
                for key, nested in item.items()
            }
        )
    return tuple(prescriptions)


def _canonicalize(values: Mapping[str, object], code_fields: tuple[str, ...]) -> dict[str, object]:
    canonical: dict[str, object] = {}
    for key, value in values.items():
        if key in code_fields:
            canonical[key] = _canonical_codes(value)
        elif key == "exercise_prescriptions":
            canonical[key] = _canonical_prescriptions(value)
        else:
            canonical[key] = value
    return canonical


def canonical_proposal_values(values: Mapping[str, object]) -> dict[str, object]:
    """Normalize a specialist proposal payload returned by a provider."""

    return _canonicalize(values, _PROPOSAL_CODE_FIELDS)


def canonical_plan_values(values: Mapping[str, object]) -> dict[str, object]:
    """Normalize a coordinator PlanSpec payload returned by a provider."""

    return _canonicalize(values, _PLAN_CODE_FIELDS)


__all__ = ["canonical_plan_values", "canonical_proposal_values"]
