from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

SCRIPT_DIR = Path(__file__).resolve().parents[1]

# 스크립트끼리 형제 모듈을 import하므로 로더가 경로를 알아야 한다.
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


load_script("kspo_fitness100_pipeline", "kspo_fitness100_pipeline.py")
rules_module = load_script("build_exercise_safety_rules", "build_exercise_safety_rules.py")


@contextmanager
def workspace_directory() -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix="helkki-test-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


POLICY = {
    "schema_version": "1.0",
    "status": "APPROVED",
    "policy_version": "1.0.0",
    "severity_effects": {
        "PRIMARY": [
            {
                "minimum_severity_code": "MILD",
                "maximum_severity_code": "SEVERE",
                "effect_code": "EXCLUDE",
                "reason_code": "DIRECT_JOINT_LOAD",
            }
        ],
        "SECONDARY": [
            {
                "minimum_severity_code": "MILD",
                "maximum_severity_code": "MILD",
                "effect_code": "CAUTION",
                "reason_code": "STABILIZER_LOAD",
            },
            {
                "minimum_severity_code": "MODERATE",
                "maximum_severity_code": "SEVERE",
                "effect_code": "EXCLUDE",
                "reason_code": "STABILIZER_LOAD",
            },
        ],
    },
    "pattern_rules": {
        "KNEE_DOMINANT": {"primary": ["KNEE"], "secondary": []},
        "HORIZONTAL_PULL": {"primary": ["UPPER_BACK"], "secondary": ["ELBOW"]},
    },
}


def exercise(
    stable_code: str,
    pattern: str,
    primary: list[str],
    secondary: list[str],
) -> dict[str, object]:
    return {
        "stable_code": stable_code,
        "name_ko": f"운동 {stable_code}",
        "primary_movement_pattern_code": pattern,
        "body_focus_code": "LOWER_BODY",
        "primary_body_area_codes": primary,
        "secondary_body_area_codes": secondary,
        "recovery_eligible": False,
        "review_status_code": "DOMAIN_APPROVED",
    }


DEFAULT_EXERCISES = [
    exercise("leg_press", "KNEE_DOMINANT", ["KNEE", "HIP"], ["LOWER_BACK"]),
    exercise("leg_extension", "KNEE_DOMINANT", ["KNEE"], []),
    exercise("seated_row", "HORIZONTAL_PULL", ["UPPER_BACK"], ["ELBOW"]),
]


