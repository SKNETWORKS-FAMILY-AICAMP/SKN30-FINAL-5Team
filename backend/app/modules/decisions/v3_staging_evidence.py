"""Framework-independent contracts for one-shot V3 staging shadow evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Final, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from pydantic_core import to_jsonable_python

STAGING_REQUEST_SCHEMA_VERSION: Final[Literal["v3-staging-shadow-request-v1"]] = (
    "v3-staging-shadow-request-v1"
)
STAGING_BUDGET_SCHEMA_VERSION: Final[Literal["v3-provider-call-budget-v1"]] = (
    "v3-provider-call-budget-v1"
)
STAGING_MANIFEST_SCHEMA_VERSION: Final[Literal["v3-staging-shadow-manifest-v1"]] = (
    "v3-staging-shadow-manifest-v1"
)
STAGING_BUDGET_CALCULATION_VERSION: Final[str] = "v3-shadow-worst-case-budget-v1"
STAGING_INVOCATION_SLOTS_PER_CASE: Final[int] = 8
STAGING_MAX_REPEAT_COUNT: Final[int] = 5
STAGING_MAX_PROVIDER_CALLS: Final[int] = 10_000

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MACHINE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_FILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SUCCESS_REPORT_FILES = frozenset(
    {
        "results.jsonl",
        "summary.json",
        "summary.md",
        "expert_review_template.jsonl",
        "manifest.json",
    }
)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        to_jsonable_python(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_aware(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information")
    return value


class V3StagingShadowRunStatusCode(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class V3StagingShadowFailureCode(StrEnum):
    OPT_IN_REQUIRED = "OPT_IN_REQUIRED"
    ENVIRONMENT_NOT_STAGING = "ENVIRONMENT_NOT_STAGING"
    LLM_AGENTS_DISABLED = "LLM_AGENTS_DISABLED"
    PROVIDER_NOT_OPENAI = "PROVIDER_NOT_OPENAI"
    MODEL_NOT_APPROVED = "MODEL_NOT_APPROVED"
    LANGGRAPH_DISABLED = "LANGGRAPH_DISABLED"
    SHADOW_EVALUATION_DISABLED = "SHADOW_EVALUATION_DISABLED"
    CREDENTIAL_MISSING = "CREDENTIAL_MISSING"
    PROVIDER_CALL_BUDGET_EXCEEDED = "PROVIDER_CALL_BUDGET_EXCEEDED"
    OUTPUT_PATH_INVALID = "OUTPUT_PATH_INVALID"
    RUN_ALREADY_EXISTS = "RUN_ALREADY_EXISTS"
    RUN_TIMEOUT = "RUN_TIMEOUT"
    INTERRUPTED = "INTERRUPTED"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    PARTIAL_RESULTS = "PARTIAL_RESULTS"
    RESULT_CONTRACT_MISMATCH = "RESULT_CONTRACT_MISMATCH"
    REPORT_WRITE_FAILED = "REPORT_WRITE_FAILED"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


class V3StagingEvidencePrivacyError(ValueError):
    pass


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class V3ProviderCallBudget(_FrozenContract):
    schema_version: Literal["v3-provider-call-budget-v1"] = STAGING_BUDGET_SCHEMA_VERSION
    calculation_version: str = STAGING_BUDGET_CALCULATION_VERSION
    expected_case_count: int = Field(gt=0)
    invocation_slots_per_case: int = STAGING_INVOCATION_SLOTS_PER_CASE
    maximum_attempts_per_invocation: int = Field(ge=1, le=2)
    expected_provider_call_upper_bound: int = Field(gt=0, le=STAGING_MAX_PROVIDER_CALLS)
    maximum_provider_call_budget: int = Field(gt=0, le=STAGING_MAX_PROVIDER_CALLS)
    budget_hash: str

    @field_validator("calculation_version")
    @classmethod
    def validate_calculation_version(cls, value: str) -> str:
        if not _MACHINE_CODE_PATTERN.fullmatch(value):
            raise ValueError("budget calculation version must be a machine code")
        return value

    @field_validator("budget_hash")
    @classmethod
    def validate_budget_hash(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("budget_hash must be a lowercase SHA-256 digest")
        return value

    @model_validator(mode="after")
    def validate_budget(self) -> Self:
        expected = (
            self.expected_case_count
            * self.invocation_slots_per_case
            * self.maximum_attempts_per_invocation
        )
        if self.invocation_slots_per_case != STAGING_INVOCATION_SLOTS_PER_CASE:
            raise ValueError("invocation slot count does not match the bounded graph contract")
        if self.expected_provider_call_upper_bound != expected:
            raise ValueError("provider call upper bound does not match the bounded graph contract")
        if self.maximum_provider_call_budget < expected:
            raise ValueError("maximum provider call budget is below the precomputed upper bound")
        expected_hash = _canonical_hash(self.model_dump(mode="json", exclude={"budget_hash"}))
        if self.budget_hash != expected_hash:
            raise ValueError("budget_hash does not match the canonical budget")
        return self

    @classmethod
    def create(
        cls,
        *,
        expected_case_count: int,
        maximum_attempts_per_invocation: int,
        maximum_provider_call_budget: int,
    ) -> Self:
        payload: dict[str, object] = {
            "schema_version": STAGING_BUDGET_SCHEMA_VERSION,
            "calculation_version": STAGING_BUDGET_CALCULATION_VERSION,
            "expected_case_count": expected_case_count,
            "invocation_slots_per_case": STAGING_INVOCATION_SLOTS_PER_CASE,
            "maximum_attempts_per_invocation": maximum_attempts_per_invocation,
            "expected_provider_call_upper_bound": (
                expected_case_count
                * STAGING_INVOCATION_SLOTS_PER_CASE
                * maximum_attempts_per_invocation
            ),
            "maximum_provider_call_budget": maximum_provider_call_budget,
        }
        payload["budget_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


class V3StagingShadowRunRequest(_FrozenContract):
    schema_version: Literal["v3-staging-shadow-request-v1"] = STAGING_REQUEST_SCHEMA_VERSION
    run_id: str
    fixture_version: str
    harness_version: str
    graph_version: str
    policy_version: str
    catalog_version: str
    prompt_version: str
    provider_code: str
    model_version: str
    fixture_case_count: int = Field(gt=0)
    repeat_count: int = Field(gt=0, le=STAGING_MAX_REPEAT_COUNT)
    expected_case_count: int = Field(gt=0)
    provider_call_budget: V3ProviderCallBudget
    started_at: datetime
    request_hash: str

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        if not _RUN_ID_PATTERN.fullmatch(value):
            raise ValueError("run_id must be a structured local output code")
        return value

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
    def validate_machine_references(cls, value: str, info: ValidationInfo) -> str:
        if not _MACHINE_CODE_PATTERN.fullmatch(value):
            raise ValueError(f"{info.field_name} must be a machine reference")
        return value

    @field_validator("started_at")
    @classmethod
    def validate_started_at(cls, value: datetime) -> datetime:
        return _validate_aware(value, field_name="started_at")

    @field_validator("request_hash")
    @classmethod
    def validate_request_hash(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("request_hash must be a lowercase SHA-256 digest")
        return value

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.expected_case_count != self.fixture_case_count * self.repeat_count:
            raise ValueError("expected case count must equal fixture cases times repeat count")
        if self.provider_call_budget.expected_case_count != self.expected_case_count:
            raise ValueError("request and provider budget case counts do not match")
        expected_hash = _canonical_hash(self.model_dump(mode="json", exclude={"request_hash"}))
        if self.request_hash != expected_hash:
            raise ValueError("request_hash does not match the canonical staging request")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": STAGING_REQUEST_SCHEMA_VERSION, **values}
        payload["request_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


class V3StagingEvidenceFile(_FrozenContract):
    file_name: str
    sha256: str
    record_count: int = Field(gt=0)

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        if not _FILE_NAME_PATTERN.fullmatch(value):
            raise ValueError("evidence file name must not contain a path")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("file hash must be a lowercase SHA-256 digest")
        return value


class V3StagingShadowRunManifest(_FrozenContract):
    schema_version: Literal["v3-staging-shadow-manifest-v1"] = STAGING_MANIFEST_SCHEMA_VERSION
    run_id: str
    request_hash: str
    fixture_version: str
    harness_version: str
    graph_version: str
    policy_version: str
    catalog_version: str
    prompt_version: str
    provider_code: str
    model_version: str
    repeat_count: int = Field(gt=0, le=STAGING_MAX_REPEAT_COUNT)
    expected_case_count: int = Field(gt=0)
    actual_result_count: int = Field(ge=0)
    provider_call_budget: V3ProviderCallBudget
    actual_provider_call_count: int | None = Field(default=None, ge=0)
    started_at: datetime
    finished_at: datetime
    status_code: V3StagingShadowRunStatusCode
    failure_code: V3StagingShadowFailureCode | None = None
    files: tuple[V3StagingEvidenceFile, ...] = ()
    manifest_hash: str

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        if not _RUN_ID_PATTERN.fullmatch(value):
            raise ValueError("run_id must be a structured local output code")
        return value

    @field_validator("request_hash", "manifest_hash")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("staging evidence hash must be a lowercase SHA-256 digest")
        return value

    @field_validator("started_at", "finished_at")
    @classmethod
    def validate_timestamps(cls, value: datetime, info: ValidationInfo) -> datetime:
        return _validate_aware(value, field_name=info.field_name or "timestamp")

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at")
        if (
            self.status_code is V3StagingShadowRunStatusCode.SUCCEEDED
            and self.actual_provider_call_count is not None
            and self.actual_provider_call_count
            > self.provider_call_budget.maximum_provider_call_budget
        ):
            raise ValueError("actual provider calls exceeded the declared budget")
        names = tuple(item.file_name for item in self.files)
        if names != tuple(sorted(set(names))):
            raise ValueError("evidence files must be unique and canonically ordered")
        succeeded = self.status_code is V3StagingShadowRunStatusCode.SUCCEEDED
        if succeeded:
            if self.failure_code is not None:
                raise ValueError("successful staging evidence cannot include a failure code")
            if self.actual_result_count != self.expected_case_count:
                raise ValueError("partial staging results cannot be marked successful")
            if self.actual_provider_call_count is None:
                raise ValueError(
                    "successful staging evidence requires an actual provider call count"
                )
            if self.actual_provider_call_count == 0:
                raise ValueError(
                    "live staging evidence cannot claim success with zero provider calls"
                )
            if set(names) != _SUCCESS_REPORT_FILES:
                raise ValueError("successful staging evidence requires every C1 report")
        elif self.failure_code is None:
            raise ValueError("failed staging evidence requires a canonical failure code")
        expected_hash = _canonical_hash(self.model_dump(mode="json", exclude={"manifest_hash"}))
        if self.manifest_hash != expected_hash:
            raise ValueError("manifest_hash does not match canonical staging evidence")
        return self

    @classmethod
    def create(cls, request: V3StagingShadowRunRequest, **values: object) -> Self:
        payload: dict[str, object] = {
            "schema_version": STAGING_MANIFEST_SCHEMA_VERSION,
            "run_id": request.run_id,
            "request_hash": request.request_hash,
            "fixture_version": request.fixture_version,
            "harness_version": request.harness_version,
            "graph_version": request.graph_version,
            "policy_version": request.policy_version,
            "catalog_version": request.catalog_version,
            "prompt_version": request.prompt_version,
            "provider_code": request.provider_code,
            "model_version": request.model_version,
            "repeat_count": request.repeat_count,
            "expected_case_count": request.expected_case_count,
            "provider_call_budget": request.provider_call_budget,
            "started_at": request.started_at,
            **values,
        }
        files = cast(tuple[V3StagingEvidenceFile, ...], payload.get("files", ()))
        payload["files"] = tuple(sorted(files, key=lambda item: item.file_name))
        payload["manifest_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


_ALLOWED_STAGING_KEYS = frozenset(
    set(V3ProviderCallBudget.model_fields)
    | set(V3StagingShadowRunRequest.model_fields)
    | set(V3StagingEvidenceFile.model_fields)
    | set(V3StagingShadowRunManifest.model_fields)
)


def validate_staging_evidence_privacy(value: object) -> None:
    """Reject non-contract fields before staging evidence is serialized."""

    if isinstance(value, BaseModel):
        validate_staging_evidence_privacy(value.model_dump(mode="json"))
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            if key not in _ALLOWED_STAGING_KEYS:
                raise V3StagingEvidencePrivacyError("staging evidence contains a forbidden key")
            validate_staging_evidence_privacy(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            validate_staging_evidence_privacy(nested)


__all__ = [
    "STAGING_BUDGET_CALCULATION_VERSION",
    "STAGING_BUDGET_SCHEMA_VERSION",
    "STAGING_INVOCATION_SLOTS_PER_CASE",
    "STAGING_MANIFEST_SCHEMA_VERSION",
    "STAGING_MAX_PROVIDER_CALLS",
    "STAGING_MAX_REPEAT_COUNT",
    "STAGING_REQUEST_SCHEMA_VERSION",
    "V3ProviderCallBudget",
    "V3StagingEvidenceFile",
    "V3StagingEvidencePrivacyError",
    "V3StagingShadowFailureCode",
    "V3StagingShadowRunManifest",
    "V3StagingShadowRunRequest",
    "V3StagingShadowRunStatusCode",
    "file_sha256",
    "validate_staging_evidence_privacy",
]
