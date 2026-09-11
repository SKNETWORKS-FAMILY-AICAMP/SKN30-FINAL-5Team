"""Re-read D-2 against the shipped catalog. No provider call, no cost.

    uv run python -m backend.tests.evaluation.fallback_reproduction_cli

D-2 recorded the deterministic fallback failing to produce a plan and classified
it SERVICE, while stating that the measurement was taken on an 18-exercise
catalog written for tests and had to be re-read against the catalog that ships.
This is that re-read.

Three arms, so a difference can be attributed rather than just observed:

1. the harness catalog composed the way the harness composes it -- what D-2 measured
2. the harness catalog composed the way production composes it -- isolates the rule
3. the shipped catalog composed the way production composes it -- what users get

Arm 2 exists because the harness declares each case's pool directly and so never
applies the phase and role reservation `QdrantExercisePoolSnapshotLoader` applies.
Without it, "the real catalog is bigger" and "the harness skipped a production
step" are indistinguishable, and only one of those is a finding about the service.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.tests.evaluation.budget import planning_cases
from backend.tests.evaluation.fallback_reproduction import (
    DEFAULT_SLICE_COUNT,
    CatalogReplay,
    replay_production,
    replay_synthetic,
    replay_synthetic_with_production_composition,
)
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.production_catalog import (
    ProductionCatalogUnavailableError,
    coverage,
    load_production_records,
)

DEFAULT_OUTPUT = Path("results/d2_reproduction.json")

# How far past each case's declared exclusions the replay pushes. D-2 named
# shrinking MAIN candidates as a driver, so the re-read has to press on it.
EXCLUSION_MULTIPLIERS = (1, 2, 4, 8)


def _line(replay: CatalogReplay) -> str:
    buckets = replay.cases_by_reliability()
    return (
        f"{replay.catalog_label:<58} "
        f"slices {replay.slice_success_rate:>6} "
        f"always {len(buckets['always']):>2} "
        f"sometimes {len(buckets['sometimes']):>2} "
        f"never {len(buckets['never']):>2}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slices", type=int, default=DEFAULT_SLICE_COUNT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()

    cases = planning_cases(GRAPH_CASES)
    print(f"{len(cases)} planning cases, {arguments.slices} ranking slices each, 0 LLM calls\n")

    as_measured = replay_synthetic(cases)
    composed = replay_synthetic_with_production_composition(cases, slice_count=arguments.slices)
    print(_line(as_measured))
    print(_line(composed))

    try:
        records = load_production_records()
    except ProductionCatalogUnavailableError as error:
        print(f"\nProduction catalog unavailable: {error}")
        return 2

    production: list[CatalogReplay] = []
    for multiplier in EXCLUSION_MULTIPLIERS:
        replay = replay_production(
            cases, slice_count=arguments.slices, exclusion_multiplier=multiplier
        )
        production.append(replay)
        print(_line(replay))

    payload = {
        "finding": "D-2",
        "question": (
            "Does the deterministic fallback still fail to produce a plan once the "
            "shipped catalog and the shipped pool composition replace the harness's?"
        ),
        "llm_calls": 0,
        "slices_per_case": arguments.slices,
        "production_catalog_coverage": coverage(records).to_json(),
        "arms": {
            "synthetic_as_measured": as_measured.to_json(),
            "synthetic_production_composition": composed.to_json(),
            "production": [item.to_json() for item in production],
        },
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"\nartifact: {arguments.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
