"""Korean display-name review rules shared by the KSPO and wger review gates.

wger snapshot에는 한국어 번역이 없고 KSPO 원천명은 영상 프레임 라벨이므로 모든
`review_display_name_ko` 값은 사람이 작성한다. 이 모듈은 작성된 값의 형식만 검사하며
번역을 생성하거나 제안하지 않는다.

각 규칙의 근거:

- 한글 포함: `docs/DATA_MODEL.md`의 `name_ko`는 한국어 표시명이다.
- 원천 영문명과 동일 금지: 영문명을 그대로 붙여넣은 미완료 행을 잡는다. 원천명에 한글이
  있으면(KSPO) 그대로 사용하는 것이 정상일 수 있으므로 이 규칙을 적용하지 않는다.
- 배치 내 중복 금지: 사용자에게 같은 이름의 운동이 둘 이상 보이지 않게 한다.
- 의료 표현 금지: `AGENTS.md` 제품 불변 규칙과 `docs/DOMAIN_RULES.md`의
  "의료 진단, 치료 또는 재활 처방이 아니다"를 표시명에 적용한다.

의료 표현 목록은 위 문장에서 직접 가져온 최소 집합이다. 확장은 PM과 도메인 검토자의
승인을 받는다.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable

HANGUL_SYLLABLE_PATTERN = re.compile(r"[가-힣]")
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
MEDICAL_CLAIM_TERMS = ("진단", "치료", "처방", "재활")


def normalized_display_name(value: object) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def display_name_problems(display_name: object, *, source_name: object = "") -> list[str]:
    """Return every rule violation for one authored Korean display name."""

    raw = "" if display_name is None else str(display_name)
    name = normalized_display_name(raw)
    problems: list[str] = []

    if not name:
        return ["Korean display name is missing"]
    if CONTROL_CHARACTER_PATTERN.search(raw):
        problems.append("Korean display name contains control characters")
    # macOS에서 입력한 한국어는 NFD인 경우가 많고 검토자가 눈으로 구분할 수 없으므로
    # 정규화 형태는 문제로 보지 않고 NFC로 맞춘다. 공백은 눈에 보이므로 반려한다.
    if raw != raw.strip():
        problems.append("Korean display name has leading or trailing whitespace")
    if not HANGUL_SYLLABLE_PATTERN.search(name):
        problems.append("Korean display name contains no Hangul")

    # KSPO 원천명은 이미 한국어이므로 그대로 쓰는 것이 정상일 수 있다. 영문 등 한글이
    # 없는 원천명을 그대로 붙여넣은 경우만 미완료로 본다.
    source = normalized_display_name(source_name)
    if (
        source
        and not HANGUL_SYLLABLE_PATTERN.search(source)
        and name.casefold() == source.casefold()
    ):
        problems.append("Korean display name is identical to the source name")

    found_terms = [term for term in MEDICAL_CLAIM_TERMS if term in name]
    if found_terms:
        problems.append(
            "Korean display name uses medical claim language: " + ", ".join(found_terms)
        )
    return problems


def duplicate_display_names(display_names: Iterable[object]) -> list[str]:
    """Return display names used by more than one exercise, in sorted order."""

    counts = Counter(
        normalized_display_name(name) for name in display_names if normalized_display_name(name)
    )
    return sorted(name for name, count in counts.items() if count > 1)
