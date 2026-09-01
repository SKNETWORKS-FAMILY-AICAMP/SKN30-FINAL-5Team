import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "promote_all_met_approvals.py"
spec = importlib.util.spec_from_file_location("promote_all_met_approvals", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
promote = module.promote
read_csv = module.read_csv


ROOT = Path(__file__).resolve().parents[2]


def test_promote_all_met_approvals_requires_complete_evidenced_mapping() -> None:
    mapping = read_csv(
        ROOT / "generated/exercise-met-mapping-v0.1.0/exercise_met_mapping_reviewed.csv"
    )
    approvals = read_csv(ROOT / "validation/review_results/met_domain_approval_manifest.csv")
    updated, changes = promote(mapping, approvals)
    assert len(updated) == 208
    assert len(changes) == 208
    assert {row["review_status"] for row in updated} == {"DOMAIN_APPROVED"}
    assert {row["production_eligible"] for row in updated} == {"true"}
