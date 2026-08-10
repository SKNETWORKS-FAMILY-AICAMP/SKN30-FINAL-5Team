from __future__ import annotations

import importlib.util
import sys
import unicodedata
import unittest
from pathlib import Path
from types import ModuleType

SCRIPT_DIR = Path(__file__).resolve().parents[1]

# 스크립트끼리 형제 모듈을 import하므로 로더가 경로를 알아야 한다. 이 줄이 없으면
# 테스트 모듈이 먼저 로드한 순서에 우연히 의존하게 된다.
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def load_script(module_name: str, file_name: str) -> ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / file_name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rules = load_script("korean_display_name_rules", "korean_display_name_rules.py")


class KoreanDisplayNameRuleTests(unittest.TestCase):
    def test_reviewed_korean_name_passes(self) -> None:
        self.assertEqual(
            rules.display_name_problems(
                "뉴트럴 그립 랫풀다운", source_name="Neutral Grip Lat Pulldown"
            ),
            [],
        )

    def test_latin_letters_are_allowed_when_hangul_is_present(self) -> None:
        self.assertEqual(rules.display_name_problems("T바 로우"), [])

    def test_missing_name_is_reported_once(self) -> None:
        self.assertEqual(rules.display_name_problems("   "), ["Korean display name is missing"])

    def test_english_only_name_is_rejected(self) -> None:
        problems = rules.display_name_problems(
            "Lat Pulldown", source_name="Neutral Grip Lat Pulldown"
        )

        self.assertIn("Korean display name contains no Hangul", problems)

    def test_untranslated_source_name_is_rejected(self) -> None:
        problems = rules.display_name_problems("Seated Cable Row", source_name="Seated Cable Row")

        self.assertIn("Korean display name is identical to the source name", problems)

    def test_korean_source_name_may_be_reused_as_display_name(self) -> None:
        """KSPO 원천명은 이미 한국어이므로 그대로 사용하는 것이 정상일 수 있다."""

        self.assertEqual(
            rules.display_name_problems("가슴펴고 천장보기", source_name="가슴펴고 천장보기"),
            [],
        )

    def test_medical_claim_language_is_rejected(self) -> None:
        problems = rules.display_name_problems("허리 통증 치료 운동")

        self.assertIn("Korean display name uses medical claim language: 치료", problems)

    def test_every_medical_term_is_detected(self) -> None:
        for term in rules.MEDICAL_CLAIM_TERMS:
            with self.subTest(term=term):
                problems = rules.display_name_problems(f"무릎 {term} 스트레칭")
                self.assertTrue(any("medical claim language" in problem for problem in problems))

    def test_surrounding_whitespace_is_rejected(self) -> None:
        problems = rules.display_name_problems(" 랫풀다운 ")

        self.assertIn("Korean display name has leading or trailing whitespace", problems)

    def test_control_characters_are_rejected(self) -> None:
        problems = rules.display_name_problems("랫풀\t다운")

        self.assertIn("Korean display name contains control characters", problems)

    def test_decomposed_hangul_from_macos_input_is_accepted(self) -> None:
        decomposed = unicodedata.normalize("NFD", "랫풀다운")
        self.assertNotEqual(decomposed, "랫풀다운")

        self.assertEqual(rules.display_name_problems(decomposed), [])

    def test_duplicate_display_names_are_reported(self) -> None:
        duplicates = rules.duplicate_display_names(["랫풀다운", "덤벨로우", "랫풀다운", "", "  "])

        self.assertEqual(duplicates, ["랫풀다운"])

    def test_duplicate_detection_normalizes_before_comparing(self) -> None:
        duplicates = rules.duplicate_display_names(["랫풀다운", " 랫풀다운"])

        self.assertEqual(duplicates, ["랫풀다운"])

    def test_unique_display_names_report_nothing(self) -> None:
        self.assertEqual(rules.duplicate_display_names(["랫풀다운", "덤벨로우", "스쿼트"]), [])


if __name__ == "__main__":
    unittest.main()
