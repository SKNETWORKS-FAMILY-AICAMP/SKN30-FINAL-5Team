from backend.app.modules.catalog.approvals import (
    get_catalog_approval,
    get_derived_data_approval,
)
from backend.scripts.catalog_promote_v2_0_6 import (
    APPROVED_BUNDLE_MANIFEST_SHA256,
    APPROVED_TAXONOMY_REGISTRY_SHA256,
    V2_0_6_CATALOG_VERSION_CODE,
)


def test_v2_0_6_approval_registry_is_exact_and_domain_reviewed() -> None:
    artifacts = (
        (
            "CATALOG",
            V2_0_6_CATALOG_VERSION_CODE,
            "a811aba17747b3f1a74207397aad4c672fbbf0ce4ce9b4da508ce65ceea9cefc",
            237,
        ),
        (
            "SAFETY_RULES",
            "safety-rule-set-v2.0.6",
            "ff70f4bd9ee2ed8781fb72ddee43b1697e06eefb6cdbd039c7e6b68a0dce16e4",
            2131,
        ),
        (
            "ALTERNATIVES",
            "alternative-set-v2.0.6-stretch-strap-fallback",
            "2a10913eb5c8e5532c7ed27a0af99abbdea8445cec19bf391d496559da5452c7",
            1,
        ),
        (
            "PRESCRIPTIONS",
            "prescription-set-v2.0.6",
            "659d95393db3482276db7d5c19ec859b01404685270b42f04bcecac31b395616",
            2160,
        ),
        (
            "MEDIA_ASSETS",
            "media-set-v2.0.6",
            "938b17a54a449dd03dbdb58d18ee4593a479e2d86ab5376d1a2514d5b5f55e2d",
            237,
        ),
    )

    for artifact_kind, version_code, manifest_hash, record_count in artifacts:
        approval = (
            get_catalog_approval(version_code, manifest_hash, record_count)
            if artifact_kind == "CATALOG"
            else get_derived_data_approval(artifact_kind, version_code, manifest_hash, record_count)
        )
        assert approval is not None
        assert approval.approver_role_codes == ("PM", "DOMAIN_REVIEWER")
        metadata = approval.metadata()["approval_metadata"]
        assert metadata["review_method_code"] == "DOMAIN_REVIEWER"
        assert metadata["status_interpretation_code"] == "PRODUCTION_APPROVED"


def test_v2_0_6_promotion_pins_root_and_taxonomy_hashes() -> None:
    assert len(APPROVED_BUNDLE_MANIFEST_SHA256) == 64
    assert len(APPROVED_TAXONOMY_REGISTRY_SHA256) == 64
