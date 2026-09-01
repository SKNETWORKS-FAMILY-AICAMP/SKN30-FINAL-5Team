from __future__ import annotations

import csv
import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "route_v2_0_2_relationship_queues.py"
spec = importlib.util.spec_from_file_location("route_v2_0_2_relationship_queues", SCRIPT)
assert spec and spec.loader
routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routing)


class RelationshipQueueRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.batch_dir = routing.DEFAULT_BATCH_DIR
        cls.rows = routing.read_jsonl(cls.batch_dir / "review_batch.jsonl")

    def test_routes_all_records_to_disjoint_queues(self) -> None:
        counts = Counter(row["queue_code"] for row in self.rows)
        self.assertEqual(len(self.rows), 593)
        self.assertEqual(
            counts,
            Counter(
                {
                    "VARIANT_CANDIDATE_QUEUE": 79,
                    "SEPARATE_EXERCISE_QUEUE": 174,
                    "HOME_POLICY_EXCLUDED_QUEUE": 8,
                    "HUMAN_REVIEW_QUEUE": 332,
                }
            ),
        )
        self.assertEqual(sum(counts.values()), len(self.rows))
        self.assertEqual(len({row["candidate_pair_id"] for row in self.rows}), len(self.rows))

    def test_auto_routing_preserves_original_relation_and_records_evidence(self) -> None:
        self.assertTrue(all(row["candidate_relation_code"] for row in self.rows))
        auto_rows = [row for row in self.rows if row["decision_source"] == "AUTO_RULE"]
        self.assertEqual(len(auto_rows), 261)
        self.assertTrue(all(row["decision_reason_code"] for row in auto_rows))
        self.assertTrue(all(row["decision_note"] for row in auto_rows))

    def test_human_review_rows_have_korean_reason(self) -> None:
        human_rows = [row for row in self.rows if row["queue_code"] == "HUMAN_REVIEW_QUEUE"]
        self.assertEqual(len(human_rows), 332)
        self.assertTrue(
            all(
                row.get("human_review_reason_ko", "").endswith(
                    "자동 중복 확정 대신 사람 확인이 필요함."
                )
                for row in human_rows
            )
        )

    def test_home_policy_exclusion_is_exactly_the_known_step_box_set(self) -> None:
        expected = {
            ("bodyweight_crunch_core_brace_bodyweight", "cardio_gait_step_box"),
            (
                "bodyweight_crunch_core_brace_bodyweight",
                "dumbbell_step_up_lunge_knee_dominant_dumbbell_step_box",
            ),
            (
                "bodyweight_forward_lunge_knee_dominant_bodyweight",
                "dumbbell_step_up_lunge_knee_dominant_dumbbell_step_box",
            ),
            (
                "bodyweight_split_squat_knee_dominant_bodyweight",
                "dumbbell_step_up_lunge_knee_dominant_dumbbell_step_box",
            ),
            ("cardio_gait_bodyweight", "cardio_gait_step_box"),
            ("cardio_gait_bodyweight_rex_000058", "cardio_gait_step_box"),
            ("cardio_gait_bodyweight_rex_000062", "cardio_gait_step_box"),
            (
                "dumbbell_goblet_squat_knee_dominant_dumbbell",
                "dumbbell_step_up_lunge_knee_dominant_dumbbell_step_box",
            ),
        }
        actual = {
            (row["left_stable_code"], row["right_stable_code"])
            for row in self.rows
            if row["queue_code"] == "HOME_POLICY_EXCLUDED_QUEUE"
        }
        self.assertEqual(actual, expected)
        self.assertTrue(
            all(
                row["decision_reason_code"] == "HOME_UNSUPPORTED_STEP_BOX"
                for row in self.rows
                if row["queue_code"] == "HOME_POLICY_EXCLUDED_QUEUE"
            )
        )

    def test_queue_files_match_source_partition(self) -> None:
        source_ids = {row["candidate_pair_id"] for row in self.rows}
        for queue_code, stem in routing.QUEUE_FILES.items():
            expected_ids = {
                row["candidate_pair_id"] for row in self.rows if row["queue_code"] == queue_code
            }
            with (self.batch_dir / f"{stem}.jsonl").open(encoding="utf-8") as handle:
                jsonl_rows = [json.loads(line) for line in handle if line.strip()]
            with (self.batch_dir / f"{stem}.csv").open(encoding="utf-8-sig", newline="") as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual({row["candidate_pair_id"] for row in jsonl_rows}, expected_ids)
            self.assertEqual({row["candidate_pair_id"] for row in csv_rows}, expected_ids)
            self.assertTrue(expected_ids <= source_ids)

    def test_manifest_matches_generated_partition(self) -> None:
        with (self.batch_dir / "queue_manifest.json").open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["source_batch"]["record_count"], 593)
        self.assertEqual(manifest["summary"]["human_review_queue_count"], 332)
        self.assertEqual(manifest["summary"]["auto_rule_routed_count"], 261)
        self.assertEqual(len(manifest["queue_files"]), 4)


if __name__ == "__main__":
    unittest.main()
