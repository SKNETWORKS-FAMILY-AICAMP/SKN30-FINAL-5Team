#!/usr/bin/env python3
"""Build final-named, fail-closed v2 catalog artifacts.

The source review artifacts are immutable evidence.  This exporter materializes
the approved 2026-08-21 taxonomy decision in a separate final artifact and
keeps policy definitions, representative mappings, and media metadata apart.
It never uploads media or stores media binaries locally. Production media is
managed by the AWS media storage/database boundary; this exporter may only
emit an externally-managed asset key after rights approval.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = DATA_ROOT / "generated" / "exercise-catalog-v2.0.0-final"
TAXONOMY_PATH = DATA_ROOT / "reports" / "representative_exercise_taxonomy_reviewed.csv"
INTEGRATED_PATH = DATA_ROOT / "reports" / "integrated_exercise_review_updated.csv"
ENRICHMENT_PATH = DATA_ROOT / "normalized" / "catalog_enrichment_v3_fitt.csv"
MET_PATH = (
    DATA_ROOT / "generated" / "exercise-met-mapping-v0.1.0" / "exercise_met_mapping_reviewed.csv"
)
MET_APPROVAL_MANIFEST_PATH = (
    DATA_ROOT / "validation" / "review_results" / "met_domain_approval_manifest.csv"
)
ALTERNATIVES_PATH = (
    DATA_ROOT / "generated" / "exercise-alternatives-v0.3.0" / "alternative_relationships.csv"
)
SAFETY_RULES_PATH = (
    DATA_ROOT / "generated" / "exercise-safety-rules-v2.0.0" / "safety_rules_v2.jsonl"
)
SAFETY_MAPPING_PATH = (
    DATA_ROOT / "generated" / "exercise-safety-rules-v2.0.0" / "exercise_safety_mapping_v2.csv"
)
DISCOMFORT_MAPPING_PATH = DATA_ROOT / "normalized" / "v2_discomfort_alternative_mapping.csv"
DECISIONS_PATH = DATA_ROOT / "normalized" / "v2_representative_decisions.json"
CONTENT_PATH = (
    DATA_ROOT
    / "generated"
    / "representative-exercise-content-safety-v0.1.0"
    / "representative_exercise_content.csv"
)

EXPECTED_REPRESENTATIVES = 102
MET_APPROVED_STATUSES = {"APPROVED", "DOMAIN_APPROVED"}
VALID_SOURCE_TRACKS = {"wger", "kspo", "gymvisual"}
VALID_LOCATION_CODES = {"HOME", "GYM"}
FORBIDDEN_V2_EQUIPMENT_CODES = {"BENCH", "CHAIR"}
FORBIDDEN_V2_LOCATION_CODES = {"OUTDOOR"}
APPROVAL_DATE = "2026-08-21T00:00:00+09:00"
APPROVAL_REVIEWER = "DOMAIN_EXPERT_REVIEW"
APPROVAL_REASON = "DOMAIN_EXPERT_TAXONOMY_APPROVAL_2026_08_21"

# These are the 12 final family decisions confirmed for the 2026-08-21
# approval event.  Replacing the placeholder value and retaining review
# metadata avoids the unsafe "status-only" promotion of REVIEW_REQUIRED_*.
FINAL_FAMILY_RESOLUTIONS = {
    "REX-000056": "CARDIO",
    "REX-000057": "HIP_FLEXION",
    "REX-000058": "CARDIO",
    "REX-000061": "KETTLEBELL_SWING",
    "REX-000062": "CARDIO",
    "REX-000063": "HIP_ADDUCTION",
    "REX-000064": "HIP_FLEXION",
    "REX-000065": "CARDIO",
    "REX-000068": "CARDIO",
    "REX-000069": "LEG_PRESS",
    "REX-000070": "CARDIO",
    "REX-000071": "CARDIO",
}

REPRESENTATIVE_COLUMNS = (
    "representative_exercise_id",
    "stable_code",
    "name_ko",
    "name_en",
    "source_name",
    "source_name_en",
    "exercise_family_code",
    "primary_movement_pattern_code",
    "training_type_code",
    "body_focus_code",
    "target_muscle_status",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "body_area_status",
    "equipment_codes",
    "location_codes",
    "setup_condition_ko",
    "difficulty_code",
    "beginner_suitable",
    "recovery_eligible",
    "difficulty_status",
    "fitt_template_id",
    "timing_mode_code",
    "fitt_default_sets",
    "fitt_default_reps",
    "fitt_default_work_seconds",
    "fitt_default_rest_seconds",
    "fitt_default_transition_seconds",
    "default_seconds_per_rep",
    "default_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "instruction_summary_ko",
    "form_cues_ko",
    "instruction_content_version",
    "review_status_code",
    "source_track",
    "source_identity",
    "fitt_intensity_level",
    "fitt_status",
    "met_value",
    "met_intensity_level",
    "met_source",
    "met_status",
    "nex_exercise_ids",
    "nex_exercise_count",
    "taxonomy_review_status",
    "taxonomy_reviewer",
    "taxonomy_reviewed_at",
    "catalog_status",
)
ALTERNATIVE_COLUMNS = (
    "source_exercise_stable_code",
    "alternative_exercise_stable_code",
    "source_representative_exercise_id",
    "alternative_representative_exercise_id",
    "reason_code",
    "goal_preservation_code",
    "difficulty_delta",
    "source_primary_body_area_codes",
    "source_secondary_body_area_codes",
    "alternative_primary_body_area_codes",
    "alternative_secondary_body_area_codes",
    "allowed_equipment_codes",
    "allowed_location_codes",
    "rule_version",
    "alternative_set_version_code",
    "review_status_code",
    "production_eligible",
    "direction_code",
    "pain_score_min",
    "pain_score_max",
    "service_action_code",
    "alternative_strategy_code",
    "source_metadata",
    "source_relation_key",
)
SAFETY_MAPPING_COLUMNS = (
    "representative_exercise_id",
    "rule_id",
    "action",
    "alternative_required",
    "source_rule_ids",
    "activation_status",
    "mapping_review_status",
    "production_eligible",
)
MEDIA_COLUMNS = (
    "representative_exercise_id",
    "s3_key",
    "media_status",
    "rights_review_status",
    "rights_reviewer",
    "rights_reviewed_at",
    "rights_evidence_reference",
)


class FinalizationError(ValueError):
    """Raised when a source artifact cannot safely be finalized."""


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise FinalizationError(f"CSV header missing: {path}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def read_decisions() -> dict[str, Any]:
    try:
        value = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FinalizationError("v2 representative decisions are missing or invalid") from error
    if value.get("schema_version") != "1.0":
        raise FinalizationError("unsupported v2 representative decisions schema")
    return value


def read_content() -> dict[str, dict[str, str]]:
    rows = read_csv(CONTENT_PATH)
    indexed = index_unique(rows, "representative_id", "representative content")
    if len(indexed) != EXPECTED_REPRESENTATIVES:
        raise FinalizationError("representative content must cover every representative")
    return indexed


def split_codes(value: str) -> list[str]:
    return [item for item in value.split("|") if item]


def normalize_equipment_codes(codes: list[str], aliases: dict[str, str]) -> tuple[list[str], str]:
    """Normalize load equipment while keeping support conditions out of codes."""
    raw = [code for code in codes if code]
    mapped = [aliases.get(code, code) for code in raw]
    if "CABLE_MACHINE" in mapped:
        mapped = [code for code in mapped if code != "MACHINE"]
    support = [code for code in raw if code in FORBIDDEN_V2_EQUIPMENT_CODES]
    normalized: list[str] = []
    for code in mapped:
        if code in FORBIDDEN_V2_EQUIPMENT_CODES:
            continue
        if code not in normalized:
            normalized.append(code)
    if not normalized:
        normalized = ["BODYWEIGHT"]
    setup_condition = ""
    if support:
        setup_condition = "안정적인 지지물(벤치 또는 의자 등)을 준비한다."
    return normalized, setup_condition


def sanitize_taxonomy_equipment(value: str) -> tuple[str, str]:
    """Keep taxonomy evidence usable without emitting V2 BENCH/CHAIR codes."""
    parts = value.split(";")
    support_required = False
    cleaned: list[str] = []
    for part in parts:
        if part.startswith("equipment="):
            codes = split_codes(part.removeprefix("equipment="))
            kept = [code for code in codes if code not in FORBIDDEN_V2_EQUIPMENT_CODES]
            support_required = len(kept) != len(codes)
            cleaned.append("equipment=" + "|".join(kept or ["BODYWEIGHT"]))
            continue
        cleaned.append(part)
    condition = "안정적인 지지물(벤치 또는 의자 등)을 준비한다." if support_required else ""
    return ";".join(cleaned), condition


def reviewed_attributes(row: dict[str, str]) -> tuple[list[str], list[str]]:
    reviewed = row.get("reviewed_equipment", "")
    equipment_value = reviewed.split(";", 1)[0].removeprefix("equipment=")
    equipment_codes = split_codes(equipment_value)
    location_value = next(
        (
            part.removeprefix("locations=")
            for part in reviewed.split(";")
            if part.startswith("locations=")
        ),
        "",
    )
    return equipment_codes, split_codes(location_value)


def stable_code_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return token or "unspecified"


def build_stable_code_registry(
    taxonomy_rows: list[dict[str, str]], decisions: dict[str, Any]
) -> dict[str, str]:
    overrides = decisions.get("representative_overrides", {})
    aliases = decisions.get("equipment_aliases", {})
    registry: dict[str, str] = {}
    used: set[str] = set()
    for row in sorted(taxonomy_rows, key=lambda item: item["representative_id"]):
        representative_id = row["representative_id"]
        override = overrides.get(representative_id, {})
        equipment_codes = override.get("equipment_codes") or reviewed_attributes(row)[0]
        equipment_codes, _ = normalize_equipment_codes(equipment_codes, aliases)
        if not equipment_codes:
            equipment_codes = split_codes(row.get("equipment", ""))
        base = "_".join(
            stable_code_token(part)
            for part in (
                row.get("exercise_family", ""),
                row.get("movement_pattern", ""),
                *equipment_codes,
            )
        )
        stable_code = base
        if stable_code in used:
            stable_code = f"{base}_rex_{representative_id.removeprefix('REX-').lower()}"
        if stable_code in used:
            raise FinalizationError(f"stable_code collision: {representative_id}")
        used.add(stable_code)
        registry[representative_id] = stable_code
    if len(registry) != EXPECTED_REPRESENTATIVES or len(set(registry.values())) != len(registry):
        raise FinalizationError(
            "stable_code registry must contain unique codes for all representatives"
        )
    return registry


def runtime_integer(value: str) -> str:
    return value if value.isdigit() and int(value) > 0 else ""


def runtime_json_blockers(rows: list[dict[str, str]]) -> dict[str, int]:
    blockers: dict[str, int] = {}
    required_fields = (
        "stable_code",
        "location_codes",
        "beginner_suitable",
        "recovery_eligible",
        "default_rest_seconds",
        "default_transition_seconds",
        "instruction_summary_ko",
        "form_cues_ko",
        "instruction_content_version",
        "review_status_code",
        "source_track",
        "source_identity",
    )
    for field in required_fields:
        missing = sum(not row.get(field, "") for row in rows)
        if missing:
            blockers[field] = missing
    timing_missing = sum(
        not row.get(
            "default_seconds_per_rep"
            if row.get("timing_mode_code") == "REPS"
            else "default_work_seconds",
            "",
        )
        for row in rows
    )
    if timing_missing:
        blockers["runtime_timing_value"] = timing_missing
    return blockers


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise FinalizationError(f"invalid safety JSON at line {line_number}") from error
        if not isinstance(value, dict):
            raise FinalizationError(f"safety rule must be an object at line {line_number}")
        rules.append(value)
    if not rules:
        raise FinalizationError("safety rule source is empty")
    return rules


def finalized_taxonomy(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(rows) != EXPECTED_REPRESENTATIVES:
        raise FinalizationError(f"taxonomy must contain {EXPECTED_REPRESENTATIVES} representatives")
    by_id = {row["representative_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise FinalizationError("duplicate representative_id in taxonomy")
    unresolved = {
        row["representative_id"]
        for row in rows
        if row["exercise_family"].startswith("REVIEW_REQUIRED_")
    }
    if unresolved != set(FINAL_FAMILY_RESOLUTIONS):
        raise FinalizationError(
            "taxonomy REVIEW_REQUIRED family set does not match the approved resolution set: "
            f"{sorted(unresolved)}"
        )

    finalized: list[dict[str, str]] = []
    for source in rows:
        row = dict(source)
        final_family = FINAL_FAMILY_RESOLUTIONS.get(row["representative_id"])
        if final_family:
            row.update(
                {
                    "exercise_family": final_family,
                    "reviewed_family": final_family,
                    "representative_review_status": "FAMILY_SELECTION_COMPLETE",
                    "review_required": "false",
                    "review_required_codes": "",
                    "removable_review_required_codes": "",
                    "additional_review_required_codes": "",
                    "review_decision": "APPROVED",
                    "review_reason_code": APPROVAL_REASON,
                    "reviewer": APPROVAL_REVIEWER,
                    "reviewed_at": APPROVAL_DATE,
                    "taxonomy_review_status": "TAXONOMY_APPROVED",
                }
            )
        if row["exercise_family"].startswith("REVIEW_REQUIRED_"):
            raise FinalizationError(f"unresolved final family: {row['representative_id']}")
        row["reviewed_equipment"], setup_condition = sanitize_taxonomy_equipment(
            row.get("reviewed_equipment", "")
        )
        row["setup_condition_ko"] = setup_condition
        # The approval event covers taxonomy only.  Do not erase the source
        # row's independent content, safety, license, or media blockers.
        row.update(
            {
                "reviewed_family": row["exercise_family"],
                "reviewed_movement_pattern": row["movement_pattern"],
                "review_decision": "APPROVED",
                "review_reason_code": APPROVAL_REASON,
                "reviewer": APPROVAL_REVIEWER,
                "reviewed_at": APPROVAL_DATE,
                "taxonomy_review_status": "TAXONOMY_APPROVED",
            }
        )
        finalized.append(row)
    return sorted(finalized, key=lambda row: row["representative_id"])


def index_unique(rows: list[dict[str, str]], key: str, label: str) -> dict[str, dict[str, str]]:
    index = {row.get(key, ""): row for row in rows}
    if "" in index or len(index) != len(rows):
        raise FinalizationError(f"{label} must have unique non-empty {key}")
    return index


def selected_nex_by_rex(integrated_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    selected = [row for row in integrated_rows if row.get("representative_selected") == "true"]
    result = index_unique(selected, "representative_id", "selected NEX mapping")
    if len(result) != EXPECTED_REPRESENTATIVES:
        raise FinalizationError("selected NEX mapping must cover every representative")
    return result


def apply_enrichment_to_taxonomy(
    taxonomy_rows: list[dict[str, str]],
    integrated_rows: list[dict[str, str]],
    enrichment_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Replace stale representative attributes with the reviewed enrichment values."""
    selected = selected_nex_by_rex(integrated_rows)
    enrichment = index_unique(enrichment_rows, "exercise_id", "FITT enrichment")
    enriched: list[dict[str, str]] = []
    for source in taxonomy_rows:
        row = dict(source)
        representative_id = row["representative_id"]
        nex_id = selected[representative_id]["normalized_exercise_id"]
        attributes = enrichment.get(nex_id)
        if attributes is None:
            raise FinalizationError(f"enrichment missing for {representative_id}:{nex_id}")
        body_focus = attributes.get("body_focus_code", "")
        difficulty = attributes.get("difficulty_code", "")
        primary = attributes.get("primary_body_area_codes", "")
        secondary = attributes.get("secondary_body_area_codes", "")
        if (
            not body_focus
            or body_focus != body_focus.upper()
            or any("\uac00" <= character <= "\ud7a3" for character in body_focus)
        ):
            raise FinalizationError(f"body focus must be an English machine code: {nex_id}")
        if difficulty not in {"BEGINNER", "INTERMEDIATE", "ADVANCED"}:
            raise FinalizationError(f"difficulty is unresolved or invalid: {nex_id}")
        for field, value in (
            ("primary_body_area_codes", primary),
            ("secondary_body_area_codes", secondary),
        ):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as error:
                raise FinalizationError(f"{field} is not JSON for {nex_id}") from error
            if not isinstance(parsed, list) or any(
                not isinstance(item, str)
                or item != item.upper()
                or any("\uac00" <= character <= "\ud7a3" for character in item)
                for item in parsed
            ):
                raise FinalizationError(f"{field} must contain English machine codes: {nex_id}")
        row.update(
            {
                "target_muscle": body_focus,
                "target_muscle_status": attributes.get("body_focus_status", ""),
                "primary_body_area_codes": primary,
                "secondary_body_area_codes": secondary,
                "body_area_status": attributes.get("body_area_status", ""),
                "difficulty": difficulty,
                "difficulty_status": attributes.get("difficulty_status", ""),
            }
        )
        enriched.append(row)
    return enriched


