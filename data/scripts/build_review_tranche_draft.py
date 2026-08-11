"""Render reviewer-facing DRAFT sheets from a tranche definition.

검토자가 빈 시트 60행을 처음부터 채우는 대신 기계가 채운 초안을 검토·수정하도록 만든다.
이 도구는 승인 상태를 절대 바꾸지 않는다. `review_decision`과 모든 `*_status`는 생성
결과에서도 `PENDING`이며, attribute 행의 `attribute_status`도 `PENDING`이다.

의도적으로 비워 두는 값이 있다.

- `primary_body_area_codes`, `secondary_body_area_codes`: body_area는 사용 근육이 아니라
  관절·부위 부하이고 어떤 원천도 제공하지 않는다. 근육에서 추론하지 않는다.
- `instruction_summary_ko`, `form_cues_ko`, `instruction_content_version`: 자세 문구는
  사람이 작성한다.

`draft_source` 열로 기계가 채운 행을 표시하므로 검토자가 무엇을 반드시 확인해야 하는지
구분할 수 있다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from build_exercise_catalog_seed import ATTRIBUTE_FIELDS, TRACKS, TrackSpec, read_csv, write_csv
from korean_display_name_rules import display_name_problems, duplicate_display_names
from kspo_fitness100_pipeline import PipelineError

DRAFT_SOURCE_MARK = "AI_DRAFT_v0.1.0"
REVIEW_BATCH_ROOT = Path(__file__).resolve().parents[1] / "validation" / "review_batches"


def load_tranche(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"tranche definition is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("tranche definition is not valid JSON") from exc
    if payload.get("status") != "DRAFT" or payload.get("production_eligible") is not False:
        raise PipelineError("tranche definition must stay DRAFT and production-ineligible")
    return payload


def tranche_for_track(payload: dict[str, object], track: TrackSpec) -> dict[str, object]:
    tranches = payload.get("tranches")
    if not isinstance(tranches, list):
        raise PipelineError("tranche definition has no tranches list")
    for entry in tranches:
        if isinstance(entry, dict) and entry.get("track") == track.name:
            return entry
    raise PipelineError(f"tranche definition has no rows for track {track.name}")


def render_drafts(
    track: TrackSpec,
    tranche_path: Path,
    mapping_out: Path,
    attributes_out: Path,
    batch_root: Path = REVIEW_BATCH_ROOT,
) -> dict[str, object]:
    payload = load_tranche(tranche_path)
    entry = tranche_for_track(payload, track)
    batch_dir = (batch_root / str(entry["batch_directory"])).resolve()
    rows = entry.get("rows")
    if not isinstance(rows, list) or not rows:
        raise PipelineError("tranche has no rows")

    mapping_path = batch_dir / track.mapping_file
    with mapping_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        mapping_fields = list(reader.fieldnames or [])
        mapping_rows = list(reader)

    by_position = {row["batch_position"]: row for row in mapping_rows}
    attribute_rows: list[dict[str, object]] = []

    for spec in rows:
        position = str(spec["batch_position"])
        target = by_position.get(position)
        if target is None:
            raise PipelineError(f"batch position {position} is not in {track.mapping_file}")

        name_ko = str(spec["name_ko"])
        problems = display_name_problems(name_ko, source_name=target[track.source_name_field])
        if problems:
            raise PipelineError(f"draft display name for position {position}: {problems[0]}")

        # 내용만 채우고 승인 상태는 건드리지 않는다.
        target["review_normalized_exercise_id"] = str(spec["stable_code"])
        target["review_display_name_ko"] = name_ko
        target["review_taxonomy_code"] = str(spec["movement_pattern_code"]).lower()
        target["reviewer_notes"] = f"{DRAFT_SOURCE_MARK}: 기계 초안. 승인 전 반드시 확인 필요."

        attribute_rows.append(
            {
                "source_identity": target[track.identity_field],
                "review_normalized_exercise_id": str(spec["stable_code"]),
                "review_display_name_ko": name_ko,
                "training_type_code": spec["training_type_code"],
                "body_focus_code": spec["body_focus_code"],
                "primary_movement_pattern_code": spec["movement_pattern_code"],
                "difficulty_code": spec["difficulty_code"],
                "timing_mode_code": spec["timing_mode_code"],
                "default_seconds_per_rep": spec.get("default_seconds_per_rep", ""),
                "default_work_seconds": spec.get("default_work_seconds", ""),
                "default_rest_seconds": spec["default_rest_seconds"],
                # DOMAIN_RULES가 확정한 10~20 범위의 정책값이다.
                "default_transition_seconds": 15,
                "recovery_eligible": spec["recovery_eligible"],
                # 아래 다섯 값은 의도적으로 비운다. 근거는 모듈 docstring 참고.
                "primary_body_area_codes": "",
                "secondary_body_area_codes": "",
                "equipment_codes": spec["equipment_codes"],
                "location_codes": spec["location_codes"],
                "instruction_summary_ko": "",
                "form_cues_ko": "",
                "instruction_content_version": "",
                "draft_source": DRAFT_SOURCE_MARK,
                "attribute_status": "PENDING",
            }
        )

    drafted_names = [str(row["review_display_name_ko"]) for row in attribute_rows]
    duplicates = duplicate_display_names(drafted_names)
    if duplicates:
        raise PipelineError(f"draft display names are duplicated: {', '.join(duplicates)}")
    stable_codes = [str(row["review_normalized_exercise_id"]) for row in attribute_rows]
    if len(set(stable_codes)) != len(stable_codes):
        raise PipelineError("draft normalized exercise IDs are duplicated")

    write_csv(mapping_out, mapping_fields, list(mapping_rows))
    write_csv(attributes_out, ATTRIBUTE_FIELDS, attribute_rows)

    untouched = len(mapping_rows) - len(attribute_rows)
    return {
        "track": track.name,
        "batch": batch_dir.name,
        "mapping_rows": len(mapping_rows),
        "drafted_rows": len(attribute_rows),
        "left_pending_rows": untouched,
        "draft_source": DRAFT_SOURCE_MARK,
        "review_decision": "PENDING",
        "production_eligible": False,
        "status": "draft_written",
    }


def verify_draft_is_unapproved(mapping_out: Path, attributes_out: Path) -> dict[str, object]:
    """생성된 초안이 어떤 승인 상태도 올리지 않았는지 확인한다."""

    mapping_rows = read_csv(mapping_out)
    # `review_status`는 배치 상태(DRAFT)이지 승인 열이 아니므로 제외한다.
    approval_fields = [
        field
        for field in mapping_rows[0]
        if field.startswith("review_") and field.endswith("_status") and field != "review_status"
    ]
    approval_fields += ["review_decision", "review_beginner_suitability"]
    for row in mapping_rows:
        if row["review_status"].strip() != "DRAFT":
            raise PipelineError("draft mapping must keep review_status DRAFT")
        if row["production_eligible"].strip() != "false":
            raise PipelineError("draft mapping must keep production_eligible false")
        for field in approval_fields:
            if row[field].strip() != "PENDING":
                raise PipelineError(f"draft mapping must keep {field} PENDING")

    attribute_rows = read_csv(attributes_out, ATTRIBUTE_FIELDS)
    for row in attribute_rows:
        if row["attribute_status"].strip() != "PENDING":
            raise PipelineError("draft attributes must keep attribute_status PENDING")
        for field in ("primary_body_area_codes", "instruction_summary_ko", "form_cues_ko"):
            if row[field].strip():
                raise PipelineError(f"{field} must be left blank for the domain reviewer")
    return {
        "mapping_rows": len(mapping_rows),
        "attribute_rows": len(attribute_rows),
        "status": "unapproved",
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("track", choices=sorted(TRACKS))
    parser.add_argument("tranche", type=Path)
    parser.add_argument("--mapping-out", type=Path, required=True)
    parser.add_argument("--attributes-out", type=Path, required=True)
    parser.add_argument("--batch-root", type=Path, default=REVIEW_BATCH_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        result = render_drafts(
            TRACKS[args.track],
            args.tranche,
            args.mapping_out,
            args.attributes_out,
            args.batch_root,
        )
        result["verification"] = verify_draft_is_unapproved(args.mapping_out, args.attributes_out)
    except (PipelineError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
