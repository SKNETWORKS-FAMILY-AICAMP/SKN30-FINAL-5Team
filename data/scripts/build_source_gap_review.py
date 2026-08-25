"""Calculate Gym Visual coverage and queue only source candidates for real gaps.

This stage is deliberately before catalog, safety, and alternative generation.
It consumes the aligned review projection and emits a review queue; it never
creates a service catalog record.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from align_source_candidates import (
    COMMON_COLUMNS,
    DEFAULT_KSPO_INVENTORY,
    DEFAULT_KSPO_REVIEW,
    DEFAULT_WGER_INVENTORY,
    DEFAULT_WGER_REVIEW,
    align_inventory_rows,
    load_csv,
    load_jsonl,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STRENGTH = REPO_ROOT / "data/validation/review_batches/gymvisual_strength_representative_review.csv"
DEFAULT_CARDIO = REPO_ROOT / "data/validation/review_batches/gymvisual_cardio_review.csv"
DEFAULT_MOBILITY = REPO_ROOT / "data/validation/review_batches/gymvisual_mobility_review.csv"
DEFAULT_POLICY = REPO_ROOT / "data/normalized/source_gap_policy.json"
DEFAULT_OUTPUT = REPO_ROOT / "data/validation/review_batches/source-gap-review-v0.4.0"
DEFAULT_REPORT = REPO_ROOT / "data/validation/profiles/source-gap-profile-v0.4.0.json"


def selected_rows(path: Path, decision_column: str, decision: str) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get(decision_column) == decision]


def pipe_values(row: dict[str, str], field: str) -> list[str]:
    return [value for value in row.get(field, "").split("|") if value]


def coverage_profile(strength: Iterable[dict[str, str]], cardio: Iterable[dict[str, str]], mobility: Iterable[dict[str, str]], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    strength_rows = list(strength)
    cardio_rows = list(cardio)
    mobility_rows = list(mobility)

    def counts(rows: Iterable[dict[str, str]], field: str) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for row in rows:
            counter.update(pipe_values(row, field))
        return dict(sorted(counter.items()))

    low_impact_home = sum(
        "LOW" == row.get("impact_level_candidate") and "HOME" in pipe_values(row, "location_code_candidates")
        for row in cardio_rows
    )
    policy = policy or {
        "gaps": {"HOME_LOW_IMPACT_CARDIO": {"minimum_selected": 3, "priority_source": "kspo", "fallback_source": "wger"}},
        "covered_checks": {"STRENGTH_MACHINE_CABLE_BAND": {"required_values": ["MACHINE", "CABLE_MACHINE", "RESISTANCE_BAND"], "priority_source": "wger"}},
    }
    gap_policy = policy["gaps"]["HOME_LOW_IMPACT_CARDIO"]
    gaps = []
    if low_impact_home < int(gap_policy["minimum_selected"]):
        gaps.append(
            {
                "gap_code": "HOME_LOW_IMPACT_CARDIO",
                "observed": low_impact_home,
                "minimum": gap_policy["minimum_selected"],
                "priority_source": gap_policy["priority_source"],
                "fallback_source": gap_policy["fallback_source"],
                "reason": "Gym Visual 선정 결과에서 저충격 홈 유산소 대표 후보가 최소 기준보다 적음.",
            }
        )

    # These are explicit checks, not targets.  They prove that no source
    # supplementation is requested where Gym Visual already covers the class.
    equipment = set(counts(strength_rows, "equipment_code_candidate"))
    required_equipment = set(policy["covered_checks"]["STRENGTH_MACHINE_CABLE_BAND"]["required_values"])
    if required_equipment <= equipment:
        equipment_gap = None
    else:
        equipment_gap = {
            "gap_code": "STRENGTH_MACHINE_CABLE_BAND",
            "missing_values": sorted(required_equipment - equipment),
            "priority_source": policy["covered_checks"]["STRENGTH_MACHINE_CABLE_BAND"]["priority_source"],
        }

    return {
        "policy_version": policy.get("policy_version", "inline-test-policy"),
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "selected_counts": {"strength": len(strength_rows), "cardio": len(cardio_rows), "mobility": len(mobility_rows)},
        "coverage": {
            "strength_targets": counts(strength_rows, "target"),
            "strength_movement_patterns": counts(strength_rows, "movement_pattern_candidate"),
            "strength_equipment": counts(strength_rows, "equipment_code_candidate"),
            "strength_locations": counts(strength_rows, "location_code_candidates"),
            "cardio_movement_patterns": counts(cardio_rows, "movement_pattern_code_candidate"),
            "cardio_locations": counts(cardio_rows, "location_code_candidates"),
            "mobility_movement_patterns": counts(mobility_rows, "movement_pattern_code_candidate"),
            "low_impact_home_cardio": low_impact_home,
        },
        "gaps": gaps,
        "covered_checks": {
            "STRENGTH_MACHINE_CABLE_BAND": equipment_gap is None,
            "MOBILITY_STRETCH": bool(mobility_rows),
        },
        "not_gaps": [
            "family_variant_is_not_alternative_relation",
            "safety_rules_are_not_generated_at_coverage_stage",
            "existing_catalog_safety_and_alternative_artifacts_are_read_only",
        ],
    }


def candidate_matches_gap(row: dict[str, str], gap: dict[str, Any]) -> bool:
    if gap["gap_code"] != "HOME_LOW_IMPACT_CARDIO":
        return False
    if (
        row["source_track"] != "kspo"
        or row["source_scope_status"] != "MVP_SCOPE_REVIEW"
        or row["review_decision"] not in {"", "PENDING"}
    ):
        return False
    source_location = row["source_location"]
    source_name = row["source_name"]
    if "실내" not in source_location or any(token in source_location for token in ("헬스장", "수영장")):
        return False
    low_impact_tokens = ("걷", "스텝", "제자리", "사이드", "실내자전거", "펀치스텝")
    high_impact_tokens = ("점프", "뛰", "달리", "런지", "계단", "줄넘기")
    return any(token in source_name for token in low_impact_tokens) and not any(
        token in source_name for token in high_impact_tokens
    )


def build_queue(rows: Iterable[dict[str, str]], gaps: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    gaps_list = list(gaps)
    queue: list[dict[str, str]] = []
    for row in rows:
        matching = [gap["gap_code"] for gap in gaps_list if candidate_matches_gap(row, gap)]
        if not matching:
            continue
        queued = dict(row)
        queued["gap_codes"] = "|".join(matching)
        queued["gap_review_status"] = "PENDING"
        queued["gap_candidate_status"] = "REVIEW_REQUIRED"
        queued["gap_reason_code"] = "SOURCE_TEXT_MATCH_ONLY"
        queue.append(queued)
    queue.sort(key=lambda row: (row["gap_codes"], row["source_track"], row["source_identity"]))
    return queue


def write_outputs(profile: dict[str, Any], queue: list[dict[str, str]], *, output: Path, report: Path) -> None:
    if output.exists() or report.exists():
        raise FileExistsError("기존 gap 산출물을 덮어쓰지 않기 위해 새 출력 경로가 필요합니다.")
    output.mkdir(parents=True)
    queue_columns = [
        *COMMON_COLUMNS,
        "gap_codes",
        "gap_review_status",
        "gap_candidate_status",
        "gap_reason_code",
    ]
    csv_path = output / "source_gap_review.csv"
    jsonl_path = output / "source_gap_review.jsonl"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=queue_columns)
        writer.writeheader()
        writer.writerows(queue)
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in queue:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    profile["queue"] = {"record_count": len(queue), "csv": str(csv_path), "jsonl": str(jsonl_path)}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strength", type=Path, default=DEFAULT_STRENGTH)
    parser.add_argument("--cardio", type=Path, default=DEFAULT_CARDIO)
    parser.add_argument("--mobility", type=Path, default=DEFAULT_MOBILITY)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--wger-input", type=Path, default=DEFAULT_WGER_INVENTORY)
    parser.add_argument("--kspo-input", type=Path, default=DEFAULT_KSPO_INVENTORY)
    parser.add_argument("--wger-review-input", type=Path, default=DEFAULT_WGER_REVIEW)
    parser.add_argument("--kspo-review-input", type=Path, default=DEFAULT_KSPO_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    strength = selected_rows(args.strength, "screening_decision", "INCLUDE")
    cardio = selected_rows(args.cardio, "screening_decision", "INCLUDE")
    mobility = selected_rows(args.mobility, "selection_screening_decision", "INCLUDE_CANDIDATE")
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    profile = coverage_profile(strength, cardio, mobility, policy)
    aligned = align_inventory_rows(
        load_jsonl(args.wger_input),
        load_jsonl(args.kspo_input),
        load_csv(args.wger_review_input),
        load_csv(args.kspo_review_input),
    )
    profile["aligned_candidate_count"] = len(aligned)
    queue = build_queue(aligned, profile["gaps"])
    write_outputs(profile, queue, output=args.output, report=args.report)
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
