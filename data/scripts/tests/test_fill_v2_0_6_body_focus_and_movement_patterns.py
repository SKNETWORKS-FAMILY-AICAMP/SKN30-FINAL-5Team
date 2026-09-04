from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "fill_v2_0_6_body_focus_and_movement_patterns.py"
spec = importlib.util.spec_from_file_location(
    "fill_v2_0_6_body_focus_and_movement_patterns", SCRIPT
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(identity: str, **overrides: str) -> dict[str, str]:
    return {
        "source_identity": identity,
        "stable_code": "exercise",
        "name_ko": "운동",
        "name_en": "exercise",
        "instruction_summary_ko": "1. 천천히 움직입니다",
        "training_type_code": "STRENGTH",
        "body_focus_code": "",
        "primary_movement_pattern_code": "",
        **overrides,
    }


def test_fills_confirmed_adductors_and_patterns_from_instruction_action() -> None:
    rows, report = module.apply_fill(
        [
            row(
                "0168",
                stable_code="cable_hip_adduction",
                name_ko="케이블 힙 어덕션",
                instruction_summary_ko="다리를 몸의 정중선 쪽으로 옮깁니다",
            ),
            row(
                "0597",
                stable_code="lever_seated_hip_abduction",
                name_ko="레버 시티드 힙 어브덕션",
                instruction_summary_ko="다리를 몸의 중심선에서 멀어지게 벌립니다",
            ),
            row(
                "3667",
                stable_code="side_lying_hip_adduction",
                name_ko="사이드 라잉 힙 어덕션",
                instruction_summary_ko="내전근에 힘을 주고 다리를 들어 올립니다",
            ),
        ]
    )

    assert [item["body_focus_code"] for item in rows] == ["ADDUCTORS"] * 3
    assert [item["primary_movement_pattern_code"] for item in rows] == ["ISOLATION"] * 3
    assert len(report["body_focus_updates"]) == 3


def test_classifies_instruction_actions_using_approved_pattern_codes() -> None:
    cases = {
        "squat": ("무릎을 굽혀 몸을 스쿼트 자세로 내립니다", "KNEE_DOMINANT"),
        "deadlift": ("엉덩이를 뒤로 밀며 바벨을 들어 올립니다", "HIP_DOMINANT"),
        "row": ("손잡이를 몸 쪽으로 당깁니다", "HORIZONTAL_PULL"),
        "overhead": ("덤벨을 머리 위로 밉니다", "VERTICAL_PUSH"),
        "jump": ("바닥을 밀며 점프하고 부드럽게 착지합니다", "JUMP_PLYOMETRIC"),
        "cardio": ("발을 번갈아 내디디며 달립니다", "GAIT"),
    }
    for stable, (instruction, expected) in cases.items():
        training_type = "CARDIO" if stable == "cardio" else "STRENGTH"
        assert (
            module.classify_movement_pattern(
                row(
                    "9999",
                    stable_code=stable,
                    instruction_summary_ko=instruction,
                    training_type_code=training_type,
                )
            )
            == expected
        )


def test_corrects_0514_from_jump_to_bodyweight_squat_pattern() -> None:
    rows, report = module.apply_fill(
        [
            row(
                "0514",
                stable_code="bodyweight_squat",
                name_ko="맨몸 스쿼트",
                instruction_summary_ko="1. 무릎을 굽혀 몸을 내립니다",
                primary_movement_pattern_code="JUMP_PLYOMETRIC",
            ),
            row("0168", stable_code="cable_hip_adduction"),
            row("0597", stable_code="lever_seated_hip_abduction"),
            row("3667", stable_code="side_lying_hip_adduction"),
        ]
    )
    assert rows[0]["primary_movement_pattern_code"] == "KNEE_DOMINANT"
    assert report["movement_pattern_updates"][0]["before"] == "JUMP_PLYOMETRIC"
