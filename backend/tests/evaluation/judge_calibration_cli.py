"""Produce the Round 2 judge calibration from artefacts already on disk.

    uv run python -m backend.tests.evaluation.judge_calibration_cli \
        --run-dir results/round2/heldout_adr22

Costs nothing: every number comes from a completed run's judge scores, case
records and judge payloads. Gate 7 of `ROUND2_IMPROVEMENT_PLAN` asks for the
calibration as a separate artefact, and it is separate because it must not be
produced by the same pass that produces the comparison it qualifies.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from backend.tests.evaluation.judge_calibration import (
    compare_groups,
    paired_preference,
    pearson,
)

ARCHITECTURE_FILES: Final[Mapping[str, str]] = {
    "single_llm": "A. Single LLM",
    "single_agent_rag": "B. Single Agent + RAG",
    "multi_agent": "C. Multi-Agent",
}

# PHASE 10, on the tuning set with unblinded payloads. Carried here so the
# report states what is known about human agreement, not so it can be
# subtracted from held-out numbers taken under different conditions.
ROUND1_HUMAN_CALIBRATION: Final[Mapping[str, Any]] = {
    "sample_count": 24,
    "pearson_correlation": -0.0890,
    "within_0_5_rate": 0.5417,
    "judge_minus_human_by_architecture": {
        "MULTI_AGENT": 0.3333,
        "SINGLE_AGENT_RAG": 0.0646,
        "SINGLE_LLM": -0.4021,
    },
    "applicability": (
        "Measured on the tuning set with unblinded payloads. The held-out "
        "scores are blind and drawn from the deployed catalog, so this bias is "
        "reported, not subtracted."
    ),
}


def _load(run_dir: Path, name: str) -> Any:
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


def build_calibration(run_dir: Path) -> dict[str, Any]:
    judge = {
        arch: {item["case_id"]: item for item in _load(run_dir, f"judge_{arch}.json")["scores"]}
        for arch in ARCHITECTURE_FILES
    }
    cases = {
        arch: {item["case_id"]: item for item in _load(run_dir, f"cases_{arch}.json")}
        for arch in ARCHITECTURE_FILES
    }
    payloads = _load(run_dir, "pairwise_payloads.json")["cases"]

    def scored(arch: str, *, authored_only: bool) -> dict[str, float]:
        return {
            case_id: item["mean_score"]
            for case_id, item in judge[arch].items()
            if item["mean_score"] is not None
            and not (authored_only and cases[arch][case_id]["used_fallback"])
        }

    # 1. Discrimination. The judge was blind, so a template it scores like a
    #    model's plan is a judge that cannot separate them.
    model, fallback = [], []
    for arch in ARCHITECTURE_FILES:
        for case_id, item in judge[arch].items():
            if item["mean_score"] is None:
                continue
            bucket = fallback if cases[arch][case_id]["used_fallback"] else model
            bucket.append(item["mean_score"])
    discrimination = compare_groups(
        label_a="model plan",
        values_a=model,
        label_b="deterministic fallback",
        values_b=fallback,
    )

    # 2. Groundedness, on authored plans only. Pooling fallbacks in reverses the
    #    sign: templates hit the duration exactly and score low, so the
    #    correlation would measure fallback status instead.
    errors: list[float] = []
    feasibility: list[float] = []
    for arch in ARCHITECTURE_FILES:
        for case_id, item in judge[arch].items():
            if cases[arch][case_id]["used_fallback"] or item.get("scores") is None:
                continue
            entry = payloads[case_id]["architectures"][arch.upper()]
            requested = entry["user_context"]["requested_duration_minutes"]
            errors.append(abs(entry["plan"]["estimated_duration_seconds"] - requested * 60))
            feasibility.append(item["scores"]["FEASIBILITY"])

    # 3. Preference, within case. Comparing means across cases confounds the
    #    architecture with which cases happened to be hard.
    def pair(left: str, right: str, *, authored_only: bool) -> dict[str, Any]:
        result = paired_preference(
            scored(left, authored_only=authored_only),
            scored(right, authored_only=authored_only),
        )
        return {
            "architecture_a": ARCHITECTURE_FILES[left],
            "architecture_b": ARCHITECTURE_FILES[right],
            "authored_plans_only": authored_only,
            **result.to_json(),
        }

    return {
        "run_dir": str(run_dir),
        "discrimination": {
            **discrimination.to_json(),
            "by_architecture": {
                ARCHITECTURE_FILES[arch]: compare_groups(
                    label_a="model plan",
                    values_a=[
                        judge[arch][c]["mean_score"]
                        for c in judge[arch]
                        if not cases[arch][c]["used_fallback"]
                        and judge[arch][c]["mean_score"] is not None
                    ],
                    label_b="deterministic fallback",
                    values_b=[
                        judge[arch][c]["mean_score"]
                        for c in judge[arch]
                        if cases[arch][c]["used_fallback"]
                        and judge[arch][c]["mean_score"] is not None
                    ],
                ).to_json()
                for arch in ARCHITECTURE_FILES
            },
        },
        "groundedness": {
            "sample_count": len(errors),
            "pearson_duration_error_vs_feasibility": pearson(errors, feasibility),
            "note": (
                "Authored plans only. FEASIBILITY should fall as the plan drifts "
                "from the requested duration, which the compiler measures exactly."
            ),
        },
        "authored_plan_means": {
            ARCHITECTURE_FILES[arch]: compare_groups(
                label_a=ARCHITECTURE_FILES[arch],
                values_a=list(scored(arch, authored_only=True).values()),
                label_b="all runs",
                values_b=list(scored(arch, authored_only=False).values()),
            ).to_json()
            for arch in ARCHITECTURE_FILES
        },
        "paired_preference": [
            pair("multi_agent", "single_agent_rag", authored_only=False),
            pair("multi_agent", "single_agent_rag", authored_only=True),
            pair("single_agent_rag", "single_llm", authored_only=False),
            pair("multi_agent", "single_llm", authored_only=False),
        ],
        "round1_human_calibration": ROUND1_HUMAN_CALIBRATION,
    }


def _render(calibration: Mapping[str, Any]) -> str:
    lines: list[str] = ["# Judge calibration", ""]
    discrimination = calibration["discrimination"]
    lines.append(
        f"Discrimination: model plan {discrimination['mean_a']} vs deterministic "
        f"fallback {discrimination['mean_b']} (difference {discrimination['difference']}, "
        f"n={discrimination['count_a']}/{discrimination['count_b']})"
    )
    grounded = calibration["groundedness"]
    lines.append(
        f"Groundedness: pearson(duration error, FEASIBILITY) = "
        f"{grounded['pearson_duration_error_vs_feasibility']} over "
        f"{grounded['sample_count']} authored plans"
    )
    lines.append("")
    lines.append("| comparison | authored only | wins A | wins B | ties | p |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for item in calibration["paired_preference"]:
        lines.append(
            f"| {item['architecture_a']} vs {item['architecture_b']} | "
            f"{'yes' if item['authored_plans_only'] else 'no'} | {item['wins_a']} | "
            f"{item['wins_b']} | {item['ties']} | {item['p_value']} |"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results/round2/judge_calibration"))
    arguments = parser.parse_args(argv)

    calibration = build_calibration(arguments.run_dir)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    (arguments.output_dir / "judge_calibration.json").write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rendered = _render(calibration)
    (arguments.output_dir / "judge_calibration.md").write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    print(f"\nartifacts: {arguments.output_dir.resolve()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
