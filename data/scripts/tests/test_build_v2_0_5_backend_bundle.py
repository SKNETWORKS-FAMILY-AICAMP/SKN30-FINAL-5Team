from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_5_backend_bundle.py"
spec = importlib.util.spec_from_file_location("build_v2_0_5_backend_bundle", SCRIPT)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = builder
spec.loader.exec_module(builder)


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_build_publishes_all_and_only_exact_current_gymvisual_media() -> None:
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "bundle"
        summary = builder.build(target=target)
        assert summary["catalog_records"] == 162
        assert summary["media_asset_records"] == 76
        assert summary["withheld_media_records"] == 86

        catalog = _jsonl(target / "catalog/exercises.jsonl")
        media = _jsonl(target / "media/media_assets.jsonl")
        registry_lines = (target / "catalog/input/representative_exercises.csv").read_text(
            encoding="utf-8"
        )
        assert len(media) == sum(row["source_track"] == "gymvisual" for row in catalog)
        assert all(row["media_status"] == "AVAILABLE" for row in media)
        assert all(row["rights_review_status"] == "APPROVED" for row in media)
        assert all(
            row["source_metadata"]["source_object_key"].startswith("videos/") for row in media
        )
        for representative_id in (
            "REX-000012",
            "REX-000015",
            "REX-000078",
            "REX-000086",
            "REX-000109",
            "REX-000119",
            "REX-000124",
            "REX-000125",
        ):
            assert representative_id in registry_lines
            assert any(row["representative_exercise_id"] == representative_id for row in media)


def test_build_is_deterministic() -> None:
    with tempfile.TemporaryDirectory() as directory:
        first = Path(directory) / "first"
        second = Path(directory) / "second"
        first_summary = builder.build(target=first)
        second_summary = builder.build(target=second)
        assert first_summary == second_summary
        assert (first / "bundle_manifest.json").read_bytes() == (
            second / "bundle_manifest.json"
        ).read_bytes()
