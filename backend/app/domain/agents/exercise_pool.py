"""Deterministic V3 ExercisePoolSnapshot assembly.

The module consumes PostgreSQL-owned candidate and revalidation projections. It
does not access a database, vector store, web framework, or orchestration SDK.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExercisePoolSnapshot,
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    ExerciseRetriever,
    RetrievalFailureCode,
    RetrievalMetadata,
    RetrievalModeCode,
    RetrievalStatusCode,
)
from backend.app.domain.rules.safety import SafetyRequiredActionCode, SafetyStatusCode

_MACHINE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FAILURE_ORDER = tuple(RetrievalFailureCode)


def _machine_code(value: str, *, field_name: str) -> str:
    if not _MACHINE_CODE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a structured machine code")
    return value


def _sha256(value: str, *, field_name: str) -> str:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return value


def _unique_ids(values: tuple[UUID, ...], *, field_name: str) -> tuple[UUID, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def _canonical_ids(values: tuple[UUID, ...], *, field_name: str) -> tuple[UUID, ...]:
    _unique_ids(values, field_name=field_name)
    if values != tuple(sorted(values, key=str)):
        raise ValueError(f"{field_name} must use canonical UUID order")
    return values


class SafetyRetrievalGate(BaseModel):
    """Minimal SafetyPolicyEngine projection evaluated before request creation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    status_code: SafetyStatusCode
    required_action_code: SafetyRequiredActionCode | None = None
    plan_generation_allowed: bool

    @model_validator(mode="after")
    def validate_gate(self) -> Self:
        allowed_statuses = {SafetyStatusCode.PASS, SafetyStatusCode.REVISE}
        if self.plan_generation_allowed:
            if self.status_code not in allowed_statuses or self.required_action_code is not None:
                raise ValueError("plan generation may only follow PASS or REVISE without an action")
        elif self.status_code in allowed_statuses and self.required_action_code is None:
            raise ValueError("PASS or REVISE must explicitly allow V3 pool generation")
        if (
            self.required_action_code is not None
            and self.status_code is not SafetyStatusCode.BLOCKED
        ):
            raise ValueError("REST or STOP_AND_SEEK_HELP requires BLOCKED safety status")
        return self


class ExerciseRetrievalPolicy(BaseModel):
    """Versioned non-medical policy for query allowlisting and pool sizing."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policy_version: str
    allowed_query_codes: frozenset[str] = Field(min_length=1)
    requested_limit_max: int = Field(gt=0)
    minimum_vector_candidates: int = Field(ge=0)
    deterministic_fallback_version: str
    expected_collection_name: str
    expected_vector_index_version: str
    expected_embedding_model_version: str

    @field_validator(
        "policy_version",
        "deterministic_fallback_version",
        "expected_collection_name",
        "expected_vector_index_version",
        "expected_embedding_model_version",
    )
    @classmethod
    def validate_machine_fields(cls, value: str, info: ValidationInfo) -> str:
        return _machine_code(value, field_name=info.field_name or "policy field")

    @field_validator("allowed_query_codes")
    @classmethod
    def validate_allowed_query_codes(cls, values: frozenset[str]) -> frozenset[str]:
        for value in values:
            _machine_code(value, field_name="allowed_query_codes")
        return values

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        if self.minimum_vector_candidates > self.requested_limit_max:
            raise ValueError("minimum_vector_candidates cannot exceed requested_limit_max")
        return self


class CanonicalExerciseRevalidation(BaseModel):
    """One PostgreSQL revalidation row; rejected flags never enter a snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    exercise: ExercisePoolExerciseRecord
    catalog_content_version: str
    catalog_review_version: str
    production_approved: bool

    @field_validator("catalog_content_version", "catalog_review_version")
    @classmethod
    def validate_version(cls, value: str, info: ValidationInfo) -> str:
        return _machine_code(value, field_name=info.field_name or "version")


