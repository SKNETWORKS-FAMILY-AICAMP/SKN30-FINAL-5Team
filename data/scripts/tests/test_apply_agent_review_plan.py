from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from apply_agent_review_plan import apply_plan  # noqa: E402
from build_exercise_catalog_seed import ATTRIBUTE_FIELDS, TRACKS, write_csv  # noqa: E402
from kspo_fitness100_pipeline import PipelineError  # noqa: E402


class ApplyAgentReviewPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.mapping = self.root / "mapping.csv"
        self.evidence = self.root / "evidence.csv"
        self.attributes = self.root / "attributes.csv"
        self.plan = self.root / "plan.json"
        self.policy = self.root / "policy.json"
        mapping_rows = []
        for position, decision in (("1", "INCLUDE"), ("2", "PENDING"), ("3", "PENDING")):
            mapping_rows.append(
                {
                    "batch_position": position,
                    "source_exercise_id": f"id-{position}",
                    "primary_source_name_en": f"Exercise {position}",
                    "review_normalized_exercise_id": "existing" if position == "1" else "",
                    "review_display_name_ko": "기존 운동" if position == "1" else "",
                    "review_taxonomy_code": "HORIZONTAL_PULL" if position == "1" else "",
                    "review_beginner_suitability": "YES" if position == "1" else "PENDING",
                    "review_execution_guidance_status": "APPROVED"
                    if position == "1"
                    else "PENDING",
                    "review_license_status": "APPROVED" if position == "1" else "PENDING",
                    "review_domain_safety_status": "APPROVED" if position == "1" else "PENDING",
                    "review_decision": decision,
                    "reviewer_notes": "existing" if position == "1" else "",
                    "review_status": "DRAFT",
                    "production_eligible": "false",
                }
            )
        write_csv(
            self.mapping,
            list(mapping_rows[0]),
            cast(list[dict[str, object]], mapping_rows),
        )

        evidence_rows = []
        for position in ("1", "2", "3"):
            for role in ("DATA_OWNER", "BACKEND_REVIEWER", "PM_REVIEWER", "DOMAIN_REVIEWER"):
                evidence_rows.append(
                    {
                        "source_exercise_id": f"id-{position}",
                        "target_reference": f"wger:id-{position}",
                        "reviewer_role_code": role,
                        "review_status_code": "DRAFT",
                        "reviewer_reference": "",
                        "evidence_reference": "",
                        "reviewed_at": "",
                    }
                )
        write_csv(
            self.evidence,
            list(evidence_rows[0]),
            cast(list[dict[str, object]], evidence_rows),
        )
        write_csv(
            self.attributes,
            ATTRIBUTE_FIELDS,
            [
                {
                    **dict.fromkeys(ATTRIBUTE_FIELDS, ""),
                    "source_identity": "id-1",
                    "review_normalized_exercise_id": "existing",
                    "review_display_name_ko": "기존 운동",
                    "attribute_status": "DOMAIN_APPROVED",
                }
            ],
        )
        self.policy.write_text(
            json.dumps(
                {
                    "review_method_code": "AGENT_ONLY",
                    "production_eligible": False,
                    "roles": [
                        {"reviewer_role_code": role, "reviewer_reference": f"AGENT-{role}"}
                        for role in (
                            "DATA_OWNER",
                            "BACKEND_REVIEWER",
                            "PM_REVIEWER",
                            "DOMAIN_REVIEWER",
                        )
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.payload: dict[str, Any] = {
            "status": "AGENT_REVIEWED_DRAFT",
            "review_method_code": "AGENT_ONLY",
            "production_eligible": False,
            "plan_version": "2.0.0",
            "reviewed_at": "2026-08-11T16:30:00+09:00",
            "tranches": [
                {
                    "track": "wger",
                    "includes": [
                        {
                            "batch_position": 2,
                            "stable_code": "new_row",
                            "name_ko": "새 로우 운동",
                            "training_type_code": "STRENGTH",
                            "body_focus_code": "UPPER_BODY",
                            "movement_pattern_code": "HORIZONTAL_PULL",
                            "difficulty_code": "BEGINNER",
                            "beginner_suitability": "YES",
                            "timing_mode_code": "REPS",
                            "default_seconds_per_rep": 4,
                            "default_rest_seconds": 60,
                            "recovery_eligible": False,
                            "primary_body_area_codes": ["UPPER_BACK"],
                            "secondary_body_area_codes": ["ELBOW"],
                            "equipment_codes": ["DUMBBELL"],
                            "location_codes": ["GYM"],
                            "instruction_summary_ko": "자세를 안정적으로 유지하며 당긴다.",
                            "form_cues_ko": [
                                "허리를 곧게 편다",
                                "반동을 쓰지 않는다",
                                "천천히 돌아온다",
                            ],
                        }
                    ],
                    "exclude_groups": [
                        {
                            "positions": [3],
                            "reason_code": "REDUNDANT",
                            "reason_ko": "기존 운동과 중복된다.",
                        }
                    ],
                }
            ],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self) -> tuple[dict[str, object], list[dict[str, str]], list[dict[str, str]]]:
        self.plan.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
        result = apply_plan(
            TRACKS["wger"],
            self.plan,
            self.policy,
            self.mapping,
            self.evidence,
            self.attributes,
            self.root / "mapping-out.csv",
            self.root / "evidence-out.csv",
            self.root / "attributes-out.csv",
        )
        with (self.root / "mapping-out.csv").open(encoding="utf-8-sig", newline="") as handle:
            mapping_rows = list(csv.DictReader(handle))
        with (self.root / "evidence-out.csv").open(encoding="utf-8-sig", newline="") as handle:
            evidence_rows = list(csv.DictReader(handle))
        return result, mapping_rows, evidence_rows

    def test_applies_complete_partition_and_agent_provenance(self) -> None:
        result, mapping_rows, evidence_rows = self._run()
        self.assertEqual(result["remaining_pending"], 0)
        self.assertEqual(
            [row["review_decision"] for row in mapping_rows], ["INCLUDE", "INCLUDE", "EXCLUDE"]
        )
        self.assertEqual(mapping_rows[0]["reviewer_notes"], "existing")
        self.assertIn("production_eligible=false", mapping_rows[1]["reviewer_notes"])
        included_evidence = [row for row in evidence_rows if row["target_reference"] == "wger:id-2"]
        self.assertEqual(
            {row["review_status_code"] for row in included_evidence},
            {"TECH_REVIEWED", "DOMAIN_APPROVED"},
        )
        self.assertTrue(
            all(row["reviewer_reference"].startswith("AGENT-") for row in included_evidence)
        )

    def test_rejects_omitted_pending_position(self) -> None:
        self.payload["tranches"][0]["exclude_groups"] = []
        self.plan.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "partition all pending rows"):
            apply_plan(
                TRACKS["wger"],
                self.plan,
                self.policy,
                self.mapping,
                self.evidence,
                self.attributes,
                self.root / "mapping-out.csv",
                self.root / "evidence-out.csv",
                self.root / "attributes-out.csv",
            )


if __name__ == "__main__":
    unittest.main()
