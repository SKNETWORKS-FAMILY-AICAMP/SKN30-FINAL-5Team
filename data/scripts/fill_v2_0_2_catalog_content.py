"""Fill the v2.0.2 catalog gaps that an approved policy already determines.

Two of the three gaps the content review queue reports are not judgement calls:

* **Dosage.** v2.0.1 does not set rest per exercise - it sets it per
  ``(training_type_code, timing_mode_code)`` class, with no exception across its
  102 records, and every record uses a 15 second transition. All 58 v2.0.2
  records missing a rest interval are ``(MOBILITY, DURATION)``, which that table
  already covers. Applying it is consistency, not a new dosage decision
  (project owner approval, 2026-08-30).
* **Safe-variant form cues.** The 54 safe variants that do have cues carry a
  fixed four-line template built from the record's own posture, support, pain
  area and base exercise. The remaining 21 have every input the template needs.
  Rendering it for them keeps one voice across the set; writing fresh prose for
  21 of 75 would not.

The third gap is left alone. The 15 ``VARIANT`` records have no posture template
to render, and their ``instruction_summary_ko`` is the exercise name rather than
an instruction, so they need authored content and stay in the review queue.

Nothing here is approval. Filled records carry the policy or template reference
that produced them, and the safe variants keep the ``REVIEW_REQUIRED`` status of
the artifact their siblings came from.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FINAL = DATA_ROOT / "generated/exercise-catalog-v2.0.2-final"

DOSAGE_POLICY_VERSION = "v2.0.1-dosage-table-v1"
SAFE_VARIANT_CUE_TEMPLATE_VERSION = "safe-variant-cue-template-v1"
APPROVAL_REFERENCE = "USER_DIRECT_REVIEW_2026_08_30"

# Measured from data/generated/exercise-catalog-v2.0.1-final/runtime/
# representative_exercises.jsonl: 102 records, zero exceptions.
_REST_SECONDS_BY_CLASS = {
    ("CARDIO", "DURATION"): 60,
    ("MOBILITY", "DURATION"): 30,
    ("STRENGTH", "DURATION"): 90,
    ("STRENGTH", "REPS"): 90,
}
_TRANSITION_SECONDS = 15

_SAFE_VARIANT_SUFFIX = re.compile(r"^(?P<base>.+)__(?P<area>[a-z_]+)_no_load_safe_v\d+$")


class ContentFillError(RuntimeError):
    """Raised when a gap cannot be filled from an approved policy."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContentFillError(f"artifact is missing: {path}") from exc
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def pain_area_from_stable_code(stable_code: str) -> str | None:
    """Read the pain area a safe variant is named for, or None if not one."""
    match = _SAFE_VARIANT_SUFFIX.match(stable_code)
    return match.group("area").upper() if match else None


def render_safe_variant_cues(
    *, posture_code: str, support_code: str, pain_area_code: str, base_name_ko: str
) -> list[str]:
    """Render the same four cues the 54 reviewed safe variants already use."""
    if not (posture_code and support_code and pain_area_code and base_name_ko):
        raise ContentFillError("safe-variant cue template is missing an input")
    return [
        f"{posture_code} 자세를 먼저 잡고 {support_code} 지지를 끝날 때까지 유지한다.",
        f"{pain_area_code} 부위는 체중지지·그립·브레이싱에 사용하지 않는다.",
        "원본의 서기·기울이기·손으로 잡기 지시는 사용하지 않고, "
        f"{base_name_ko} 목표 관절만 천천히 움직인다.",
        "통증과 불편감이 증가하면 즉시 중단한다.",
    ]