class DeterministicExerciseCandidates(BaseModel):
    """PostgreSQL-owned eligible set plus its canonical revalidation projection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    catalog_version: str
    catalog_content_version: str
    catalog_review_version: str
    constraint_envelope_hash: str
    eligible_exercise_ids: tuple[UUID, ...] = Field(min_length=1)
    mandatory_goal_exercise_ids: tuple[UUID, ...] = ()
    approved_safe_alternative_ids: tuple[UUID, ...] = ()
    deterministic_fallback_order: tuple[UUID, ...]
    revalidated_exercises: tuple[CanonicalExerciseRevalidation, ...]

    @field_validator("catalog_version", "catalog_content_version", "catalog_review_version")
    @classmethod
    def validate_versions(cls, value: str, info: ValidationInfo) -> str:
        return _machine_code(value, field_name=info.field_name or "version")

    @field_validator("constraint_envelope_hash")
    @classmethod
    def validate_envelope_hash(cls, value: str) -> str:
        return _sha256(value, field_name="constraint_envelope_hash")

    @field_validator(
        "eligible_exercise_ids",
        "mandatory_goal_exercise_ids",
        "approved_safe_alternative_ids",
    )
    @classmethod
    def validate_canonical_fields(
        cls,
        values: tuple[UUID, ...],
        info: ValidationInfo,
    ) -> tuple[UUID, ...]:
        return _canonical_ids(values, field_name=info.field_name or "exercise IDs")

    @field_validator("deterministic_fallback_order")
    @classmethod
    def validate_fallback_order(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _unique_ids(values, field_name="deterministic_fallback_order")

    @model_validator(mode="after")
    def validate_candidate_set(self) -> Self:
        eligible = set(self.eligible_exercise_ids)
        required = set(self.mandatory_goal_exercise_ids) | set(self.approved_safe_alternative_ids)
        if not required.issubset(eligible):
            raise ValueError("mandatory and approved safe alternatives must be eligible")
        if not set(self.deterministic_fallback_order).issubset(eligible):
            raise ValueError("deterministic fallback IDs must be eligible")
        revalidated_ids = tuple(item.exercise.exercise_id for item in self.revalidated_exercises)
        _unique_ids(revalidated_ids, field_name="revalidated exercise IDs")
        if not set(revalidated_ids).issubset(eligible):
            raise ValueError("PostgreSQL revalidation must not introduce an ineligible exercise")
        return self

    @property
    def mandatory_exercise_ids(self) -> tuple[UUID, ...]:
        return tuple(
            sorted(
                set(self.mandatory_goal_exercise_ids) | set(self.approved_safe_alternative_ids),
                key=str,
            )
        )


class ExercisePoolBuildInput(BaseModel):
    """Application input that remains safe to construct before the retrieval gate opens."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    safety_gate: SafetyRetrievalGate
    candidates: DeterministicExerciseCandidates
    retrieval_policy: ExerciseRetrievalPolicy
    previous_plan_exercise_ids: tuple[UUID, ...] = ()
    normalized_query_codes: tuple[str, ...]
    retrieval_mode: RetrievalModeCode
    requested_limit: int = Field(gt=0)

    @field_validator("previous_plan_exercise_ids")
    @classmethod
    def validate_previous_ids(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _unique_ids(values, field_name="previous_plan_exercise_ids")


class ExercisePoolBuildError(ValueError):
    """The application must map this fail-closed outcome to its existing terminal boundary."""


class ExercisePoolBuilder(Protocol):
    def build(
        self, build_input: ExercisePoolBuildInput, *, created_at: datetime
    ) -> ExercisePoolSnapshot: ...


def _ordered_failure_codes(
    values: set[RetrievalFailureCode],
) -> tuple[RetrievalFailureCode, ...]:
    return tuple(code for code in _FAILURE_ORDER if code in values)


class DeterministicExercisePoolBuilder:
    """Combine retriever output and PostgreSQL revalidation without weakening Safety."""

    def __init__(self, retriever: ExerciseRetriever) -> None:
        self._retriever = retriever

    def build(
        self,
        build_input: ExercisePoolBuildInput,
        *,
        created_at: datetime,
    ) -> ExercisePoolSnapshot:
        if not build_input.safety_gate.plan_generation_allowed:
            raise ExercisePoolBuildError("Safety gate forbids exercise retrieval")

        source = build_input.candidates
        policy = build_input.retrieval_policy
        request = ExerciseRetrievalRequest(
            catalog_version=source.catalog_version,
            constraint_envelope_hash=source.constraint_envelope_hash,
            eligible_exercise_ids=source.eligible_exercise_ids,
            mandatory_exercise_ids=source.mandatory_exercise_ids,
            previous_plan_exercise_ids=build_input.previous_plan_exercise_ids,
            normalized_query_codes=build_input.normalized_query_codes,
            retrieval_mode=build_input.retrieval_mode,
            requested_limit=build_input.requested_limit,
        )
        request.validate_policy(
            allowed_query_codes=policy.allowed_query_codes,
            requested_limit_max=policy.requested_limit_max,
        )
        result = self._retriever.retrieve(request)
        return self._assemble(
            request=request,
            result=result,
            source=source,
            policy=policy,
            created_at=created_at,
        )

    def _assemble(
        self,
        *,
        request: ExerciseRetrievalRequest,
        result: ExerciseRetrievalResult,
        source: DeterministicExerciseCandidates,
        policy: ExerciseRetrievalPolicy,
        created_at: datetime,
    ) -> ExercisePoolSnapshot:
        failures: set[RetrievalFailureCode] = set()
        if result.retrieval_status_code is not RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED:
            failures.add(RetrievalFailureCode(result.retrieval_status_code.value))

        try:
            result.validate_against(request)
        except ValueError:
            failures.add(RetrievalFailureCode.VECTOR_RESULT_NOT_CANONICAL)

        if result.retrieval_status_code is RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED and (
            result.collection_name != policy.expected_collection_name
            or result.vector_index_version != policy.expected_vector_index_version
            or result.embedding_model_version != policy.expected_embedding_model_version
        ):
            failures.add(RetrievalFailureCode.VECTOR_INDEX_VERSION_MISMATCH)

        valid_records: dict[UUID, ExercisePoolExerciseRecord] = {}
        stale_ids: set[UUID] = set()
        unapproved_ids: set[UUID] = set()
        for item in source.revalidated_exercises:
            exercise = item.exercise
            if (
                exercise.catalog_version != source.catalog_version
                or item.catalog_content_version != source.catalog_content_version
                or item.catalog_review_version != source.catalog_review_version
            ):
                stale_ids.add(exercise.exercise_id)
                continue
            if not item.production_approved:
                unapproved_ids.add(exercise.exercise_id)
                continue
            valid_records[exercise.exercise_id] = exercise

        vector_ids: tuple[UUID, ...] = ()
        if not failures:
            vector_ids = tuple(
                exercise_id
                for exercise_id in result.ranked_exercise_ids
                if exercise_id in valid_records
            )
            ranked_set = set(result.ranked_exercise_ids)
            if ranked_set & stale_ids:
                failures.add(RetrievalFailureCode.VECTOR_RESULT_STALE)
            if ranked_set & unapproved_ids or len(vector_ids) != len(result.ranked_exercise_ids):
                failures.add(RetrievalFailureCode.VECTOR_RESULT_NOT_CANONICAL)

        required_ids = source.mandatory_exercise_ids
        if not set(required_ids).issubset(valid_records):
            raise ExercisePoolBuildError(
                "mandatory or approved safe alternative failed PostgreSQL revalidation"
            )

        nonmandatory_vector_ids = tuple(
            value for value in vector_ids if value not in set(required_ids)
        )
        if (
            result.retrieval_status_code is RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
            and len(nonmandatory_vector_ids) < policy.minimum_vector_candidates
        ):
            failures.add(RetrievalFailureCode.VECTOR_RESULT_INSUFFICIENT)

        selected_order: list[UUID] = list(required_ids)
        selected_order.extend(value for value in vector_ids if value not in selected_order)
        if failures:
            target_nonmandatory = request.requested_limit
            current_nonmandatory = len(
                [value for value in selected_order if value not in set(required_ids)]
            )
            for exercise_id in source.deterministic_fallback_order:
                if current_nonmandatory >= target_nonmandatory:
                    break
                if exercise_id in valid_records and exercise_id not in selected_order:
                    selected_order.append(exercise_id)
                    if exercise_id not in set(required_ids):
                        current_nonmandatory += 1

        if not selected_order:
            raise ExercisePoolBuildError("no production-approved exercise survived revalidation")

        fallback_used = bool(failures)
        failure_codes = _ordered_failure_codes(failures)
        status_code = (
            RetrievalStatusCode(failure_codes[0].value)
            if failure_codes
            else RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
        )
        metadata = RetrievalMetadata(
            collection_name=result.collection_name,
            vector_index_version=result.vector_index_version,
            embedding_model_version=result.embedding_model_version,
            query_hash=result.query_hash,
            retrieval_status_code=status_code,
            retrieval_failure_codes=failure_codes,
            deterministic_fallback_version=(
                policy.deterministic_fallback_version if fallback_used else None
            ),
            deterministic_pool_fallback_used=fallback_used,
        )
        exercises = tuple(
            valid_records[exercise_id] for exercise_id in sorted(selected_order, key=str)
        )
        return ExercisePoolSnapshot.create(
            catalog_version=source.catalog_version,
            constraint_envelope_hash=source.constraint_envelope_hash,
            exercises=exercises,
            mandatory_exercise_ids=required_ids,
            vector_ranked_exercise_ids=vector_ids,
            retrieval_metadata=metadata,
            created_at=created_at,
        )


__all__ = [
    "CanonicalExerciseRevalidation",
    "DeterministicExerciseCandidates",
    "DeterministicExercisePoolBuilder",
    "ExercisePoolBuildError",
    "ExercisePoolBuildInput",
    "ExercisePoolBuilder",
    "ExerciseRetrievalPolicy",
    "SafetyRetrievalGate",
]
