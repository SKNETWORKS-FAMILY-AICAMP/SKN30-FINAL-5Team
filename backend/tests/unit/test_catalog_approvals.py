from backend.app.modules.catalog.approvals import get_derived_data_approval


def test_exact_reviewed_safety_artifact_is_production_approved() -> None:
    approval = get_derived_data_approval(
        "SAFETY_RULES",
        "mvp-v0.3.0",
        "d3281fb7bcf85d614ace027b1a50587430a6578733aab765f0d0b805dd85f51b",
        354,
    )

    assert approval is not None
    assert approval.metadata()["scope"] == "ALL_RECORDS"


def test_changed_artifact_is_not_covered_by_approval() -> None:
    assert get_derived_data_approval("ALTERNATIVES", "mvp-v0.2.0", "0" * 64, 238) is None
