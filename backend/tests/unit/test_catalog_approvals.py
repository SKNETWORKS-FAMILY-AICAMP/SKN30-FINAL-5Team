from backend.app.modules.catalog.approvals import get_catalog_approval, get_derived_data_approval


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


def test_exact_merged_bundle_approvals_are_hash_and_count_bound() -> None:
    catalog = get_catalog_approval(
        "merged-mvp-v0.4.0",
        "5686be3d379c8e3742e7e891b9fb5265215aaebd4c3b3c0ec76a000b3175a9a1",
        56,
    )
    prescriptions = get_derived_data_approval(
        "PRESCRIPTIONS",
        "merged-mvp-v0.1.0",
        "0ff5bf451345a57b6152cacc6d90e4aeb3cc9da5283093b2863ffbcd8af87273",
        68,
    )

    assert catalog is not None
    assert prescriptions is not None
    assert catalog.approval_record_code == prescriptions.approval_record_code
