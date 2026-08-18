from dataclasses import dataclass
from typing import Literal

DerivedArtifactKind = Literal["SAFETY_RULES", "ALTERNATIVES"]


@dataclass(frozen=True)
class DerivedDataApproval:
    artifact_kind: DerivedArtifactKind
    version_code: str
    manifest_sha256: str
    record_count: int
    approval_record_code: str
    approved_on: str
    approver_role_codes: tuple[str, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "approval_record_code": self.approval_record_code,
            "approved_on": self.approved_on,
            "approver_role_codes": list(self.approver_role_codes),
            "scope": "ALL_RECORDS",
            "manifest_sha256": self.manifest_sha256,
            "record_count": self.record_count,
        }


_APPROVALS = {
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
    artifact_kind: DerivedArtifactKind,
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


__all__ = ["DerivedDataApproval", "get_derived_data_approval"]
