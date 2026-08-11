from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_exercise_alternatives as alternatives  # noqa: E402


def exercise(
    code: str,
    difficulty: str,
    equipment: str,
    location: str,
    pattern: str,
) -> dict[str, object]:
    return {
        "stable_code": code,
        "name_ko": f"테스트 {code}",
        "difficulty_code": difficulty,
        "equipment_codes": [equipment],
        "location_codes": [location],
        "primary_movement_pattern_code": pattern,
        "review_status_code": "DOMAIN_APPROVED",
    }


class BuildExerciseAlternativesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="helkki-alternatives-test-"))
        self.seed = self.root / "exercise-catalog-seed-test"
        self.seed.mkdir()
        records = [
            exercise("knee_machine", "BEGINNER", "MACHINE", "GYM", "KNEE_DOMINANT"),
            exercise("knee_home", "BEGINNER", "CHAIR", "HOME", "KNEE_DOMINANT"),
            exercise("hip_gym", "BEGINNER", "DUMBBELL", "GYM", "HIP_DOMINANT"),
            exercise("hip_home", "BEGINNER", "MAT", "HOME", "HIP_DOMINANT"),
            exercise("core_easy", "BEGINNER", "MAT", "HOME", "CORE_BRACE"),
            exercise("core_harder", "INTERMEDIATE", "CABLE_MACHINE", "GYM", "CORE_BRACE"),
        ]
        exercise_path = self.seed / "exercises.jsonl"
        exercise_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
            encoding="utf-8",
        )
        raw = exercise_path.read_bytes()
        (self.seed / "seed_manifest.json").write_text(
            json.dumps(
                {
                    "catalog_version": {"version_code": "test-v1", "status_code": "DRAFT"},
                    "review": {"production_eligible": False},
                    "files": [
                        {
                            "path": "exercises.jsonl",
                            "sha256": alternatives.sha256_bytes(raw),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.safety = self.root / "safety"
        self.safety.mkdir()
        (self.safety / "rules_manifest.json").write_text("{}\n", encoding="utf-8")
        (self.safety / "coverage_report.json").write_text(
            json.dumps(
                {
                    "KNEE": {
                        "MILD": {"excluded_codes": ["knee_machine", "knee_home"]},
                        "MODERATE": {
                            "excluded_codes": [
                                "knee_machine",
                                "knee_home",
                                "hip_gym",
                                "hip_home",
                            ]
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        self.policy = self.root / "policy.json"
        self.policy_payload: dict[str, object] = {
            "policy_version": "1.0.0",
            "status": "APPROVED_FOR_DRAFT_PIPELINE",
            "review_method_code": "AGENT_ONLY",
            "production_eligible": False,
            "reviewed_at": "2026-08-11T18:00:00+09:00",
            "reason_codes": ["DIFFICULTY", "EQUIPMENT", "LOCATION", "DISCOMFORT"],
            "difficulty_rank": {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2},
            "exact_goal_groups": [
                {
                    "goal_preservation_code": "KNEE_EXTENSION_STRENGTH",
                    "exercise_codes": ["knee_machine", "knee_home"],
                },
                {
                    "goal_preservation_code": "HIP_EXTENSION_STRENGTH",
                    "exercise_codes": ["hip_gym", "hip_home"],
                },
                {
                    "goal_preservation_code": "CORE_STABILITY",
                    "exercise_codes": ["core_easy", "core_harder"],
                },
            ],
            "discomfort_cross_group_rules": [
                {
                    "goal_preservation_code": "LOWER_BODY_STRENGTH",
                    "source_goal_group": "KNEE_EXTENSION_STRENGTH",
                    "alternative_goal_group": "HIP_EXTENSION_STRENGTH",
                    "alternative_difficulty_code": "BEGINNER",
                    "bidirectional": True,
                    "reason_code": "DISCOMFORT",
                }
            ],
        }
        self.write_policy()

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def write_policy(self) -> None:
        self.policy.write_text(
            json.dumps(self.policy_payload, ensure_ascii=False), encoding="utf-8"
        )

    def build(self) -> Path:
        return alternatives.build_alternatives(
            [self.seed],
            self.safety,
            self.policy,
            self.root / "generated",
            "test-v1",
        )

    def test_builds_directional_relations_and_knee_fallback_coverage(self) -> None:
        output = self.build()
        result = alternatives.verify_alternatives(output)
        self.assertEqual(result["status"], "valid")
        rows = [
            json.loads(line)
            for line in (output / "alternatives.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        pairs = {
            (row["source_exercise_stable_code"], row["alternative_exercise_stable_code"])
            for row in rows
        }
        self.assertIn(("core_harder", "core_easy"), pairs)
        self.assertNotIn(("core_easy", "core_harder"), pairs)
        self.assertTrue(all(row["difficulty_delta"] <= 0 for row in rows))
        coverage = json.loads((output / "coverage_report.json").read_text(encoding="utf-8"))
        self.assertEqual(coverage["knee_discomfort"]["MILD"]["sources_with_safe_candidate"], 2)
        self.assertEqual(coverage["knee_discomfort"]["MODERATE"]["sources_with_safe_candidate"], 0)
        self.assertEqual(
            len(coverage["knee_discomfort"]["MODERATE"]["fallback_required_sources"]), 2
        )

    def test_unknown_policy_exercise_fails_closed(self) -> None:
        groups = self.policy_payload["exact_goal_groups"]
        assert isinstance(groups, list) and isinstance(groups[0], dict)
        groups[0]["exercise_codes"] = ["knee_machine", "missing"]
        self.write_policy()
        with self.assertRaisesRegex(alternatives.PipelineError, "unknown"):
            self.build()

    def test_tampered_relation_file_fails_verification(self) -> None:
        output = self.build()
        path = output / "alternatives.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
        with self.assertRaisesRegex(alternatives.PipelineError, "hash or size mismatch"):
            alternatives.verify_alternatives(output)


if __name__ == "__main__":
    unittest.main()
