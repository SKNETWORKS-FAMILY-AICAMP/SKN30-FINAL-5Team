"""Generate and verify all canonical PHASE 11 result artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.tests.evaluation.phase11_outputs import write_phase11_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    arguments = parser.parse_args()
    manifest = write_phase11_outputs(arguments.results_dir)
    print(f"phase11 status={manifest['status']} required={manifest['required_artifact_count']}")
    print(f"manifest: {(arguments.results_dir / 'phase11_manifest.json').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
