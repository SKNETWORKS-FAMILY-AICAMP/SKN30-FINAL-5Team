"""Generate a deterministic safety-rule calibration report from a catalog bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

DEFAULT_BUNDLE = (
    Path(__file__).resolve().parents[2]
    / "data/generated/exercise-catalog-v2.0.5-final/backend_bundle"
)
PAIN_POLICY_VERSION = "pain-intensity-action-v2"
RECOVERY_POLICY_VERSION = "recovery-sleep-fatigue-v1"
RETURN_MODE_COMPLETION_GAP_DAYS = 14


class CalibrationInputError(ValueError):
    """Raised when calibration input cannot be trusted."""


class LoadCapCode(StrEnum):
    NORMAL = "NORMAL"
    LIGHT = "LIGHT"
    VERY_LIGHT = "VERY_LIGHT"
    STOP = "STOP"
    APPROVED_CAPS_REQUIRED = "APPROVED_CAPS_REQUIRED"


class FatigueLevelCode(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class SeverityCode(StrEnum):
    MILD = "MILD"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"


@dataclass(frozen=True, slots=True)
class PainInput:
    body_area_code: str
    intensity_score: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.body_area_code, str)
            or not self.body_area_code
            or self.body_area_code == "OTHER"
        ):
            raise CalibrationInputError("body_area_code must be a concrete non-empty code")
        if (
            isinstance(self.intensity_score, bool)
            or not isinstance(self.intensity_score, int)
            or not 1 <= self.intensity_score <= 10
        ):
            raise CalibrationInputError("intensity_score must be an integer from 1 to 10")


@dataclass(frozen=True, slots=True)
class CalibrationScenario:
    scenario_code: str
    pains: tuple[PainInput, ...] = ()
    red_flag_present: bool = False
    sleep_minutes: int | None = 420
    fatigue_level_code: FatigueLevelCode = FatigueLevelCode.LOW
    completion_gap_days: int | None = None

    def __post_init__(self) -> None:
        if not self.scenario_code:
            raise CalibrationInputError("scenario_code must not be empty")
        areas = tuple(pain.body_area_code for pain in self.pains)
        if len(areas) != len(set(areas)):
            raise CalibrationInputError("pain body areas must not contain duplicates")
        if not isinstance(self.fatigue_level_code, FatigueLevelCode):
            raise CalibrationInputError("fatigue_level_code must be an approved code")
        if self.sleep_minutes is not None and (
            isinstance(self.sleep_minutes, bool)
            or not isinstance(self.sleep_minutes, int)
            or not 0 <= self.sleep_minutes <= 1440
        ):
            raise CalibrationInputError("sleep_minutes must be null or an integer from 0 to 1440")
        if self.completion_gap_days is not None and (
            isinstance(self.completion_gap_days, bool)
            or not isinstance(self.completion_gap_days, int)
            or self.completion_gap_days < 0
        ):
            raise CalibrationInputError("completion_gap_days must be null or non-negative")


@dataclass(frozen=True, slots=True)
class ExerciseRecord:
    stable_code: str
    movement_pattern_code: str


@dataclass(frozen=True, slots=True)
class SafetyRuleRecord:
    body_area_code: str
    minimum_severity_code: SeverityCode
    maximum_severity_code: SeverityCode
    effect_code: str
    exercise_stable_code: str | None
    movement_pattern_code: str | None


@dataclass(frozen=True, slots=True)
class CalibrationBundle:
    catalog_version_code: str
    bundle_version: str
    production_eligible: bool
    exercises: tuple[ExerciseRecord, ...]
    rules: tuple[SafetyRuleRecord, ...]


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario_code: str
    total_candidate_count: int
    approved_pool_size: int
    excluded_exercise_count: int
    caution_exercise_count: int
    plan_generation_failed: bool
    applied_cap_code: LoadCapCode
    safety_action_code: str
    return_mode_active: bool


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    schema_version: str
    bundle_version: str
    catalog_version_code: str
    bundle_production_eligible: bool
    pain_policy_version: str
    recovery_policy_version: str
    scenario_count: int
    failed_scenario_count: int
    plan_generation_failure_rate: float
    results: tuple[ScenarioResult, ...]


DEFAULT_SCENARIOS = (
    CalibrationScenario(scenario_code="HEALTHY_NORMAL"),
    CalibrationScenario(
        scenario_code="KNEE_NRS_3",
        pains=(PainInput("KNEE", 3),),
    ),
    CalibrationScenario(
        scenario_code="KNEE_NRS_4",
        pains=(PainInput("KNEE", 4),),
    ),
    CalibrationScenario(
        scenario_code="MULTI_AREA_NRS_6",
        pains=(
            PainInput("KNEE", 6),
            PainInput("LOWER_BACK", 6),
            PainInput("SHOULDER", 6),
        ),
    ),
    CalibrationScenario(
        scenario_code="KNEE_NRS_7",
        pains=(PainInput("KNEE", 7),),
    ),
    CalibrationScenario(scenario_code="RED_FLAG", red_flag_present=True),
    CalibrationScenario(
        scenario_code="RECOVERY_VERY_LIGHT",
        sleep_minutes=330,
        fatigue_level_code=FatigueLevelCode.HIGH,
    ),
    CalibrationScenario(scenario_code="RETURN_GAP_13_DAYS", completion_gap_days=13),
    CalibrationScenario(scenario_code="RETURN_GAP_14_DAYS", completion_gap_days=14),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise CalibrationInputError(f"{path}:{line_number} must contain an object")
            rows.append(value)
    return rows


def _validated_bundle_file(
    bundle_path: Path,
    manifest_entries: dict[str, dict[str, Any]],
    relative_path: str,
) -> Path:
    entry = manifest_entries.get(relative_path)
    if entry is None:
        raise CalibrationInputError(f"manifest is missing {relative_path}")
    path = (bundle_path / relative_path).resolve()
    if bundle_path.resolve() not in path.parents:
        raise CalibrationInputError(f"bundle path escapes its root: {relative_path}")
    if not path.is_file():
        raise CalibrationInputError(f"bundle file does not exist: {relative_path}")
    if _sha256(path) != entry.get("sha256"):
        raise CalibrationInputError(f"bundle hash mismatch: {relative_path}")
    return path


def load_bundle(bundle_path: Path) -> CalibrationBundle:
    """Load only manifest-verified, domain-approved calibration records."""

    bundle_path = bundle_path.resolve()
    manifest_path = bundle_path / "bundle_manifest.json"
    if not manifest_path.is_file():
        raise CalibrationInputError("bundle_manifest.json is required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise CalibrationInputError("bundle manifest must be an object")
    raw_entries = manifest.get("files")
    if not isinstance(raw_entries, list):
        raise CalibrationInputError("bundle manifest files must be a list")
    manifest_entries = {
        str(entry["path"]): entry
        for entry in raw_entries
        if isinstance(entry, dict) and "path" in entry
    }
    catalog_path = _validated_bundle_file(bundle_path, manifest_entries, "catalog/exercises.jsonl")
    rules_path = _validated_bundle_file(bundle_path, manifest_entries, "safety/safety_rules.jsonl")
    catalog_rows = _read_jsonl(catalog_path)
    rule_rows = _read_jsonl(rules_path)
    for relative_path, rows in (
        ("catalog/exercises.jsonl", catalog_rows),
        ("safety/safety_rules.jsonl", rule_rows),
    ):
        expected_records = manifest_entries[relative_path].get("records")
        if expected_records != len(rows):
            raise CalibrationInputError(f"bundle record count mismatch: {relative_path}")

    catalog_version = str(manifest.get("catalog_version_code", ""))
    bundle_version = str(manifest.get("bundle_version", ""))
    if not catalog_version or not bundle_version:
        raise CalibrationInputError("bundle and catalog versions must not be empty")
    exercises = tuple(
        ExerciseRecord(
            stable_code=str(row["stable_code"]),
            movement_pattern_code=str(row["primary_movement_pattern_code"]),
        )
        for row in catalog_rows
        if row.get("review_status_code") == "DOMAIN_APPROVED"
    )
    if not exercises or len({item.stable_code for item in exercises}) != len(exercises):
        raise CalibrationInputError("approved catalog exercises must be non-empty and unique")

    rules: list[SafetyRuleRecord] = []
    exercise_codes = {item.stable_code for item in exercises}
    movement_patterns = {item.movement_pattern_code for item in exercises}
    for row in rule_rows:
        if row.get("review_status_code") != "DOMAIN_APPROVED":
            continue
        if row.get("catalog_version_code") != catalog_version:
            raise CalibrationInputError("approved safety rule has a different catalog version")
        exercise_code = row.get("exercise_stable_code")
        movement_pattern_code = row.get("movement_pattern_code")
        if (exercise_code is None) == (movement_pattern_code is None):
            raise CalibrationInputError("approved safety rule must have exactly one target")
        if exercise_code is not None and str(exercise_code) not in exercise_codes:
            raise CalibrationInputError("approved safety rule targets an unknown exercise")
        if (
            movement_pattern_code is not None
            and str(movement_pattern_code) not in movement_patterns
        ):
            raise CalibrationInputError("approved safety rule targets an unknown movement pattern")
        effect_code = str(row["effect_code"])
        if effect_code not in {"EXCLUDE", "CAUTION"}:
            raise CalibrationInputError("approved safety rule has an unknown effect")
        rules.append(
            SafetyRuleRecord(
                body_area_code=str(row["body_area_code"]),
                minimum_severity_code=SeverityCode(str(row["minimum_severity_code"])),
                maximum_severity_code=SeverityCode(str(row["maximum_severity_code"])),
                effect_code=effect_code,
                exercise_stable_code=(str(exercise_code) if exercise_code is not None else None),
                movement_pattern_code=(
                    str(movement_pattern_code) if movement_pattern_code is not None else None
                ),
            )
        )
    if not rules:
        raise CalibrationInputError("approved safety rules must not be empty")
    return CalibrationBundle(
        catalog_version_code=catalog_version,
        bundle_version=bundle_version,
        production_eligible=manifest.get("production_eligible") is True,
        exercises=tuple(sorted(exercises, key=lambda item: item.stable_code)),
        rules=tuple(rules),
    )


_SEVERITY_RANK = {
    SeverityCode.MILD: 1,
    SeverityCode.MODERATE: 2,
    SeverityCode.SEVERE: 3,
}
_CAP_RANK = {
    LoadCapCode.NORMAL: 0,
    LoadCapCode.LIGHT: 1,
    LoadCapCode.VERY_LIGHT: 2,
    LoadCapCode.STOP: 3,
}


def severity_for_nrs(intensity_score: int) -> SeverityCode:
    if (
        isinstance(intensity_score, bool)
        or not isinstance(intensity_score, int)
        or not 1 <= intensity_score <= 10
    ):
        raise CalibrationInputError("intensity_score must be an integer from 1 to 10")
    if intensity_score <= 3:
        return SeverityCode.MILD
    if intensity_score <= 6:
        return SeverityCode.MODERATE
    return SeverityCode.SEVERE


def recovery_cap(sleep_minutes: int | None, fatigue_level_code: FatigueLevelCode) -> LoadCapCode:
    if sleep_minutes is None:
        row = {
            FatigueLevelCode.LOW: LoadCapCode.NORMAL,
            FatigueLevelCode.MODERATE: LoadCapCode.LIGHT,
            FatigueLevelCode.HIGH: LoadCapCode.VERY_LIGHT,
        }
    elif sleep_minutes >= 420:
        row = {
            FatigueLevelCode.LOW: LoadCapCode.NORMAL,
            FatigueLevelCode.MODERATE: LoadCapCode.NORMAL,
            FatigueLevelCode.HIGH: LoadCapCode.LIGHT,
        }
    elif sleep_minutes >= 360:
        row = {
            FatigueLevelCode.LOW: LoadCapCode.NORMAL,
            FatigueLevelCode.MODERATE: LoadCapCode.LIGHT,
            FatigueLevelCode.HIGH: LoadCapCode.VERY_LIGHT,
        }
    else:
        row = {
            FatigueLevelCode.LOW: LoadCapCode.LIGHT,
            FatigueLevelCode.MODERATE: LoadCapCode.VERY_LIGHT,
            FatigueLevelCode.HIGH: LoadCapCode.VERY_LIGHT,
        }
    return row[fatigue_level_code]


def _rule_applies(rule: SafetyRuleRecord, pain: PainInput, exercise: ExerciseRecord) -> bool:
    severity = severity_for_nrs(pain.intensity_score)
    rank = _SEVERITY_RANK[severity]
    if rule.body_area_code != pain.body_area_code:
        return False
    if not (
        _SEVERITY_RANK[rule.minimum_severity_code]
        <= rank
        <= _SEVERITY_RANK[rule.maximum_severity_code]
    ):
        return False
    if rule.exercise_stable_code is not None:
        return rule.exercise_stable_code == exercise.stable_code
    return rule.movement_pattern_code == exercise.movement_pattern_code


def evaluate_scenario(bundle: CalibrationBundle, scenario: CalibrationScenario) -> ScenarioResult:
    total = len(bundle.exercises)
    return_mode_active = (
        scenario.completion_gap_days is not None
        and scenario.completion_gap_days >= RETURN_MODE_COMPLETION_GAP_DAYS
    )
    if scenario.red_flag_present:
        return ScenarioResult(
            scenario_code=scenario.scenario_code,
            total_candidate_count=total,
            approved_pool_size=0,
            excluded_exercise_count=total,
            caution_exercise_count=0,
            plan_generation_failed=True,
            applied_cap_code=LoadCapCode.STOP,
            safety_action_code="STOP_AND_SEEK_HELP",
            return_mode_active=return_mode_active,
        )
    if any(
        severity_for_nrs(pain.intensity_score) is SeverityCode.SEVERE for pain in scenario.pains
    ):
        return ScenarioResult(
            scenario_code=scenario.scenario_code,
            total_candidate_count=total,
            approved_pool_size=0,
            excluded_exercise_count=total,
            caution_exercise_count=0,
            plan_generation_failed=True,
            applied_cap_code=LoadCapCode.STOP,
            safety_action_code="REST",
            return_mode_active=return_mode_active,
        )

    excluded: set[str] = set()
    cautions: set[str] = set()
    for exercise in bundle.exercises:
        for pain in scenario.pains:
            matching = [rule for rule in bundle.rules if _rule_applies(rule, pain, exercise)]
            if any(rule.effect_code == "EXCLUDE" for rule in matching):
                excluded.add(exercise.stable_code)
            elif any(rule.effect_code == "CAUTION" for rule in matching):
                cautions.add(exercise.stable_code)
    cautions.difference_update(excluded)
    pain_cap = (
        LoadCapCode.LIGHT
        if any(
            severity_for_nrs(pain.intensity_score) is SeverityCode.MODERATE
            for pain in scenario.pains
        )
        else LoadCapCode.NORMAL
    )
    effective_cap = max(
        (pain_cap, recovery_cap(scenario.sleep_minutes, scenario.fatigue_level_code)),
        key=_CAP_RANK.__getitem__,
    )
    approved_pool_size = total - len(excluded)
    plan_failed = approved_pool_size == 0
    action_code = "REST" if plan_failed else ("REVISE" if excluded or cautions else "KEEP")
    if return_mode_active:
        effective_cap = LoadCapCode.APPROVED_CAPS_REQUIRED
        plan_failed = True
        action_code = "APPROVED_CAPS_REQUIRED"
    return ScenarioResult(
        scenario_code=scenario.scenario_code,
        total_candidate_count=total,
        approved_pool_size=approved_pool_size,
        excluded_exercise_count=len(excluded),
        caution_exercise_count=len(cautions),
        plan_generation_failed=plan_failed,
        applied_cap_code=effective_cap,
        safety_action_code=action_code,
        return_mode_active=return_mode_active,
    )


def build_report(
    bundle: CalibrationBundle,
    scenarios: tuple[CalibrationScenario, ...] = DEFAULT_SCENARIOS,
) -> CalibrationReport:
    if not scenarios:
        raise CalibrationInputError("at least one calibration scenario is required")
    codes = tuple(scenario.scenario_code for scenario in scenarios)
    if len(codes) != len(set(codes)):
        raise CalibrationInputError("scenario codes must be unique")
    results = tuple(evaluate_scenario(bundle, scenario) for scenario in scenarios)
    failed_count = sum(result.plan_generation_failed for result in results)
    return CalibrationReport(
        schema_version="1.0",
        bundle_version=bundle.bundle_version,
        catalog_version_code=bundle.catalog_version_code,
        bundle_production_eligible=bundle.production_eligible,
        pain_policy_version=PAIN_POLICY_VERSION,
        recovery_policy_version=RECOVERY_POLICY_VERSION,
        scenario_count=len(results),
        failed_scenario_count=failed_count,
        plan_generation_failure_rate=failed_count / len(results),
        results=results,
    )


def report_as_json(report: CalibrationReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n"


def report_as_markdown(report: CalibrationReport) -> str:
    lines = [
        "# Safety rule calibration report",
        "",
        f"- Bundle: `{report.bundle_version}`",
        f"- Catalog: `{report.catalog_version_code}`",
        f"- Bundle production eligible: `{str(report.bundle_production_eligible).lower()}`",
        f"- Pain policy: `{report.pain_policy_version}`",
        f"- Recovery policy: `{report.recovery_policy_version}`",
        f"- Plan generation failure rate: `{report.failed_scenario_count}/{report.scenario_count}` "
        f"(`{report.plan_generation_failure_rate:.1%}`)",
        "",
        "| Scenario | Pool | Excluded | Caution | Failed | Applied cap | Action | Return mode |",
        "|---|---:|---:|---:|:---:|---|---|:---:|",
    ]
    lines.extend(
        "| "
        f"{result.scenario_code} | {result.approved_pool_size}/{result.total_candidate_count} | "
        f"{result.excluded_exercise_count} | {result.caution_exercise_count} | "
        f"{'yes' if result.plan_generation_failed else 'no'} | {result.applied_cap_code} | "
        f"{result.safety_action_code} | {'yes' if result.return_mode_active else 'no'} |"
        for result in report.results
    )
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_report(load_bundle(args.bundle))
    rendered = report_as_json(report) if args.format == "json" else report_as_markdown(report)
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
