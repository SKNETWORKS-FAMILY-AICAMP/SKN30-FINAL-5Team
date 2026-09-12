"""Generate PHASE 9 performance and failure artifacts without provider calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.tests.evaluation.performance_failure import build_phase9_report

DEFAULT_PAID_SUMMARY = Path("results/paid/evaluation_summary.json")
DEFAULT_OUTPUT_DIR = Path("results/phase9")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paid-summary", type=Path, default=DEFAULT_PAID_SUMMARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()

    report = build_phase9_report(arguments.paid_summary)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    output = arguments.output_dir / "performance_failure.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )

    performance = report["performance"]
    failure = report["failure_evaluation"]
    assert isinstance(performance, dict) and isinstance(failure, dict)
    print(
        f"performance runs={performance['run_count']} "
        f"p50={performance['latency_ms']['p50']}ms "  # type: ignore[index]
        f"p95={performance['latency_ms']['p95']}ms"  # type: ignore[index]
    )
    print(
        f"failure scenarios={failure['scenario_count']} "
        f"safe={failure['safe_termination_count']} "
        f"node_errors={failure['unhandled_node_error_count']}"
    )
    print(f"artifact: {output.resolve()}")
    return 0 if failure["safe_termination_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
