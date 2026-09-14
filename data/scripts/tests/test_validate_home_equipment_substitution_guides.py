from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "validate_home_equipment_substitution_guides.py"
spec = importlib.util.spec_from_file_location("validate_home_equipment_substitution_guides", SCRIPT)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def test_reviewed_home_equipment_artifacts_are_approved_and_valid() -> None:
    errors: list[str] = []
    catalog = validator.load_catalog(validator.DEFAULT_CATALOG, errors)
    guides = validator.read_jsonl(validator.DEFAULT_GUIDES, errors)
    variants = validator.read_jsonl(validator.DEFAULT_VARIANTS, errors)
    dumbbell = validator.read_jsonl(validator.DEFAULT_DUMBBELL_VARIANTS, errors)
    foam = validator.read_jsonl(validator.DEFAULT_FOAM_VARIANTS, errors)
    stretch = validator.read_jsonl(validator.DEFAULT_STRETCH, errors)
    gaps = validator.read_json(validator.DEFAULT_GAPS, errors)

    validator.validate_guides(catalog, guides, errors)
    validator.validate_variants(catalog, variants, gaps, errors)
    validator.validate_variants(catalog, dumbbell, None, errors, source_equipment_code="DUMBBELL")
    validator.validate_variants(catalog, foam, None, errors, source_equipment_code="FOAM_ROLLER")
    validator.validate_stretch(catalog, stretch, errors)

    assert not errors
    for rows in (guides, variants, dumbbell, foam):
        assert all(row["review_status_code"] == validator.APPROVED_REVIEW_STATUS for row in rows)
