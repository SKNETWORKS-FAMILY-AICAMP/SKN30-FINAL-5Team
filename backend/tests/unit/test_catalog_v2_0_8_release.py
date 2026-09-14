import json

from backend.app.modules.catalog.approvals import (
    get_catalog_approval,
    get_derived_data_approval,
)
from backend.app.modules.catalog.service import load_integrated_catalog_bundle
from backend.scripts.catalog_promote_v2_0_8 import (
    APPROVED_CATALOG_BUNDLE_MANIFEST_SHA256,
    APPROVED_INTEGRATED_BUNDLE_MANIFEST_SHA256,
    APPROVED_TAXONOMY_REGISTRY_SHA256,
    DEFAULT_BUNDLE_DIRECTORY,
    V2_0_8_CATALOG_VERSION_CODE,
    _sha256,
)

_ARTIFACTS = (
    (
        "CATALOG",
        V2_0_8_CATALOG_VERSION_CODE,
        "09ab8305a0a506e14ed452d8244dd481dbbc347441a99a742e4426bc0d85423b",
        237,
        "catalog/catalog/seed_manifest.json",
        ("exercise_records",),
    ),
    (
        "SAFETY_RULES",
        "safety-rule-set-v2.0.8",
        "7e1a573593d03b1121d44f0d9b150a988d2cd422aefb26a0242574b9b81d9ed3",
        2131,
        "catalog/safety/rules_manifest.json",
        ("rule_records",),
    ),
    (
        "ALTERNATIVES",
        "alternative-set-v2.0.8-stretch-strap-fallback",
        "a37ca2d415b7ab270afaab3a711604469cfd12b56726973a37f04aed70cda449",
        1,
        "catalog/alternatives/alternatives_manifest.json",
        ("alternative_records",),
    ),
    (
        "PRESCRIPTIONS",
        "prescription-set-v2.0.8",
        "07a6f4d0f8aea6ad75c4ee6da09b46da67c5753d935a36fe7ba9eb556be4a84d",
        2175,
        "catalog/prescriptions/prescription_manifest.json",
        ("goal_tag_records", "prescription_records"),
    ),
    (
        "MEDIA_ASSETS",
        "media-set-v2.0.8",
        "4dbcfc63d59de676a9df0f330fb578c315447cccc316efa32bfe04e79c884812",
        237,
        "catalog/media/media_manifest.json",
        ("media_asset_records",),
    ),
)


def test_v2_0_8_bundle_and_registry_are_pinned() -> None:
    loaded = load_integrated_catalog_bundle(
        DEFAULT_BUNDLE_DIRECTORY,
        expected_catalog_version=V2_0_8_CATALOG_VERSION_CODE,
    )
    assert len(loaded.catalog.records) == 237
    assert _sha256(DEFAULT_BUNDLE_DIRECTORY / "bundle_manifest.json") == (
        APPROVED_INTEGRATED_BUNDLE_MANIFEST_SHA256
    )
    assert _sha256(DEFAULT_BUNDLE_DIRECTORY / "catalog/bundle_manifest.json") == (
        APPROVED_CATALOG_BUNDLE_MANIFEST_SHA256
    )
    assert len(APPROVED_TAXONOMY_REGISTRY_SHA256) == 64

    for kind, version, digest, count, path, fields in _ARTIFACTS:
        approval = (
            get_catalog_approval(version, digest, count)
            if kind == "CATALOG"
            else get_derived_data_approval(kind, version, digest, count)
        )
        assert approval is not None
        assert approval.approver_role_codes == ("PM",)
        assert (
            approval.metadata()["approval_metadata"]["status_interpretation_code"]
            == "PRODUCTION_APPROVED"
        )
        manifest = DEFAULT_BUNDLE_DIRECTORY / path
        assert _sha256(manifest) == digest
        summary = json.loads(manifest.read_text(encoding="utf-8"))["summary"]
        assert sum(summary[field] for field in fields) == count
