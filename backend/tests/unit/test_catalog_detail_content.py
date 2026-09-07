import pytest

from backend.app.modules.catalog.service import _instruction_steps


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ("1. 준비합니다 2. 천천히 움직입니다", ["준비합니다", "천천히 움직입니다"]),
        (
            "1. 준비합니다 2. 천천히 움직입니다 3. 시작 자세로 돌아옵니다",
            ["준비합니다", "천천히 움직입니다", "시작 자세로 돌아옵니다"],
        ),
        (
            "1. 준비합니다 2. 천천히 움직입니다 3. 멈춥니다 4. 돌아옵니다",
            ["준비합니다", "천천히 움직입니다", "멈춥니다", "돌아옵니다"],
        ),
    ],
)
def test_instruction_steps_split_reviewed_numbered_content(
    summary: str, expected: list[str]
) -> None:
    assert _instruction_steps(summary) == expected


def test_instruction_steps_falls_back_to_the_original_text_without_number_markers() -> None:
    summary = "번호가 없는 검수된 설명"

    assert _instruction_steps(summary) == [summary]
