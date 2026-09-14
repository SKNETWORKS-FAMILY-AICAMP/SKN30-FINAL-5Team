import json
from dataclasses import replace

import pytest

import backend.scripts.safety_calibration_report as calibration
from backend.scripts.safety_calibration_report import (
    DEFAULT_BUNDLE,
    CalibrationInputError,
    CalibrationScenario,
    FatigueLevelCode,
    LoadCapCode,
    PainInput,
    build_report,
    load_bundle,
    recovery_cap,
    report_as_json,
    severity_for_nrs,
)


@pytest.mark.parametrize(
    ("score", "expected"),
    [(1, "MILD"), (3, "MILD"), (4, "MODERATE"), (6, "MODERATE"), (7, "SEVERE"), (10, "SEVERE")],
)
def test_nrs_policy_boundaries(score: int, expected: str) -> None:
    assert severity_for_nrs(score) == expected


@pytest.mark.parametrize("score", [0, 11, True])
def test_nrs_rejects_values_outside_policy(score: int) -> None:
    with pytest.raises(CalibrationInputError):
        severity_for_nrs(score)


@pytest.mark.parametrize(
    ("sleep_minutes", "fatigue", "expected"),
    [
        (420, FatigueLevelCode.LOW, LoadCapCode.NORMAL),
        (420, FatigueLevelCode.HIGH, LoadCapCode.LIGHT),
        (419, FatigueLevelCode.MODERATE, LoadCapCode.LIGHT),
        (359, FatigueLevelCode.LOW, LoadCapCode.LIGHT),
        (None, FatigueLevelCode.HIGH, LoadCapCode.VERY_LIGHT),
    ],
)
def test_recovery_cap_uses_documented_combination_table(
    sleep_minutes: int | None,
    fatigue: FatigueLevelCode,
    expected: LoadCapCode,
) -> None:
    assert recovery_cap(sleep_minutes, fatigue) is expected


def test_duplicate_pain_areas_are_rejected() -> None:
    with pytest.raises(CalibrationInputError):
        CalibrationScenario(
            scenario_code="DUPLICATE",
            pains=(PainInput("KNEE", 2), PainInput("KNEE", 4)),
        )


def test_bundle_manifest_hash_is_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(calibration, "_sha256", lambda _: "0" * 64)

    with pytest.raises(CalibrationInputError, match="hash mismatch"):
        load_bundle(DEFAULT_BUNDLE)


def test_json_report_is_identifier_free_and_deterministic() -> None:
    report = build_report(load_bundle(DEFAULT_BUNDLE))

    first = report_as_json(report)
    second = report_as_json(report)

    assert first == second
    assert "user_id" not in first
    assert "email" not in first
    assert json.loads(first)["scenario_count"] == 9


def test_report_metrics_do_not_depend_on_bundle_row_order() -> None:
    bundle = load_bundle(DEFAULT_BUNDLE)
    reordered = replace(
        bundle,
        exercises=tuple(reversed(bundle.exercises)),
        rules=tuple(reversed(bundle.rules)),
    )

    assert build_report(reordered) == build_report(bundle)
