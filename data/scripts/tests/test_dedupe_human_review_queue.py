from __future__ import annotations

import csv
import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "dedupe_human_review_queue.py"
spec = importlib.util.spec_from_file_location("dedupe_human_review_queue", SCRIPT)
assert spec and spec.loader
dedupe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dedupe)


class HumanReviewQueueDedupeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.batch_dir = dedupe.DEFAULT_BATCH_DIR
        cls.batch_rows = dedupe.read_jsonl(cls.batch_dir / "review_batch.jsonl")
        cls.human_rows = dedupe.read_jsonl(cls.batch_dir / "human_review_queue.jsonl")

    def test_duplicate_pairs_are_removed_from_both_jsonl_outputs(self) -> None:
        batch_ids = {row["candidate_pair_id"] for row in self.batch_rows}
        human_ids = {row["candidate_pair_id"] for row in self.human_rows}
        self.assertEqual(len(self.batch_rows), 593)
        self.assertEqual(len(self.human_rows), 332)
        self.assertFalse(set(dedupe.DUPLICATE_DECISIONS) & batch_ids)
        self.assertFalse(set(dedupe.DUPLICATE_DECISIONS) & human_ids)

    def test_manifest_records_all_deleted_pair_decisions(self) -> None:
        with (self.batch_dir / "queue_manifest.json").open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        decisions = {
            item["candidate_pair_id"] for item in manifest["duplicate_deduplication"]["decisions"]
        }
        self.assertEqual(decisions, set(dedupe.DUPLICATE_DECISIONS))

    def test_csv_outputs_match_jsonl_outputs(self) -> None:
        for filename, expected_rows in [
            ("review_batch.csv", self.batch_rows),
            ("human_review_queue.csv", self.human_rows),
        ]:
            with (self.batch_dir / filename).open(encoding="utf-8-sig", newline="") as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual(
                {row["candidate_pair_id"] for row in csv_rows},
                {row["candidate_pair_id"] for row in expected_rows},
            )

    def test_manifests_record_deduplication(self) -> None:
        with (self.batch_dir / "queue_manifest.json").open(encoding="utf-8") as handle:
            queue_manifest = json.load(handle)
        self.assertEqual(queue_manifest["source_batch"]["record_count"], 593)
        self.assertEqual(queue_manifest["summary"]["human_review_queue_count"], 332)
        self.assertEqual(queue_manifest["duplicate_deduplication"]["removed_pair_count"], 10)


if __name__ == "__main__":
    unittest.main()
