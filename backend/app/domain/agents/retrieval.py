"""Framework-independent contracts for V3 exercise-pool retrieval."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from enum import StrEnum
from typing import Final, Literal, Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from backend.app.domain.rules.safety import BodyAreaCode

EXERCISE_RETRIEVAL_REQUEST_SCHEMA_VERSION: Final[Literal["exercise-retrieval-request-v1"]] = (
    "exercise-retrieval-request-v1"
)
EXERCISE_RETRIEVAL_RESULT_SCHEMA_VERSION: Final[Literal["exercise-retrieval-result-v1"]] = (
    "exercise-retrieval-result-v1"
)
EXERCISE_POOL_SNAPSHOT_SCHEMA_VERSION: Final[Literal["exercise-pool-snapshot-v4"]] = (
    "exercise-pool-snapshot-v4"
)

_MACHINE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_COLLECTION_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_QUERY_FRAGMENTS = frozenset(
    {
        "BODY_AREA",
        "DISCOMFORT",
        "EMAIL",
        "HEALTH",
        "INTENSITY_SCORE",
        "PAIN",
        "SEVERITY",
        "USER_ID",
        "WEARABLE",
    }
)
_BODY_AREA_CODES = frozenset(code.value for code in BodyAreaCode)


class RetrievalModeCode(StrEnum):
    VECTOR_RANKED = "VECTOR_RANKED"
    DETERMINISTIC_ONLY = "DETERMINISTIC_ONLY"


class RetrievalStatusCode(StrEnum):
    VECTOR_RETRIEVAL_SUCCEEDED = "VECTOR_RETRIEVAL_SUCCEEDED"
    VECTOR_INDEX_UNAVAILABLE = "VECTOR_INDEX_UNAVAILABLE"
    VECTOR_INDEX_NOT_READY = "VECTOR_INDEX_NOT_READY"
    VECTOR_INDEX_VERSION_MISMATCH = "VECTOR_INDEX_VERSION_MISMATCH"
    VECTOR_SEARCH_TIMEOUT = "VECTOR_SEARCH_TIMEOUT"
    VECTOR_RESULT_STALE = "VECTOR_RESULT_STALE"
    VECTOR_RESULT_NOT_CANONICAL = "VECTOR_RESULT_NOT_CANONICAL"
    VECTOR_RESULT_INSUFFICIENT = "VECTOR_RESULT_INSUFFICIENT"


class RetrievalFailureCode(StrEnum):
    VECTOR_INDEX_UNAVAILABLE = "VECTOR_INDEX_UNAVAILABLE"
    VECTOR_INDEX_NOT_READY = "VECTOR_INDEX_NOT_READY"
    VECTOR_INDEX_VERSION_MISMATCH = "VECTOR_INDEX_VERSION_MISMATCH"
    VECTOR_SEARCH_TIMEOUT = "VECTOR_SEARCH_TIMEOUT"
    VECTOR_RESULT_STALE = "VECTOR_RESULT_STALE"
    VECTOR_RESULT_NOT_CANONICAL = "VECTOR_RESULT_NOT_CANONICAL"
    VECTOR_RESULT_INSUFFICIENT = "VECTOR_RESULT_INSUFFICIENT"


class RetrievalAuditCode(StrEnum):
    DETERMINISTIC_POOL_FALLBACK_USED = "DETERMINISTIC_POOL_FALLBACK_USED"


def _validate_machine_reference(value: str, *, field_name: str) -> str:
    if not _MACHINE_REFERENCE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must contain only a structured machine reference")
    return value


def _validate_collection_reference(value: str, *, field_name: str) -> str:
    if not _COLLECTION_REFERENCE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must contain only a structured collection reference")
    return value


def _validate_hash(value: str, *, field_name: str) -> str:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return value


def _validate_unique(values: tuple[UUID, ...], *, field_name: str) -> tuple[UUID, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def _validate_canonical_uuids(
    values: tuple[UUID, ...],
    *,
    field_name: str,
) -> tuple[UUID, ...]:
    _validate_unique(values, field_name=field_name)
    if values != tuple(sorted(values, key=str)):
        raise ValueError(f"{field_name} must use canonical UUID order")
    return values


def _validate_canonical_machine_references(
    values: tuple[str, ...],
    *,
    field_name: str,
) -> tuple[str, ...]:
    for value in values:
        _validate_machine_reference(value, field_name=field_name)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    if values != tuple(sorted(values)):
        raise ValueError(f"{field_name} must use canonical sorted order")
    return values


class ExerciseRetrievalRequest(BaseModel):
    """Version-bound, identifier-free request accepted by an exercise retriever."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["exercise-retrieval-request-v1"] = (
        EXERCISE_RETRIEVAL_REQUEST_SCHEMA_VERSION
    )
    catalog_version: str
    constraint_envelope_hash: str
    eligible_exercise_ids: tuple[UUID, ...]
    mandatory_exercise_ids: tuple[UUID, ...] = ()
    previous_plan_exercise_ids: tuple[UUID, ...] = ()
    normalized_query_codes: tuple[str, ...]
    retrieval_mode: RetrievalModeCode
    requested_limit: int = Field(gt=0)

    @field_validator("catalog_version")
    @classmethod
    def validate_catalog_version(cls, value: str) -> str:
        return _validate_machine_reference(value, field_name="catalog_version")

    @field_validator("constraint_envelope_hash")
    @classmethod
    def validate_constraint_envelope_hash(cls, value: str) -> str:
        return _validate_hash(value, field_name="constraint_envelope_hash")

    @field_validator("eligible_exercise_ids", "mandatory_exercise_ids")
    @classmethod
    def validate_canonical_id_fields(
        cls,
        value: tuple[UUID, ...],
        info: ValidationInfo,
    ) -> tuple[UUID, ...]:
        return _validate_canonical_uuids(value, field_name=info.field_name or "exercise IDs")

    @field_validator("previous_plan_exercise_ids")
    @classmethod
    def validate_previous_plan_exercise_ids(
        cls,
        values: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        # Previous-plan order is semantically meaningful, so canonicalization
        # validates UUIDs and uniqueness without sorting the sequence.
        return _validate_unique(values, field_name="previous_plan_exercise_ids")

    @field_validator("normalized_query_codes")
    @classmethod
    def validate_normalized_query_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        _validate_canonical_machine_references(values, field_name="normalized_query_codes")
        for value in values:
            normalized = value.upper()
            if normalized in _BODY_AREA_CODES or any(
                fragment in normalized for fragment in _SENSITIVE_QUERY_FRAGMENTS
            ):
                raise ValueError(
                    "normalized_query_codes must not contain health, pain, or identifier data"
                )
        return values

    @model_validator(mode="after")
    def validate_request_invariants(self) -> Self:
        eligible_ids = set(self.eligible_exercise_ids)
        if not eligible_ids:
            raise ValueError("eligible_exercise_ids must not be empty")
        if not set(self.mandatory_exercise_ids).issubset(eligible_ids):
            raise ValueError("mandatory_exercise_ids must be a subset of eligible_exercise_ids")
        return self

    def validate_policy(
        self,
        *,
        allowed_query_codes: frozenset[str],
        requested_limit_max: int,
    ) -> None:
        """Apply versioned policy without adding fields to the wire contract."""

        if requested_limit_max <= 0:
            raise ValueError("requested_limit_max must be positive")
        if self.requested_limit > requested_limit_max:
            raise ValueError("requested_limit exceeds the retrieval policy maximum")
        unknown_codes = set(self.normalized_query_codes) - allowed_query_codes
        if unknown_codes:
            raise ValueError("normalized_query_codes contains a non-allowlisted machine code")


class ExerciseRetrievalResult(BaseModel):
    """Structured retrieval result; never establishes exercise eligibility by itself."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["exercise-retrieval-result-v1"] = (
        EXERCISE_RETRIEVAL_RESULT_SCHEMA_VERSION
    )
    ranked_exercise_ids: tuple[UUID, ...] = ()
    similarity_scores: tuple[float | None, ...] = ()
    collection_name: str | None = None
    vector_index_version: str | None = None
    embedding_model_version: str | None = None
    query_hash: str
    retrieval_status_code: RetrievalStatusCode
    fallback_used: bool

    @field_validator("ranked_exercise_ids")
    @classmethod
    def validate_ranked_exercise_ids(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _validate_unique(values, field_name="ranked_exercise_ids")

    @field_validator("collection_name")
    @classmethod
    def validate_collection_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_collection_reference(value, field_name="collection_name")

    @field_validator("vector_index_version", "embedding_model_version")
    @classmethod
    def validate_optional_references(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _validate_machine_reference(value, field_name=info.field_name or "retrieval field")

    @field_validator("query_hash")
    @classmethod
    def validate_query_hash(cls, value: str) -> str:
        return _validate_hash(value, field_name="query_hash")

    @field_validator("similarity_scores")
    @classmethod
    def validate_similarity_scores(
        cls,
        values: tuple[float | None, ...],
    ) -> tuple[float | None, ...]:
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("similarity_scores must contain only finite numbers or null")
        return values

    @model_validator(mode="after")
    def validate_result_invariants(self) -> Self:
        if len(self.ranked_exercise_ids) != len(self.similarity_scores):
            raise ValueError("ranked_exercise_ids and similarity_scores must have equal length")
        if self.retrieval_status_code is RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED:
            if self.fallback_used:
                raise ValueError("successful vector retrieval cannot claim deterministic fallback")
            if not self.ranked_exercise_ids:
                raise ValueError("successful vector retrieval requires at least one ranked ID")
            if any(
                value is None
                for value in (
                    self.collection_name,
                    self.vector_index_version,
                    self.embedding_model_version,
                )
            ):
                raise ValueError("successful vector retrieval requires collection and version data")
            if any(score is None for score in self.similarity_scores):
                raise ValueError("successful vector retrieval requires a score for every ranked ID")
        elif not self.fallback_used:
            raise ValueError("failed vector retrieval must activate deterministic fallback")
        return self

    def validate_against(self, request: ExerciseRetrievalRequest) -> None:
        """Reject provider output that exceeds the deterministic request boundary."""

        if not set(self.ranked_exercise_ids).issubset(set(request.eligible_exercise_ids)):
            raise ValueError("ranked_exercise_ids must be a subset of eligible_exercise_ids")
        if len(self.ranked_exercise_ids) > request.requested_limit:
            raise ValueError("ranked_exercise_ids must not exceed requested_limit")
        if (
            request.retrieval_mode is RetrievalModeCode.DETERMINISTIC_ONLY
            and self.retrieval_status_code is RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
        ):
            raise ValueError("DETERMINISTIC_ONLY requests cannot report vector retrieval success")


class ExercisePoolExerciseRecord(BaseModel):
    """Canonical, reviewed exercise projection made available to downstream agents."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    exercise_id: UUID
    catalog_version: str
    content_version: str
    stable_code: str
    training_type_code: str
    body_focus_code: str
    movement_pattern_codes: tuple[str, ...]
    difficulty_code: str
    timing_mode_code: str
    # The approved per-exercise timing basis, carried so downstream duration
    # arithmetic reads reviewed catalog values instead of inventing constants.
    # Bounds mirror the catalog CHECK constraints on the exercises table.
    default_seconds_per_rep: int | None = Field(default=None, gt=0)
    default_work_seconds: int | None = Field(default=None, gt=0)
    default_rest_seconds: int = Field(ge=0)
    default_transition_seconds: int = Field(ge=10, le=20)
    recovery_eligible: bool
    goal_codes: tuple[str, ...]
    # The reviewed phases this exercise is approved for and the role it plays in
    # the goal. Both already reach this layer from the catalog; dropping them
    # left the plan with no way to build a warmup/main/cooldown shape or to tell
    # goal-driving work from support work, so every plan came out flat.
    phase_codes: tuple[str, ...] = ()
    role_eligibility_code: str | None = None
    equipment_codes: tuple[str, ...]
    location_codes: tuple[str, ...]
    prescription_reference_codes: tuple[str, ...]
    source_reference_codes: tuple[str, ...]
    review_reference_codes: tuple[str, ...]

    @field_validator(
        "catalog_version",
        "content_version",
        "stable_code",
        "training_type_code",
        "body_focus_code",
        "difficulty_code",
        "timing_mode_code",
    )
    @classmethod
    def validate_scalar_references(cls, value: str, info: ValidationInfo) -> str:
        return _validate_machine_reference(value, field_name=info.field_name or "exercise field")

    @field_validator(
        "movement_pattern_codes",
        "goal_codes",
        "equipment_codes",
        "location_codes",
        "prescription_reference_codes",
        "source_reference_codes",
        "review_reference_codes",
    )
    @classmethod
    def validate_reference_tuples(
        cls,
        values: tuple[str, ...],
        info: ValidationInfo,
    ) -> tuple[str, ...]:
        return _validate_canonical_machine_references(
            values,
            field_name=info.field_name or "exercise references",
        )

    @model_validator(mode="after")
    def validate_timing_basis(self) -> Self:
        """Mirror the catalog constraint pairing timing mode with its seconds basis."""

        if self.timing_mode_code == "REPS":
            if self.default_seconds_per_rep is None or self.default_work_seconds is not None:
                raise ValueError("REPS timing requires seconds per rep without work seconds")
        elif self.timing_mode_code == "DURATION":
            if self.default_work_seconds is None or self.default_seconds_per_rep is not None:
                raise ValueError("DURATION timing requires work seconds without seconds per rep")
        else:
            raise ValueError("timing_mode_code must be REPS or DURATION")
        return self


class RetrievalMetadata(BaseModel):
    """Version and failure lineage included in the immutable pool hash."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    request_schema_version: Literal["exercise-retrieval-request-v1"] = (
        EXERCISE_RETRIEVAL_REQUEST_SCHEMA_VERSION
    )
    result_schema_version: Literal["exercise-retrieval-result-v1"] = (
        EXERCISE_RETRIEVAL_RESULT_SCHEMA_VERSION
    )
    collection_name: str | None = None
    vector_index_version: str | None = None
    embedding_model_version: str | None = None
    query_hash: str
    retrieval_status_code: RetrievalStatusCode
    retrieval_failure_codes: tuple[RetrievalFailureCode, ...] = ()
    deterministic_fallback_version: str | None = None
    deterministic_pool_fallback_used: bool

    @field_validator("collection_name")
    @classmethod
    def validate_collection_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_collection_reference(value, field_name="collection_name")

    @field_validator("vector_index_version", "embedding_model_version")
    @classmethod
    def validate_optional_references(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _validate_machine_reference(value, field_name=info.field_name or "metadata field")

    @field_validator("deterministic_fallback_version")
    @classmethod
    def validate_fallback_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_machine_reference(value, field_name="deterministic_fallback_version")

    @field_validator("query_hash")
    @classmethod
    def validate_query_hash(cls, value: str) -> str:
        return _validate_hash(value, field_name="query_hash")

    @field_validator("retrieval_failure_codes")
    @classmethod
    def validate_failure_codes(
        cls,
        values: tuple[RetrievalFailureCode, ...],
    ) -> tuple[RetrievalFailureCode, ...]:
        if len(values) != len(set(values)):
            raise ValueError("retrieval_failure_codes must not contain duplicates")
        return values

    @model_validator(mode="after")
    def validate_metadata_invariants(self) -> Self:
        succeeded = self.retrieval_status_code is RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
        if succeeded:
            if self.retrieval_failure_codes or self.deterministic_pool_fallback_used:
                raise ValueError("successful retrieval cannot carry failure or fallback metadata")
            if any(
                value is None
                for value in (
                    self.collection_name,
                    self.vector_index_version,
                    self.embedding_model_version,
                )
            ):
                raise ValueError("successful retrieval metadata requires collection and versions")
        else:
            expected_failure = RetrievalFailureCode(self.retrieval_status_code.value)
            if expected_failure not in self.retrieval_failure_codes:
                raise ValueError("failure metadata must retain the primary retrieval status code")
            if not self.deterministic_pool_fallback_used:
                raise ValueError("failed retrieval metadata must retain deterministic fallback use")
        if self.deterministic_pool_fallback_used != (
            self.deterministic_fallback_version is not None
        ):
            raise ValueError("fallback use and deterministic_fallback_version must agree")
        return self


def _snapshot_hash_payload(
    *,
    catalog_version: str,
    constraint_envelope_hash: str,
    exercises: tuple[ExercisePoolExerciseRecord, ...],
    mandatory_exercise_ids: tuple[UUID, ...],
    vector_ranked_exercise_ids: tuple[UUID, ...],
    retrieval_metadata: RetrievalMetadata,
) -> dict[str, object]:
    return {
        "schema_version": EXERCISE_POOL_SNAPSHOT_SCHEMA_VERSION,
        "catalog_version": catalog_version,
        "constraint_envelope_hash": constraint_envelope_hash,
        "exercises": [exercise.model_dump(mode="json") for exercise in exercises],
        "mandatory_exercise_ids": [str(value) for value in mandatory_exercise_ids],
        "vector_ranked_exercise_ids": [str(value) for value in vector_ranked_exercise_ids],
        "retrieval_metadata": retrieval_metadata.model_dump(mode="json"),
    }


def exercise_pool_hash(
    *,
    catalog_version: str,
    constraint_envelope_hash: str,
    exercises: tuple[ExercisePoolExerciseRecord, ...],
    mandatory_exercise_ids: tuple[UUID, ...],
    vector_ranked_exercise_ids: tuple[UUID, ...],
    retrieval_metadata: RetrievalMetadata,
) -> str:
    """Return a stable hash without request-time timestamps."""

    payload = _snapshot_hash_payload(
        catalog_version=catalog_version,
        constraint_envelope_hash=constraint_envelope_hash,
        exercises=exercises,
        mandatory_exercise_ids=mandatory_exercise_ids,
        vector_ranked_exercise_ids=vector_ranked_exercise_ids,
        retrieval_metadata=retrieval_metadata,
    )
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class ExercisePoolSnapshot(BaseModel):
    """Immutable, canonical pool shared by all three V3 specialist agents."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["exercise-pool-snapshot-v4"] = EXERCISE_POOL_SNAPSHOT_SCHEMA_VERSION
    catalog_version: str
    constraint_envelope_hash: str
    exercises: tuple[ExercisePoolExerciseRecord, ...] = Field(min_length=1)
    mandatory_exercise_ids: tuple[UUID, ...] = ()
    vector_ranked_exercise_ids: tuple[UUID, ...] = ()
    pool_hash: str
    retrieval_metadata: RetrievalMetadata
    created_at: datetime

    @field_validator("catalog_version")
    @classmethod
    def validate_catalog_version(cls, value: str) -> str:
        return _validate_machine_reference(value, field_name="catalog_version")

    @field_validator("constraint_envelope_hash", "pool_hash")
    @classmethod
    def validate_hash_fields(cls, value: str, info: ValidationInfo) -> str:
        return _validate_hash(value, field_name=info.field_name or "snapshot hash")

    @field_validator("mandatory_exercise_ids")
    @classmethod
    def validate_mandatory_ids(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _validate_canonical_uuids(values, field_name="mandatory_exercise_ids")

    @field_validator("vector_ranked_exercise_ids")
    @classmethod
    def validate_vector_ranked_ids(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _validate_unique(values, field_name="vector_ranked_exercise_ids")

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_snapshot_invariants(self) -> Self:
        exercise_ids = tuple(exercise.exercise_id for exercise in self.exercises)
        _validate_canonical_uuids(exercise_ids, field_name="exercises")
        if any(exercise.catalog_version != self.catalog_version for exercise in self.exercises):
            raise ValueError("all exercises must use the snapshot catalog_version")
        exercise_id_set = set(exercise_ids)
        if not set(self.mandatory_exercise_ids).issubset(exercise_id_set):
            raise ValueError("mandatory_exercise_ids must be present in exercises")
        if not set(self.vector_ranked_exercise_ids).issubset(exercise_id_set):
            raise ValueError("vector_ranked_exercise_ids must be present in exercises")
        expected_hash = exercise_pool_hash(
            catalog_version=self.catalog_version,
            constraint_envelope_hash=self.constraint_envelope_hash,
            exercises=self.exercises,
            mandatory_exercise_ids=self.mandatory_exercise_ids,
            vector_ranked_exercise_ids=self.vector_ranked_exercise_ids,
            retrieval_metadata=self.retrieval_metadata,
        )
        if self.pool_hash != expected_hash:
            raise ValueError("pool_hash does not match the canonical snapshot payload")
        return self

    @classmethod
    def create(
        cls,
        *,
        catalog_version: str,
        constraint_envelope_hash: str,
        exercises: tuple[ExercisePoolExerciseRecord, ...],
        mandatory_exercise_ids: tuple[UUID, ...],
        vector_ranked_exercise_ids: tuple[UUID, ...],
        retrieval_metadata: RetrievalMetadata,
        created_at: datetime,
    ) -> Self:
        pool_hash = exercise_pool_hash(
            catalog_version=catalog_version,
            constraint_envelope_hash=constraint_envelope_hash,
            exercises=exercises,
            mandatory_exercise_ids=mandatory_exercise_ids,
            vector_ranked_exercise_ids=vector_ranked_exercise_ids,
            retrieval_metadata=retrieval_metadata,
        )
        return cls(
            catalog_version=catalog_version,
            constraint_envelope_hash=constraint_envelope_hash,
            exercises=exercises,
            mandatory_exercise_ids=mandatory_exercise_ids,
            vector_ranked_exercise_ids=vector_ranked_exercise_ids,
            pool_hash=pool_hash,
            retrieval_metadata=retrieval_metadata,
            created_at=created_at,
        )


class ExerciseRetriever(Protocol):
    """External retrieval boundary implemented by infrastructure adapters only."""

    def retrieve(self, request: ExerciseRetrievalRequest) -> ExerciseRetrievalResult: ...


__all__ = [
    "EXERCISE_POOL_SNAPSHOT_SCHEMA_VERSION",
    "EXERCISE_RETRIEVAL_REQUEST_SCHEMA_VERSION",
    "EXERCISE_RETRIEVAL_RESULT_SCHEMA_VERSION",
    "ExercisePoolExerciseRecord",
    "ExercisePoolSnapshot",
    "ExerciseRetrievalRequest",
    "ExerciseRetrievalResult",
    "ExerciseRetriever",
    "RetrievalAuditCode",
    "RetrievalFailureCode",
    "RetrievalMetadata",
    "RetrievalModeCode",
    "RetrievalStatusCode",
    "exercise_pool_hash",
]