def catalog_status(fitt: dict[str, str], met_row: dict[str, str]) -> str:
    pending: list[str] = []
    statuses = (
        ("TARGET_MUSCLE_REVIEW", fitt.get("body_focus_status", "")),
        ("BODY_AREA_REVIEW", fitt.get("body_area_status", "")),
        ("DIFFICULTY_REVIEW", fitt.get("difficulty_status", "")),
        ("FITT_REVIEW", fitt.get("fitt_status", "")),
        ("MET_REVIEW", met_row.get("review_status", "")),
    )
    for label, status in statuses:
        approved = (
            status in MET_APPROVED_STATUSES if label == "MET_REVIEW" else status == "APPROVED"
        )
        if not approved:
            pending.append(label)
    pending.append("MEDIA_RIGHTS")
    return "FINAL_CATALOG_PENDING_" + "_AND_".join(pending)


def build_representatives(
    taxonomy_rows: list[dict[str, str]],
    integrated_rows: list[dict[str, str]],
    enrichment_rows: list[dict[str, str]],
    met_rows: list[dict[str, str]],
    stable_codes: dict[str, str],
    decisions: dict[str, Any],
    content_rows: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    taxonomy = index_unique(taxonomy_rows, "representative_id", "final taxonomy")
    index_unique(integrated_rows, "normalized_exercise_id", "integrated catalog")
    enrichment = index_unique(enrichment_rows, "exercise_id", "FITT enrichment")
    met = index_unique(met_rows, "exercise_id", "MET mapping")
    selected = selected_nex_by_rex(integrated_rows)
    overrides = decisions.get("representative_overrides", {})
    aliases = decisions.get("equipment_aliases", {})
    materialization = decisions.get("runtime_materialization", {})
    beginner_by_review = materialization.get("beginner_suitable_by_review_code", {})
    recovery_by_training = materialization.get("recovery_eligible_by_training_type", {})
    default_work_by_training = materialization.get("default_work_seconds_by_training_type", {})
    default_rest_by_training = materialization.get("default_rest_seconds_by_training_type", {})
    content_version = materialization.get("instruction_content_version", "")
    nex_by_rex: dict[str, list[str]] = defaultdict(list)
    for row in integrated_rows:
        representative_id = row.get("representative_id", "")
        nex_id = row.get("normalized_exercise_id", "")
        if representative_id and nex_id:
            nex_by_rex[representative_id].append(nex_id)

    result: list[dict[str, str]] = []
    for representative_id, taxon in sorted(taxonomy.items()):
        source = selected.get(representative_id)
        if source is None:
            raise FinalizationError(f"selected NEX missing for {representative_id}")
        nex_id = source["normalized_exercise_id"]
        fitt = enrichment.get(nex_id)
        met_row = met.get(nex_id)
        if fitt is None or met_row is None:
            raise FinalizationError(f"FITT or MET mapping missing for {representative_id}:{nex_id}")
        override = overrides.get(representative_id, {})
        raw_equipment_codes = override.get("equipment_codes") or reviewed_attributes(taxon)[0]
        equipment_codes, setup_condition = normalize_equipment_codes(raw_equipment_codes, aliases)
        setup_condition = taxon.get("setup_condition_ko", "") or setup_condition
        if not equipment_codes:
            raise FinalizationError(f"equipment codes are unresolved for {representative_id}")
        location_codes = reviewed_attributes(taxon)[1]
        if not location_codes:
            raise FinalizationError(f"location codes are unresolved for {representative_id}")
        if (
            set(location_codes) & FORBIDDEN_V2_LOCATION_CODES
            or not set(location_codes) <= VALID_LOCATION_CODES
        ):
            raise FinalizationError(f"V2 release location must be HOME/GYM: {representative_id}")
        source_track = source.get("source_track", "")
        source_identity = source.get("source_identity", "") or source.get("source_id", "")
        if not source_track or not source_identity:
            raise FinalizationError(f"source identity is unresolved for {representative_id}")
        if source_track not in VALID_SOURCE_TRACKS:
            raise FinalizationError(
                f"exercise source_track must preserve the original track: {representative_id}"
            )
        source_name_en = (
            source.get("name_en") or fitt.get("name_en", "") or source.get("source_name", "")
        )
        if not source_name_en:
            raise FinalizationError(f"source_name_en missing for {representative_id}")
        content = content_rows.get(representative_id)
        if (
            content is None
            or not content.get("short_description")
            or not content.get("how_to_steps")
        ):
            raise FinalizationError(
                f"reviewed representative content missing for {representative_id}"
            )
        try:
            form_cues = json.loads(content["how_to_steps"])
        except json.JSONDecodeError as error:
            raise FinalizationError(
                f"representative content steps are not JSON: {representative_id}"
            ) from error
        training_type = taxon["training_type"]
        timing_mode = fitt.get("timing_mode_code", "")
        if timing_mode not in {"REPS", "DURATION"}:
            raise FinalizationError(f"timing mode is unresolved for {representative_id}")
        reviewed_beginner = taxon.get("beginner_suitable", "")
        if reviewed_beginner not in beginner_by_review:
            raise FinalizationError(f"beginner suitability is unresolved for {representative_id}")
        if training_type not in recovery_by_training:
            raise FinalizationError(f"recovery eligibility is unresolved for {representative_id}")
        runtime_default_rest = default_rest_by_training.get(training_type)
        runtime_default_transition = materialization.get("default_transition_seconds")
        if not isinstance(runtime_default_rest, int) or not isinstance(
            runtime_default_transition, int
        ):
            raise FinalizationError(
                f"runtime rest/transition is unresolved for {representative_id}"
            )
        runtime_seconds_per_rep = materialization.get("default_seconds_per_rep")
        runtime_work_seconds = default_work_by_training.get(training_type)
        if timing_mode == "REPS" and not isinstance(runtime_seconds_per_rep, int):
            raise FinalizationError(f"seconds per rep is unresolved for {representative_id}")
        if timing_mode == "DURATION" and not isinstance(runtime_work_seconds, int):
            raise FinalizationError(f"work seconds is unresolved for {representative_id}")
        result.append(
            {
                "representative_exercise_id": representative_id,
                "stable_code": stable_codes[representative_id],
                "name_ko": taxon["representative_name_ko"],
                "name_en": source_name_en,
                "source_name": source.get("source_name")
                or source.get("source_display_name_ko", ""),
                "source_name_en": source_name_en,
                "exercise_family_code": taxon["exercise_family"],
                "primary_movement_pattern_code": taxon["movement_pattern"],
                "training_type_code": taxon["training_type"],
                "body_focus_code": fitt.get("body_focus_code", ""),
                "target_muscle_status": fitt.get("body_focus_status", ""),
                "primary_body_area_codes": fitt.get("primary_body_area_codes", ""),
                "secondary_body_area_codes": fitt.get("secondary_body_area_codes", ""),
                "body_area_status": fitt.get("body_area_status", ""),
                "equipment_codes": "|".join(equipment_codes),
                "location_codes": "|".join(location_codes),
                "setup_condition_ko": setup_condition,
                "difficulty_code": fitt.get("difficulty_code", ""),
                "beginner_suitable": ("true" if beginner_by_review[reviewed_beginner] else "false"),
                "recovery_eligible": "true" if recovery_by_training[training_type] else "false",
                "difficulty_status": fitt.get("difficulty_status", ""),
                "fitt_template_id": fitt.get("fitt_template_id", ""),
                "timing_mode_code": fitt.get("timing_mode_code", ""),
                "fitt_default_sets": fitt.get("default_sets", ""),
                "fitt_default_reps": fitt.get("default_reps", ""),
                "fitt_default_work_seconds": fitt.get("default_work_seconds", ""),
                "fitt_default_rest_seconds": fitt.get("default_rest_seconds", ""),
                "fitt_default_transition_seconds": fitt.get("default_transition_seconds", ""),
                "default_seconds_per_rep": (
                    str(runtime_seconds_per_rep) if timing_mode == "REPS" else ""
                ),
                "default_work_seconds": (
                    str(runtime_work_seconds) if timing_mode == "DURATION" else ""
                ),
                "default_rest_seconds": str(runtime_default_rest),
                "default_transition_seconds": str(runtime_default_transition),
                "instruction_summary_ko": content["short_description"],
                "form_cues_ko": json.dumps(form_cues, ensure_ascii=False),
                "instruction_content_version": content_version,
                "review_status_code": decisions["domain_review"]["status"],
                "source_track": source_track,
                "source_identity": source_identity,
                "fitt_intensity_level": fitt.get("intensity_level", ""),
                "fitt_status": fitt.get("fitt_status", ""),
                "met_value": met_row.get("met_value", ""),
                "met_intensity_level": met_row.get("intensity_level", ""),
                "met_source": met_row.get("met_source", ""),
                "met_status": met_row.get("review_status", ""),
                "nex_exercise_ids": json.dumps(sorted(nex_by_rex[representative_id])),
                "nex_exercise_count": str(len(nex_by_rex[representative_id])),
                "taxonomy_review_status": taxon["taxonomy_review_status"],
                "taxonomy_reviewer": taxon.get("reviewer", ""),
                "taxonomy_reviewed_at": taxon.get("reviewed_at", ""),
                "catalog_status": catalog_status(fitt, met_row),
            }
        )
    return result


def build_alternatives(
    representative_rows: list[dict[str, str]],
    relation_rows: list[dict[str, str]],
    integrated_rows: list[dict[str, str]],
    enrichment_rows: list[dict[str, str]],
    discomfort_rows: list[dict[str, str]],
    decisions: dict[str, Any],
) -> list[dict[str, str]]:
    by_nex = index_unique(integrated_rows, "normalized_exercise_id", "integrated catalog")
    enrichment = index_unique(enrichment_rows, "exercise_id", "FITT enrichment")
    by_rex = index_unique(
        representative_rows, "representative_exercise_id", "representative catalog"
    )
    difficulty_rank = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}
    result: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()

    def append_relation(
        source_row: dict[str, str],
        alternative_row: dict[str, str],
        *,
        reason_code: str,
        goal: str,
        delta: int,
        relation_key: str,
        metadata: dict[str, str],
        pain_score_min: str = "",
        pain_score_max: str = "",
        service_action_code: str = "",
        alternative_strategy_code: str = "",
    ) -> None:
        key: tuple[str, ...] = (
            (
                source_row["stable_code"],
                alternative_row["stable_code"],
                reason_code,
                relation_key,
            )
            if reason_code == "DISCOMFORT"
            else (
                source_row["stable_code"],
                alternative_row["stable_code"],
                reason_code,
            )
        )
        if key in seen:
            return
        if source_row["stable_code"] == alternative_row["stable_code"]:
            raise FinalizationError(f"alternative relation self-targets: {key}")
        if delta not in {-1, 0}:
            raise FinalizationError(f"alternative difficulty_delta is invalid: {key}")
        if not goal:
            raise FinalizationError(f"alternative goal preservation is missing: {key}")
        seen.add(key)
        materialization = decisions["alternative_materialization"]
        result.append(
            {
                "source_exercise_stable_code": source_row["stable_code"],
                "alternative_exercise_stable_code": alternative_row["stable_code"],
                "source_representative_exercise_id": source_row["representative_exercise_id"],
                "alternative_representative_exercise_id": alternative_row[
                    "representative_exercise_id"
                ],
                "reason_code": reason_code,
                "goal_preservation_code": goal,
                "difficulty_delta": str(delta),
                "source_primary_body_area_codes": source_row["primary_body_area_codes"],
                "source_secondary_body_area_codes": source_row["secondary_body_area_codes"],
                "alternative_primary_body_area_codes": alternative_row["primary_body_area_codes"],
                "alternative_secondary_body_area_codes": alternative_row[
                    "secondary_body_area_codes"
                ],
                "allowed_equipment_codes": alternative_row["equipment_codes"],
                "allowed_location_codes": alternative_row["location_codes"],
                "rule_version": materialization["rule_version"],
                "alternative_set_version_code": materialization["alternative_set_version_code"],
                "review_status_code": "DOMAIN_APPROVED",
                "production_eligible": "false",
                "direction_code": "A_TO_B",
                "pain_score_min": pain_score_min,
                "pain_score_max": pain_score_max,
                "service_action_code": service_action_code,
                "alternative_strategy_code": alternative_strategy_code,
                "source_metadata": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                "source_relation_key": relation_key,
            }
        )

    for source in relation_rows:
        source_id = source["source_exercise_id"]
        alternative_id = source["alternative_exercise_id"]
        source_rex = by_nex[source_id]["representative_id"]
        alternative_rex = by_nex[alternative_id]["representative_id"]
        source_row = by_rex[source_rex]
        alternative_row = by_rex[alternative_rex]
        source_attributes = enrichment.get(source_id, {})
        alternative_attributes = enrichment.get(alternative_id, {})
        source_difficulty = source_attributes.get("difficulty_code", source_row["difficulty_code"])
        alternative_difficulty = alternative_attributes.get(
            "difficulty_code", alternative_row["difficulty_code"]
        )
        delta = difficulty_rank[alternative_difficulty] - difficulty_rank[source_difficulty]
        if delta > 0:
            continue
        if source["alternative_type"] == "SAFETY":
            # Safety alternatives require an explicit approved mapping table;
            # legacy SAFETY rows are not inferred into V2 DISCOMFORT rows.
            continue
        source_equipment = set(source_row["equipment_codes"].split("|"))
        alternative_equipment = set(alternative_row["equipment_codes"].split("|"))
        source_locations = set(source_row["location_codes"].split("|"))
        alternative_locations = set(alternative_row["location_codes"].split("|"))
        if source_locations != alternative_locations:
            reason_code = "LOCATION"
        elif source_equipment != alternative_equipment:
            reason_code = "EQUIPMENT"
        elif delta < 0:
            reason_code = "DIFFICULTY"
        else:
            # A relationship without a current operational reason is not a
            # safe V2 relation and is left for review rather than guessed.
            continue
        append_relation(
            source_row,
            alternative_row,
            reason_code=reason_code,
            goal=source["goal_code"],
            delta=delta,
            relation_key=f"{source_id}:{alternative_id}:{source['alternative_type']}",
            metadata={
                "source_path": str(ALTERNATIVES_PATH.relative_to(DATA_ROOT)),
                "legacy_relationship_type": source["alternative_type"],
                "selection_basis": "REX_ENDPOINT_AND_V2_CATALOG_RECHECK",
            },
        )

    for spec in decisions.get("approved_equipment_relations", []):
        equipment_source = by_rex.get(str(spec.get("source_representative_exercise_id", "")))
        equipment_alternative = by_rex.get(
            str(spec.get("alternative_representative_exercise_id", ""))
        )
        if equipment_source is None or equipment_alternative is None:
            raise FinalizationError("approved equipment relation endpoint is not in V2 catalog")
        if "STRETCH_STRAP" not in equipment_source["equipment_codes"].split("|"):
            raise FinalizationError("approved strap relation source is not STRETCH_STRAP")
        if "BODYWEIGHT" not in equipment_alternative["equipment_codes"].split("|"):
            raise FinalizationError("approved strap relation target is not BODYWEIGHT")
        append_relation(
            equipment_source,
            equipment_alternative,
            reason_code="EQUIPMENT",
            goal=str(spec["goal_preservation_code"]),
            delta=int(spec["difficulty_delta"]),
            relation_key=(
                f"policy:{equipment_source['representative_exercise_id']}:"
                f"{equipment_alternative['representative_exercise_id']}:EQUIPMENT"
            ),
            metadata={
                "source_path": str(DECISIONS_PATH.relative_to(DATA_ROOT)),
                "selection_basis": "APPROVED_STRETCH_STRAP_TO_BODYWEIGHT_RELATION",
            },
        )

    target_muscle_materialization = decisions.get("target_muscle_materialization", {})
    if target_muscle_materialization.get("status") != "DOMAIN_APPROVED":
        raise FinalizationError("target muscle materialization is not domain approved")
    discomfort_materialization = decisions.get("discomfort_materialization", {})
    low_intensity = discomfort_materialization.get("low_intensity", {})
    allowed_difficulty = set(low_intensity.get("difficulty_codes", []))
    allowed_fitt_intensity = set(low_intensity.get("fitt_intensity_codes", []))
    if not allowed_difficulty or not allowed_fitt_intensity:
        raise FinalizationError("low-intensity discomfort candidate policy is incomplete")
    for mapping in discomfort_rows:
        if mapping.get("review_status_code") != "DOMAIN_APPROVED":
            raise FinalizationError("discomfort mapping must be DOMAIN_APPROVED")
        if mapping.get("production_eligible") != "false":
            raise FinalizationError("discomfort mapping must remain production-ineligible")
        score_band = mapping.get("score_band_code", "")
        if score_band not in {"NRS_1_3", "NRS_4_6"}:
            raise FinalizationError(f"unsupported discomfort score band: {score_band}")
        expected_scores = {"NRS_1_3": (1, 3), "NRS_4_6": (4, 6)}[score_band]
        if mapping.get("pain_score_min") != str(expected_scores[0]) or mapping.get(
            "pain_score_max"
        ) != str(expected_scores[1]):
            raise FinalizationError(f"discomfort score range is invalid: {score_band}")
        discomfort_source = by_rex.get(mapping.get("source_representative_exercise_id", ""))
        discomfort_alternative = by_rex.get(
            mapping.get("alternative_representative_exercise_id", "")
        )
        if discomfort_source is None or discomfort_alternative is None:
            raise FinalizationError("discomfort mapping endpoint is not in V2 catalog")
        pain_area = mapping.get("body_area_code", "")
        source_areas = set(
            json.loads(discomfort_source["primary_body_area_codes"])
            + json.loads(discomfort_source["secondary_body_area_codes"])
        )
        alternative_areas = set(
            json.loads(discomfort_alternative["primary_body_area_codes"])
            + json.loads(discomfort_alternative["secondary_body_area_codes"])
        )
        if pain_area not in source_areas:
            raise FinalizationError(
                "discomfort source does not load pain area: "
                f"{pain_area}:{discomfort_source['stable_code']}"
            )
        if discomfort_source["target_muscle_status"] != "APPROVED":
            raise FinalizationError(
                f"source target muscle is not approved: {discomfort_source['stable_code']}"
            )
        if discomfort_alternative["target_muscle_status"] != "APPROVED":
            raise FinalizationError(
                "alternative target muscle is not approved: "
                f"{discomfort_alternative['stable_code']}"
            )
        discomfort_source_rank = difficulty_rank[discomfort_source["difficulty_code"]]
        discomfort_alternative_rank = difficulty_rank[discomfort_alternative["difficulty_code"]]
        service_action = mapping.get("service_action_code", "")
        strategy = mapping.get("alternative_strategy_code", "")
        if score_band == "NRS_1_3":
            if service_action not in {"LOAD_REDUCED", "ROM_REDUCED"}:
                raise FinalizationError("NRS_1_3 must use LOAD_REDUCED or ROM_REDUCED")
            if mapping.get("goal_preservation_code") != "SAME_GOAL":
                raise FinalizationError("NRS_1_3 must preserve the original goal")
            if (
                mapping.get("source_goal_group")
                != discomfort_source["primary_movement_pattern_code"]
                or mapping.get("source_target_muscle_code") != discomfort_source["body_focus_code"]
            ):
                raise FinalizationError("NRS_1_3 source goal or target muscle is stale")
            if not (
                mapping.get("alternative_goal_group")
                == discomfort_alternative["primary_movement_pattern_code"]
                and (
                    discomfort_alternative["body_focus_code"]
                    == discomfort_source["body_focus_code"]
                    or discomfort_alternative["primary_movement_pattern_code"]
                    == discomfort_source["primary_movement_pattern_code"]
                )
            ):
                raise FinalizationError("NRS_1_3 candidate does not preserve the goal")
            if discomfort_alternative_rank > discomfort_source_rank:
                raise FinalizationError("NRS_1_3 candidate increases difficulty")
        else:
            if (
                service_action != "SKIP_AFFECTED_AREA"
                or strategy != "AVOID_PAIN_AREA_ACTIVE_RECOVERY"
            ):
                raise FinalizationError("NRS_4_6 must skip the affected area with active recovery")
            if pain_area in alternative_areas:
                raise FinalizationError(
                    "NRS_4_6 candidate uses pain area: "
                    f"{pain_area}:{discomfort_alternative['stable_code']}"
                )
            if discomfort_alternative["difficulty_code"] not in allowed_difficulty:
                raise FinalizationError(
                    "NRS_4_6 candidate is not low difficulty: "
                    f"{discomfort_alternative['stable_code']}"
                )
            if discomfort_alternative["fitt_intensity_level"] not in allowed_fitt_intensity:
                raise FinalizationError(
                    "NRS_4_6 candidate is not low FITT intensity: "
                    f"{discomfort_alternative['stable_code']}"
                )
            if mapping.get("goal_preservation_code") != "ACTIVE_RECOVERY":
                raise FinalizationError("NRS_4_6 must use ACTIVE_RECOVERY as the fallback goal")
        append_relation(
            discomfort_source,
            discomfort_alternative,
            reason_code="DISCOMFORT",
            goal=mapping["goal_preservation_code"],
            delta=discomfort_alternative_rank - discomfort_source_rank,
            relation_key=(
                f"mapping:{pain_area}:{score_band}:"
                f"{discomfort_source['representative_exercise_id']}:"
                f"{discomfort_alternative['representative_exercise_id']}:DISCOMFORT"
            ),
            metadata={
                "source_path": str(DISCOMFORT_MAPPING_PATH.relative_to(DATA_ROOT)),
                "selection_basis": "DOMAIN_APPROVED_SCORE_BAND_AND_TARGET_MUSCLE_POLICY",
                "body_area_code": pain_area,
                "score_band_code": score_band,
                "source_target_muscle_code": discomfort_source["body_focus_code"],
                "alternative_target_muscle_code": discomfort_alternative["body_focus_code"],
            },
            pain_score_min=mapping["pain_score_min"],
            pain_score_max=mapping["pain_score_max"],
            service_action_code=service_action,
            alternative_strategy_code=strategy,
        )
    return sorted(
        result,
        key=lambda row: (
            row["source_representative_exercise_id"],
            row["reason_code"],
            row["alternative_exercise_stable_code"],
        ),
    )


