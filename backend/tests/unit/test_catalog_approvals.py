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


def test_exact_v2_approvals_preserve_packet_metadata_and_waiver() -> None:
    artifacts = (
        (
            "CATALOG",
            "exercise-catalog-v2.0.1-final",
            "731182224ab367ffee526a90deeca9d967a894e16c2f9543aa0109b19e7f8994",
            102,
        ),
        (
            "SAFETY_RULES",
            "safety-rule-set-v2.0.0",
            "5fbfff04c82aceb044d9f05dfb3c3367b6b66328ce749d6dc9993f203b54dbe3",
            394,
        ),
        (
            "ALTERNATIVES",
            "alternative-set-v2.0.0",
            "23443a260056e2b5bb294089fc257e629ef4ab10a4d3265e1fa3ebc608af7b24",
            285,
        ),
        (
            "PRESCRIPTIONS",
            "prescription-set-v2.0.0",
            "156c9702aa8156826cc5709cc9f80b660158f1a4225830efb0599894031f7641",
            239,
        ),
    )

    approvals = [get_derived_data_approval(*artifact) for artifact in artifacts]

    assert all(approval is not None for approval in approvals)
    catalog = approvals[0]
    assert catalog is not None
    assert catalog.metadata()["waiver"] == {
        "reference": "V2-PROMOTION-WAIVER-2026-08-25-R01",
        "text": "외부 전문가 의견 XLSX 원본은 작업 폴더에 보관되지 않았음을 인지하고 승인함.",
    }


def test_media_approval_kind_is_fail_closed_without_exact_registry_entry() -> None:
    assert get_derived_data_approval("MEDIA_ASSETS", "media-set-v2", "0" * 64, 1) is None