def write_seed(root: Path, name: str, exercises: list[dict[str, object]]) -> Path:
    seed_dir = root / f"exercise-catalog-seed-{name}"
    seed_dir.mkdir(parents=True)
    path = seed_dir / "exercises.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in exercises:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    raw = path.read_bytes()
    manifest = {
        "schema_version": "1.0",
        "catalog_version": {"version_code": name, "status_code": "DRAFT"},
        "review": {"status": "DOMAIN_APPROVED", "production_eligible": False},
        "files": [{"path": "exercises.jsonl", "sha256": rules_module.sha256_bytes(raw)}],
    }
    (seed_dir / "seed_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return seed_dir


class ExerciseSafetyRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = workspace_directory()
        self.root = self.stack.__enter__()
        self.policy = self.root / "policy.json"
        self.write_policy(POLICY)
        self.seed = write_seed(self.root, "t1", DEFAULT_EXERCISES)

    def tearDown(self) -> None:
        self.stack.__exit__(None, None, None)

    def write_policy(self, payload: Mapping[str, object]) -> None:
        self.policy.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def build(self, version: str = "v1") -> Path:
        return rules_module.build_rules([self.seed], self.policy, self.root / "generated", version)

    def load_rules(self, rules_dir: Path) -> list[dict[str, object]]:
        raw = (rules_dir / "safety_rules.jsonl").read_bytes()
        return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]

    def test_draft_policy_blocks_rule_generation(self) -> None:
        self.write_policy({**POLICY, "status": "DRAFT"})

        with self.assertRaisesRegex(rules_module.PipelineError, "not APPROVED"):
            self.build()
        self.assertFalse((self.root / "generated").exists())

    def test_overgeneralised_pattern_rule_fails_closed(self) -> None:
        """레그 익스텐션은 엉덩관절 부하가 없다. 패턴이 HIP을 주장하면 실패해야 한다."""

        broken = json.loads(json.dumps(POLICY))
        broken["pattern_rules"]["KNEE_DOMINANT"]["primary"] = ["KNEE", "HIP"]
        self.write_policy(broken)

        with self.assertRaisesRegex(rules_module.PipelineError, "does not load it that way"):
            self.build()
        self.assertFalse((self.root / "generated").exists())

    def test_rule_targets_exactly_one_of_exercise_or_pattern(self) -> None:
        """docs/DATA_MODEL.md 5.9의 배타 제약."""

        for rule in self.load_rules(self.build()):
            has_exercise = bool(rule["exercise_stable_code"])
            has_pattern = bool(rule["movement_pattern_code"])
            self.assertNotEqual(has_exercise, has_pattern, rule)

    def test_pattern_covered_area_is_not_repeated_per_exercise(self) -> None:
        rules = self.load_rules(self.build())
        knee_exercise_rules = [
            r
            for r in rules
            if r["rule_scope"] == "EXERCISE"
            and r["body_area_code"] == "KNEE"
            and r["exercise_stable_code"] in {"leg_press", "leg_extension"}
        ]
        self.assertEqual(knee_exercise_rules, [])

    def test_golden_knee_mild_and_moderate_exclude_knee_loading_exercises(self) -> None:
        """필수 골든 4: 무릎 MILD/MODERATE는 충돌 운동을 제외한다."""

        rules = self.load_rules(self.build())
        for severity in ("MILD", "MODERATE"):
            resolved = rules_module.resolve_effects(rules, DEFAULT_EXERCISES, "KNEE", severity)
            self.assertEqual(resolved.get("leg_press"), "EXCLUDE", severity)
            self.assertEqual(resolved.get("leg_extension"), "EXCLUDE", severity)
            self.assertIsNone(resolved.get("seated_row"), severity)

    def test_secondary_area_is_caution_at_mild_and_exclude_at_moderate(self) -> None:
        rules = self.load_rules(self.build())

        mild = rules_module.resolve_effects(rules, DEFAULT_EXERCISES, "LOWER_BACK", "MILD")
        moderate = rules_module.resolve_effects(rules, DEFAULT_EXERCISES, "LOWER_BACK", "MODERATE")

        self.assertEqual(mild.get("leg_press"), "CAUTION")
        self.assertEqual(moderate.get("leg_press"), "EXCLUDE")

    def test_no_rule_applies_at_severity_none(self) -> None:
        rules = self.load_rules(self.build())
        for rule in rules:
            self.assertFalse(rules_module.applies(rule, "NONE"), rule)

    def test_coverage_report_counts_selectable_exercises(self) -> None:
        rules = self.load_rules(self.build())

        report = rules_module.build_coverage_report(rules, DEFAULT_EXERCISES)

        self.assertEqual(report["_total_exercises"], 3)
        knee = report["KNEE"]
        assert isinstance(knee, dict)
        self.assertEqual(knee["MODERATE"]["selectable"], 1)
        self.assertEqual(knee["MODERATE"]["excluded_codes"], ["leg_extension", "leg_press"])

    def test_build_and_verify_round_trip(self) -> None:
        rules_dir = self.build()

        result = rules_module.verify_rules(rules_dir)

        self.assertEqual(result["status"], "valid")
        self.assertFalse(result["production_eligible"])
        manifest = json.loads((rules_dir / "rules_manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["review"]["production_eligible"])
        self.assertEqual(manifest["review"]["review_method_code"], "AGENT_ONLY")
        artifacts = manifest["source"]["catalog_seed_artifacts"]
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(len(artifacts[0]["seed_manifest_sha256"]), 64)
        self.assertEqual(len(artifacts[0]["exercises_sha256"]), 64)

    def test_tampered_rules_file_fails_verification(self) -> None:
        rules_dir = self.build()
        path = rules_dir / "safety_rules.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        record["effect_code"] = "CAUTION"
        lines[0] = json.dumps(record, ensure_ascii=False, sort_keys=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(rules_module.PipelineError, "hash or size mismatch"):
            rules_module.verify_rules(rules_dir)

    def test_seed_without_domain_approval_is_refused(self) -> None:
        rejected = [
            {**DEFAULT_EXERCISES[0], "review_status_code": "TECH_REVIEWED"},
        ]
        seed_dir = write_seed(self.root, "t2", rejected)

        with self.assertRaisesRegex(rules_module.PipelineError, "without domain approval"):
            rules_module.build_rules([seed_dir], self.policy, self.root / "generated", "v2")


if __name__ == "__main__":
    unittest.main()
