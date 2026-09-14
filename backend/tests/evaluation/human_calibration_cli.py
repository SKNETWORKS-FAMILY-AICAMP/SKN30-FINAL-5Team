"""Generate the PHASE 10 blinded human-calibration files."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.tests.evaluation.human_calibration import write_packet

DEFAULT_JUDGE_PATHS = {
    "MULTI_AGENT": Path("results/comparison/judge_multi_agent.json"),
    "SINGLE_AGENT_RAG": Path("results/comparison/judge_single_agent_rag.json"),
    "SINGLE_LLM": Path("results/comparison/judge_single_llm.json"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pairwise-payload",
        type=Path,
        default=Path("results/pairwise/payloads.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/human_calibration"),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing blank form; never use after human scoring",
    )
    arguments = parser.parse_args()

    blind_path, reference_path = write_packet(
        pairwise_path=arguments.pairwise_payload,
        judge_paths=DEFAULT_JUDGE_PATHS,
        output_dir=arguments.output_dir,
        overwrite=arguments.force,
    )
    print("blind samples=24; architectures hidden; judge scores hidden")
    print(f"reviewer form: {blind_path.resolve()}")
    print(f"sealed reference: {reference_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
