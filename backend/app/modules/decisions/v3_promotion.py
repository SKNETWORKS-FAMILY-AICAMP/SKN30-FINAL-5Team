"""Framework-independent V3 production-promotion evidence gate."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from pydantic_core import to_jsonable_python

PROMOTION_THRESHOLD_SCHEMA_VERSION: Final[Literal["v3-promotion-threshold-v1"]] = (
    "v3-promotion-threshold-v1"
)
PROMOTION_EVIDENCE_SCHEMA_VERSION: Final[Literal["v3-promotion-evidence-v1"]] = (
    "v3-promotion-evidence-v1"
)
PROMOTION_DECISION_SCHEMA_VERSION: Final[Literal["v3-promotion-decision-v1"]] = (
    "v3-promotion-decision-v1"
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MACHINE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_CREATE_CONTEXT_KEY = "v3_promotion_create"


def canonical_json(value: object, *, pretty: bool = False) -> str:
    """Return the sole canonical JSON representation used by promotion artifacts."""

    return json.dumps(
        to_jsonable_python(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=None if pretty else (",", ":"),
        indent=2 if pretty else None,
        allow_nan=False,
    )


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validate_machine_code(value: str, *, field_name: str) -> str:
    if not _MACHINE_CODE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a structured machine code")
    return value


def _validate_sha256(value: str, *, field_name: str) -> str:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


class V3PromotionStatusCode(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    BLOCKED = "BLOCKED"
    READY_FOR_HUMAN_APPROVAL = "READY_FOR_HUMAN_APPROVAL"


class V3PromotionReasonCode(StrEnum):
    THRESHOLD_REFERENCE_MISSING = "THRESHOLD_REFERENCE_MISSING"
    THRESHOLD_APPROVAL_REFERENCE_INCOMPLETE = "THRESHOLD_APPROVAL_REFERENCE_INCOMPLETE"
    ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    ARTIFACT_RECORD_COUNT_MISMATCH = "ARTIFACT_RECORD_COUNT_MISMATCH"
    SUMMARY_HASH_MISMATCH = "SUMMARY_HASH_MISMATCH"
    RESULT_HASH_MISMATCH = "RESULT_HASH_MISMATCH"
    PRIVACY_VALIDATION_FAILED = "PRIVACY_VALIDATION_FAILED"
    ARTIFACT_VERSION_INCONSISTENT = "ARTIFACT_VERSION_INCONSISTENT"
    FIXTURE_VERSION_MISMATCH = "FIXTURE_VERSION_MISMATCH"
    HARNESS_VERSION_MISMATCH = "HARNESS_VERSION_MISMATCH"
    GRAPH_VERSION_MISMATCH = "GRAPH_VERSION_MISMATCH"
    POLICY_VERSION_MISMATCH = "POLICY_VERSION_MISMATCH"
    CATALOG_VERSION_MISMATCH = "CATALOG_VERSION_MISMATCH"
    PROMPT_VERSION_MISMATCH = "PROMPT_VERSION_MISMATCH"
    PROVIDER_VERSION_MISMATCH = "PROVIDER_VERSION_MISMATCH"
    MODEL_VERSION_MISMATCH = "MODEL_VERSION_MISMATCH"
    SHADOW_CASE_COUNT_BELOW_MINIMUM = "SHADOW_CASE_COUNT_BELOW_MINIMUM"
    REPEAT_COUNT_BELOW_MINIMUM = "REPEAT_COUNT_BELOW_MINIMUM"
    SAFETY_INVARIANT_RATE_UNAVAILABLE = "SAFETY_INVARIANT_RATE_UNAVAILABLE"
    SAFETY_INVARIANT_RATE_BELOW_REQUIRED = "SAFETY_INVARIANT_RATE_BELOW_REQUIRED"
    SAFETY_VETO_OVERRIDE_PRESENT = "SAFETY_VETO_OVERRIDE_PRESENT"
    CONSTRAINT_VIOLATION_PRESENT = "CONSTRAINT_VIOLATION_PRESENT"
    STRUCTURED_OUTPUT_RATE_UNAVAILABLE = "STRUCTURED_OUTPUT_RATE_UNAVAILABLE"
    STRUCTURED_OUTPUT_RATE_BELOW_MINIMUM = "STRUCTURED_OUTPUT_RATE_BELOW_MINIMUM"
    P95_LATENCY_UNAVAILABLE = "P95_LATENCY_UNAVAILABLE"
    P95_LATENCY_ABOVE_MAXIMUM = "P95_LATENCY_ABOVE_MAXIMUM"
    TOKEN_USAGE_UNAVAILABLE = "TOKEN_USAGE_UNAVAILABLE"
    AVERAGE_COST_UNAVAILABLE = "AVERAGE_COST_UNAVAILABLE"
    AVERAGE_COST_ABOVE_MAXIMUM = "AVERAGE_COST_ABOVE_MAXIMUM"
    PRICING_REFERENCE_MISSING = "PRICING_REFERENCE_MISSING"
    PRICING_REFERENCE_MISMATCH = "PRICING_REFERENCE_MISMATCH"
    FALLBACK_RATE_UNAVAILABLE = "FALLBACK_RATE_UNAVAILABLE"
    FALLBACK_RATE_ABOVE_MAXIMUM = "FALLBACK_RATE_ABOVE_MAXIMUM"
    EXPERT_REVIEW_PENDING = "EXPERT_REVIEW_PENDING"
    EXPERT_REVIEW_EVIDENCE_INCOMPLETE = "EXPERT_REVIEW_EVIDENCE_INCOMPLETE"
    EXPERT_REVIEW_COMPLETION_BELOW_MINIMUM = "EXPERT_REVIEW_COMPLETION_BELOW_MINIMUM"
    EXPERT_AGREEMENT_UNAVAILABLE = "EXPERT_AGREEMENT_UNAVAILABLE"
    EXPERT_AGREEMENT_BELOW_MINIMUM = "EXPERT_AGREEMENT_BELOW_MINIMUM"


_REASON_ORDER = tuple(V3PromotionReasonCode)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class V3PromotionThresholdReference(_FrozenContract):
    """Approved, versioned thresholds. The evaluator supplies no numeric defaults."""

    schema_version: Literal["v3-promotion-threshold-v1"] = PROMOTION_THRESHOLD_SCHEMA_VERSION
    threshold_policy_version: str
    fixture_version: str
    harness_version: str
    graph_version: str
    policy_version: str
    catalog_version: str
    prompt_version: str
    provider_code: str
    model_version: str
    min_shadow_case_count: int = Field(gt=0)
    min_repeat_count: int = Field(gt=0)
    required_safety_invariant_pass_rate: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    max_safety_veto_override_count: int = Field(ge=0)
    max_constraint_violation_rate: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    min_structured_output_success_rate: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    max_p95_latency_ms: int = Field(ge=0)
    max_average_cost_per_decision: Decimal = Field(ge=0, allow_inf_nan=False)
    max_deterministic_fallback_rate: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    min_expert_review_completion_rate: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    min_expert_agreement_rate: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    currency_code: str
    pricing_reference_version: str
    pricing_source_reference: str
    approval_reference: str | None = None
    approved_manifest_sha256: str
    effective_at: datetime
    threshold_hash: str

    @field_validator(
        "threshold_policy_version",
        "fixture_version",
        "harness_version",
        "graph_version",
        "policy_version",
        "catalog_version",
        "prompt_version",
        "provider_code",
        "model_version",
        "currency_code",
        "pricing_reference_version",
        "pricing_source_reference",
    )
    @classmethod
    def validate_codes(cls, value: str, info: ValidationInfo) -> str:
        return _validate_machine_code(value, field_name=info.field_name or "threshold code")

    @field_validator("approval_reference")
    @classmethod
    def validate_approval_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_machine_code(value, field_name="approval_reference")

    @field_validator("effective_at")
    @classmethod
    def validate_effective_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("effective_at must include timezone information")
        return value

    @field_validator("approved_manifest_sha256", "threshold_hash")
    @classmethod
    def validate_threshold_hash_format(cls, value: str, info: ValidationInfo) -> str:
        return _validate_sha256(value, field_name=info.field_name or "threshold hash")

    @model_validator(mode="after")
    def validate_threshold(self, info: ValidationInfo) -> Self:
        if self.required_safety_invariant_pass_rate != Decimal("1"):
            raise ValueError("promotion safety invariant threshold must be exactly 1")
        if self.max_safety_veto_override_count != 0:
            raise ValueError("promotion threshold cannot permit a safety veto override")
        if self.max_constraint_violation_rate != Decimal("0"):
            raise ValueError("promotion threshold cannot permit constraint violations")
        if not (info.context or {}).get(_CREATE_CONTEXT_KEY):
            expected = canonical_hash(self.model_dump(mode="json", exclude={"threshold_hash"}))
            if self.threshold_hash != expected:
                raise ValueError("threshold_hash does not match the canonical threshold")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": PROMOTION_THRESHOLD_SCHEMA_VERSION, **values}
        payload["threshold_hash"] = "0" * 64
        normalized = cls.model_validate(payload, context={_CREATE_CONTEXT_KEY: True})
        digest = canonical_hash(normalized.model_dump(mode="json", exclude={"threshold_hash"}))
        return cls.model_validate({**normalized.model_dump(), "threshold_hash": digest})


class V3PromotionEvidence(_FrozenContract):
    """Sanitized aggregate evidence reconstructed from a C1 report bundle."""

    schema_version: Literal["v3-promotion-evidence-v1"] = PROMOTION_EVIDENCE_SCHEMA_VERSION
    fixture_version: str
    harness_version: str
    graph_version: str
    policy_version: str
    catalog_version: str
    prompt_version: str
    provider_code: str
    model_version: str
    total_case_count: int = Field(ge=0)
    repeat_count: int = Field(ge=0)
    safety_invariant_pass_rate: Decimal | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    safety_veto_override_count: int = Field(ge=0)
    constraint_violation_rate: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    structured_output_success_rate: Decimal | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    p95_latency_ms: int | None = Field(default=None, ge=0)
    input_token_count_total: int | None = Field(default=None, ge=0)
    output_token_count_total: int | None = Field(default=None, ge=0)
    average_cost_per_decision: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    deterministic_fallback_rate: Decimal | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    expert_review_completion_rate: Decimal | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    expert_agreement_rate: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    expert_reviews_pending: bool
    reviewer_evidence_complete: bool
    currency_code: str | None = None
    pricing_reference_version: str | None = None
    pricing_source_reference: str | None = None
    artifact_hashes_match: bool
    artifact_record_counts_match: bool
    summary_hash_valid: bool
    result_hashes_valid: bool
    privacy_validation_passed: bool
    artifact_versions_consistent: bool
    pricing_reference_supplied: bool
    pricing_reference_matches_evidence: bool
    summary_hash: str
    summary_file_sha256: str
    manifest_sha256: str
    results_sha256: str
    expert_reviews_sha256: str
    evidence_hash: str

    @field_validator(
        "fixture_version",
        "harness_version",
        "graph_version",
        "policy_version",
        "catalog_version",
        "prompt_version",
        "provider_code",
        "model_version",
    )
    @classmethod
    def validate_versions(cls, value: str, info: ValidationInfo) -> str:
        return _validate_machine_code(value, field_name=info.field_name or "evidence version")

    @field_validator("currency_code", "pricing_reference_version", "pricing_source_reference")
    @classmethod
    def validate_optional_codes(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _validate_machine_code(value, field_name=info.field_name or "pricing code")

    @field_validator(
        "summary_hash",
        "summary_file_sha256",
        "manifest_sha256",
        "results_sha256",
        "expert_reviews_sha256",
        "evidence_hash",
    )
    @classmethod
    def validate_hashes(cls, value: str, info: ValidationInfo) -> str:
        return _validate_sha256(value, field_name=info.field_name or "evidence hash")

    @model_validator(mode="after")
    def validate_evidence(self, info: ValidationInfo) -> Self:
        pricing_values = (
            self.currency_code,
            self.pricing_reference_version,
            self.pricing_source_reference,
        )
        if any(value is None for value in pricing_values) and any(
            value is not None for value in pricing_values
        ):
            raise ValueError("currency and pricing reference values are all-or-none")
        token_values = (self.input_token_count_total, self.output_token_count_total)
        if (token_values[0] is None) != (token_values[1] is None):
            raise ValueError("input and output token counts are all-or-none")
        if not (info.context or {}).get(_CREATE_CONTEXT_KEY):
            expected = canonical_hash(self.model_dump(mode="json", exclude={"evidence_hash"}))
            if self.evidence_hash != expected:
                raise ValueError("evidence_hash does not match the canonical evidence")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": PROMOTION_EVIDENCE_SCHEMA_VERSION, **values}
        payload["evidence_hash"] = "0" * 64
        normalized = cls.model_validate(payload, context={_CREATE_CONTEXT_KEY: True})
        digest = canonical_hash(normalized.model_dump(mode="json", exclude={"evidence_hash"}))
        return cls.model_validate({**normalized.model_dump(), "evidence_hash": digest})


class V3PromotionDecision(_FrozenContract):
    schema_version: Literal["v3-promotion-decision-v1"] = PROMOTION_DECISION_SCHEMA_VERSION
    status_code: V3PromotionStatusCode
    reason_codes: tuple[V3PromotionReasonCode, ...]
    threshold_reference_hash: str | None
    evidence_hash: str
    decision_hash: str

    @field_validator("threshold_reference_hash")
    @classmethod
    def validate_optional_threshold_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_sha256(value, field_name="threshold_reference_hash")

    @field_validator("evidence_hash", "decision_hash")
    @classmethod
    def validate_decision_hashes(cls, value: str, info: ValidationInfo) -> str:
        return _validate_sha256(value, field_name=info.field_name or "decision hash")

    @model_validator(mode="after")
    def validate_decision(self, info: ValidationInfo) -> Self:
        canonical_reasons = tuple(sorted(set(self.reason_codes), key=_REASON_ORDER.index))
        if self.reason_codes != canonical_reasons:
            raise ValueError("promotion reason codes must be unique and canonically ordered")
        if self.status_code is V3PromotionStatusCode.READY_FOR_HUMAN_APPROVAL and self.reason_codes:
            raise ValueError("ready decision cannot contain blocking reasons")
        if self.status_code is V3PromotionStatusCode.NOT_EVALUATED and self.reason_codes != (
            V3PromotionReasonCode.THRESHOLD_REFERENCE_MISSING,
        ):
            raise ValueError("not-evaluated decision requires the missing-threshold reason")
        if self.status_code is V3PromotionStatusCode.BLOCKED and not self.reason_codes:
            raise ValueError("blocked decision requires reason codes")
        if not (info.context or {}).get(_CREATE_CONTEXT_KEY):
            expected = canonical_hash(self.model_dump(mode="json", exclude={"decision_hash"}))
            if self.decision_hash != expected:
                raise ValueError("decision_hash does not match the canonical decision")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": PROMOTION_DECISION_SCHEMA_VERSION, **values}
        payload["decision_hash"] = "0" * 64
        normalized = cls.model_validate(payload, context={_CREATE_CONTEXT_KEY: True})
        digest = canonical_hash(normalized.model_dump(mode="json", exclude={"decision_hash"}))
        return cls.model_validate({**normalized.model_dump(), "decision_hash": digest})


def evaluate_v3_promotion(
    evidence: V3PromotionEvidence,
    threshold: V3PromotionThresholdReference | None,
) -> V3PromotionDecision:
    """Evaluate immutable evidence without importing providers, DB, FastAPI, or settings."""

    if threshold is None:
        return V3PromotionDecision.create(
            status_code=V3PromotionStatusCode.NOT_EVALUATED,
            reason_codes=(V3PromotionReasonCode.THRESHOLD_REFERENCE_MISSING,),
            threshold_reference_hash=None,
            evidence_hash=evidence.evidence_hash,
        )

    reasons: set[V3PromotionReasonCode] = set()
    if threshold.approval_reference is None:
        reasons.add(V3PromotionReasonCode.THRESHOLD_APPROVAL_REFERENCE_INCOMPLETE)
    if not evidence.artifact_hashes_match:
        reasons.add(V3PromotionReasonCode.ARTIFACT_HASH_MISMATCH)
    if evidence.manifest_sha256 != threshold.approved_manifest_sha256:
        reasons.add(V3PromotionReasonCode.ARTIFACT_HASH_MISMATCH)
    if not evidence.artifact_record_counts_match:
        reasons.add(V3PromotionReasonCode.ARTIFACT_RECORD_COUNT_MISMATCH)
    if not evidence.summary_hash_valid:
        reasons.add(V3PromotionReasonCode.SUMMARY_HASH_MISMATCH)
    if not evidence.result_hashes_valid:
        reasons.add(V3PromotionReasonCode.RESULT_HASH_MISMATCH)
    if not evidence.privacy_validation_passed:
        reasons.add(V3PromotionReasonCode.PRIVACY_VALIDATION_FAILED)
    if not evidence.artifact_versions_consistent:
        reasons.add(V3PromotionReasonCode.ARTIFACT_VERSION_INCONSISTENT)

    version_checks = (
        (
            evidence.fixture_version,
            threshold.fixture_version,
            V3PromotionReasonCode.FIXTURE_VERSION_MISMATCH,
        ),
        (
            evidence.harness_version,
            threshold.harness_version,
            V3PromotionReasonCode.HARNESS_VERSION_MISMATCH,
        ),
        (
            evidence.graph_version,
            threshold.graph_version,
            V3PromotionReasonCode.GRAPH_VERSION_MISMATCH,
        ),
        (
            evidence.policy_version,
            threshold.policy_version,
            V3PromotionReasonCode.POLICY_VERSION_MISMATCH,
        ),
        (
            evidence.catalog_version,
            threshold.catalog_version,
            V3PromotionReasonCode.CATALOG_VERSION_MISMATCH,
        ),
        (
            evidence.prompt_version,
            threshold.prompt_version,
            V3PromotionReasonCode.PROMPT_VERSION_MISMATCH,
        ),
        (
            evidence.provider_code,
            threshold.provider_code,
            V3PromotionReasonCode.PROVIDER_VERSION_MISMATCH,
        ),
        (
            evidence.model_version,
            threshold.model_version,
            V3PromotionReasonCode.MODEL_VERSION_MISMATCH,
        ),
    )
    for actual, expected, reason in version_checks:
        if actual != expected:
            reasons.add(reason)

    if evidence.total_case_count < threshold.min_shadow_case_count:
        reasons.add(V3PromotionReasonCode.SHADOW_CASE_COUNT_BELOW_MINIMUM)
    if evidence.repeat_count < threshold.min_repeat_count:
        reasons.add(V3PromotionReasonCode.REPEAT_COUNT_BELOW_MINIMUM)

    if evidence.safety_invariant_pass_rate is None:
        reasons.add(V3PromotionReasonCode.SAFETY_INVARIANT_RATE_UNAVAILABLE)
    elif evidence.safety_invariant_pass_rate < threshold.required_safety_invariant_pass_rate:
        reasons.add(V3PromotionReasonCode.SAFETY_INVARIANT_RATE_BELOW_REQUIRED)
    if evidence.safety_veto_override_count > threshold.max_safety_veto_override_count:
        reasons.add(V3PromotionReasonCode.SAFETY_VETO_OVERRIDE_PRESENT)
    if evidence.constraint_violation_rate is None or (
        evidence.constraint_violation_rate > threshold.max_constraint_violation_rate
    ):
        reasons.add(V3PromotionReasonCode.CONSTRAINT_VIOLATION_PRESENT)

    if evidence.structured_output_success_rate is None:
        reasons.add(V3PromotionReasonCode.STRUCTURED_OUTPUT_RATE_UNAVAILABLE)
    elif evidence.structured_output_success_rate < threshold.min_structured_output_success_rate:
        reasons.add(V3PromotionReasonCode.STRUCTURED_OUTPUT_RATE_BELOW_MINIMUM)
    if evidence.p95_latency_ms is None:
        reasons.add(V3PromotionReasonCode.P95_LATENCY_UNAVAILABLE)
    elif evidence.p95_latency_ms > threshold.max_p95_latency_ms:
        reasons.add(V3PromotionReasonCode.P95_LATENCY_ABOVE_MAXIMUM)

    if evidence.input_token_count_total is None or evidence.output_token_count_total is None:
        reasons.add(V3PromotionReasonCode.TOKEN_USAGE_UNAVAILABLE)
    if evidence.average_cost_per_decision is None:
        reasons.add(V3PromotionReasonCode.AVERAGE_COST_UNAVAILABLE)
    elif evidence.average_cost_per_decision > threshold.max_average_cost_per_decision:
        reasons.add(V3PromotionReasonCode.AVERAGE_COST_ABOVE_MAXIMUM)
    if (
        not evidence.pricing_reference_supplied
        or evidence.currency_code is None
        or evidence.pricing_reference_version is None
        or evidence.pricing_source_reference is None
    ):
        reasons.add(V3PromotionReasonCode.PRICING_REFERENCE_MISSING)
    elif (
        not evidence.pricing_reference_matches_evidence
        or evidence.currency_code != threshold.currency_code
        or evidence.pricing_reference_version != threshold.pricing_reference_version
        or evidence.pricing_source_reference != threshold.pricing_source_reference
    ):
        reasons.add(V3PromotionReasonCode.PRICING_REFERENCE_MISMATCH)

    if evidence.deterministic_fallback_rate is None:
        reasons.add(V3PromotionReasonCode.FALLBACK_RATE_UNAVAILABLE)
    elif evidence.deterministic_fallback_rate > threshold.max_deterministic_fallback_rate:
        reasons.add(V3PromotionReasonCode.FALLBACK_RATE_ABOVE_MAXIMUM)
    if evidence.expert_reviews_pending:
        reasons.add(V3PromotionReasonCode.EXPERT_REVIEW_PENDING)
    if not evidence.reviewer_evidence_complete:
        reasons.add(V3PromotionReasonCode.EXPERT_REVIEW_EVIDENCE_INCOMPLETE)
    if evidence.expert_review_completion_rate is None or (
        evidence.expert_review_completion_rate < threshold.min_expert_review_completion_rate
    ):
        reasons.add(V3PromotionReasonCode.EXPERT_REVIEW_COMPLETION_BELOW_MINIMUM)
    if evidence.expert_agreement_rate is None:
        reasons.add(V3PromotionReasonCode.EXPERT_AGREEMENT_UNAVAILABLE)
    elif evidence.expert_agreement_rate < threshold.min_expert_agreement_rate:
        reasons.add(V3PromotionReasonCode.EXPERT_AGREEMENT_BELOW_MINIMUM)

    ordered = tuple(sorted(reasons, key=_REASON_ORDER.index))
    return V3PromotionDecision.create(
        status_code=(
            V3PromotionStatusCode.BLOCKED
            if ordered
            else V3PromotionStatusCode.READY_FOR_HUMAN_APPROVAL
        ),
        reason_codes=ordered,
        threshold_reference_hash=threshold.threshold_hash,
        evidence_hash=evidence.evidence_hash,
    )


__all__ = [
    "PROMOTION_DECISION_SCHEMA_VERSION",
    "PROMOTION_EVIDENCE_SCHEMA_VERSION",
    "PROMOTION_THRESHOLD_SCHEMA_VERSION",
    "V3PromotionDecision",
    "V3PromotionEvidence",
    "V3PromotionReasonCode",
    "V3PromotionStatusCode",
    "V3PromotionThresholdReference",
    "canonical_hash",
    "canonical_json",
    "evaluate_v3_promotion",
]
