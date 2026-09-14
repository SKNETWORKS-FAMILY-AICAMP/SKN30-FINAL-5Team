"""Measure the deterministic byte effect of role-minimized specialist payloads."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from backend.app.domain.agents.v3_contracts import (
    SpecialistAgentInput,
    SpecialistAgentTypeCode,
)
from backend.app.integrations.llm_agents.payload import (
    project_exercise_pool,
    specialist_payload,
)
from backend.tests.evaluation.budget import planning_cases
from backend.tests.evaluation.dataset import EvaluationCase
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.scenario import build_scenario


def _serialized_bytes(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def build_payload_size_report(cases: Sequence[EvaluationCase]) -> dict[str, object]:
    """Compare current payloads with the v1 all-roles-full-pool projection."""

    old_total = 0
    new_total = 0
    rows: list[dict[str, object]] = []
    for case in cases:
        scenario = build_scenario(case)
        old_case = 0
        new_case = 0
        for role in SpecialistAgentTypeCode:
            agent_input = SpecialistAgentInput(
                agent_type_code=role,
                constraint_envelope=scenario.constraint_envelope,
                envelope_hash=scenario.constraint_envelope.envelope_hash,
                exercise_pool=scenario.exercise_pool,
                pool_hash=scenario.exercise_pool.pool_hash,
            )
            current = specialist_payload(agent_input)
            new_case += _serialized_bytes(current)
            v1_projection = {
                **current,
                "exercise_pool": project_exercise_pool(scenario.exercise_pool),
            }
            old_case += _serialized_bytes(v1_projection)
        old_total += old_case
        new_total += new_case
        rows.append(
            {
                "case_id": case.case_id,
                "v1_specialist_payload_bytes": old_case,
                "v2_specialist_payload_bytes": new_case,
                "reduction_rate": round((old_case - new_case) / old_case, 6),
            }
        )
    return {
        "measurement": "canonical specialist input payload bytes; excludes output and tokenizer",
        "case_count": len(rows),
        "v1_specialist_payload_bytes": old_total,
        "v2_specialist_payload_bytes": new_total,
        "reduction_rate": round((old_total - new_total) / old_total, 6),
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = build_payload_size_report(planning_cases(GRAPH_CASES))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
