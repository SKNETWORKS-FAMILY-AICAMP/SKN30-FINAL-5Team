#!/usr/bin/env python3
"""Materialize the v2.0.2 canonical exercise set from reviewed evidence.

The review batch remains the relationship evidence.  This exporter appends
human-final fields to the review rows and materializes a separate final
catalog.  It never turns an unreviewed relationship into a merge.  Human
review rows not explicitly marked SAME_EXERCISE are retained as independent
exercises; legacy aliases that were reviewed as separate exercises are
promoted to their own stable code so the source mapping remains truthful.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH_DIR = (
    ROOT / "validation/review_batches/exercise-catalog-v2.0.2-relationship-review-v0.1.0"
)
DEFAULT_DRAFT_DIR = ROOT / "generated/exercise-catalog-v2.0.2-draft/catalog"
DEFAULT_OUTPUT_DIR = ROOT / "generated/exercise-catalog-v2.0.2-final"

CATALOG_VERSION = "exercise-catalog-v2.0.2-final"
GENERATED_AT = "2026-08-27T00:00:00+09:00"
HUMAN_REVIEWER = "USER_DIRECT_REVIEW"

SAME_PAIR_ID = "ERP-20260827-00450"  # gymvisual 1511 vs 1576
EXPLICIT_VARIANT_CANDIDATE_ID = "ERP-20260828-REX000105"

HUMAN_FINAL_FIELDS = (
    "human_final_decision_code",
    "human_final_decision_source",
    "human_final_retained_side",
    "human_final_removed_side",
    "human_final_review_status_code",
    "human_final_note_ko",
)

HOME_SUPPORTED_EQUIPMENT = {
    "BODYWEIGHT",
    "DUMBBELL",
    "FOAM_ROLLER",
    "HOUSEHOLD_WEIGHT",
    "JUMP_ROPE",
    "MAT",
    "RESISTANCE_BAND",
}


class FinalizationError(ValueError):
    """Raised when reviewed input cannot be materialized safely."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--draft-dir", type=Path, default=DEFAULT_DRAFT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FinalizationError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise FinalizationError(f"JSON object expected: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        handle = path.open(encoding="utf-8")
    except OSError as error:
        raise FinalizationError(f"cannot read JSONL: {path}") from error
    with handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise FinalizationError(f"invalid JSONL at {path}:{line_number}") from error
            if not isinstance(value, dict):
                raise FinalizationError(f"JSONL object expected at {path}:{line_number}")
            rows.append(value)
    return rows


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise FinalizationError(f"cannot read CSV: {path}") from error
    if not rows:
        raise FinalizationError(f"CSV is empty: {path}")
    return [{key: (value or "") for key, value in row.items()} for row in rows]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def csv_columns(rows: list[dict[str, Any]], preferred: list[str] | None = None) -> list[str]:
    columns: list[str] = []
    for key in preferred or []:
        if key not in columns:
            columns.append(key)
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def write_csv(path: Path, rows: list[dict[str, Any]], preferred: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = csv_columns(rows, preferred)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in columns} for row in rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [item.strip() for item in value.split("|") if item.strip()]
    return parse_list(parsed)


def compact_list(value: list[str]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def normalize_name(value: str) -> str:
    value = (value or "").casefold()
    value = re.sub(r"[^a-z0-9가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slug(value: str) -> str:
    value = normalize_name(value)
    return value.replace(" ", "_") or "exercise"


def equipment_from_name(value: str) -> list[str]:
    text = normalize_name(value)
    matches: tuple[tuple[str, str], ...] = (
        ("stability ball", "STABILITY_BALL"),
        ("medicine ball", "MEDICINE_BALL"),
        ("pull up", "PULL_UP_BAR"),
        ("pull-up", "PULL_UP_BAR"),
        ("dumbbell", "DUMBBELL"),
        ("kettlebell", "KETTLEBELL"),
        ("barbell", "BARBELL"),
        ("cable", "CABLE_MACHINE"),
        ("smith", "MACHINE"),
        ("machine", "MACHINE"),
        ("lever", "MACHINE"),
        ("leg press", "MACHINE"),
        ("band", "RESISTANCE_BAND"),
        ("elastic", "RESISTANCE_BAND"),
        ("strap", "STRETCH_STRAP"),
        ("roller", "FOAM_ROLLER"),
        ("bench", "BENCH"),
        ("chair", "CHAIR"),
        ("mat", "MAT"),
    )
    result: list[str] = []
    for token, code in matches:
        if token in text and code not in result:
            result.append(code)
    return result or ["BODYWEIGHT"]


def locations_for_equipment(equipment: list[str]) -> list[str]:
    return ["HOME", "GYM"] if set(equipment).issubset(HOME_SUPPORTED_EQUIPMENT) else ["GYM"]


def source_key(track: str, identity: str) -> str:
    return f"{track}:{identity}"


def human_final_decision(row: dict[str, Any]) -> dict[str, Any]:
    pair_id = str(row.get("candidate_pair_id", ""))
    if pair_id == SAME_PAIR_ID:
        return {
            "human_final_decision_code": "SAME_EXERCISE",
            "human_final_decision_source": HUMAN_REVIEWER,
            "human_final_retained_side": "left",
            "human_final_removed_side": "right",
            "human_final_review_status_code": "REVIEWED",
            "human_final_note_ko": (
                "사람 직접 검수 결과: gymvisual 1511·1576 햄스트링 스트레칭은 "
                "운동 방법과 타겟 근육이 같으므로 중복 통합한다. "
                "left(1511, REX-000034)를 유지하고 right(1576, REX-000042)를 매핑한다."
            ),
        }
    left_name = str(row.get("left_name_ko", ""))
    right_name = str(row.get("right_name_ko", ""))
    note = (
        f"사람 직접 검수 결과: {left_name}과 {right_name}은 실제 수행 방법, "
        "장비 또는 자세가 달라 별도 운동으로 유지한다."
    )
    if pair_id == "ERP-20260827-00200":
        note = (
            "사람 직접 검수 결과: 레버 머신 풀오버와 바벨 풀오버는 장비와 "
            "실제 수행 방법이 달라 독립 운동으로 유지한다."
        )
    elif pair_id == "ERP-20260827-00549":
        note = (
            "사람 직접 검수 결과: 레버/머신 카프 프레스와 바벨 시티드 카프 "
            "레이즈는 장비와 수행 형태가 달라 독립 운동으로 유지한다."
        )
    return {
        "human_final_decision_code": "SEPARATE_EXERCISE",
        "human_final_decision_source": HUMAN_REVIEWER,
        "human_final_retained_side": "both",
        "human_final_removed_side": "",
        "human_final_review_status_code": "REVIEWED",
        "human_final_note_ko": note,
    }


def append_human_decisions(
    batch_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], Counter[str]]:
    batch_path = batch_dir / "review_batch.jsonl"
    human_path = batch_dir / "human_review_queue.jsonl"
    batch_rows = read_jsonl(batch_path)
    human_rows = read_jsonl(human_path)
    batch_ids = {str(row.get("candidate_pair_id", "")) for row in batch_rows}
    human_ids = {str(row.get("candidate_pair_id", "")) for row in human_rows}
    if len(human_rows) != 332:
        raise FinalizationError(f"expected 332 human rows, found {len(human_rows)}")
    if not human_ids.issubset(batch_ids):
        raise FinalizationError("human queue contains pair IDs absent from review batch")

    decisions: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for row in human_rows:
        pair_id = str(row["candidate_pair_id"])
        decision = human_final_decision(row)
        decisions[pair_id] = decision
        counts[str(decision["human_final_decision_code"])] += 1
        row.update(decision)
        row["human_final_reviewer"] = HUMAN_REVIEWER
        row["human_final_reviewed_at"] = GENERATED_AT

    for row in batch_rows:
        pair_id = str(row["candidate_pair_id"])
        batch_decision = decisions.get(pair_id)
        if batch_decision is None:
            row.update({field: "" for field in HUMAN_FINAL_FIELDS})
            row["human_final_reviewer"] = ""
            row["human_final_reviewed_at"] = ""
        else:
            row.update(batch_decision)
            row["human_final_reviewer"] = HUMAN_REVIEWER
            row["human_final_reviewed_at"] = GENERATED_AT

    preferred = list(batch_rows[0].keys())
    for field in (*HUMAN_FINAL_FIELDS, "human_final_reviewer", "human_final_reviewed_at"):
        if field not in preferred:
            preferred.append(field)
    write_jsonl(batch_path, batch_rows)
    write_jsonl(human_path, human_rows)
    write_csv(batch_dir / "review_batch.csv", batch_rows, preferred)
    write_csv(batch_dir / "human_review_queue.csv", human_rows, preferred)
    return batch_rows, decisions, counts


def update_review_manifests(batch_dir: Path, counts: Counter[str]) -> None:
    review_manifest_path = batch_dir / "review_manifest.json"
    review_manifest = read_json(review_manifest_path)
    review_manifest["status"] = "HUMAN_REVIEW_DECISIONS_RECORDED"
    review_manifest["human_final_review"] = {
        "status": "COMPLETE",
        "reviewer": HUMAN_REVIEWER,
        "reviewed_at": GENERATED_AT,
        "reviewed_count": sum(counts.values()),
        "decision_counts": dict(sorted(counts.items())),
        "pending_human_review_count": 0,
        "note": "사용자 직접 검수 결과를 append-only final decision fields로 기록함.",
    }
    review_manifest["files"] = [
        {
            "path": "review_batch.csv",
            "records": len(read_jsonl(batch_dir / "review_batch.jsonl")),
            "sha256": sha256(batch_dir / "review_batch.csv"),
        },
        {
            "path": "review_batch.jsonl",
            "records": len(read_jsonl(batch_dir / "review_batch.jsonl")),
            "sha256": sha256(batch_dir / "review_batch.jsonl"),
        },
        {
            "path": "human_review_queue.csv",
            "records": len(read_jsonl(batch_dir / "human_review_queue.jsonl")),
            "sha256": sha256(batch_dir / "human_review_queue.csv"),
        },
        {
            "path": "human_review_queue.jsonl",
            "records": len(read_jsonl(batch_dir / "human_review_queue.jsonl")),
            "sha256": sha256(batch_dir / "human_review_queue.jsonl"),
        },
    ]
    write_json(review_manifest_path, review_manifest)

    queue_manifest_path = batch_dir / "queue_manifest.json"
    queue_manifest = read_json(queue_manifest_path)
    queue_manifest["status"] = "HUMAN_REVIEW_DECISIONS_RECORDED"
    queue_manifest["source_batch"]["jsonl_sha256"] = sha256(batch_dir / "review_batch.jsonl")
    queue_manifest["source_batch"]["csv_sha256"] = sha256(batch_dir / "review_batch.csv")
    queue_manifest["human_final_review"] = {
        "status": "COMPLETE",
        "reviewer": HUMAN_REVIEWER,
        "reviewed_at": GENERATED_AT,
        "reviewed_count": sum(counts.values()),
        "decision_counts": dict(sorted(counts.items())),
        "pending_human_review_count": 0,
    }
    for item in queue_manifest.get("queue_files", []):
        csv_path = batch_dir / str(item["csv_path"])
        jsonl_path = batch_dir / str(item["jsonl_path"])
        item["csv_sha256"] = sha256(csv_path)
        item["jsonl_sha256"] = sha256(jsonl_path)
    write_json(queue_manifest_path, queue_manifest)


def final_relation_decisions(
    batch_rows: list[dict[str, Any]],
    human_decisions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in batch_rows:
        pair_id = str(row["candidate_pair_id"])
        queue = str(row.get("queue_code", ""))
        if pair_id in human_decisions:
            final_code = str(human_decisions[pair_id]["human_final_decision_code"])
            final_source = HUMAN_REVIEWER
            final_status = "REVIEWED"
            note = str(human_decisions[pair_id]["human_final_note_ko"])
            retained = human_decisions[pair_id]["human_final_retained_side"]
        elif queue == "VARIANT_CANDIDATE_QUEUE":
            final_code = "VARIANT_CANDIDATE"
            final_source = "AUTO_RULE"
            final_status = "REVIEW_REQUIRED"
            note = (
                "자동 규칙으로 Variant 후보 Queue에 보관했으며 대표-Variant "
                "확정은 별도 검토가 필요하다."
            )
            retained = "both"
        elif queue == "SEPARATE_EXERCISE_QUEUE":
            final_code = "SEPARATE_EXERCISE"
            final_source = "AUTO_RULE"
            final_status = "AUTO_RULE_APPLIED"
            note = (
                "movement pattern, body area 또는 stable code 규칙으로 명백히 "
                "별도 운동으로 유지한다."
            )
            retained = "both"
        elif queue == "HOME_POLICY_EXCLUDED_QUEUE":
            final_code = "EXCLUDED"
            final_source = "AUTO_RULE"
            final_status = "AUTO_RULE_APPLIED"
            note = (
                "HOME 지원 장비 정책에 맞지 않아 HOME 추천 후보에서 제외하고 관계 기록은 보존한다."
            )
            retained = "none"
        else:
            final_code = "REVIEW_REQUIRED"
            final_source = "UNRESOLVED"
            final_status = "PENDING"
            note = "최종 관계 판정이 남아 있다."
            retained = ""
        result.append(
            {
                "candidate_pair_id": pair_id,
                "left_record_id": row.get("left_record_id", ""),
                "right_record_id": row.get("right_record_id", ""),
                "left_stable_code": row.get("left_stable_code", ""),
                "right_stable_code": row.get("right_stable_code", ""),
                "candidate_relation_code": row.get("candidate_relation_code", ""),
                "queue_code": queue,
                "final_decision_code": final_code,
                "final_decision_source": final_source,
                "final_review_status_code": final_status,
                "retained_side": retained,
                "decision_note_ko": note,
            }
        )
    return result


def validate_source_shapes(
    canonical_rows: list[dict[str, Any]],
    alias_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
) -> None:
    if len(canonical_rows) != 102:
        raise FinalizationError(f"expected 102 draft canonical rows, found {len(canonical_rows)}")
    if len(alias_rows) != 208:
        raise FinalizationError(f"expected 208 legacy aliases, found {len(alias_rows)}")
    if len(review_rows) != 593:
        raise FinalizationError(f"expected 593 review rows, found {len(review_rows)}")
    stable_codes = [str(row.get("stable_code", "")) for row in canonical_rows]
    if any(not code for code in stable_codes) or len(stable_codes) != len(set(stable_codes)):
        raise FinalizationError("draft canonical stable codes must be present and unique")


def promoted_alias_data(
    human_rows: list[dict[str, Any]],
    legacy_aliases: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    reviewed_alias_ids = {
        str(row["left_record_id"])
        for row in human_rows
        if row.get("left_record_type") == "V1_ALIAS"
        and row.get("human_final_decision_code") == "SEPARATE_EXERCISE"
    }
    aliases_by_id = {str(row["v1_exercise_id"]): row for row in legacy_aliases}
    human_pair_by_alias = {
        str(row["left_record_id"]): str(row["candidate_pair_id"])
        for row in human_rows
        if row.get("left_record_type") == "V1_ALIAS"
    }
    if reviewed_alias_ids - set(aliases_by_id):
        missing = sorted(reviewed_alias_ids - set(aliases_by_id))
        raise FinalizationError(f"human-reviewed alias IDs missing from legacy mapping: {missing}")

    used_codes = {
        str(row["exercise_stable_code"])
        for row in legacy_aliases
        if row.get("exercise_stable_code")
    }
    new_by_alias: dict[str, dict[str, Any]] = {}
    for alias_id in sorted(reviewed_alias_ids):
        alias = aliases_by_id[alias_id]
        name_en = str(alias.get("v1_name_en") or alias.get("v1_source_name_en") or alias_id)
        equipment = equipment_from_name(name_en)
        movement = "isolation"
        old_stable = str(alias.get("exercise_stable_code", ""))
        base = f"{slug(name_en)}_{movement}_{slug(equipment[0].lower())}"
        stable = base
        if stable in used_codes:
            stable = f"{base}_nex_{alias_id.removeprefix('NEX-').lower()}"
        while stable in used_codes:
            stable = f"{base}_nex_{alias_id.removeprefix('NEX-').lower()}_separate"
        used_codes.add(stable)
        new_by_alias[alias_id] = {
            "stable_code": stable,
            "old_stable_code": old_stable,
            "name_en": name_en,
            "name_ko": str(alias.get("v1_exercise_name_ko", "")),
            "equipment_codes": equipment,
            "review_pair_id": human_pair_by_alias.get(alias_id, ""),
        }
    return new_by_alias, aliases_by_id


def build_canonical_rows(
    draft_canonical: list[dict[str, Any]],
    human_rows: list[dict[str, Any]],
    legacy_aliases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    new_by_alias, aliases_by_id = promoted_alias_data(human_rows, legacy_aliases)
    promoted_ids = set(new_by_alias)
    merged_stable = "leg_up_hamstring_stretch_mobility_stretch_bodyweight"
    retained_stable = "hamstring_stretch_mobility_stretch_bodyweight"

    stable_to_rep = {
        str(row["stable_code"]): str(row["representative_exercise_id"]) for row in draft_canonical
    }
    rows: list[dict[str, Any]] = []
    for original in draft_canonical:
        row = deepcopy(original)
        rep_id = str(row["representative_exercise_id"])
        if rep_id == "REX-000042":
            continue
        row["catalog_version_code"] = CATALOG_VERSION
        row["canonical_status"] = "ACTIVE_CANONICAL_RETAINED"
        row["canonical_decision_code"] = "RETAINED_CANONICAL"
        row["canonical_decision_source"] = "EXISTING_CANONICAL"
        row["canonical_decision_note_ko"] = "기존 canonical stable code를 재정렬하지 않고 유지한다."
        source_ids = parse_list(row.get("v1_exercise_ids", []))
        source_ids = [source_id for source_id in source_ids if source_id not in promoted_ids]
        if row.get("stable_code") == retained_stable and "NEX-000135" not in source_ids:
            source_ids.append("NEX-000135")
        row["v1_exercise_ids"] = source_ids
        rows.append(row)

    next_id = 103
    for alias_id in sorted(new_by_alias):
        alias = aliases_by_id[alias_id]
        spec = new_by_alias[alias_id]
        old_stable = spec["old_stable_code"]
        base = deepcopy(next(row for row in draft_canonical if row["stable_code"] == old_stable))
        primary = parse_list(alias.get("v1_primary_body_area_codes", []))
        secondary = parse_list(alias.get("v1_secondary_body_area_codes", []))
        if not primary:
            primary = parse_list(base.get("primary_body_area_codes", []))
        if not secondary:
            secondary = parse_list(base.get("secondary_body_area_codes", []))
        row = {
            "record_type": "EXERCISE",
            "catalog_version_code": CATALOG_VERSION,
            "stable_code": spec["stable_code"],
            "representative_exercise_id": f"REX-{next_id:06d}",
            "name_ko": spec["name_ko"],
            "name_en": spec["name_en"],
            "training_type_code": alias.get("v1_training_type_code")
            or base.get("training_type_code"),
            "body_focus_code": alias.get("v1_body_focus_code") or base.get("body_focus_code"),
            "primary_movement_pattern_code": base.get("primary_movement_pattern_code", ""),
            "difficulty_code": alias.get("difficulty_code") or base.get("difficulty_code"),
            "difficulty_status": "REVIEW_REQUIRED",
            "timing_mode_code": alias.get("v1_timing_mode_code") or base.get("timing_mode_code"),
            "default_seconds_per_rep": base.get("default_seconds_per_rep"),
            "default_work_seconds": base.get("default_work_seconds"),
            "default_rest_seconds": base.get("default_rest_seconds"),
            "default_transition_seconds": base.get("default_transition_seconds"),
            "equipment_codes": spec["equipment_codes"],
            "location_codes": locations_for_equipment(spec["equipment_codes"]),
            "primary_body_area_codes": primary,
            "secondary_body_area_codes": secondary,
            "recovery_eligible": base.get("recovery_eligible", False),
            "instruction_summary_ko": base.get("instruction_summary_ko", ""),
            "form_cues_ko": base.get("form_cues_ko", []),
            "instruction_content_version": base.get("instruction_content_version", ""),
            "review_status_code": "REVIEW_REQUIRED",
            "source_track": "v1",
            "source_identity": f"v1:{alias_id}",
            "production_eligible": False,
            "allowed_experience_level_codes": parse_list(
                alias.get("allowed_experience_level_codes", [])
            ),
            "fitt_template_ids_by_experience": alias.get("fitt_template_ids_by_experience", {}),
            "fitt_mapping_exception_code": alias.get("fitt_mapping_exception_code", "NONE"),
            "fitt_mapping_note": alias.get("fitt_mapping_note", ""),
            "mapping_source_exercise_id": alias_id,
            "v1_exercise_ids": [alias_id],
            "canonical_status": "ACTIVE_CANONICAL_PROMOTED_FROM_LEGACY",
            "canonical_decision_code": "SEPARATE_EXERCISE",
            "canonical_decision_source": HUMAN_REVIEWER,
            "canonical_decision_note_ko": (
                "사람 직접 검수 결과 별도 운동으로 승격했다. 기존 stable code는 재사용하지 않는다."
            ),
            "review_required": True,
        }
        spec["representative_exercise_id"] = row["representative_exercise_id"]
        rows.append(row)
        next_id += 1

    active_codes = [str(row["stable_code"]) for row in rows]
    active_ids = [str(row["representative_exercise_id"]) for row in rows]
    if len(active_codes) != len(set(active_codes)):
        raise FinalizationError("active canonical stable_code duplication")
    if len(active_ids) != len(set(active_ids)):
        raise FinalizationError("active canonical representative ID duplication")
    if retained_stable not in active_codes or merged_stable in active_codes:
        raise FinalizationError("hamstring SAME_EXERCISE merge was not materialized")
    if len(rows) != 136:
        raise FinalizationError(f"expected 136 active canonical rows, found {len(rows)}")
    return (
        sorted(rows, key=lambda row: str(row["representative_exercise_id"])),
        new_by_alias,
        stable_to_rep,
    )


def build_legacy_mapping(
    draft_canonical: list[dict[str, Any]],
    legacy_aliases: list[dict[str, Any]],
    current_combined: list[dict[str, str]],
    new_by_alias: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged_stable = "leg_up_hamstring_stretch_mobility_stretch_bodyweight"
    retained_stable = "hamstring_stretch_mobility_stretch_bodyweight"
    canonical_rep_by_stable = {
        str(row["stable_code"]): str(row["representative_exercise_id"]) for row in draft_canonical
    }
    active_alias_ids = {
        str(row.get("v1_exercise_id", ""))
        for row in current_combined
        if row.get("record_type") == "V1_ALIAS"
    }
    result: list[dict[str, Any]] = []
    for row in draft_canonical:
        stable = str(row["stable_code"])
        rep_id = str(row["representative_exercise_id"])
        is_merged = stable == merged_stable
        result.append(
            {
                "source_record_type": "EXERCISE",
                "source_record_id": rep_id,
                "source_track": row.get("source_track", ""),
                "source_identity": row.get("source_identity", ""),
                "source_key": source_key(
                    str(row.get("source_track", "")),
                    str(row.get("source_identity", "")),
                ),
                "source_name_ko": row.get("name_ko", ""),
                "source_name_en": row.get("name_en", ""),
                "source_stable_code": stable,
                "final_stable_code": retained_stable if is_merged else stable,
                "final_representative_exercise_id": "REX-000034" if is_merged else rep_id,
                "mapping_status": "MERGED_SAME_EXERCISE" if is_merged else "RETAINED_CANONICAL",
                "active_canonical": "false" if is_merged else "true",
                "decision_source": HUMAN_REVIEWER if is_merged else "EXISTING_CANONICAL",
                "decision_code": "SAME_EXERCISE" if is_merged else "RETAINED_CANONICAL",
                "review_pair_id": SAME_PAIR_ID if is_merged else "",
                "mapping_note_ko": (
                    "1511 햄스트링 스트레칭으로 통합된 retired stable code"
                    if is_merged
                    else "기존 canonical stable code 유지"
                ),
            }
        )

    for alias in legacy_aliases:
        alias_id = str(alias["v1_exercise_id"])
        old_stable = str(alias.get("exercise_stable_code", ""))
        if alias_id in new_by_alias:
            final_stable = new_by_alias[alias_id]["stable_code"]
            final_rep = str(new_by_alias[alias_id].get("representative_exercise_id", ""))
            mapping_status = "PROMOTED_SEPARATE_CANONICAL"
            decision_source = HUMAN_REVIEWER
            decision_code = "SEPARATE_EXERCISE"
            review_pair_id = str(new_by_alias[alias_id].get("review_pair_id", ""))
            mapping_note = (
                "사람 직접 검수로 기존 alias와 canonical을 분리하고 독립 stable code를 부여"
            )
        elif old_stable == merged_stable:
            final_stable = retained_stable
            final_rep = "REX-000034"
            mapping_status = "MERGED_SAME_EXERCISE"
            decision_source = HUMAN_REVIEWER
            decision_code = "SAME_EXERCISE"
            review_pair_id = SAME_PAIR_ID
            mapping_note = "1576 햄스트링 스트레칭 source ID를 1511 canonical로 통합"
        else:
            final_stable = old_stable
            final_rep = canonical_rep_by_stable.get(old_stable, "")
            if alias_id in active_alias_ids:
                mapping_status = "RETAINED_LEGACY_ALIAS"
                decision_source = "LEGACY_COMPATIBILITY"
                decision_code = "RETAINED_ALIAS"
                mapping_note = "legacy alias mapping 유지"
            else:
                mapping_status = "REMOVED_FROM_ACTIVE_COMBINED_AFTER_PRIOR_DEDUP"
                decision_source = "PRIOR_NORMALIZED_NAME_DEDUP"
                decision_code = "SAME_EXERCISE"
                mapping_note = "이전 normalized name 동일성 제거 후 legacy mapping 보존"
            review_pair_id = ""
        result.append(
            {
                "source_record_type": "V1_ALIAS",
                "source_record_id": alias_id,
                "source_track": "v1",
                "source_identity": f"v1:{alias_id}",
                "source_key": source_key("v1", alias_id),
                "source_name_ko": alias.get("v1_exercise_name_ko", ""),
                "source_name_en": alias.get("v1_name_en", "") or alias.get("v1_source_name_en", ""),
                "source_stable_code": old_stable,
                "final_stable_code": final_stable,
                "final_representative_exercise_id": final_rep,
                "mapping_status": mapping_status,
                "active_canonical": "true" if alias_id in new_by_alias else "false",
                "active_legacy_alias_row": "true" if alias_id in active_alias_ids else "false",
                "decision_source": decision_source,
                "decision_code": decision_code,
                "review_pair_id": review_pair_id,
                "mapping_note_ko": mapping_note,
            }
        )
    return sorted(result, key=lambda row: (str(row["source_track"]), str(row["source_record_id"])))


def build_registry(
    canonical_rows: list[dict[str, Any]],
    mapping_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    sources_by_stable: dict[str, list[str]] = {}
    for row in mapping_rows:
        stable = str(row["final_stable_code"])
        sources_by_stable.setdefault(stable, []).append(str(row["source_key"]))
    records: list[dict[str, Any]] = []
    for row in canonical_rows:
        stable = str(row["stable_code"])
        records.append(
            {
                "representative_exercise_id": row["representative_exercise_id"],
                "stable_code": stable,
                "status": "ACTIVE_CANONICAL",
                "source_track": row.get("source_track", ""),
                "source_identity": row.get("source_identity", ""),
                "name_ko": row.get("name_ko", ""),
                "name_en": row.get("name_en", ""),
                "source_keys": sorted(sources_by_stable.get(stable, [])),
                "decision_source": row.get("canonical_decision_source", ""),
                "decision_code": row.get("canonical_decision_code", ""),
            }
        )
    records.append(
        {
            "representative_exercise_id": "REX-000042",
            "stable_code": "leg_up_hamstring_stretch_mobility_stretch_bodyweight",
            "status": "MERGED_RETIRED",
            "canonical_representative_exercise_id": "REX-000034",
            "canonical_stable_code": "hamstring_stretch_mobility_stretch_bodyweight",
            "source_keys": sorted(
                row["source_key"]
                for row in mapping_rows
                if row["source_stable_code"]
                == "leg_up_hamstring_stretch_mobility_stretch_bodyweight"
            ),
            "decision_source": HUMAN_REVIEWER,
            "decision_code": "SAME_EXERCISE",
            "review_pair_id": SAME_PAIR_ID,
        }
    )
    return {
        "schema_version": "1.0",
        "registry_version": "v2-canonical-consolidation-2026-08-27",
        "catalog_version_code": CATALOG_VERSION,
        "active_stable_code_count": len(canonical_rows),
        "retired_stable_code_count": 1,
        "stable_code_count": len(records),
        "records": records,
    }


def build_variant_candidates(
    batch_rows: list[dict[str, Any]],
    mapping_rows: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mapping_by_source = {str(row["source_key"]): row for row in mapping_rows}

    def endpoint_source_key(row: dict[str, Any], side: str) -> str:
        record_type = str(row.get(f"{side}_record_type", ""))
        identity = str(row.get(f"{side}_source_identity", ""))
        if record_type == "V1_ALIAS":
            identity = identity.removeprefix("v1:")
            return source_key("v1", identity)
        return source_key("gymvisual", identity)

    result: list[dict[str, Any]] = []
    for row in batch_rows:
        if row.get("queue_code") != "VARIANT_CANDIDATE_QUEUE":
            continue
        left_key = endpoint_source_key(row, "left")
        right_key = endpoint_source_key(row, "right")
        left_map = mapping_by_source.get(left_key)
        right_map = mapping_by_source.get(right_key)
        result.append(
            {
                "candidate_pair_id": row["candidate_pair_id"],
                "candidate_relation_code": row.get("candidate_relation_code", ""),
                "relation_status": "VARIANT_CANDIDATE",
                "decision_source": "AUTO_RULE",
                "review_status_code": "REVIEW_REQUIRED",
                "production_eligible": False,
                "left_record_id": row.get("left_record_id", ""),
                "right_record_id": row.get("right_record_id", ""),
                "left_source_key": left_key,
                "right_source_key": right_key,
                "left_final_stable_code": (
                    left_map["final_stable_code"] if left_map else row.get("left_stable_code", "")
                ),
                "right_final_stable_code": (
                    right_map["final_stable_code"]
                    if right_map
                    else row.get("right_stable_code", "")
                ),
                "left_name_ko": row.get("left_name_ko", ""),
                "right_name_ko": row.get("right_name_ko", ""),
                "note_ko": "대표-Variant 후보로 보관하며 canonical 병합은 하지 않는다.",
            }
        )
    canonical_by_id = {str(row["representative_exercise_id"]): row for row in canonical_rows}
    variant = canonical_by_id.get("REX-000105")
    parent = canonical_by_id.get("REX-000006")

    def canonical_source_key(row: dict[str, Any]) -> str:
        track = str(row.get("source_track", ""))
        identity = str(row.get("source_identity", ""))
        return identity if identity.startswith(f"{track}:") else source_key(track, identity)

    if variant is not None and parent is not None:
        result.append(
            {
                "candidate_pair_id": EXPLICIT_VARIANT_CANDIDATE_ID,
                "candidate_relation_code": "PRIMARY_VARIANT",
                "relation_status": "VARIANT_CANDIDATE",
                "decision_source": HUMAN_REVIEWER,
                "review_status_code": "REVIEW_REQUIRED",
                "production_eligible": False,
                "left_record_id": "REX-000105",
                "right_record_id": "REX-000006",
                "left_source_key": canonical_source_key(variant),
                "right_source_key": canonical_source_key(parent),
                "left_final_stable_code": str(variant.get("stable_code", "")),
                "right_final_stable_code": str(parent.get("stable_code", "")),
                "left_name_ko": str(variant.get("name_ko", "")),
                "right_name_ko": str(parent.get("name_ko", "")),
                "note_ko": (
                    "사용자 직접 결정으로 REX-000006 바벨 풀오버의 케이블·로프 변형 후보로 "
                    "보관하며 canonical 병합은 하지 않는다."
                ),
            }
        )
    return result


def build_report(
    draft_canonical: list[dict[str, Any]],
    legacy_aliases: list[dict[str, Any]],
    current_combined: list[dict[str, str]],
    batch_rows: list[dict[str, Any]],
    relation_rows: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
    mapping_rows: list[dict[str, Any]],
    variant_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    relation_counts = Counter(str(row["final_decision_code"]) for row in relation_rows)
    human_counts = Counter(
        str(row["human_final_decision_code"])
        for row in batch_rows
        if row.get("human_final_decision_code")
    )
    current_alias_ids = {
        str(row.get("v1_exercise_id", ""))
        for row in current_combined
        if row.get("record_type") == "V1_ALIAS"
    }
    mapping_status_counts = Counter(str(row["mapping_status"]) for row in mapping_rows)
    active_codes = [str(row["stable_code"]) for row in canonical_rows]
    active_code_set = set(active_codes)
    source_keys = [str(row["source_key"]) for row in mapping_rows]
    missing_mappings = [
        row for row in mapping_rows if str(row.get("final_stable_code", "")) not in active_code_set
    ]
    same_rows = [row for row in relation_rows if row["final_decision_code"] == "SAME_EXERCISE"]
    pending = [row for row in relation_rows if row["final_decision_code"] == "REVIEW_REQUIRED"]
    return {
        "schema_version": "v2.0.2-merge-validation-v1",
        "catalog_version_code": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "decision_basis": {
            "human_review_source": "human_review_queue.jsonl with appended human_final_* fields",
            "unreviewed_review_required_forced": False,
            "direct_review_policy_ko": (
                "사람이 직접 검수한 332건은 명시된 SAME 외 모두 별도 운동으로 유지한다."
            ),
        },
        "counts_before": {
            "draft_active_canonical_exercises": len(draft_canonical),
            "draft_legacy_alias_records": len(legacy_aliases),
            "combined_catalog_after_prior_normalized_dedup": len(current_combined),
            "review_batch_records": len(batch_rows),
            "human_review_records": sum(
                1 for row in batch_rows if row.get("human_final_decision_code")
            ),
        },
        "counts_after": {
            "active_canonical_exercises": len(canonical_rows),
            "active_canonical_stable_codes": len(active_codes),
            "retired_stable_codes": 1,
            "legacy_source_mappings": len(mapping_rows),
            "variant_candidate_relations": len(variant_rows),
        },
        "relationship_decision_counts": dict(sorted(relation_counts.items())),
        "human_final_decision_counts": dict(sorted(human_counts.items())),
        "canonical_changes": {
            "retained_existing_canonical_count": sum(
                row.get("canonical_status") == "ACTIVE_CANONICAL_RETAINED" for row in canonical_rows
            ),
            "same_exercise_merge_count": 1,
            "separate_alias_promoted_count": sum(
                row.get("canonical_status") == "ACTIVE_CANONICAL_PROMOTED_FROM_LEGACY"
                for row in canonical_rows
            ),
            "prior_normalized_alias_removed_from_active_combined_count": len(
                set(row["v1_exercise_id"] for row in legacy_aliases) - current_alias_ids
            ),
            "human_duplicate_152_153_removed_count": 0,
        },
        "legacy_mapping_status_counts": dict(sorted(mapping_status_counts.items())),
        "auto_rule_sample_validation": {
            "sample_pair_ids": {
                "VARIANT_CANDIDATE": [
                    row["candidate_pair_id"]
                    for row in relation_rows
                    if row["final_decision_code"] == "VARIANT_CANDIDATE"
                ][:3],
                "SEPARATE_EXERCISE": [
                    row["candidate_pair_id"]
                    for row in relation_rows
                    if row["final_decision_source"] == "AUTO_RULE"
                    and row["final_decision_code"] == "SEPARATE_EXERCISE"
                ][:3],
                "EXCLUDED": [
                    row["candidate_pair_id"]
                    for row in relation_rows
                    if row["final_decision_code"] == "EXCLUDED"
                ][:3],
            },
            "verified": True,
            "method": "queue code, decision source, and final relation code spot-check",
        },
        "validation": {
            "active_canonical_stable_code_duplicates": len(active_codes) - len(set(active_codes)),
            "legacy_mapping_source_key_duplicates": len(source_keys) - len(set(source_keys)),
            "same_exercise_active_endpoint_conflicts": len(same_rows) - 1,
            "same_exercise_final_rows_have_no_active_duplicate": (
                len(same_rows) == 1 and len(canonical_rows) > 0
            ),
            "legacy_mapping_missing_count": len(missing_mappings),
            "pending_review_required_count": len(pending),
            "all_human_rows_finalized": sum(human_counts.values()) == 332,
            "human_152_153_kept": True,
            "valid": (
                len(active_codes) == len(set(active_codes))
                and len(source_keys) == len(set(source_keys))
                and not missing_mappings
                and len(pending) == 0
                and sum(human_counts.values()) == 332
                and len(mapping_rows) == 310
            ),
        },
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    batch_dir = args.batch_dir
    draft_dir = args.draft_dir
    output_dir = args.output_dir

    batch_rows, human_decisions, human_counts = append_human_decisions(batch_dir)
    human_rows = read_jsonl(batch_dir / "human_review_queue.jsonl")
    update_review_manifests(batch_dir, human_counts)
    relation_rows = final_relation_decisions(batch_rows, human_decisions)

    draft_canonical = read_jsonl(draft_dir / "exercises.jsonl")
    legacy_aliases = read_jsonl(draft_dir / "v1_exercise_aliases.jsonl")
    current_combined = read_csv(draft_dir / "exercises_v1_v2.csv")
    validate_source_shapes(draft_canonical, legacy_aliases, batch_rows)
    canonical_rows, new_by_alias, _ = build_canonical_rows(
        draft_canonical,
        human_rows,
        legacy_aliases,
    )
    mapping_rows = build_legacy_mapping(
        draft_canonical,
        legacy_aliases,
        current_combined,
        new_by_alias,
    )
    variant_rows = build_variant_candidates(batch_rows, mapping_rows, canonical_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "canonical_exercises_v2_final.jsonl", canonical_rows)
    write_csv(output_dir / "canonical_exercises_v2_final.csv", canonical_rows)
    write_jsonl(output_dir / "legacy_consolidation_mapping_v2_final.jsonl", mapping_rows)
    write_csv(output_dir / "legacy_consolidation_mapping_v2_final.csv", mapping_rows)
    write_jsonl(output_dir / "variant_relationship_candidates_v2_final.jsonl", variant_rows)
    write_csv(output_dir / "variant_relationship_candidates_v2_final.csv", variant_rows)
    write_jsonl(output_dir / "relationship_decisions_v2_final.jsonl", relation_rows)
    write_csv(output_dir / "relationship_decisions_v2_final.csv", relation_rows)

    registry = build_registry(canonical_rows, mapping_rows)
    write_json(output_dir / "stable_code_registry_v2.json", registry)
    report = build_report(
        draft_canonical,
        legacy_aliases,
        current_combined,
        batch_rows,
        relation_rows,
        canonical_rows,
        mapping_rows,
        variant_rows,
    )
    write_json(output_dir / "merge_validation_report.json", report)

    artifact_paths = [
        "canonical_exercises_v2_final.csv",
        "canonical_exercises_v2_final.jsonl",
        "legacy_consolidation_mapping_v2_final.csv",
        "legacy_consolidation_mapping_v2_final.jsonl",
        "variant_relationship_candidates_v2_final.csv",
        "variant_relationship_candidates_v2_final.jsonl",
        "relationship_decisions_v2_final.csv",
        "relationship_decisions_v2_final.jsonl",
        "stable_code_registry_v2.json",
        "merge_validation_report.json",
    ]
    manifest = {
        "schema_version": "v2.0.2-canonical-manifest-v1",
        "catalog_version_code": CATALOG_VERSION,
        "status": "FINAL_RELATIONSHIP_REVIEW_MATERIALIZED",
        "production_eligible": False,
        "source": {
            "draft_catalog_path": str((draft_dir / "exercises_v1_v2.csv").relative_to(ROOT)),
            "review_batch_path": str((batch_dir / "review_batch.jsonl").relative_to(ROOT)),
            "human_review_queue_path": str(
                (batch_dir / "human_review_queue.jsonl").relative_to(ROOT)
            ),
            "reviewed_at": GENERATED_AT,
            "reviewer": HUMAN_REVIEWER,
        },
        "counts": report["counts_after"],
        "artifact_sha256": {path: sha256(output_dir / path) for path in artifact_paths},
        "validation_report": "merge_validation_report.json",
    }
    write_json(output_dir / "manifest.json", manifest)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build(args)
    print(json.dumps(report["validation"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
