from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import sys
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import uuid4

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


kspo_pipeline = load_script("kspo_fitness100_pipeline", "kspo_fitness100_pipeline.py")
kspo_profile = load_script("profile_kspo_fitness100", "profile_kspo_fitness100.py")
kspo_batch = load_script(
    "build_kspo_fitness100_review_batch", "build_kspo_fitness100_review_batch.py"
)
seed = load_script("build_exercise_catalog_seed", "build_exercise_catalog_seed.py")

TRACK = seed.TRACKS["kspo"]


@contextmanager
def workspace_directory() -> Iterator[Path]:
    path = Path.cwd() / f"test-work-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def response_bytes(items: list[dict[str, object]]) -> bytes:
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
            "body": {"pageNo": 1, "totalCount": len(items), "items": {"item": items}},
        }
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def source_items() -> list[dict[str, object]]:
    base: dict[str, object] = {
        "aggrp_nm": "성인기",
        "trng_plc_nm": "실내",
        "tool_nm": "매트",
        "trng_mscl_part": "복부",
        "set_cnt_nm": "",
        "rptt_tcnt_nm": "",
        "trng_hr_nm": "",
        "ecrg_cycl_nm": "",
        "vdo_desc": "원천 설명",
        "vdo_ttl_nm": "원천 제목",
    }
    names = ["가슴펴기", "무릎 굽히기", "팔 들어올리기"]
    return [
        {**base, "file_nm": f"v-{i}.mp4", "trng_nm": n, "img_file_nm": f"{i}.jpg"}
        for i, n in enumerate(names, start=1)
    ]


def make_batch(root: Path) -> Path:
    snapshot = kspo_pipeline.collect_snapshot(
        service_key="test-secret",
        endpoint="training-video",
        output_root=root / "snapshots",
        page_size=100,
        fetcher=lambda _u, _t: response_bytes(source_items()),
        now=datetime(2026, 8, 11, 7, 0, tzinfo=UTC),
    )
    profile = kspo_profile.create_profile(snapshot, root / "profiles")
    return kspo_batch.create_review_batch(profile, root / "review_batches", size=3)


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
        return list(reader.fieldnames), list(reader)


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


APPROVED_REGISTRY = {
    "schema_version": "1.0",
    "status": "APPROVED",
    "code_sets": {
        "training_type_code": [{"code": "STRENGTH"}, {"code": "MOBILITY"}],
        "body_focus_code": [{"code": "CORE"}, {"code": "UPPER_BODY"}],
        "movement_pattern_code": [{"code": "CORE_BRACE"}, {"code": "MOBILITY_STRETCH"}],
        "equipment_code": [{"code": "MAT"}, {"code": "BODYWEIGHT"}],
        "location_code": [{"code": "HOME"}],
    },
}


def write_registry(path: Path, status: str = "APPROVED") -> Path:
    payload = {**APPROVED_REGISTRY, "status": status}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def complete_attribute_row(row: dict[str, str], index: int) -> None:
    row.update(
        {
            "training_type_code": "MOBILITY",
            "body_focus_code": "CORE",
            "primary_movement_pattern_code": "MOBILITY_STRETCH",
            "difficulty_code": "BEGINNER",
            "timing_mode_code": "DURATION",
            "default_seconds_per_rep": "",
            "default_work_seconds": "30",
            "default_rest_seconds": "30",
            "default_transition_seconds": "15",
            "recovery_eligible": "TRUE",
            "primary_body_area_codes": "ABDOMEN",
            "secondary_body_area_codes": "CHEST",
            "equipment_codes": "MAT",
            "location_codes": "HOME",
            "instruction_summary_ko": f"검수된 실행 안내 {index}",
            "form_cues_ko": "허리를 과도하게 젖히지 않는다",
            "instruction_content_version": "1.0.0",
            "attribute_status": "DOMAIN_APPROVED",
        }
    )


class BuildExerciseCatalogSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = workspace_directory()
        self.root = self.stack.__enter__()
        self.batch = make_batch(self.root)
        self.mapping = self.root / "mapping.csv"
        self.evidence = self.root / "evidence.csv"
        shutil.copyfile(self.batch / "review_batch.csv", self.mapping)
        shutil.copyfile(self.batch / "catalog_review_records_template.csv", self.evidence)

    def tearDown(self) -> None:
        self.stack.__exit__(None, None, None)

    def approve_all(self) -> None:
        fields, rows = read_rows(self.mapping)
        for index, row in enumerate(rows, start=1):
            row.update(
                {
                    "review_normalized_exercise_id": f"reviewed_exercise_{index}",
                    "review_display_name_ko": f"검수된 운동 {index}",
                    "review_taxonomy_code": "mobility_stretch",
                    "review_beginner_suitability": "YES",
                    "review_execution_guidance_status": "APPROVED",
                    "review_media_rights_status": "APPROVED",
                    "review_domain_safety_status": "APPROVED",
                    "review_decision": "INCLUDE",
                    "reviewer_notes": "synthetic",
                }
            )
        write_rows(self.mapping, fields, rows)

        fields, rows = read_rows(self.evidence)
        for row in rows:
            role = row["reviewer_role_code"]
            row.update(
                {
                    "review_status_code": "DOMAIN_APPROVED"
                    if role == "DOMAIN_REVIEWER"
                    else "TECH_REVIEWED",
                    "reviewer_reference": f"{role}:reviewer001",
                    "evidence_reference": "docs/reviews/TEST-001",
                    "reviewed_at": "2026-08-11T12:00:00+09:00",
                }
            )
        write_rows(self.evidence, fields, rows)

    def make_attributes(self) -> Path:
        attributes = self.root / "attributes.csv"
        seed.build_attribute_template(TRACK, self.batch, self.mapping, attributes)
        fields, rows = read_rows(attributes)
        for index, row in enumerate(rows, start=1):
            complete_attribute_row(row, index)
        write_rows(attributes, fields, rows)
        return attributes

    def test_readiness_reports_blockers_before_any_review(self) -> None:
        report = seed.assess_readiness(TRACK, self.batch, self.mapping, self.evidence, None, None)

        self.assertEqual(report["status"], "not_ready")
        self.assertEqual(report["seed_ready_rows"], 0)
        self.assertFalse(report["production_eligible"])
        joined = " ".join(str(b) for b in report["blockers"])
        self.assertIn("no INCLUDE or MERGE rows", joined)
        self.assertIn("taxonomy registry", joined)

    def test_template_requires_completed_mapping_review(self) -> None:
        with self.assertRaisesRegex(seed.PipelineError, "complete the mapping review first"):
            seed.build_attribute_template(TRACK, self.batch, self.mapping, self.root / "a.csv")

    def test_draft_taxonomy_registry_blocks_seed_build(self) -> None:
        self.approve_all()
        attributes = self.make_attributes()
        registry = write_registry(self.root / "registry.json", status="DRAFT")

        with self.assertRaisesRegex(seed.PipelineError, "requires an APPROVED code list"):
            seed.build_seed(
                TRACK,
                self.batch,
                self.mapping,
                self.evidence,
                attributes,
                registry,
                self.root / "generated",
                "v0.1.0",
            )
        self.assertFalse((self.root / "generated").exists())

    def test_missing_domain_evidence_blocks_seed_build(self) -> None:
        self.approve_all()
        attributes = self.make_attributes()
        registry = write_registry(self.root / "registry.json")
        fields, rows = read_rows(self.evidence)
        for row in rows:
            if row["reviewer_role_code"] == "DOMAIN_REVIEWER":
                row.update(
                    {
                        "review_status_code": "DRAFT",
                        "reviewer_reference": "",
                        "evidence_reference": "",
                        "reviewed_at": "",
                    }
                )
        write_rows(self.evidence, fields, rows)

        with self.assertRaises(seed.PipelineError):
            seed.build_seed(
                TRACK,
                self.batch,
                self.mapping,
                self.evidence,
                attributes,
                registry,
                self.root / "generated",
                "v0.1.0",
            )

    def test_transition_seconds_outside_contract_range_is_rejected(self) -> None:
        self.approve_all()
        attributes = self.make_attributes()
        registry = write_registry(self.root / "registry.json")
        fields, rows = read_rows(attributes)
        rows[0]["default_transition_seconds"] = "45"
        write_rows(attributes, fields, rows)

        with self.assertRaisesRegex(seed.PipelineError, "between 10 and 20"):
            seed.build_seed(
                TRACK,
                self.batch,
                self.mapping,
                self.evidence,
                attributes,
                registry,
                self.root / "generated",
                "v0.1.0",
            )

    def test_body_area_outside_domain_rules_is_rejected(self) -> None:
        self.approve_all()
        attributes = self.make_attributes()
        registry = write_registry(self.root / "registry.json")
        fields, rows = read_rows(attributes)
        rows[0]["primary_body_area_codes"] = "LATISSIMUS_DORSI"
        write_rows(attributes, fields, rows)

        with self.assertRaisesRegex(seed.PipelineError, "not in DOMAIN_RULES"):
            seed.build_seed(
                TRACK,
                self.batch,
                self.mapping,
                self.evidence,
                attributes,
                registry,
                self.root / "generated",
                "v0.1.0",
            )

    def test_unapproved_taxonomy_code_is_rejected(self) -> None:
        self.approve_all()
        attributes = self.make_attributes()
        registry = write_registry(self.root / "registry.json")
        fields, rows = read_rows(attributes)
        rows[0]["primary_movement_pattern_code"] = "INVENTED_PATTERN"
        write_rows(attributes, fields, rows)

        with self.assertRaisesRegex(seed.PipelineError, "not in the approved code list"):
            seed.build_seed(
                TRACK,
                self.batch,
                self.mapping,
                self.evidence,
                attributes,
                registry,
                self.root / "generated",
                "v0.1.0",
            )

    def test_fully_approved_input_builds_and_verifies_seed(self) -> None:
        self.approve_all()
        attributes = self.make_attributes()
        registry = write_registry(self.root / "registry.json")

        seed_dir = seed.build_seed(
            TRACK,
            self.batch,
            self.mapping,
            self.evidence,
            attributes,
            registry,
            self.root / "generated",
            "v0.1.0",
        )

        result = seed.verify_seed(seed_dir)
        self.assertEqual(result["records"], 3)
        records = [
            json.loads(line)
            for line in (seed_dir / "exercises.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertTrue(all(r["review_status_code"] == "DOMAIN_APPROVED" for r in records))
        self.assertTrue(all(10 <= r["default_transition_seconds"] <= 20 for r in records))
        manifest = json.loads((seed_dir / "seed_manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["review"]["production_eligible"])

    def test_readiness_reports_ready_when_everything_is_approved(self) -> None:
        self.approve_all()
        attributes = self.make_attributes()
        registry = write_registry(self.root / "registry.json")

        report = seed.assess_readiness(
            TRACK, self.batch, self.mapping, self.evidence, attributes, registry
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["seed_ready_rows"], 3)
        self.assertEqual(report["blockers"], [])
        self.assertFalse(report["production_eligible"])


if __name__ == "__main__":
    unittest.main()