def fill(final: Path = DEFAULT_FINAL) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    catalog = _read_jsonl(final / "catalog/exercises.jsonl")
    by_code = {str(record.get("stable_code")): record for record in catalog}
    reviewed_cues = {
        str(row["stable_code"]): row["form_cues_ko"]
        for row in _read_jsonl(final / "audit/alternatives/discomfort_safe_variants_v2_0_2.jsonl")
        if row.get("form_cues_ko")
    }
    recovered_representative_cues = _recovered_representative_cues(final)

    filled = {"rest": 0, "transition": 0, "cues_recovered": 0, "cues_rendered": 0}
    deferred: list[str] = []
    for record in catalog:
        code = str(record.get("stable_code"))

        if record.get("default_rest_seconds") is None:
            key = (str(record.get("training_type_code")), str(record.get("timing_mode_code")))
            seconds = _REST_SECONDS_BY_CLASS.get(key)
            if seconds is None:
                raise ContentFillError(f"no approved rest policy for {key}: {code}")
            record["default_rest_seconds"] = seconds
            record["default_rest_seconds_source"] = DOSAGE_POLICY_VERSION
            filled["rest"] += 1
        if record.get("default_transition_seconds") is None:
            record["default_transition_seconds"] = _TRANSITION_SECONDS
            record["default_transition_seconds_source"] = DOSAGE_POLICY_VERSION
            filled["transition"] += 1

        if record.get("form_cues_ko"):
            continue
        if code in reviewed_cues:
            record["form_cues_ko"] = list(reviewed_cues[code])
            record["form_cues_source"] = "discomfort_safe_variants_v2_0_2.jsonl"
            filled["cues_recovered"] += 1
            continue
        if code in recovered_representative_cues:
            record["form_cues_ko"] = list(recovered_representative_cues[code])
            record["form_cues_source"] = "canonical_exercises_v2_0_2_refined.csv"
            filled["cues_recovered"] += 1
            continue
        pain_area = pain_area_from_stable_code(code)
        base = by_code.get(str(record.get("alternative_source_base_stable_code")))
        if pain_area and base and base.get("name_ko"):
            record["form_cues_ko"] = render_safe_variant_cues(
                posture_code=str(record.get("fixed_posture_code")),
                support_code=str(record.get("fixed_support_code")),
                pain_area_code=pain_area,
                base_name_ko=str(base["name_ko"]),
            )
            record["form_cues_source"] = SAFE_VARIANT_CUE_TEMPLATE_VERSION
            record["form_cues_review_status"] = "REVIEW_REQUIRED"
            filled["cues_rendered"] += 1
            continue
        deferred.append(code)

    summary = {
        "catalog_records": len(catalog),
        "filled": filled,
        "deferred_records": len(deferred),
        "deferred_stable_codes": sorted(deferred),
        "dosage_policy_version": DOSAGE_POLICY_VERSION,
        "safe_variant_cue_template_version": SAFE_VARIANT_CUE_TEMPLATE_VERSION,
        "approval_reference": APPROVAL_REFERENCE,
        "note": (
            "Rendered cues are REVIEW_REQUIRED, matching the artifact their 54 "
            "siblings came from. Filling is not approval."
        ),
    }
    return catalog, summary


def _recovered_representative_cues(final: Path) -> dict[str, list[str]]:
    path = final / "audit/canonical_exercises_v2_0_2_refined.csv"
    recovered: dict[str, list[str]] = {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                raw = (row.get("form_cues_ko") or "").strip()
                code = (row.get("stable_code") or "").strip()
                if not raw or raw == "[]" or not code:
                    continue
                try:
                    cues = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(cues, list) and cues:
                    recovered.setdefault(code, [str(item) for item in cues])
    except OSError as exc:
        raise ContentFillError(f"artifact is missing: {path}") from exc
    return recovered


def write_catalog(catalog: list[dict[str, Any]], final: Path) -> None:
    (final / "catalog/exercises.jsonl").write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in catalog
        ),
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", type=Path, default=DEFAULT_FINAL)
    parser.add_argument(
        "--report-only", action="store_true", help="print what would be filled and stop"
    )
    args = parser.parse_args(argv)
    catalog, summary = fill(args.final)
    if not args.report_only:
        write_catalog(catalog, args.final)
        summary["written"] = str(args.final / "catalog/exercises.jsonl")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
