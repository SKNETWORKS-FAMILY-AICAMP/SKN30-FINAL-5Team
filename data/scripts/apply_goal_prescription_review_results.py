"""Stamp the domain reviewer's verdict onto a prescription review sheet.

The reviewer performs the review; this script only records their verdict so the
result is reproducible and auditable instead of a hand edit. It refuses to run
unless the caller names the reviewer, the approval reference and the review
date, so an approval can never appear without an accountable owner.

The defaults address the goal-expansion sheet. The compound promotion sheet
shares its columns and its policy shape, so it is recorded through the same
command with --input, --output and --policy pointed at its artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    PROJECT_ROOT / "data/validation/review_input/goal_expansion_prescription_review_input.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data/validation/review_results/goal_expansion_prescription_review_results.csv"
)
DEFAULT_POLICY = PROJECT_ROOT / "data/normalized/goal_prescription_review_policy.json"

VERDICT_COLUMNS = (
    "reviewer_role_code",
    "reviewer_reference",
    "evidence_reference",
    "reviewed_at",
    "review_status_code",
)


class ReviewResultError(RuntimeError):
    """Raised when a verdict cannot be recorded truthfully."""


def apply_results(
    *,
    input_path: Path,
    output_path: Path,
    policy_path: Path,
    reviewer_role_code: str,
    reviewer_reference: str,
    evidence_reference: str,
    reviewed_at: str,
    approval_method_code: str,
    review_status_code: str = "DOMAIN_APPROVED",
) -> int:
    for name, value in (
        ("reviewer_reference", reviewer_reference),
        ("evidence_reference", evidence_reference),
        ("reviewed_at", reviewed_at),
        ("approval_method_code", approval_method_code),
    ):
        if not value.strip():
            raise ReviewResultError(f"{name} is required to record a verdict")
    try:
        datetime.fromisoformat(reviewed_at)
    except ValueError as exc:
        raise ReviewResultError("reviewed_at must be ISO 8601 with an offset") from exc

    with input_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)
    if not rows:
        raise ReviewResultError("review sheet is empty")
    missing = [column for column in VERDICT_COLUMNS if column not in fieldnames]
    if missing:
        raise ReviewResultError(f"review sheet is missing columns: {missing}")

    for row in rows:
        row["reviewer_role_code"] = reviewer_role_code
        row["reviewer_reference"] = reviewer_reference
        row["evidence_reference"] = evidence_reference
        row["reviewed_at"] = reviewed_at
        row["review_status_code"] = review_status_code
        row["production_eligible"] = "true" if review_status_code == "DOMAIN_APPROVED" else "false"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["review_status_code"] = review_status_code
    policy["reviewer_role_code"] = reviewer_role_code
    policy["reviewer_reference"] = reviewer_reference
    policy["evidence_reference"] = evidence_reference
    policy["reviewed_at"] = reviewed_at
    policy["status"] = "REVIEWED"
    policy["production_eligible"] = review_status_code == "DOMAIN_APPROVED"
    # Records how the verdict was reached. A batch confirmation by the project
    # owner is not the same evidence class as per-row external expert review,
    # and the artifact must not imply otherwise.
    policy["approval_method_code"] = approval_method_code
    policy_path.write_text(
        json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--reviewer-role-code", default="DOMAIN_REVIEWER")
    parser.add_argument("--reviewer-reference", required=True)
    parser.add_argument("--evidence-reference", required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--approval-method-code", required=True)
    parser.add_argument("--review-status-code", default="DOMAIN_APPROVED")
    args = parser.parse_args()
    count = apply_results(
        input_path=args.input,
        output_path=args.output,
        policy_path=args.policy,
        reviewer_role_code=args.reviewer_role_code,
        reviewer_reference=args.reviewer_reference,
        evidence_reference=args.evidence_reference,
        reviewed_at=args.reviewed_at,
        approval_method_code=args.approval_method_code,
        review_status_code=args.review_status_code,
    )
    print(f"recorded {count} rows -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
