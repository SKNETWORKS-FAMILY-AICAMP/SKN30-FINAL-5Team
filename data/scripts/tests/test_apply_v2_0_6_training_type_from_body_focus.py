from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "apply_v2_0_6_training_type_from_body_focus.py"
spec = importlib.util.spec_from_file_location("apply_training_type", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_apply_training_type_fills_only_blank_values() -> None:
    catalog = [
        {"source_identity": "0001", "training_type_code": None},
        {"source_identity": "0002", "training_type_code": "STRENGTH"},
        {"source_identity": "0003", "training_type_code": None},
        {"source_identity": "0004", "training_type_code": None},
    ]
    review = {
        "0001": "CARDIO",
        "0002": "GLUTES",
        "0003": "MOBILITY",
        "0004": "",
    }
    assert module.apply_training_type(catalog, review) == 2
    assert [row["training_type_code"] for row in catalog] == [
        "CARDIO",
        "STRENGTH",
        "MOBILITY",
        None,
    ]


def test_apply_training_type_rejects_conflicting_existing_value() -> None:
    catalog = [{"source_identity": "0001", "training_type_code": "CARDIO"}]
    review = {"0001": "GLUTES"}
    try:
        module.apply_training_type(catalog, review)
    except module.TrainingTypeApplyError as exc:
        assert "0001" in str(exc)
    else:
        raise AssertionError("expected conflicting training type to fail")
