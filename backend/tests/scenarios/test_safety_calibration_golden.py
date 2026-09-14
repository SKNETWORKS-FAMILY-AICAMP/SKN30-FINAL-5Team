from backend.scripts.safety_calibration_report import (
    DEFAULT_BUNDLE,
    LoadCapCode,
    build_report,
    load_bundle,
)


def test_v2_0_5_safety_calibration_golden_scenarios() -> None:
    report = build_report(load_bundle(DEFAULT_BUNDLE))
    results = {result.scenario_code: result for result in report.results}

    assert results["HEALTHY_NORMAL"].approved_pool_size == 162
    assert results["HEALTHY_NORMAL"].excluded_exercise_count == 0
    assert results["HEALTHY_NORMAL"].plan_generation_failed is False

    assert results["KNEE_NRS_3"].approved_pool_size == 122
    assert results["KNEE_NRS_3"].excluded_exercise_count == 40
    assert results["KNEE_NRS_3"].applied_cap_code is LoadCapCode.NORMAL

    assert results["KNEE_NRS_4"].approved_pool_size == 82
    assert results["KNEE_NRS_4"].excluded_exercise_count == 80
    assert results["KNEE_NRS_4"].applied_cap_code is LoadCapCode.LIGHT

    assert results["MULTI_AREA_NRS_6"].approved_pool_size == 16
    assert results["MULTI_AREA_NRS_6"].excluded_exercise_count == 146
    assert results["MULTI_AREA_NRS_6"].applied_cap_code is LoadCapCode.LIGHT

    assert results["KNEE_NRS_7"].approved_pool_size == 0
    assert results["KNEE_NRS_7"].plan_generation_failed is True
    assert results["KNEE_NRS_7"].applied_cap_code is LoadCapCode.STOP

    assert results["RED_FLAG"].approved_pool_size == 0
    assert results["RED_FLAG"].safety_action_code == "STOP_AND_SEEK_HELP"

    assert results["RECOVERY_VERY_LIGHT"].applied_cap_code is LoadCapCode.VERY_LIGHT
    assert results["RECOVERY_VERY_LIGHT"].plan_generation_failed is False

    assert results["RETURN_GAP_13_DAYS"].return_mode_active is False
    assert results["RETURN_GAP_13_DAYS"].plan_generation_failed is False
    assert results["RETURN_GAP_14_DAYS"].return_mode_active is True
    assert results["RETURN_GAP_14_DAYS"].plan_generation_failed is True
    assert results["RETURN_GAP_14_DAYS"].applied_cap_code is LoadCapCode.APPROVED_CAPS_REQUIRED

    assert report.failed_scenario_count == 3
    assert report.plan_generation_failure_rate == 3 / 9
