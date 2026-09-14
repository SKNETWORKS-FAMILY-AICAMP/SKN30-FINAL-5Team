"""Analyze completed PHASE 10 human labels against sealed Judge scores."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.tests.evaluation.human_calibration_analysis import (
    CalibrationInputError,
    write_analysis,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--form",
        type=Path,
        default=Path("results/human_calibration/blind_evaluation_form.csv"),
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path("results/human_calibration/sealed_judge_reference.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/human_calibration"),
    )
    arguments = parser.parse_args()
    try:
        results_path, summary_path = write_analysis(
            form_path=arguments.form,
            reference_path=arguments.reference,
            output_dir=arguments.output_dir,
        )
    except CalibrationInputError as error:
        for issue in error.errors:
            print(f"INVALID: {issue}")
        return 2
    print(f"results: {results_path.resolve()}")
    print(f"summary: {summary_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
