from dataclasses import dataclass
from typing import Any, Literal

ArtifactKind = Literal["CATALOG", "SAFETY_RULES", "ALTERNATIVES", "PRESCRIPTIONS", "MEDIA_ASSETS"]


@dataclass(frozen=True)
class DerivedDataApproval:
    artifact_kind: ArtifactKind
    version_code: str
    manifest_sha256: str
    record_count: int
    approval_record_code: str
    approved_on: str
    approver_role_codes: tuple[str, ...]
    approval_metadata: dict[str, Any] | None = None
    waiver: dict[str, str] | None = None

    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "approval_record_code": self.approval_record_code,
            "approved_on": self.approved_on,
            "approver_role_codes": list(self.approver_role_codes),
            "scope": "ALL_RECORDS",
            "manifest_sha256": self.manifest_sha256,
            "record_count": self.record_count,
        }
        if self.approval_metadata is not None:
            metadata["approval_metadata"] = self.approval_metadata
        if self.waiver is not None:
            metadata["waiver"] = self.waiver
        return metadata


_APPROVALS = {
    (
        "CATALOG",
        "exercise-catalog-v2.0.0-final",
    ): DerivedDataApproval(
        artifact_kind="CATALOG",
        version_code="exercise-catalog-v2.0.0-final",
        manifest_sha256="e3ad5c3eabf193d173aa3b01c4c503962a43074ad3ecbd44343efb1195677b24",
        record_count=102,
        approval_record_code="V2-PROMOTION-APPROVAL-2026-08-25-R01",
        approved_on="2026-08-25",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
        approval_metadata={
            "reviewer_reference": "V2-PRESCRIPTION-DOMAIN-REVIEW-2026-08-25-R01",
            "reviewed_at": "2026-08-25T15:00:00+09:00",
        },
        waiver={
            "reference": "V2-PROMOTION-WAIVER-2026-08-25-R01",
            "text": "외부 전문가 의견 XLSX 원본은 작업 폴더에 보관되지 않았음을 인지하고 승인함.",
        },
    ),
    (
        "SAFETY_RULES",
        "safety-rule-set-v2.0.0",
    ): DerivedDataApproval(
        artifact_kind="SAFETY_RULES",
        version_code="safety-rule-set-v2.0.0",
        manifest_sha256="53e8f597f4e312999cd9c04402c17ec7faa741692aae90ab8a67889f144c0807",
        record_count=394,
        approval_record_code="V2-PROMOTION-APPROVAL-2026-08-25-R01",
        approved_on="2026-08-25",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
    (
        "ALTERNATIVES",
        "alternative-set-v2.0.0",
    ): DerivedDataApproval(
        artifact_kind="ALTERNATIVES",
        version_code="alternative-set-v2.0.0",
        manifest_sha256="4f78c1c735a3b1129d8396233612bb27b69c25672967990116cca91b7dd74b5c",
        record_count=285,
        approval_record_code="V2-PROMOTION-APPROVAL-2026-08-25-R01",
        approved_on="2026-08-25",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
    (
        "PRESCRIPTIONS",
        "prescription-set-v2.0.0",
    ): DerivedDataApproval(
        artifact_kind="PRESCRIPTIONS",
        version_code="prescription-set-v2.0.0",
        manifest_sha256="6c1ccbae1f234d30fa9b3bac9c92c4493a9f143c475450fd7985ed717218fa71",
        record_count=239,
        approval_record_code="V2-PROMOTION-APPROVAL-2026-08-25-R01",
        approved_on="2026-08-25",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
    (
        "CATALOG",
        "merged-mvp-v0.4.0",
    ): DerivedDataApproval(
        artifact_kind="CATALOG",
        version_code="merged-mvp-v0.4.0",
        manifest_sha256="5686be3d379c8e3742e7e891b9fb5265215aaebd4c3b3c0ec76a000b3175a9a1",
        record_count=56,
        approval_record_code="MERGED-MVP-20260820-PM-DOMAIN-APPROVAL",
        approved_on="2026-08-20",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
    (
        "SAFETY_RULES",
        "merged-mvp-v0.5.0",
    ): DerivedDataApproval(
        artifact_kind="SAFETY_RULES",
        version_code="merged-mvp-v0.5.0",
        manifest_sha256="e42133f2550b6bd4d82063668200f6c08fe57be1445fe8e462cba92487961172",
        record_count=282,
        approval_record_code="MERGED-MVP-20260820-PM-DOMAIN-APPROVAL",
        approved_on="2026-08-20",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
    (
        "ALTERNATIVES",
        "merged-mvp-v0.4.0",
    ): DerivedDataApproval(
        artifact_kind="ALTERNATIVES",
        version_code="merged-mvp-v0.4.0",
        manifest_sha256="8acc955f5ce24b145b9e0041ff7c70df89274d4cefa0b9a69c9429e3ecf4bb24",
        record_count=238,
        approval_record_code="MERGED-MVP-20260820-PM-DOMAIN-APPROVAL",
        approved_on="2026-08-20",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
    (
        "PRESCRIPTIONS",
        "merged-mvp-v0.1.0",
    ): DerivedDataApproval(
        artifact_kind="PRESCRIPTIONS",
        version_code="merged-mvp-v0.1.0",
        manifest_sha256="0ff5bf451345a57b6152cacc6d90e4aeb3cc9da5283093b2863ffbcd8af87273",
        record_count=68,
        approval_record_code="MERGED-MVP-20260820-PM-DOMAIN-APPROVAL",
        approved_on="2026-08-20",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
    (
        "SAFETY_RULES",
        "mvp-v0.3.0",
    ): DerivedDataApproval(
        artifact_kind="SAFETY_RULES",
        version_code="mvp-v0.3.0",
        manifest_sha256="d3281fb7bcf85d614ace027b1a50587430a6578733aab765f0d0b805dd85f51b",
        record_count=354,
        approval_record_code="ISSUE-53-PM-DOMAIN-APPROVAL",
        approved_on="2026-08-18",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
    (
        "ALTERNATIVES",
        "mvp-v0.2.0",
    ): DerivedDataApproval(
        artifact_kind="ALTERNATIVES",
        version_code="mvp-v0.2.0",
        manifest_sha256="9875cecc075ff1e3f827243f1ebe4db475dfe9a86985a122febaf2558b81ec7f",
        record_count=238,
        approval_record_code="ISSUE-53-PM-DOMAIN-APPROVAL",
        approved_on="2026-08-18",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
}


def get_derived_data_approval(
    artifact_kind: ArtifactKind,
    version_code: str,
    manifest_sha256: str,
    record_count: int,
) -> DerivedDataApproval | None:
    approval = _APPROVALS.get((artifact_kind, version_code))
    if approval is None:
        return None
    if approval.manifest_sha256 != manifest_sha256 or approval.record_count != record_count:
        return None
    return approval


def get_catalog_approval(
    version_code: str, manifest_sha256: str, record_count: int
) -> DerivedDataApproval | None:
    return get_derived_data_approval("CATALOG", version_code, manifest_sha256, record_count)


__all__ = ["DerivedDataApproval", "get_catalog_approval", "get_derived_data_approval"]
