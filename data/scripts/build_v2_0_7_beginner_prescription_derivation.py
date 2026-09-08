#!/usr/bin/env python3
"""Derive the missing BEGINNER prescription rows from the reviewed corpus.

The v2.0.6 difficulty re-review moved 24 exercises down to BEGINNER without the
prescription review being re-run, so they carry INTERMEDIATE prescriptions only
and never reach a beginner's pool. This does not invent a beginner volume: it
reads the INTERMEDIATE-to-BEGINNER transformation the reviewed corpus already
applies to every exercise that carries both levels, proves that transformation
is a total function with no ambiguity, and applies it to the 24.

The output is a review input, not a bundle artifact. Prescription rows can only
be imported as DOMAIN_APPROVED -- the code set has no other value -- so shipping
these requires a reviewer to approve the derivation itself. This script produces
what that reviewer needs to see and refuses to emit anything it cannot derive.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "data/generated/integrated-catalog-v2.0.7-final/backend_bundle/catalog"
REPORT = ROOT / "data/reports/integrated_catalog_v2_0_7_final/beginner_prescription_derivation.json"

# The fields the transformation is allowed to change. Everything else on a
# derived row is copied verbatim from its INTERMEDIATE source.
_SHAPE_FIELDS = ("sets", "reps", "rest_seconds_per_set", "work_seconds_per_set", "intensity_code")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _shape(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row[field] for field in _SHAPE_FIELDS)


def learn_mapping(profiles: list[dict[str, Any]]) -> dict[tuple[Any, ...], tuple[Any, ...]]:
    """Read the transformation out of every exercise that carries both levels.

    A slot is one exercise/goal/phase. Learning the rule per slot rather than per
    exercise is what makes it checkable: if two slots with identical INTERMEDIATE
    values disagreed on the BEGINNER result there would be no rule to apply, and
    this raises instead of picking one.
    """

    slots: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    for row in profiles:
        key = (row["exercise_stable_code"], row["goal_code"], row["phase_code"])
        slots[key][row["experience_level_code"]] = row

    observed: dict[tuple[Any, ...], set[tuple[Any, ...]]] = collections.defaultdict(set)
    for levels in slots.values():
        if len(levels) != 2:
            continue
        observed[_shape(levels["INTERMEDIATE"])].add(_shape(levels["BEGINNER"]))

    ambiguous = {source: results for source, results in observed.items() if len(results) > 1}
    if ambiguous:
        raise ValueError(f"transformation is not a function: {sorted(map(str, ambiguous))}")
    if not observed:
        raise ValueError("no exercise carries both levels; nothing can be derived")
    return {source: next(iter(results)) for source, results in observed.items()}


def derive(
    profiles: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    mapping: dict[tuple[Any, ...], tuple[Any, ...]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply the learned rule to exercises reviewed BEGINNER that lack the level."""

    levels: dict[str, set[str]] = collections.defaultdict(set)
    for row in profiles:
        levels[row["exercise_stable_code"]].add(row["experience_level_code"])
    targets = sorted(
        code
        for code, record in catalog.items()
        if record["difficulty_code"] == "BEGINNER" and "BEGINNER" not in levels.get(code, set())
    )

    derived: list[dict[str, Any]] = []
    undecidable: list[str] = []
    for row in profiles:
        if row["exercise_stable_code"] not in targets:
            continue
        if row["experience_level_code"] != "INTERMEDIATE":
            continue
        result = mapping.get(_shape(row))
        if result is None:
            undecidable.append(f"{row['exercise_stable_code']}/{row['goal_code']}: {_shape(row)}")
            continue
        new = dict(row)
        new["experience_level_code"] = "BEGINNER"
        new.update(dict(zip(_SHAPE_FIELDS, result, strict=True)))
        derived.append(new)
    return derived, undecidable


def build(bundle: Path = BUNDLE, report: Path = REPORT) -> dict[str, Any]:
    profiles = _read_jsonl(bundle / "prescriptions/prescription_profiles.jsonl")
    catalog = {row["stable_code"]: row for row in _read_jsonl(bundle / "catalog/exercises.jsonl")}
    mapping = learn_mapping(profiles)
    derived, undecidable = derive(profiles, catalog, mapping)
    if undecidable:
        raise ValueError(
            "an INTERMEDIATE row falls outside the observed transformation; it needs a "
            f"reviewer, not a derivation: {undecidable}"
        )

    precedents: collections.Counter[tuple[Any, ...]] = collections.Counter()
    slots: dict[tuple[str, str, str], set[str]] = collections.defaultdict(set)
    for row in profiles:
        slots[(row["exercise_stable_code"], row["goal_code"], row["phase_code"])].add(
            row["experience_level_code"]
        )
    for row in profiles:
        key = (row["exercise_stable_code"], row["goal_code"], row["phase_code"])
        if row["experience_level_code"] == "INTERMEDIATE" and len(slots[key]) == 2:
            precedents[_shape(row)] += 1

    payload = {
        "status": "DERIVED_PENDING_REVIEW",
        "source_bundle": bundle.relative_to(ROOT).as_posix(),
        "derivation": {
            "basis": (
                "INTERMEDIATE-to-BEGINNER transformation observed in every exercise that "
                "carries both reviewed levels"
            ),
            "changed_fields": list(_SHAPE_FIELDS),
            "is_total_function": True,
            "ambiguous_inputs": 0,
            "rules": [
                {
                    "from": dict(zip(_SHAPE_FIELDS, source, strict=True)),
                    "to": dict(zip(_SHAPE_FIELDS, result, strict=True)),
                    "precedent_rows": precedents[source],
                }
                for source, result in sorted(mapping.items(), key=str)
            ],
        },
        "summary": {
            "exercises": len({row["exercise_stable_code"] for row in derived}),
            "derived_rows": len(derived),
            "rows_outside_the_rule": len(undecidable),
        },
        "rows": derived,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    payload = build(args.bundle, args.report)
    print(
        json.dumps({k: v for k, v in payload.items() if k != "rows"}, ensure_ascii=False, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
