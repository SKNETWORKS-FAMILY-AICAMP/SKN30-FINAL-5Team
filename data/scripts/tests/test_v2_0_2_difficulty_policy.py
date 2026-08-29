from data.scripts.v2_0_2_difficulty_policy import apply_difficulty_policy, load_policy


def test_policy_is_user_reviewed() -> None:
    policy = load_policy()
    assert policy["reviewer"] == "USER_DIRECT_REVIEW"
    assert policy["review_status_code"] == "DOMAIN_APPROVED"


def test_cable_rule_has_priority() -> None:
    difficulty, rule = apply_difficulty_policy(
        {
            "stable_code": "bodyweight_crunch_core_brace_bodyweight",
            "equipment_codes": ["CABLE_MACHINE"],
        },
        "BEGINNER",
    )
    assert difficulty == "INTERMEDIATE"
    assert rule == "CABLE_MACHINE_IS_INTERMEDIATE"


def test_base_and_variant_rules() -> None:
    base_lunge, _ = apply_difficulty_policy(
        {
            "stable_code": "bodyweight_forward_lunge_knee_dominant_bodyweight",
            "equipment_codes": ["BODYWEIGHT"],
        },
        "INTERMEDIATE",
    )
    base_crunch, _ = apply_difficulty_policy(
        {
            "stable_code": "bodyweight_crunch_core_brace_bodyweight",
            "equipment_codes": ["BODYWEIGHT"],
        },
        "INTERMEDIATE",
    )
    reverse_crunch, _ = apply_difficulty_policy(
        {
            "stable_code": "bodyweight_reverse_crunch_core_brace_bodyweight",
            "equipment_codes": ["BODYWEIGHT"],
        },
        "BEGINNER",
    )
    assert base_lunge == "BEGINNER"
    assert base_crunch == "BEGINNER"
    assert reverse_crunch == "INTERMEDIATE"