def build_safety(
    rules: list[dict[str, Any]],
    mapping_rows: list[dict[str, str]],
    integrated_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rule_status: dict[str, str] = {}
    final_rules: list[dict[str, Any]] = []
    for source in rules:
        if source.get("migration_status") == "LEGACY_EXERCISE_UNMAPPED_REVIEW_REQUIRED":
            continue
        row = dict(source)
        # Keep source fields and add aliases whose meaning and value set are
        # identical to the runtime safety-rule contract. pain_level remains
        # review-only here:
        # the runtime contract requires explicit minimum/maximum severity
        # columns and the legacy/reference rows do not all have a resolvable
        # target yet.
        row["movement_pattern_code"] = row.pop("movement_pattern")
        row["body_area_code"] = row.pop("body_area")
        row["effect_code"] = row.pop("action")
        row["reason_code"] = row.pop("reason")
        status = (
            "INACTIVE_PENDING_DOMAIN_APPROVAL"
            if row["migration_status"] == "NEW_PATTERN_RULE_REVIEW_REQUIRED"
            else "REFERENCE_ONLY_NOT_OPERATIONALLY_APPROVED"
        )
        row["activation_status"] = status
        row["production_eligible"] = False
        rule_status[row["rule_id"]] = status
        final_rules.append(row)
    by_nex = index_unique(integrated_rows, "normalized_exercise_id", "integrated catalog")
    aggregated: dict[tuple[str, str], dict[str, str]] = {}
    for source in mapping_rows:
        representative_id = by_nex[source["exercise_id"]]["representative_id"]
        key = (representative_id, source["rule_id"])
        candidate = {
            "representative_exercise_id": representative_id,
            "rule_id": source["rule_id"],
            "action": source["action"],
            "alternative_required": source["alternative_required"],
            "source_rule_ids": source["source_rule_id"],
            "activation_status": rule_status[source["rule_id"]],
            "mapping_review_status": "PENDING_DOMAIN_APPROVAL",
            "production_eligible": "false",
        }
        existing = aggregated.get(key)
        if existing is None:
            aggregated[key] = candidate
        elif existing != candidate:
            raise FinalizationError(f"conflicting representative safety mapping: {key}")
    if {row["representative_exercise_id"] for row in aggregated.values()} != {
        row["representative_id"] for row in finalized_taxonomy(read_csv(TAXONOMY_PATH))
    }:
        raise FinalizationError("safety mapping does not cover every representative")
    return final_rules, sorted(
        aggregated.values(),
        key=lambda row: (row["representative_exercise_id"], row["rule_id"]),
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    integrated_rows = read_csv(INTEGRATED_PATH)
    enrichment_rows = read_csv(ENRICHMENT_PATH)
    decisions = read_decisions()
    taxonomy_rows = apply_enrichment_to_taxonomy(
        finalized_taxonomy(read_csv(TAXONOMY_PATH)),
        integrated_rows,
        enrichment_rows,
    )
    stable_codes = build_stable_code_registry(taxonomy_rows, decisions)
    content_rows = read_content()
    representative_rows = build_representatives(
        taxonomy_rows,
        integrated_rows,
        enrichment_rows,
        read_csv(MET_PATH),
        stable_codes,
        decisions,
        content_rows,
    )
    alternative_rows = build_alternatives(
        representative_rows,
        read_csv(ALTERNATIVES_PATH),
        integrated_rows,
        enrichment_rows,
        read_csv(DISCOMFORT_MAPPING_PATH),
        decisions,
    )
    safety_rules, safety_mappings = build_safety(
        parse_jsonl(SAFETY_RULES_PATH), read_csv(SAFETY_MAPPING_PATH), integrated_rows
    )
    runtime_blockers = runtime_json_blockers(representative_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    taxonomy_columns = tuple(taxonomy_rows[0])
    write_csv(
        output_dir / "representative_exercise_taxonomy_v2_final.csv",
        taxonomy_columns,
        taxonomy_rows,
    )
    write_csv(
        output_dir / "representative_exercises_v2_final.csv",
        REPRESENTATIVE_COLUMNS,
        representative_rows,
    )
    stable_registry_path = output_dir / "stable_code_registry_v2.json"
    stable_registry_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "registry_version": decisions["decision_version"],
                "status": decisions["status"],
                "records": [
                    {
                        "representative_exercise_id": representative_id,
                        "stable_code": stable_code,
                    }
                    for representative_id, stable_code in sorted(stable_codes.items())
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_csv(
        output_dir / "exercise_alternatives_v2_final.csv",
        ALTERNATIVE_COLUMNS,
        alternative_rows,
    )
    write_jsonl(output_dir / "safety_rules_v2_final.jsonl", safety_rules)
    write_csv(
        output_dir / "representative_exercise_safety_mapping_v2_final.csv",
        SAFETY_MAPPING_COLUMNS,
        safety_mappings,
    )
    # No source media currently has rights approval; emit a header-only registry
    # rather than upload or expose an unapproved original.
    write_csv(output_dir / "media_assets_v2_final.csv", MEDIA_COLUMNS, [])
    artifact_names = (
        "representative_exercise_taxonomy_v2_final.csv",
        "representative_exercises_v2_final.csv",
        "exercise_alternatives_v2_final.csv",
        "safety_rules_v2_final.jsonl",
        "representative_exercise_safety_mapping_v2_final.csv",
        "media_assets_v2_final.csv",
        "stable_code_registry_v2.json",
    )
    report: dict[str, Any] = {
        "representative_count": len(representative_rows),
        "taxonomy_approved_representative_count": sum(
            row["taxonomy_review_status"] == "TAXONOMY_APPROVED" for row in representative_rows
        ),
        "representatives_with_approved_met": sum(
            row["met_status"] in MET_APPROVED_STATUSES for row in representative_rows
        ),
        "representatives_with_met_review_required": sum(
            row["met_status"] not in MET_APPROVED_STATUSES for row in representative_rows
        ),
        "representatives_with_approved_target_muscle": sum(
            row["target_muscle_status"] == "APPROVED" for row in representative_rows
        ),
        "representatives_with_target_muscle_review_required": sum(
            row["target_muscle_status"] != "APPROVED" for row in representative_rows
        ),
        "representatives_with_approved_body_areas": sum(
            row["body_area_status"] == "APPROVED" for row in representative_rows
        ),
        "representatives_with_approved_difficulty": sum(
            row["difficulty_status"] == "APPROVED" for row in representative_rows
        ),
        "representatives_with_difficulty_review_required": sum(
            row["difficulty_status"] != "APPROVED" for row in representative_rows
        ),
        "alternative_relationship_count": len(alternative_rows),
        "stable_code_count": len(stable_codes),
        "runtime_json_eligible": not runtime_blockers,
        "runtime_json_blockers": runtime_blockers,
        "safety_rule_count": len(safety_rules),
        "safety_mapping_count": len(safety_mappings),
        "active_safety_bridge_rule_count": sum(
            row["activation_status"] == "ACTIVE" for row in safety_rules
        ),
        "approved_media_asset_count": 0,
        "media_storage_backend": "AWS_MANAGED",
        "media_binary_local_storage": False,
        "media_local_db_storage": False,
        "artifact_sha256": {name: sha256(output_dir / name) for name in artifact_names},
        "artifact_bytes": {name: (output_dir / name).stat().st_size for name in artifact_names},
        "source_artifact_sha256": {
            "exercise_met_mapping_reviewed.csv": sha256(MET_PATH),
            "met_domain_approval_manifest.csv": sha256(MET_APPROVAL_MANIFEST_PATH),
        },
        "production_eligible": False,
    }
    (output_dir / "finalization_validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    try:
        report = build(args.output_dir)
    except (OSError, KeyError, FinalizationError, csv.Error) as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
