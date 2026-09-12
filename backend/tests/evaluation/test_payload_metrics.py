from backend.tests.evaluation.budget import planning_cases
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.payload_metrics import build_payload_size_report


def test_role_minimized_specialist_payloads_reduce_canonical_bytes() -> None:
    report = build_payload_size_report(planning_cases(GRAPH_CASES))

    assert report["case_count"] == 14
    assert report["v2_specialist_payload_bytes"] < report["v1_specialist_payload_bytes"]
    assert report["reduction_rate"] >= 0.25
