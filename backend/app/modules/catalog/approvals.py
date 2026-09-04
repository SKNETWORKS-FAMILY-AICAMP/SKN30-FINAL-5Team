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
    # v2.0.1 differs from v2.0.0-final in exactly one column: beginner_suitable
    # on the 25 MOBILITY representatives that v2.0.0 still carried as
    # REVIEW_REQUIRED. Nothing else in the catalog, safety, alternative or
    # prescription content changed; the derived manifests only re-hash because
    # they name the new catalog version. The per-item split is recorded in
    # beginner_suitability_review below so the source of that call stays
    # auditable, since REVIEW_REQUIRED means a reviewer had not yet ruled.
    (
        "CATALOG",
        "exercise-catalog-v2.0.1-final",
    ): DerivedDataApproval(
        artifact_kind="CATALOG",
        version_code="exercise-catalog-v2.0.1-final",
        manifest_sha256="731182224ab367ffee526a90deeca9d967a894e16c2f9543aa0109b19e7f8994",
        record_count=102,
        approval_record_code="V2-PROMOTION-APPROVAL-2026-08-25-R01",
        approved_on="2026-08-25",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
        approval_metadata={
            "reviewer_reference": "V2-PRESCRIPTION-DOMAIN-REVIEW-2026-08-25-R01",
            "reviewed_at": "2026-08-25T15:00:00+09:00",
            "beginner_suitability_review": {
                "applies_to": "25 MOBILITY_STRETCH representatives previously REVIEW_REQUIRED",
                "classified_by": "ASSISTANT_CLASSIFICATION",
                "classified_at": "2026-08-26",
                "directed_by": "PROJECT_OWNER",
                "rule": (
                    "SUITABLE when unloaded, self-limiting range, stable position, "
                    "no cervical or end-range spinal loading, no equipment; "
                    "CONDITIONAL otherwise"
                ),
                "suitable_count": 17,
                "conditional_count": 8,
                "conditional_reasons": {
                    "REX-000017": "deep hip adduction range",
                    "REX-000039": "kneeling knee load with overhead shoulder end range",
                    "REX-000045": "cervical spine",
                    "REX-000084": "loaded seated spinal flexion",
                    "REX-000085": "sciatic nerve proximity",
                    "REX-000091": "spinal end range",
                    "REX-000092": "rotational end range",
                    "REX-000094": "strap required, over-leverage risk",
                },
                "outstanding": (
                    "not a substitute for an external domain reviewer sign-off on "
                    "beginner suitability"
                ),
            },
        },
        waiver={
            "reference": "V2-PROMOTION-WAIVER-2026-08-25-R01",
            "text": "외부 전문가 의견 XLSX 원본은 작업 폴더에 보관되지 않았음을 인지하고 승인함.",
        },
    ),
    (
        "SAFETY_RULES",
        "safety-rule-set-v2.0.1",
    ): DerivedDataApproval(
        artifact_kind="SAFETY_RULES",
        version_code="safety-rule-set-v2.0.1",
        manifest_sha256="74f4eaedf80f6946533779fa4d7358757310697379659a7edef717d590d1b378",
        record_count=394,
        approval_record_code="V2-PROMOTION-APPROVAL-2026-08-25-R01",
        approved_on="2026-08-25",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
    (
        "ALTERNATIVES",
        "alternative-set-v2.0.1",
    ): DerivedDataApproval(
        artifact_kind="ALTERNATIVES",
        version_code="alternative-set-v2.0.1",
        manifest_sha256="858785cb2c80dccbe48edec9b472421b726d5a6d69d99d0d056f25453bac3821",
        record_count=585,
        approval_record_code="V2-PROMOTION-APPROVAL-2026-08-25-R01",
        approved_on="2026-08-25",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
        approval_metadata={
            "materialization_rescope": {
                "reason": (
                    "the materializer keyed relations without the pain area, so "
                    "relations approved for different areas at the same NRS band "
                    "collapsed into one row"
                ),
                "previous_manifest_sha256": (
                    "ef954cff31fc6fd226af1dec98d24261bb0c42537097ff1a9306a8f3839e2e99"
                ),
                "previous_record_count": 285,
                "recovered_record_count": 300,
                "source_status": (
                    "every recovered relation was already DOMAIN_APPROVED in "
                    "exercise_alternatives_v2_final.csv; no relation content changed"
                ),
                "rescoped_on": "2026-08-30",
                "directed_by": "PROJECT_OWNER",
                "outstanding": (
                    "the original DEVELOPMENT_LEAD/PM/DOMAIN_REVIEWER signature covered "
                    "285 materialized rows; the 585 row set has not been re-signed"
                ),
            }
        },
    ),
    (
        "PRESCRIPTIONS",
        "prescription-set-v2.0.1",
    ): DerivedDataApproval(
        artifact_kind="PRESCRIPTIONS",
        version_code="prescription-set-v2.0.1",
        manifest_sha256="74b911d2fc10c904698564360a8ec4b54a723244bf28a1b4f2d44a1075471ef7",
        record_count=239,
        approval_record_code="V2-PROMOTION-APPROVAL-2026-08-25-R01",
        approved_on="2026-08-25",
        approver_role_codes=("DEVELOPMENT_LEAD", "PM", "DOMAIN_REVIEWER"),
    ),
    # v2.0.2 carries 155 of its 170 records. The 15 VARIANT rows are withheld
    # because nobody has written their form cues yet, and every row that
    # referenced them is withheld with them, so the import stays whole.
    #
    # The safety rules are not a per-exercise clinical list. They are derived
    # from each exercise's reviewed primary/secondary body areas by the same
    # policy build_v2_runtime_artifacts already applies, and the 289 rules the
    # payload shipped match that policy exactly. What is approved here is the
    # policy applied consistently, not 320 individual judgements.
    (
        "CATALOG",
        "exercise-catalog-v2.0.2-final",
    ): DerivedDataApproval(
        artifact_kind="CATALOG",
        version_code="exercise-catalog-v2.0.2-final",
        manifest_sha256="d5bfba35b12f79d58aae4a8e1061d9400604d2b03d7d67f6bc4e4b57f240b634",
        record_count=155,
        approval_record_code="V2-0-2-PROMOTION-APPROVAL-2026-08-31-R01",
        approved_on="2026-08-31",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD"),
        approval_metadata={
            "approval_reference": "USER_DIRECT_REVIEW_2026_08_30",
            "withheld_records": 15,
            "withheld_reason": "VARIANT records have no authored form cues",
            "derived_content": {
                "dosage": "v2.0.1-dosage-table-v1",
                "rep_tempo": "v2-0-2-rest-class-policy-v1",
                "safe_variant_form_cues": "safe-variant-cue-template-v1",
            },
            "outstanding": (
                "safe-variant form cues are template-rendered and carry "
                "REVIEW_REQUIRED; an external domain reviewer has not signed them"
            ),
        },
    ),
    (
        "SAFETY_RULES",
        "safety-rule-set-v2.0.2",
    ): DerivedDataApproval(
        artifact_kind="SAFETY_RULES",
        version_code="safety-rule-set-v2.0.2",
        manifest_sha256="1d83325adf4667f8c11bf7e3217a14ecea3bc1e52b08aa6c583c83ef26761c08",
        record_count=563,
        approval_record_code="V2-0-2-PROMOTION-APPROVAL-2026-08-31-R01",
        approved_on="2026-08-31",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD"),
        approval_metadata={
            "approval_reference": "USER_DIRECT_REVIEW_2026_08_30",
            "derived_by": "v2-body-area-safety-policy-v1",
            "policy": (
                "PRIMARY area -> EXCLUDE MILD..SEVERE (DIRECT_JOINT_LOAD); "
                "SECONDARY area -> CAUTION MILD..MILD + EXCLUDE MODERATE..SEVERE "
                "(STABILIZER_LOAD)"
            ),
            "basis": "the exercise's reviewed primary/secondary body area codes",
        },
    ),
    (
        "ALTERNATIVES",
        "alternative-set-v2.0.2",
    ): DerivedDataApproval(
        artifact_kind="ALTERNATIVES",
        version_code="alternative-set-v2.0.2",
        manifest_sha256="fdd439e3aee9c1170092f6f83a2165f5a0eec13369959638fa4e3e69acde7a34",
        record_count=1150,
        approval_record_code="V2-0-2-PROMOTION-APPROVAL-2026-08-31-R01",
        approved_on="2026-08-31",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD", "DOMAIN_REVIEWER"),
        approval_metadata={
            "approval_reference": "USER_DIRECT_REVIEW_2026_08_29",
            "note": "the reviewed pain-area map, projected onto the relation contract",
        },
    ),
    (
        "PRESCRIPTIONS",
        "prescription-set-v2.0.2",
    ): DerivedDataApproval(
        artifact_kind="PRESCRIPTIONS",
        version_code="prescription-set-v2.0.2",
        manifest_sha256="6bba8438a8728b75715e171872ac4d0d80750659af558230f070a64806c8d6e7",
        record_count=496,
        approval_record_code="V2-0-2-PROMOTION-APPROVAL-2026-08-31-R01",
        approved_on="2026-08-31",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD"),
        approval_metadata={
            "approval_reference": "USER_DIRECT_REVIEW_2026_08_30",
            "intensity_projection": "LIGHT and LIGHT_MODERATE -> LOW, MODERATE -> MODERATE",
            "intensity_basis": (
                "v2_representative_decisions.json groups LIGHT and LIGHT_MODERATE "
                "under discomfort_materialization.low_intensity"
            ),
            "outstanding": (
                "LIGHT_MODERATE covers 4 rows on 2 core exercises; their rest "
                "interval sits between the LIGHT and MODERATE values, so the "
                "grouping is worth a second look"
            ),
        },
    ),
    # v2.0.4 is v2.0.3 plus seven compound movements. They passed domain review
    # for v2.0.2 and were then dropped before packaging: the prune step keeps a
    # base record only when the upstream payload marked it general_pool_included,
    # and these were never marked. Nothing rejected them, and the prune report
    # records deleted_record_count: 0. This closes the outstanding item the
    # v2.0.3 prescription approval left open.
    #
    # Exercise records and their form cues come from the v2.0.2 canonical
    # payload, safety rules from v2.0.1 where they were approved, and the
    # prescriptions from a 24-row review sheet. Alternatives and media are
    # carried over byte for byte, so their approvals restate the v2.0.3
    # evidence rather than claiming a fresh review.
    (
        "CATALOG",
        "exercise-catalog-v2.0.4-final",
    ): DerivedDataApproval(
        artifact_kind="CATALOG",
        version_code="exercise-catalog-v2.0.4-final",
        manifest_sha256="383acd10c7baa03b2cf3373e34ce24c5310cb8aed113c883b123655bec69af31",
        record_count=162,
        approval_record_code="V2-0-4-PROMOTION-APPROVAL-2026-09-01-R01",
        approved_on="2026-09-01",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD"),
        approval_metadata={
            "approval_reference": "COMPOUND-PROMOTION-DOMAIN-REVIEW-2026-09-01-R01",
            "derived_from": "exercise-catalog-v2.0.3-final",
            "carried_over_unchanged": False,
            "promoted_exercise_count": 7,
            "promotion_policy": "compound-promotion-policy-2026-09-01",
            "content_source": (
                "data/generated/exercise-catalog-v2.0.2-final/audit/"
                "canonical_exercises_v2_final.jsonl"
            ),
            "exclusion_cause": (
                "prune_v2_0_2_user_catalog.keep_base kept only records the payload "
                "marked general_pool_included; these seven were never marked"
            ),
            "note": (
                "no exercise content was authored here: every field, including the "
                "Korean form cues, is the value that passed v2.0.2 domain review"
            ),
        },
    ),
    (
        "SAFETY_RULES",
        "safety-rule-set-v2.0.4",
    ): DerivedDataApproval(
        artifact_kind="SAFETY_RULES",
        version_code="safety-rule-set-v2.0.4",
        manifest_sha256="3fc4a31cdf10238afad4da706480d996c5bb6a4f0b2bac00045f289fef2c120e",
        record_count=595,
        approval_record_code="V2-0-4-PROMOTION-APPROVAL-2026-09-01-R01",
        approved_on="2026-09-01",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD", "DOMAIN_REVIEWER"),
        approval_metadata={
            "approval_reference": "COMPOUND-PROMOTION-DOMAIN-REVIEW-2026-09-01-R01",
            "derived_from": "safety-rule-set-v2.0.3",
            "added_rule_count": 32,
            "added_rules_carried_from": "safety-rule-set-v2.0.1",
            "note": (
                "the 32 added rules are the DOMAIN_APPROVED v2.0.1 rules for the "
                "promoted exercises, all EXERCISE scope; every promoted record "
                "carries a substantive rule, so none can reach a user unfiltered"
            ),
        },
    ),
    (
        "ALTERNATIVES",
        "alternative-set-v2.0.4",
    ): DerivedDataApproval(
        artifact_kind="ALTERNATIVES",
        version_code="alternative-set-v2.0.4",
        manifest_sha256="32524fb4757459eb8a66e0767eb9aa29d03ecce42ecb355fcf04b7ccef0ed876",
        record_count=1150,
        approval_record_code="V2-0-4-PROMOTION-APPROVAL-2026-09-01-R01",
        approved_on="2026-09-01",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD", "DOMAIN_REVIEWER"),
        approval_metadata={
            "approval_reference": "COMPOUND-PROMOTION-DOMAIN-REVIEW-2026-09-01-R01",
            "derived_from": "alternative-set-v2.0.3",
            "carried_over_unchanged": True,
            "outstanding": (
                "the promoted exercises have no pain alternative. v2.0.1 held 49 "
                "relations for them, but the v2.0.2 pain review re-decided that "
                "set and those relations did not go through it, so restoring them "
                "is a separate safety judgement. Until then a user reporting the "
                "relevant discomfort simply does not receive the exercise, which "
                "is the conservative outcome"
            ),
        },
    ),
    (
        "PRESCRIPTIONS",
        "prescription-set-v2.0.4",
    ): DerivedDataApproval(
        artifact_kind="PRESCRIPTIONS",
        version_code="prescription-set-v2.0.4",
        manifest_sha256="262077cc43ac2185cf13ea19524ec7046cbad57c0d8c20419cde8c392f700bb6",
        record_count=1533,
        approval_record_code="V2-0-4-PROMOTION-APPROVAL-2026-09-01-R01",
        approved_on="2026-09-01",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD", "DOMAIN_REVIEWER"),
        approval_metadata={
            "approval_reference": "COMPOUND-PROMOTION-DOMAIN-REVIEW-2026-09-01-R01",
            "promotion_policy": "compound-promotion-policy-2026-09-01",
            "added_goal_tag_count": 21,
            "added_prescription_count": 24,
            "approval_method_code": "OWNER_BATCH_CONFIRMATION",
            "dosage_basis": (
                "GENERAL_FITNESS reuses the COMPOUND_STRENGTH FITT template "
                "(3 sets, 8-12 reps, 90s rest) that the 17 compound exercises "
                "already in v2.0.3 use; FAT_LOSS and MUSCLE_GAIN read the "
                "approved goal-prescription policy table unchanged"
            ),
            "difficulty_gate": (
                "six of the seven are INTERMEDIATE and carry INTERMEDIATE rows "
                "only, so a BEGINNER user cannot receive them"
            ),
            "outstanding": (
                "24 rows were confirmed in one batch by the project owner, not "
                "reviewed row by row by an external expert"
            ),
        },
    ),
    (
        "MEDIA_ASSETS",
        "media-set-v2.0.4",
    ): DerivedDataApproval(
        artifact_kind="MEDIA_ASSETS",
        version_code="media-set-v2.0.4",
        manifest_sha256="517fbe7c3102f5916966fc8d0375a40a5fc45a775f0bdc6b509e76395801e6b1",
        record_count=68,
        approval_record_code="V2-0-4-PROMOTION-APPROVAL-2026-09-01-R01",
        approved_on="2026-09-01",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD"),
        approval_metadata={
            "approval_reference": "COMPOUND-PROMOTION-DOMAIN-REVIEW-2026-09-01-R01",
            "derived_from": "media-set-v2.0.3",
            "carried_over_unchanged": True,
            "note": (
                "the v2.0.2 media ledger holds no asset for the promoted "
                "exercises, so they ship without a demonstration clip"
            ),
        },
    ),
    # v2.0.3 is v2.0.2 plus the reviewed FAT_LOSS and MUSCLE_GAIN prescriptions.
    # Onboarding already offered those goals, so before this release picking
    # either one left the approved pool empty and routine creation failed. The
    # catalog, safety rules, alternatives and media are carried over byte for
    # byte, so their approvals restate the v2.0.2 evidence rather than claiming
    # a fresh review. Only the prescription set carries new judgements.
    (
        "CATALOG",
        "exercise-catalog-v2.0.3-final",
    ): DerivedDataApproval(
        artifact_kind="CATALOG",
        version_code="exercise-catalog-v2.0.3-final",
        manifest_sha256="81ac34786bcb7f7d1c4c1a6d6f3380b84f7ee05a7658b9806b817cad6bd9478e",
        record_count=155,
        approval_record_code="V2-0-3-PROMOTION-APPROVAL-2026-08-31-R01",
        approved_on="2026-08-31",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD"),
        approval_metadata={
            "approval_reference": "GOAL-EXPANSION-DOMAIN-REVIEW-2026-08-31-R01",
            "derived_from": "exercise-catalog-v2.0.2-final",
            "carried_over_unchanged": True,
            "note": "exercise records are identical to v2.0.2; only prescriptions were added",
        },
    ),
    (
        "SAFETY_RULES",
        "safety-rule-set-v2.0.3",
    ): DerivedDataApproval(
        artifact_kind="SAFETY_RULES",
        version_code="safety-rule-set-v2.0.3",
        manifest_sha256="e16b228a8b4dae9d623b70430f0f14784c030f5ca566da52e084b7cdc92821a9",
        record_count=563,
        approval_record_code="V2-0-3-PROMOTION-APPROVAL-2026-08-31-R01",
        approved_on="2026-08-31",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD"),
        approval_metadata={
            "approval_reference": "GOAL-EXPANSION-DOMAIN-REVIEW-2026-08-31-R01",
            "derived_from": "safety-rule-set-v2.0.2",
            "carried_over_unchanged": True,
            "derived_by": "v2-body-area-safety-policy-v1",
        },
    ),
    (
        "ALTERNATIVES",
        "alternative-set-v2.0.3",
    ): DerivedDataApproval(
        artifact_kind="ALTERNATIVES",
        version_code="alternative-set-v2.0.3",
        manifest_sha256="c661e50dc2578c335dff33f1091720a6410a25b085d57e38a09ac5bfa85b37d3",
        record_count=1150,
        approval_record_code="V2-0-3-PROMOTION-APPROVAL-2026-08-31-R01",
        approved_on="2026-08-31",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD", "DOMAIN_REVIEWER"),
        approval_metadata={
            "approval_reference": "GOAL-EXPANSION-DOMAIN-REVIEW-2026-08-31-R01",
            "derived_from": "alternative-set-v2.0.2",
            "carried_over_unchanged": True,
        },
    ),
    (
        "PRESCRIPTIONS",
        "prescription-set-v2.0.3",
    ): DerivedDataApproval(
        artifact_kind="PRESCRIPTIONS",
        version_code="prescription-set-v2.0.3",
        manifest_sha256="edd2c0ee1efceb98087412d47295ca6c873737d9abe29bab4de5c27ff8ac4b35",
        record_count=1488,
        approval_record_code="V2-0-3-PROMOTION-APPROVAL-2026-08-31-R01",
        approved_on="2026-08-31",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD", "DOMAIN_REVIEWER"),
        approval_metadata={
            "approval_reference": "GOAL-EXPANSION-DOMAIN-REVIEW-2026-08-31-R01",
            "goal_expansion_policy": "goal-prescription-review-policy-2026-08-31",
            "added_goal_codes": ("FAT_LOSS", "MUSCLE_GAIN"),
            "approval_method_code": "OWNER_BATCH_CONFIRMATION",
            "dosage_basis": (
                "ACSM/NSCA ranges: hypertrophy 6-12 reps with 60-90s rest; "
                "fat loss relatively higher reps with shorter rest"
            ),
            "phase_assignment": (
                "inherited from the approved GENERAL_FITNESS set rather than "
                "re-derived, so the curated warmup/cooldown split is preserved"
            ),
            "outstanding": (
                "682 rows were confirmed in one batch by the project owner, not "
                "reviewed row by row by an external expert; MUSCLE_GAIN offers "
                "only 7 BEGINNER MAIN CORE exercises, so variety is thin until "
                "the catalog gains more compound movements"
            ),
        },
    ),
    (
        "MEDIA_ASSETS",
        "media-set-v2.0.3",
    ): DerivedDataApproval(
        artifact_kind="MEDIA_ASSETS",
        version_code="media-set-v2.0.3",
        manifest_sha256="21ee8b576642d3a14cfdb9be7535a194455a7d292091a02f662004c9edc2c53e",
        record_count=68,
        approval_record_code="V2-0-3-PROMOTION-APPROVAL-2026-08-31-R01",
        approved_on="2026-08-31",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD"),
        approval_metadata={
            "approval_reference": "GOAL-EXPANSION-DOMAIN-REVIEW-2026-08-31-R01",
            "derived_from": "media-set-v2.0.2",
            "carried_over_unchanged": True,
        },
    ),
    (
        "MEDIA_ASSETS",
        "media-set-v2.0.2",
    ): DerivedDataApproval(
        artifact_kind="MEDIA_ASSETS",
        version_code="media-set-v2.0.2",
        manifest_sha256="0ede3cef89a5dd722e9acae42cb2d6244e0f055f98ff75e5edc4fbe6d81e04d7",
        record_count=68,
        approval_record_code="V2-0-2-PROMOTION-APPROVAL-2026-08-31-R01",
        approved_on="2026-08-31",
        approver_role_codes=("DEVELOPMENT_LEAD", "DATA_LEAD"),
        approval_metadata={
            "approval_reference": "USER_DIRECT_REVIEW_2026_08_29",
            "note": "rights-approved assets only; 102 records without an asset are not loaded",
        },
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
    (
        "CATALOG",
        "exercise-catalog-v2.0.6-final",
    ): DerivedDataApproval(
        artifact_kind="CATALOG",
        version_code="exercise-catalog-v2.0.6-final",
        manifest_sha256="a811aba17747b3f1a74207397aad4c672fbbf0ce4ce9b4da508ce65ceea9cefc",
        record_count=237,
        approval_record_code="V2-0-6-PRODUCTION-APPROVAL-2026-09-04-R01",
        approved_on="2026-09-04",
        approver_role_codes=("PM", "DOMAIN_REVIEWER"),
        approval_metadata={
            "review_method_code": "DOMAIN_REVIEWER",
            "status_interpretation_code": "PRODUCTION_APPROVED",
            "evidence_manifest_path": "data/reports/v2_0_6_catalog/catalog_approval_manifest.json",
            "review_basis": (
                "PM directly reviewed exercise names, descriptions, beginner suitability, "
                "and general-pool inclusion."
            ),
        },
    ),
    (
        "SAFETY_RULES",
        "safety-rule-set-v2.0.6",
    ): DerivedDataApproval(
        artifact_kind="SAFETY_RULES",
        version_code="safety-rule-set-v2.0.6",
        manifest_sha256="ff70f4bd9ee2ed8781fb72ddee43b1697e06eefb6cdbd039c7e6b68a0dce16e4",
        record_count=2131,
        approval_record_code="V2-0-6-PRODUCTION-APPROVAL-2026-09-04-R01",
        approved_on="2026-09-04",
        approver_role_codes=("PM", "DOMAIN_REVIEWER"),
        approval_metadata={
            "review_method_code": "DOMAIN_REVIEWER",
            "status_interpretation_code": "PRODUCTION_APPROVED",
            "evidence_manifest_path": "data/reports/v2_0_6_catalog/catalog_approval_manifest.json",
            "derived_from": "approved normalized primary and secondary body-area mappings",
        },
    ),
    (
        "ALTERNATIVES",
        "alternative-set-v2.0.6-stretch-strap-fallback",
    ): DerivedDataApproval(
        artifact_kind="ALTERNATIVES",
        version_code="alternative-set-v2.0.6-stretch-strap-fallback",
        manifest_sha256="2a10913eb5c8e5532c7ed27a0af99abbdea8445cec19bf391d496559da5452c7",
        record_count=1,
        approval_record_code="V2-0-6-PRODUCTION-APPROVAL-2026-09-04-R01",
        approved_on="2026-09-04",
        approver_role_codes=("PM", "DOMAIN_REVIEWER"),
        approval_metadata={
            "review_method_code": "DOMAIN_REVIEWER",
            "status_interpretation_code": "PRODUCTION_APPROVED",
            "evidence_manifest_path": (
                "data/reports/v2_0_6_catalog/stretch_strap_fallback_approval_manifest.json"
            ),
            "policy": "STRETCH_STRAP_TO_BODYWEIGHT_ONLY",
        },
    ),
    (
        "PRESCRIPTIONS",
        "prescription-set-v2.0.6",
    ): DerivedDataApproval(
        artifact_kind="PRESCRIPTIONS",
        version_code="prescription-set-v2.0.6",
        manifest_sha256="659d95393db3482276db7d5c19ec859b01404685270b42f04bcecac31b395616",
        record_count=2160,
        approval_record_code="V2-0-6-PRODUCTION-APPROVAL-2026-09-04-R01",
        approved_on="2026-09-04",
        approver_role_codes=("PM", "DOMAIN_REVIEWER"),
        approval_metadata={
            "review_method_code": "DOMAIN_REVIEWER",
            "status_interpretation_code": "PRODUCTION_APPROVED",
            "evidence_manifest_path": "data/reports/v2_0_6_catalog/catalog_approval_manifest.json",
            "goal_tag_records": 711,
            "prescription_records": 1449,
        },
    ),
    (
        "MEDIA_ASSETS",
        "media-set-v2.0.6",
    ): DerivedDataApproval(
        artifact_kind="MEDIA_ASSETS",
        version_code="media-set-v2.0.6",
        manifest_sha256="938b17a54a449dd03dbdb58d18ee4593a479e2d86ab5376d1a2514d5b5f55e2d",
        record_count=237,
        approval_record_code="V2-0-6-PRODUCTION-APPROVAL-2026-09-04-R01",
        approved_on="2026-09-04",
        approver_role_codes=("PM", "DOMAIN_REVIEWER"),
        approval_metadata={
            "review_method_code": "DOMAIN_REVIEWER",
            "status_interpretation_code": "PRODUCTION_APPROVED",
            "evidence_manifest_path": "data/reports/v2_0_6_catalog/catalog_approval_manifest.json",
            "media_records": 237,
            "rights_review_status": "APPROVED",
        },
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


def get_approved_record_count(artifact_kind: ArtifactKind, version_code: str) -> int | None:
    """Return how many rows the approval covers, without needing the manifest hash.

    Activation gates compare loaded rows against the approved count. They read it
    from here so the number lives only in the approval record.
    """
    approval = _APPROVALS.get((artifact_kind, version_code))
    return None if approval is None else approval.record_count


__all__ = [
    "ArtifactKind",
    "DerivedDataApproval",
    "get_approved_record_count",
    "get_catalog_approval",
    "get_derived_data_approval",
]
