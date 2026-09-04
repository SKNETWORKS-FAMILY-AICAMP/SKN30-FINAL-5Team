from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "normalize_v2_0_6_instruction_style.py"
spec = importlib.util.spec_from_file_location("normalize_v2_0_6_instruction_style", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_normalizes_imperative_and_adds_other_side_step() -> None:
    value = "바닥에 평평하게 누으십시오, 한쪽 다리를 듭니다, 이어서 내립니다."

    assert module.normalize_instruction("test", value) == (
        "1. 바닥에 평평하게 눕습니다 한쪽 다리를 듭니다 "
        "2. 내립니다 3. 반대쪽도 같은 순서로 수행합니다"
    )


def test_gif_override_is_used_for_standing_ankle_circles() -> None:
    result = module.normalize_instruction("1368", "기존 설명")

    assert result == (
        "1. 서서 한쪽 다리를 바닥에서 가볍게 듭니다 "
        "2. 든 발의 발목을 원을 그리며 돌립니다 "
        "3. 반대쪽도 같은 순서로 수행합니다"
    )


def test_0514_override_uses_bodyweight_squat_steps() -> None:
    result = module.normalize_instruction("0514", "점프합니다")
    assert "뛰어" not in result
    assert "무릎을 굽혀" in result
    assert result.endswith("니다")


def test_apply_style_rejects_non_polite_sentence() -> None:
    rows = [
        {
            "source_identity": "test",
            "stable_code": "test_exercise",
            "instruction_summary_ko": "팔을 든다.",
        }
    ]

    try:
        module.apply_style(rows)
    except module.InstructionStyleError as exc:
        assert "uniformly polite" in str(exc)
    else:
        raise AssertionError("non-polite sentence must fail")


def test_hand_grip_override_mentions_grip_and_weighted_object() -> None:
    result = module.normalize_instruction("0854", "기존 설명")
    assert "악력" in result
    assert "무게가 있는 물건" in result
    assert result.endswith("니다")


def test_removes_terminal_punctuation_and_uses_friendly_words() -> None:
    result = module.normalize_instruction(
        "test", "전완을 바닥에 둡니다. 햄스트링의 스트레칭을 느낍니다."
    )

    assert result == "1. 팔뚝을 바닥에 둡니다 2. 허벅지 뒤쪽이 늘어나는 느낌이 들도록 합니다"


def test_removes_all_sentence_punctuation_except_numbered_step_markers() -> None:
    result = module.normalize_instruction(
        "test", "팔을 듭니다, (천천히) 내립니다! 2초간 유지합니다."
    )

    assert result == "1. 팔을 듭니다 천천히 내립니다 2. 2초간 유지합니다"
