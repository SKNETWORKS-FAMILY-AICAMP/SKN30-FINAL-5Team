import json

from backend.app.modules.catalog.approvals import (
    get_catalog_approval,
    get_derived_data_approval,
)
from backend.scripts.catalog_promote_v2_0_7 import (
    APPROVED_CATALOG_BUNDLE_MANIFEST_SHA256,
    APPROVED_INTEGRATED_BUNDLE_MANIFEST_SHA256,
    APPROVED_TAXONOMY_REGISTRY_SHA256,
    DEFAULT_BUNDLE_DIRECTORY,
    V2_0_7_CATALOG_VERSION_CODE,
    _sha256,
)

# The release pin, in one place: artifact kind, registered version code, the
# manifest hash and record count `approvals.py` records, where that manifest
# lives inside the pinned bundle, and which summary fields add up to the count.
_REGISTERED_ARTIFACTS = (
    (
        "CATALOG",
        V2_0_7_CATALOG_VERSION_CODE,
        "93847c5c8ffddac57a74b2ca7a80fa2ec036ec3d2687588526a2302b993a31dc",
        237,
        "catalog/catalog/seed_manifest.json",
        ("exercise_records",),
    ),
    (
        "SAFETY_RULES",
        "safety-rule-set-v2.0.7",
        "bd471174683ce02f1beb7714a972ba49a25eb5ab02732910365a181da03dd644",
        2131,
        "catalog/safety/rules_manifest.json",
        ("rule_records",),
    ),
    (
        "ALTERNATIVES",
        "alternative-set-v2.0.7-stretch-strap-fallback",
        "d59a69dd6ccaa162903a300993be01941f58e7fca0d175f944f3ec32868d0176",
        1,
        "catalog/alternatives/alternatives_manifest.json",
        ("alternative_records",),
    ),
    (
        "PRESCRIPTIONS",
        "prescription-set-v2.0.7",
        "2299cfdbdd23a6bf66ce90d9aca39e2c5d4bbc9c33a8b0ead49557cdecdb0904",
        2175,
        "catalog/prescriptions/prescription_manifest.json",
        ("goal_tag_records", "prescription_records"),
    ),
    (
        "MEDIA_ASSETS",
        "media-set-v2.0.7",
        "34c6d4cbdde6daaebba85d6e3ba3f4449e9ef80e6dd0b1e66aceb62bb79442f1",
        237,
        "catalog/media/media_manifest.json",
        ("media_asset_records",),
    ),
)


def test_v2_0_7_approval_registry_exactly_matches_final_bundle() -> None:
    for kind, version, digest, count, _path, _fields in _REGISTERED_ARTIFACTS:
        approval = (
            get_catalog_approval(version, digest, count)
            if kind == "CATALOG"
            else get_derived_data_approval(kind, version, digest, count)
        )
        assert approval is not None
        assert approval.approver_role_codes == (
            "DEVELOPMENT_LEAD",
            "DATA_LEAD",
            "DOMAIN_REVIEWER",
        )
        assert approval.metadata()["approval_metadata"]["review_method_code"] == "DOMAIN_REVIEWER"


def test_v2_0_7_promotion_pins_both_bundle_layers_and_taxonomy() -> None:
    assert _sha256(DEFAULT_BUNDLE_DIRECTORY / "bundle_manifest.json") == (
        APPROVED_INTEGRATED_BUNDLE_MANIFEST_SHA256
    )
    assert _sha256(DEFAULT_BUNDLE_DIRECTORY / "catalog/bundle_manifest.json") == (
        APPROVED_CATALOG_BUNDLE_MANIFEST_SHA256
    )
    assert len(APPROVED_TAXONOMY_REGISTRY_SHA256) == 64


def test_registered_hashes_are_the_bundle_on_disk_not_just_the_registry() -> None:
    """Every approval entry must name bytes the pinned bundle actually has.

    The assertions above only ask the registry about itself, so a rebuild that
    moves a sub-manifest leaves them passing while promotion fails closed on the
    release host. The bundle is rebuilt here, which is where that should surface.
    """

    for kind, _version, digest, _count, path, _fields in _REGISTERED_ARTIFACTS:
        manifest = DEFAULT_BUNDLE_DIRECTORY / path
        assert manifest.is_file(), f"{kind}: {manifest} is missing from the pinned bundle"
        assert _sha256(manifest) == digest, (
            f"{kind}: approvals.py records a hash the pinned bundle no longer has. "
            "Re-pin the registry entry rather than relaxing this check."
        )


def test_registered_counts_are_the_bundle_on_disk() -> None:
    """The record count is the other half of the pin the importer verifies."""

    for kind, _version, _digest, count, path, fields in _REGISTERED_ARTIFACTS:
        summary = json.loads((DEFAULT_BUNDLE_DIRECTORY / path).read_text(encoding="utf-8"))[
            "summary"
        ]
        actual = sum(summary[field] for field in fields)
        assert actual == count, (
            f"{kind}: approvals.py records {count} but the bundle manifest sums to {actual} "
            f"over {', '.join(fields)}"
        )
