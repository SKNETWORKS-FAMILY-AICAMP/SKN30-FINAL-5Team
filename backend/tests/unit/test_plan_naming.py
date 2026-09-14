from backend.app.domain.rules.plan_naming import PLAN_NAMING_RULE_VERSION, build_plan_name


def test_plan_name_is_reproducible_and_uses_main_body_composition() -> None:
    upper = build_plan_name(
        action_code="KEEP",
        main_body_focus_codes=("UPPER_BODY", "UPPER_BODY", "CORE"),
        main_movement_pattern_codes=("HORIZONTAL_PUSH", "HORIZONTAL_PULL"),
        main_training_type_codes=("STRENGTH", "STRENGTH"),
    )
    lower = build_plan_name(
        action_code="KEEP",
        main_body_focus_codes=("LOWER_BODY", "LOWER_BODY"),
        main_movement_pattern_codes=("HIP_DOMINANT",),
        main_training_type_codes=("STRENGTH",),
    )

    assert upper == build_plan_name(
        action_code="KEEP",
        main_body_focus_codes=("UPPER_BODY", "UPPER_BODY", "CORE"),
        main_movement_pattern_codes=("HORIZONTAL_PUSH", "HORIZONTAL_PULL"),
        main_training_type_codes=("STRENGTH", "STRENGTH"),
    )
    assert upper.value == "상체 근력 루틴"
    assert lower.value == "하체 근력 루틴"
    assert upper.rule_version == PLAN_NAMING_RULE_VERSION
    assert "DOMINANT_FOCUS_UPPER_BODY" in upper.reason_codes


def test_plan_name_avoids_duplicate_mobility_label_and_marks_a_downshift() -> None:
    result = build_plan_name(
        action_code="DOWNSHIFT",
        main_body_focus_codes=("MOBILITY",),
        main_movement_pattern_codes=("MOBILITY_STRETCH",),
        main_training_type_codes=("MOBILITY",),
    )

    assert result.value == "가동성 컨디션 조절 루틴"
    assert "가동성 가동성" not in result.value
    assert "LOAD_ADJUSTED" in result.reason_codes


def test_plan_name_has_a_non_medical_fallback_for_incomplete_catalog_data() -> None:
    result = build_plan_name(
        action_code="KEEP",
        main_body_focus_codes=(),
        main_movement_pattern_codes=(),
        main_training_type_codes=(),
    )

    assert result.value == "오늘의 운동 루틴"
    assert result.reason_codes == ("FALLBACK",)
