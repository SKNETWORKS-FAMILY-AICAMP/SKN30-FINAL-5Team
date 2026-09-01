"""Materialize the v2.0.2 rows an already-approved policy determines.

Two payload gaps block the import, and neither is a clinical question. Both are
the pipeline failing to run an existing rule over every record.

**Safety rules.** ``build_v2_runtime_artifacts.materialize_safety`` does not read
a per-exercise contraindication list. It derives rules from the exercise's own
reviewed body areas:

* a ``PRIMARY`` area yields ``EXCLUDE`` across ``MILD..SEVERE`` for
  ``DIRECT_JOINT_LOAD`` - the exercise loads that joint directly, so any reported
  discomfort there rules it out;
* a ``SECONDARY`` area yields ``CAUTION`` at ``MILD`` and ``EXCLUDE`` from
  ``MODERATE`` up, for ``STABILIZER_LOAD`` - the area only stabilises, so mild
  discomfort is a warning and anything worse is not.

The 289 substantive rules already in the v2.0.2 payload match that policy
exactly, and the other 94 exercises carry the same reviewed body-area fields.
Running the rule over them is the pipeline finishing its job.

**Rest intervals.** All 116 prescriptions missing ``rest_seconds_per_set`` are
``(WARMUP, LIGHT, MOBILITY)``, and all 58 rows of that class that do carry a
value use ``0``. The value is read from the payload's own class, not chosen.

This script never invents a contraindication and never writes a value it cannot
derive from a rule the repository already approved. Anything outside those rules
is left for review.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FINAL = DATA_ROOT / "generated/exercise-catalog-v2.0.2-final"

CATALOG_VERSION_CODE = "exercise-catalog-v2.0.2-final"
RULE_SET_VERSION_CODE = "safety-rule-set-v2.0.2"
SAFETY_RULE_VERSION = "safety-rule-v2.0.2"
SAFETY_POLICY_VERSION = "v2-body-area-safety-policy-v1"
REST_POLICY_VERSION = "v2-0-2-rest-class-policy-v1"
APPROVAL_REFERENCE = "USER_DIRECT_REVIEW_2026_08_30"
GENERATED_AT = "2026-08-29T00:00:00+09:00"

# The policy build_v2_runtime_artifacts.materialize_safety applies, restated so
# the two stay comparable. Changing either without the other is a bug.
_SAFETY_SPECS: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "PRIMARY": (("MILD", "SEVERE", "EXCLUDE", "DIRECT_JOINT_LOAD"),),
    "SECONDARY": (
        ("MILD", "MILD", "CAUTION", "STABILIZER_LOAD"),
        ("MODERATE", "SEVERE", "EXCLUDE", "STABILIZER_LOAD"),
    ),
}


class DerivedPolicyError(RuntimeError):
    """Raised when a row cannot be derived from an approved rule."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DerivedPolicyError(f"artifact is missing: {path}") from exc
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _is_substantive(rule: dict[str, Any]) -> bool:
    """A row that names an exercise but states no scope is a placeholder."""
    return rule.get("rule_scope") is not None


def verify_existing_safety_policy(rules: list[dict[str, Any]]) -> None:
    """Fail if the rules already in the payload disagree with the policy.

    If the shipped rules were produced some other way, deriving the rest from
    this policy would mix two different meanings of EXCLUDE in one table.
    """
    observed = {
        (
            rule["body_part_role_code"],
            rule["minimum_severity_code"],
            rule["maximum_severity_code"],
            rule["effect_code"],
            rule["reason_code"],
        )
        for rule in rules
        if _is_substantive(rule)
    }
    expected = {(role, *spec) for role, specs in _SAFETY_SPECS.items() for spec in specs}
    unexpected = observed - expected
    if unexpected:
        raise DerivedPolicyError(
            f"existing safety rules do not follow the body-area policy: {sorted(unexpected)}"
        )


