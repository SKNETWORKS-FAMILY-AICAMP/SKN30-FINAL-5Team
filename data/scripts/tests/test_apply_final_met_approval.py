import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "apply_final_met_approval.py"
spec = importlib.util.spec_from_file_location("apply_final_met_approval", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
apply = module.apply
read_csv = module.read_csv


ROOT = Path(__file__).resolve().parents[2]


def test_apply_final_met_approval_updates_only_explicit_row() -> None:
    mapping_path = ROOT / "generated/exercise-met-mapping-v0.1.0/exercise_met_mapping_reviewed.csv"
    approval_path = ROOT / "validation/review_results/met_final_approval.csv"
    updated, changes = apply(read_csv(mapping_path), read_csv(approval_path))
    row = next(item for item in updated if item["exercise_id"] == "NEX-000173")
    assert row["met_value"] == "2.3"
    assert row["review_status"] == "DOMAIN_APPROVED"
    assert row["mapping_basis"] == "USER_APPROVED_PROXY_02150_STATIC_BALANCE"
    assert row["production_eligible"] == "true"
    assert len(changes) == 1
    assert changes[0]["final_status"] == "DOMAIN_APPROVED"
