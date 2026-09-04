from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1] / "apply_v2_0_6_training_body_focus_review_to_catalog.py"
)
spec = importlib.util.spec_from_file_location("apply_v2_0_6_training_body_focus_review", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_apply_review_changes_only_nonblank_review_values() -> None:
    catalog = [
        {"source_identity": "0001", "body_focus_code": None, "name_en": "first"},
        {"source_identity": "0002", "body_focus_code": "BACK", "name_en": "second"},
    ]
    changed = module.apply_review(
        catalog,
        {"0001": "CHEST", "0002": ""},
    )
    assert changed == 1
    assert catalog == [
        {"source_identity": "0001", "body_focus_code": "CHEST", "name_en": "first"},
        {"source_identity": "0002", "body_focus_code": "BACK", "name_en": "second"},
    ]


def test_write_catalog_preserves_korean_and_json_shape(tmp_path: Path) -> None:
    output = tmp_path / "catalog.json"
    catalog = [{"source_identity": "0001", "name_ko": "한글 운동", "body_focus_code": "CORE"}]
    module.write_catalog(output, catalog)
    assert json.loads(output.read_text(encoding="utf-8")) == catalog
