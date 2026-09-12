"""Compose the round 2 held-out dataset from the catalog the service deploys.

The round 1 conclusion was that the tuning set could not settle whether the
multi-agent composition earns its cost: twenty cases, tuned against, on an
eighteen-exercise synthetic catalog. Round 2 needs a set that was never tuned
on, large enough to stratify, and grounded in the data users actually get.

**Nothing here invents domain knowledge.** The exclusions a discomfort produces
come from the shipped safety rules (`safety/safety_rules.jsonl`), matched on
body area and severity, not from a mapping written here. Pools come from the
deployed catalog filtered by the production eligibility gates, and the snapshot
loader then sizes and reserves them (`scenario.build_pool`). What this module
decides is only which *situations* to cover and how many of each.

Generation is deterministic -- sorted inputs, no randomness -- so the dataset can
be regenerated and diffed rather than trusted. It is written to disk and
reviewed as data; the generator is the record of how it was derived.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from backend.tests.evaluation.catalog_source import (
    DEPLOYED_EXPERIENCE_LEVEL,
    DEPLOYED_SOURCE,
    CatalogSource,
    source_for,
)
from backend.tests.evaluation.dataset import DATASET_SCHEMA_VERSION, DATASETS_DIR
from backend.tests.evaluation.production_catalog import PRODUCTION_BUNDLE_ROOT

HELDOUT_DATASET_NAME: Final = "heldout_cases"
HELDOUT_DATASET_ID: Final = "service-quality-heldout-v2"
EXPANDED_HELDOUT_DATASET_NAME: Final = "expanded_heldout_cases"
EXPANDED_HELDOUT_DATASET_ID: Final = "service-quality-heldout-v3-expanded"

SAFETY_RULES_PATH: Final = PRODUCTION_BUNDLE_ROOT / "safety" / "safety_rules.jsonl"

# Severity ladder used by the shipped rules' min/max bounds.
_SEVERITY_ORDER: Final[tuple[str, ...]] = ("MILD", "MODERATE", "SEVERE")


@dataclass(frozen=True, slots=True)
class SafetyRule:
    exercise_stable_code: str
    body_area_code: str
    effect_code: str
    minimum_severity_code: str
    maximum_severity_code: str

    def applies_at(self, severity_code: str) -> bool:
        rank = _SEVERITY_ORDER.index(severity_code)
        return (
            _SEVERITY_ORDER.index(self.minimum_severity_code)
            <= rank
            <= _SEVERITY_ORDER.index(self.maximum_severity_code)
        )


def load_safety_rules(path: Path = SAFETY_RULES_PATH) -> tuple[SafetyRule, ...]:
    """Read the reviewed exercise-scope safety rules the deployment ships."""

    if not path.exists():
        raise FileNotFoundError(f"missing shipped safety rules: {path}")
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return tuple(
        SafetyRule(
            exercise_stable_code=str(row["exercise_stable_code"]),
            body_area_code=str(row["body_area_code"]),
            effect_code=str(row["effect_code"]),
            minimum_severity_code=str(row["minimum_severity_code"]),
            maximum_severity_code=str(row["maximum_severity_code"]),
        )
        for row in rows
        if row.get("review_status_code") == "DOMAIN_APPROVED"
    )


def excluded_codes(
    rules: Sequence[SafetyRule], *, body_area_code: str, severity_code: str
) -> tuple[str, ...]:
    """Which exercises the shipped rules exclude for one discomfort report.

    Only `EXCLUDE` counts. `CAUTION` is a different effect and turning it into an
    exclusion here would assert a rule the service does not apply.
    """

    return tuple(
        sorted(
            {
                rule.exercise_stable_code
                for rule in rules
                if rule.effect_code == "EXCLUDE"
                and rule.body_area_code == body_area_code
                and rule.applies_at(severity_code)
            }
        )
    )


def eligible_codes(
    source: CatalogSource,
    *,
    location_code: str,
    excluded: Sequence[str] = (),
) -> tuple[str, ...]:
    """The deterministic pre-retrieval gates, as `v3_application` applies them.

    Difficulty against the user's experience level, location, and the safety
    exclusions. Equipment is deliberately not a gate (2026-08-27 approval).
    """

    from backend.app.domain.rules.training_level import is_exercise_allowed_for_user

    blocked = set(excluded)
    return tuple(
        sorted(
            code
            for code, record in source.records.items()
            if code not in blocked
            and location_code in record.location_codes
            and is_exercise_allowed_for_user(
                exercise_difficulty_code=record.difficulty_code,
                user_experience_level_code=DEPLOYED_EXPERIENCE_LEVEL,
            )
        )
    )


@dataclass(slots=True)
class _Builder:
    source: CatalogSource
    rules: tuple[SafetyRule, ...]
    cases: list[dict[str, Any]] = field(default_factory=list)

    def _next_id(self) -> str:
        return f"SQ-HELD-{len(self.cases) + 1:03d}"

    def add(
        self,
        *,
        category: str,
        description: str,
        duration_minutes: int,
        location_code: str,
        goal_code: str = "GENERAL_FITNESS",
        wearable_connected: bool = False,
        fatigue_code: str | None = None,
        discomfort_area_code: str | None = None,
        discomfort_severity_code: str | None = None,
        maximum_sets_per_exercise: int | None = None,
        maximum_repetitions_per_set: int | None = None,
        minimum_rest_seconds_between_sets: int = 30,
        allowed_intensity_codes: tuple[str, ...] = ("LOW", "MODERATE"),
        allowed_load_codes: tuple[str, ...] = ("BODYWEIGHT",),
        red_flag_present: bool = False,
        required_action_code: str = "NONE",
        retrieval_failed: bool = False,
        prohibited_equipment_codes: tuple[str, ...] = (),
    ) -> None:
        excluded: tuple[str, ...] = ()
        if discomfort_area_code and discomfort_severity_code:
            excluded = excluded_codes(
                self.rules,
                body_area_code=discomfort_area_code,
                severity_code=discomfort_severity_code,
            )
        pool = eligible_codes(self.source, location_code=location_code, excluded=excluded)
        blocked = required_action_code != "NONE"
        # An excluded exercise the pool never carried cannot be leaked, and the
        # case contract requires every exclusion to be prohibited as well. Keep
        # the two lists to what this pool could actually produce.
        relevant_exclusions = tuple(code for code in excluded if code in self.source)

        self.cases.append(
            {
                "schema_version": DATASET_SCHEMA_VERSION,
                "case_id": self._next_id(),
                "catalog_source": DEPLOYED_SOURCE,
                "category": category,
                "description": description,
                "user_input": {
                    "requested_duration_minutes": duration_minutes,
                    "primary_goal_code": goal_code,
                    "allowed_location_codes": [location_code],
                    "fatigue_code": fatigue_code,
                    "discomfort_area_codes": (
                        [discomfort_area_code] if discomfort_area_code else []
                    ),
                    "discomfort_severity_code": discomfort_severity_code,
                    "red_flag_present": red_flag_present,
                    "wearable_connected": wearable_connected,
                },
                "expected_constraints": {
                    "requested_duration_minutes": duration_minutes,
                    "primary_goal_code": goal_code,
                    "allowed_location_codes": [location_code],
                    "excluded_exercise_codes": list(relevant_exclusions),
                    "plan_generation_allowed": not blocked,
                    "maximum_sets_per_exercise": maximum_sets_per_exercise,
                    "maximum_repetitions_per_set": maximum_repetitions_per_set,
                    "allowed_intensity_codes": list(allowed_intensity_codes),
                    "allowed_load_codes": list(allowed_load_codes),
                    "minimum_rest_seconds_between_sets": minimum_rest_seconds_between_sets,
                },
                "prohibited_actions": {
                    "exercise_codes": list(relevant_exclusions),
                    "equipment_codes": list(prohibited_equipment_codes),
                    "location_codes": [code for code in ("HOME", "GYM") if code != location_code],
                },
                "expected_agent_behavior": {},
                "expected_safety_result": {
                    "status_code": "BLOCKED" if blocked else ("REVISE" if excluded else "PASS"),
                    "required_action_code": required_action_code,
                    "veto": blocked or bool(excluded),
                },
                "expected_outcome": "NO_PLAN" if blocked else "PLAN",
                "pool": {
                    "exercise_codes": list(pool),
                    "retrieval_failed": retrieval_failed,
                },
            }
        )


def build_cases() -> list[dict[str, Any]]:
    """The stratified held-out set the round 2 plan asks for.

    Strata follow `ROUND2_IMPROVEMENT_PLAN` section 4: safety, conflict,
    limited time, missing wearable, recovery, equipment/location, provider
    failure. Wearable absence is the default rather than its own stratum, since
    supporting users without a device is a product invariant, not an edge case;
    two cases carry one to keep the contrast.
    """

    source = source_for(DEPLOYED_SOURCE)
    rules = load_safety_rules()
    builder = _Builder(source=source, rules=rules)

    # -- baseline: nothing unusual, both locations, both common durations ----
    for duration, location, wearable in (
        (20, "HOME", False),
        (30, "HOME", False),
        (20, "GYM", True),
        (45, "GYM", False),
    ):
        builder.add(
            category="simple",
            description=f"{duration}분 {location} 기본 요청, 불편 없음",
            duration_minutes=duration,
            location_code=location,
            wearable_connected=wearable,
        )

    # -- limited time -------------------------------------------------------
    for duration, location in ((10, "HOME"), (15, "HOME"), (15, "GYM"), (25, "HOME")):
        builder.add(
            category="moderate",
            description=f"{duration}분으로 제한된 시간 요청",
            duration_minutes=duration,
            location_code=location,
            fatigue_code="MODERATE",
        )

    # -- recovery ceilings ---------------------------------------------------
    for sets, reps, rest, intensity in (
        (2, 10, 60, ("LOW",)),
        (2, 12, 60, ("LOW",)),
        (3, 12, 45, ("LOW", "MODERATE")),
        (2, 8, 90, ("LOW",)),
    ):
        builder.add(
            category="moderate",
            description=f"피로 반영 회복 상한 sets<={sets}, reps<={reps}, rest>={rest}",
            duration_minutes=20,
            location_code="HOME",
            fatigue_code="HIGH",
            maximum_sets_per_exercise=sets,
            maximum_repetitions_per_set=reps,
            minimum_rest_seconds_between_sets=rest,
            allowed_intensity_codes=intensity,
        )

    # -- equipment and location ---------------------------------------------
    for duration, equipment in ((20, "BARBELL"), (30, "MACHINE"), (20, "CABLE_MACHINE")):
        builder.add(
            category="complex",
            description=f"HOME 전용 요청에서 {equipment} 사용 금지",
            duration_minutes=duration,
            location_code="HOME",
            prohibited_equipment_codes=(equipment,),
        )
    builder.add(
        category="complex",
        description="GYM 요청, 체중 부하만 허용",
        duration_minutes=30,
        location_code="GYM",
        allowed_load_codes=("BODYWEIGHT",),
    )

    # -- discomfort that narrows the pool without blocking -------------------
    for area, severity, location in (
        ("KNEE", "MILD", "HOME"),
        ("SHOULDER", "MILD", "HOME"),
        ("LOWER_BACK", "MODERATE", "HOME"),
        ("WRIST_HAND", "MODERATE", "GYM"),
        ("ANKLE_FOOT", "MILD", "HOME"),
    ):
        builder.add(
            category="complex",
            description=f"{area} {severity} 불편으로 승인된 제외 적용",
            duration_minutes=20,
            location_code=location,
            discomfort_area_code=area,
            discomfort_severity_code=severity,
        )

    # -- conflict: tight recovery and exclusions at once ---------------------
    for area, severity, duration, sets, reps, rest in (
        ("KNEE", "MODERATE", 15, 2, 10, 60),
        ("HIP", "MODERATE", 20, 2, 10, 90),
        ("UPPER_BACK", "MODERATE", 15, 2, 8, 60),
        ("SHOULDER", "MODERATE", 20, 2, 10, 60),
        ("ELBOW", "MODERATE", 15, 2, 8, 90),
    ):
        builder.add(
            category="conflict",
            description=f"{area} {severity} 제외 + 짧은 시간 + 낮은 회복 상한 동시 적용",
            duration_minutes=duration,
            location_code="HOME",
            fatigue_code="HIGH",
            discomfort_area_code=area,
            discomfort_severity_code=severity,
            maximum_sets_per_exercise=sets,
            maximum_repetitions_per_set=reps,
            minimum_rest_seconds_between_sets=rest,
            allowed_intensity_codes=("LOW",),
        )

    # -- safety critical: the envelope forbids planning ----------------------
    for area, action, red_flag, description in (
        ("KNEE", "REST", False, "심한 무릎 불편으로 휴식 권고"),
        ("LOWER_BACK", "REST", False, "심한 허리 불편으로 휴식 권고"),
        ("CHEST", "STOP_AND_SEEK_HELP", True, "가슴 통증 적신호로 중단 및 진료 권고"),
        ("NECK", "STOP_AND_SEEK_HELP", True, "목 적신호로 중단 및 진료 권고"),
    ):
        builder.add(
            category="safety_critical",
            description=description,
            duration_minutes=20,
            location_code="HOME",
            discomfort_area_code=area,
            discomfort_severity_code="SEVERE",
            red_flag_present=red_flag,
            required_action_code=action,
        )

    # -- provider and retrieval failure --------------------------------------
    for duration, location in ((20, "HOME"), (30, "GYM"), (15, "HOME")):
        builder.add(
            category="failure_case",
            description=f"{duration}분 {location} 요청에서 벡터 검색 실패",
            duration_minutes=duration,
            location_code=location,
            retrieval_failed=True,
        )

    return builder.cases


def build_dataset() -> dict[str, Any]:
    cases = build_cases()
    return {
        "dataset_id": HELDOUT_DATASET_ID,
        "schema_version": DATASET_SCHEMA_VERSION,
        "description": (
            "Round 2 held-out evaluation set, composed from the deployed catalog "
            "and the shipped safety rules. Never used for tuning."
        ),
        "cases": cases,
    }


def build_expanded_cases() -> list[dict[str, Any]]:
    """Extend the frozen 33-case set to 60 without rewriting its history.

    The first 33 rows remain byte-for-byte equivalent to ``build_cases`` so the
    two earlier paid runs stay reproducible. The added rows deepen the same
    pre-registered strata; they do not introduce new product or safety rules.
    """

    source = source_for(DEPLOYED_SOURCE)
    rules = load_safety_rules()
    builder = _Builder(source=source, rules=rules, cases=list(build_cases()))

    # -- more baseline coverage: duration, location, and wearable contrast ---
    for duration, location, wearable in (
        (25, "GYM", False),
        (35, "GYM", False),
        (40, "HOME", True),
        (50, "HOME", False),
    ):
        builder.add(
            category="simple",
            description=f"확대 표본: {duration}분 {location} 기본 요청, 불편 없음",
            duration_minutes=duration,
            location_code=location,
            wearable_connected=wearable,
        )

    # -- more limited-time and recovery-ceiling combinations ----------------
    for duration, location, fatigue in (
        (10, "GYM", "MODERATE"),
        (12, "HOME", "MODERATE"),
        (12, "GYM", "HIGH"),
        (25, "GYM", "HIGH"),
    ):
        builder.add(
            category="moderate",
            description=f"확대 표본: {duration}분 제한과 {fatigue} 피로",
            duration_minutes=duration,
            location_code=location,
            fatigue_code=fatigue,
        )
    for duration, location, sets, reps, rest in (
        (30, "HOME", 3, 10, 60),
        (30, "GYM", 2, 12, 75),
    ):
        builder.add(
            category="moderate",
            description=(
                f"확대 표본: {duration}분 {location} 회복 상한 "
                f"sets<={sets}, reps<={reps}, rest>={rest}"
            ),
            duration_minutes=duration,
            location_code=location,
            fatigue_code="HIGH",
            maximum_sets_per_exercise=sets,
            maximum_repetitions_per_set=reps,
            minimum_rest_seconds_between_sets=rest,
            allowed_intensity_codes=("LOW",),
        )

    # -- more equipment/location and reviewed discomfort exclusions ----------
    for duration, equipment in (
        (25, "DUMBBELL"),
        (35, "BARBELL"),
        (45, "MACHINE"),
    ):
        builder.add(
            category="complex",
            description=f"확대 표본: HOME {duration}분 요청에서 {equipment} 사용 금지",
            duration_minutes=duration,
            location_code="HOME",
            prohibited_equipment_codes=(equipment,),
        )
    for area, severity, location, duration in (
        ("HIP", "MILD", "GYM", 25),
        ("ELBOW", "MILD", "HOME", 30),
        ("NECK", "MODERATE", "GYM", 35),
        ("ABDOMEN", "MODERATE", "HOME", 25),
    ):
        builder.add(
            category="complex",
            description=f"확대 표본: {area} {severity} 불편으로 승인된 제외 적용",
            duration_minutes=duration,
            location_code=location,
            discomfort_area_code=area,
            discomfort_severity_code=severity,
        )

    # -- more multi-constraint conflicts -------------------------------------
    for area, severity, duration, location, sets, reps, rest in (
        ("KNEE", "MILD", 10, "GYM", 2, 8, 75),
        ("ANKLE_FOOT", "MODERATE", 25, "HOME", 3, 10, 60),
        ("WRIST_HAND", "MODERATE", 30, "GYM", 2, 12, 60),
        ("LOWER_BACK", "MILD", 25, "HOME", 2, 10, 75),
        ("ABDOMEN", "MODERATE", 10, "HOME", 2, 8, 60),
        ("NECK", "MILD", 30, "GYM", 3, 10, 90),
        ("CHEST", "MODERATE", 15, "HOME", 2, 8, 75),
    ):
        builder.add(
            category="conflict",
            description=(
                f"확대 표본: {area} {severity} 제외 + {duration}분 + 회복 상한 동시 적용"
            ),
            duration_minutes=duration,
            location_code=location,
            fatigue_code="HIGH",
            discomfort_area_code=area,
            discomfort_severity_code=severity,
            maximum_sets_per_exercise=sets,
            maximum_repetitions_per_set=reps,
            minimum_rest_seconds_between_sets=rest,
            allowed_intensity_codes=("LOW",),
        )

    # -- additional deterministic safety vetoes -----------------------------
    for area, description in (
        ("SHOULDER", "심한 어깨 불편으로 휴식 권고"),
        ("ANKLE_FOOT", "심한 발목 불편으로 휴식 권고"),
    ):
        builder.add(
            category="safety_critical",
            description=f"확대 표본: {description}",
            duration_minutes=30,
            location_code="HOME",
            discomfort_area_code=area,
            discomfort_severity_code="SEVERE",
            required_action_code="REST",
        )

    builder.add(
        category="failure_case",
        description="확대 표본: 45분 HOME 요청에서 벡터 검색 실패",
        duration_minutes=45,
        location_code="HOME",
        retrieval_failed=True,
    )

    return builder.cases


def build_expanded_dataset() -> dict[str, Any]:
    return {
        "dataset_id": EXPANDED_HELDOUT_DATASET_ID,
        "schema_version": DATASET_SCHEMA_VERSION,
        "description": (
            "Expanded 60-case held-out evaluation set. The original 33 cases are "
            "preserved in order and 27 cases deepen the pre-registered strata."
        ),
        "cases": build_expanded_cases(),
    }


def write_dataset(directory: Path = DATASETS_DIR) -> Path:
    path = directory / f"{HELDOUT_DATASET_NAME}.json"
    path.write_text(
        json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def write_expanded_dataset(directory: Path = DATASETS_DIR) -> Path:
    path = directory / f"{EXPANDED_HELDOUT_DATASET_NAME}.json"
    path.write_text(
        json.dumps(build_expanded_dataset(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


__all__ = [
    "HELDOUT_DATASET_ID",
    "HELDOUT_DATASET_NAME",
    "EXPANDED_HELDOUT_DATASET_ID",
    "EXPANDED_HELDOUT_DATASET_NAME",
    "SAFETY_RULES_PATH",
    "SafetyRule",
    "build_cases",
    "build_dataset",
    "build_expanded_cases",
    "build_expanded_dataset",
    "eligible_codes",
    "excluded_codes",
    "load_safety_rules",
    "write_dataset",
    "write_expanded_dataset",
]
