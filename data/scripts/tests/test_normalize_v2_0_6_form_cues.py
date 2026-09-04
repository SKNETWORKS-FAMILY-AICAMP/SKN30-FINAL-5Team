from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "normalize_v2_0_6_form_cues.py"
spec = importlib.util.spec_from_file_location("normalize_v2_0_6_form_cues", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(identity: str, **overrides: str) -> dict[str, str]:
    return {
        "source_identity": identity,
        "stable_code": "goblet_squat",
        "name_ko": "덤벨 고블릿 스쿼트",
        "name_en": "dumbbell goblet squat",
        "instruction_summary_ko": "1. 발을 벌리고 섭니다 2. 무릎을 굽혀 내려갑니다",
        "equipment_codes": "DUMBBELL",
        "training_type_code": "STRENGTH",
        "form_cues_ko": "기존 안내입니다.",
        "form_cues_review_status": "",
        "form_cues_source": "",
        "instruction_content_version": "user-natural-language-ko-v2.0.6",
        **overrides,
    }


def test_generates_clear_lower_body_cues_with_foot_and_knee_guidance() -> None:
    rows, report = module.apply_normalization([row("0001")])

    assert rows[0]["form_cues_ko"] == (
        "무릎이 발끝과 같은 방향을 향하게 하고 안쪽으로 무너지지 않게 합니다|"
        "발바닥 전체로 바닥을 밀어 몸을 일으킵니다"
    )
    assert rows[0]["form_cues_source"] == module.EDITORIAL_SOURCE
    assert rows[0]["form_cues_review_status"] == "APPROVED"
    assert report["editorial_safety_category_counts"] == {"lower_body": 1}


def test_preserves_gif_reviewed_meaning_while_removing_punctuation() -> None:
    rows, _ = module.apply_normalization(
        [
            row(
                "0002",
                form_cues_ko="허리가 과도하게 꺾이지 않게 합니다.|반동으로 움직이지 않습니다.",
                instruction_content_version=module.GIF_REVIEWED_CONTENT_VERSION,
                form_cues_source="data/media/videos/0002.gif",
            )
        ]
    )

    assert rows[0]["form_cues_ko"] == "허리가 과도하게 꺾이지 않게 합니다|반동으로 움직이지 않습니다"
    assert rows[0]["form_cues_source"] == "data/media/videos/0002.gif"


def test_stretch_cues_do_not_add_medical_claims() -> None:
    rows, _ = module.apply_normalization(
        [
            row(
                "0003",
                stable_code="hamstring_stretch",
                name_ko="햄스트링 스트레칭",
                name_en="hamstring stretch",
                training_type_code="MOBILITY",
            )
        ]
    )

    assert rows[0]["form_cues_ko"] == (
        "당김이 느껴지는 편안한 범위까지만 움직입니다|"
        "반동으로 늘리지 말고 숨을 편안히 쉬며 자세를 유지합니다"
    )


def test_distinguishes_floor_pushups_from_overhead_pressing() -> None:
    pushup_rows, _ = module.apply_normalization(
        [row("0004", stable_code="pushup", name_ko="푸시업", name_en="push up")]
    )
    press_rows, _ = module.apply_normalization(
        [row("0005", stable_code="dumbbell_push_press", name_ko="덤벨 푸시 프레스", name_en="dumbbell push press")]
    )

    assert "손바닥 전체로 바닥을 지지합니다" in pushup_rows[0]["form_cues_ko"]
    assert "허리를 과하게 젖히지 말고" in press_rows[0]["form_cues_ko"]


def test_form_cues_do_not_repeat_the_exercise_name() -> None:
    rows, _ = module.apply_normalization(
        [
            row(
                "0006",
                stable_code="chest_stretch",
                name_ko="가슴·어깨 스트레칭",
                name_en="chest stretch",
                training_type_code="MOBILITY",
            )
        ]
    )

    assert rows[0]["form_cues_ko"].startswith("당김이 느껴지는 편안한 범위까지만")
