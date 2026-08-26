"""Write a non-activating approval-registry candidate from a validated V2 bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from kspo_fitness100_pipeline import PipelineError
from validate_v2_backend_bundle import validate

DEFAULT_BUNDLE = (
    Path(__file__).resolve().parents[1] / "generated/exercise-catalog-v2.0.1-final/backend_bundle"
)
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "validation/review_results/v2_approval_registry_candidate.json"
)


def build(bundle: Path = DEFAULT_BUNDLE, output: Path = DEFAULT_OUTPUT) -> Path:
    report = validate(bundle)
    manifest = bundle / "bundle_manifest.json"
    raw = manifest.read_bytes()
    bundle_data = json.loads(raw)
    candidate = {
        "schema_version": "1.0",
        "candidate_status": "DRAFT_CANDIDATE",
        "production_eligible": False,
        "activation_status": "NOT_ACTIVATED",
        "catalog_version_code": "exercise-catalog-v2.0.1-final",
        "bundle_manifest_path": (
            "generated/exercise-catalog-v2.0.1-final/backend_bundle/bundle_manifest.json"
        ),
        "bundle_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "bundle_summary": {key: value for key, value in report.items() if key.endswith("records")},
        "projection_status": bundle_data["projection"]["status"],
        "projection_blockers": {
            "alternative_conflict_count": bundle_data["projection"]["alternative_conflict_count"],
            "conflict_report_path": bundle_data["projection"]["conflict_report_path"],
        },
        "required_follow_up": [
            "independent data-side review of goal tags and prescription values",
            "backend local/test importer verification with the approved taxonomy hash",
            "development-lead and PM decision before any activation metadata is recorded",
        ],
        "approval_evidence": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        print(
            json.dumps(
                {
                    "status": "written",
                    "path": str(build(args.bundle, args.out)),
                    "production_eligible": False,
                },
                ensure_ascii=False,
            )
        )
    except (OSError, PipelineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