def derive_safety_rules(
    catalog: list[dict[str, Any]], rules: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the payload's rules plus the ones the policy still owes."""
    verify_existing_safety_policy(rules)
    covered = {str(rule.get("exercise_stable_code")) for rule in rules if _is_substantive(rule)}
    kept = [rule for rule in rules if _is_substantive(rule)]
    derived: list[dict[str, Any]] = []
    skipped: list[str] = []
    for record in catalog:
        code = str(record.get("stable_code"))
        if code in covered:
            continue
        areas = [(area, "PRIMARY") for area in record.get("primary_body_area_codes") or []]
        areas += [(area, "SECONDARY") for area in record.get("secondary_body_area_codes") or []]
        if not any(role == "PRIMARY" for _, role in areas):
            # Without a reviewed primary area there is nothing to derive from.
            skipped.append(code)
            continue
        for area, role in areas:
            for minimum, maximum, effect, reason in _SAFETY_SPECS[role]:
                derived.append(
                    {
                        "body_area_code": area,
                        "body_part_role_code": role,
                        "catalog_version_code": CATALOG_VERSION_CODE,
                        "effect_code": effect,
                        "exercise_stable_code": code,
                        "maximum_severity_code": maximum,
                        "minimum_severity_code": minimum,
                        "movement_pattern_code": None,
                        "reason_code": reason,
                        "review_status_code": "DOMAIN_APPROVED",
                        "rule_scope": "EXERCISE",
                        "rule_version": SAFETY_RULE_VERSION,
                        "rule_set_version_code": RULE_SET_VERSION_CODE,
                        "production_eligible": False,
                        "source_manifest_hash": None,
                        "source_metadata": {
                            "derived_by": SAFETY_POLICY_VERSION,
                            "approval_reference": APPROVAL_REFERENCE,
                            "basis": "reviewed primary/secondary body areas of the exercise",
                        },
                        "created_at": GENERATED_AT,
                        "updated_at": GENERATED_AT,
                    }
                )
    summary = {
        "existing_rules": len(kept),
        "placeholder_rules_dropped": len(rules) - len(kept),
        "derived_rules": len(derived),
        "exercises_derived": len({rule["exercise_stable_code"] for rule in derived}),
        "exercises_skipped": skipped,
        "policy_version": SAFETY_POLICY_VERSION,
    }
    return kept + derived, summary


def fill_rest_intervals(
    prescriptions: list[dict[str, Any]], catalog: list[dict[str, Any]]
) -> dict[str, Any]:
    """Fill a missing rest interval from its own (phase, intensity, type) class."""
    training_type = {
        str(record.get("stable_code")): record.get("training_type_code") for record in catalog
    }
    observed: dict[tuple[str, str, str], Counter[int]] = defaultdict(Counter)
    for row in prescriptions:
        rest = row.get("rest_seconds_per_set")
        if rest is None:
            continue
        key = (
            str(row.get("phase_code")),
            str(row.get("intensity_code")),
            str(training_type.get(str(row.get("exercise_stable_code")))),
        )
        observed[key][int(rest)] += 1

    filled = 0
    unresolved: list[str] = []
    for row in prescriptions:
        if row.get("rest_seconds_per_set") is not None:
            continue
        key = (
            str(row.get("phase_code")),
            str(row.get("intensity_code")),
            str(training_type.get(str(row.get("exercise_stable_code")))),
        )
        candidates = observed.get(key)
        # Only a class that agrees with itself can settle a missing value.
        if not candidates or len(candidates) != 1:
            unresolved.append(str(row.get("exercise_stable_code")))
            continue
        row["rest_seconds_per_set"] = next(iter(candidates))
        row["rest_seconds_per_set_source"] = REST_POLICY_VERSION
        filled += 1
    return {
        "filled": filled,
        "unresolved": sorted(set(unresolved)),
        "policy_version": REST_POLICY_VERSION,
    }


def fill_rep_tempo(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    """Fill a missing per-rep tempo from its own (training type, timing) class.

    ``timing_mode_code=REPS`` requires ``default_seconds_per_rep``; the backend
    rejects the record without it. Every REPS record that states one - 54 in
    v2.0.2 and 46 in v2.0.1 - uses the same value for its training type, so the
    class settles it.
    """
    observed: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
    for record in catalog:
        tempo = record.get("default_seconds_per_rep")
        if tempo is None:
            continue
        key = (str(record.get("training_type_code")), str(record.get("timing_mode_code")))
        observed[key][int(tempo)] += 1

    filled = 0
    unresolved: list[str] = []
    for record in catalog:
        if record.get("timing_mode_code") != "REPS":
            continue
        if record.get("default_seconds_per_rep") is not None:
            continue
        key = (str(record.get("training_type_code")), "REPS")
        candidates = observed.get(key)
        if not candidates or len(candidates) != 1:
            unresolved.append(str(record.get("stable_code")))
            continue
        record["default_seconds_per_rep"] = next(iter(candidates))
        record["default_seconds_per_rep_source"] = REST_POLICY_VERSION
        filled += 1
    return {"filled": filled, "unresolved": sorted(set(unresolved))}


SAFE_VARIANT_EQUIPMENT_POLICY_VERSION = "safe-variant-equipment-policy-v1"


def normalize_safe_variant_equipment(
    catalog: list[dict[str, Any]], reviewed_codes: set[str]
) -> dict[str, Any]:
    """Give every safe variant the equipment its reviewed siblings carry.

    A pain-area safe variant holds one fixed, supported posture and moves only
    the target joint; its rendered cues never mention an implement. All 54 rows
    written into ``discomfort_safe_variants_v2_0_2.jsonl`` say so - BODYWEIGHT,
    at HOME or GYM, with no exception. The 21 records generated after that file
    inherited the *base* exercise's equipment instead, which both contradicts the
    policy and, for the strap rows, demands equipment the movement never uses.
    """
    changed: list[dict[str, Any]] = []
    for record in catalog:
        if record.get("source_track") != "pain_alternative_policy":
            continue
        if str(record.get("stable_code")) in reviewed_codes:
            continue
        equipment = list(record.get("equipment_codes") or [])
        locations = list(record.get("location_codes") or [])
        if equipment == ["BODYWEIGHT"] and locations == ["HOME", "GYM"]:
            continue
        changed.append(
            {
                "stable_code": str(record.get("stable_code")),
                "previous_equipment_codes": equipment,
                "previous_location_codes": locations,
            }
        )
        record["equipment_codes"] = ["BODYWEIGHT"]
        record["location_codes"] = ["HOME", "GYM"]
        record["equipment_codes_source"] = SAFE_VARIANT_EQUIPMENT_POLICY_VERSION
    return {
        "normalized": len(changed),
        "records": changed,
        "policy_version": SAFE_VARIANT_EQUIPMENT_POLICY_VERSION,
    }


def run(final: Path = DEFAULT_FINAL, *, write: bool = True) -> dict[str, Any]:
    catalog = _read_jsonl(final / "catalog/exercises.jsonl")
    rules = _read_jsonl(final / "runtime/safety_rules.jsonl")
    prescriptions = _read_jsonl(final / "prescriptions/prescription_profiles.jsonl")

    reviewed_codes = {
        str(row["stable_code"])
        for row in _read_jsonl(final / "audit/alternatives/discomfort_safe_variants_v2_0_2.jsonl")
    }
    equipment_summary = normalize_safe_variant_equipment(catalog, reviewed_codes)
    rules, safety_summary = derive_safety_rules(catalog, rules)
    rest_summary = fill_rest_intervals(prescriptions, catalog)
    tempo_summary = fill_rep_tempo(catalog)

    if write:
        _write_jsonl(final / "catalog/exercises.jsonl", catalog)
        _write_jsonl(final / "runtime/safety_rules.jsonl", rules)
        _write_jsonl(final / "prescriptions/prescription_profiles.jsonl", prescriptions)

    covered = {rule["exercise_stable_code"] for rule in rules if _is_substantive(rule)}
    return {
        "catalog_records": len(catalog),
        "safety": safety_summary,
        "safety_rule_total": len(rules),
        "exercises_without_safety_rule": sorted(
            str(record["stable_code"]) for record in catalog if record["stable_code"] not in covered
        ),
        "rest": rest_summary,
        "rep_tempo": tempo_summary,
        "safe_variant_equipment": equipment_summary,
        "approval_reference": APPROVAL_REFERENCE,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", type=Path, default=DEFAULT_FINAL)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args(argv)
    summary = run(args.final, write=not args.report_only)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
