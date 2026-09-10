"""PHASE 3: score the retriever on its own, with no LLM in the loop.

Two things this module is careful about, because getting either wrong would
produce a number that reads like a quality measure and is not one.

**Ranking is not eligibility.** PostgreSQL decides which exercises a user may be
given; Qdrant only orders that set (`qdrant/snapshot_loader.py`).  A low Recall@k
therefore means "the useful movement was ranked below others that were also
approved", not "an unsafe or unavailable exercise was offered".  The safety
reading of a retrieval score is that there is none.

**The shipped query is not natural language.** `embed_query` receives
`normalized_query_codes` -- three machine codes such as
`("BEGINNER", "HOME", "STRENGTH")` -- serialized as JSON, while documents are
embedded as a rich Korean record.  Scoring a natural-language query would
measure a retriever the service does not have, so the code path is scored by
default and the natural-language variant is available only as a labelled
counterfactual.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.agents.retrieval import (
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    RetrievalModeCode,
    RetrievalStatusCode,
)
from backend.tests.evaluation import catalog

RETRIEVAL_SCHEMA_VERSION: Final = "service-quality-retrieval-case-v1"
DATASETS_DIR: Final = Path(__file__).resolve().parents[1] / "datasets"
RECALL_DEPTHS: Final[tuple[int, ...]] = (1, 3, 5)
DEFAULT_REQUESTED_LIMIT: Final = 12


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ExpectedMetadata(_Frozen):
    """Attributes a relevant document is expected to carry."""

    goal_codes_any_of: tuple[str, ...] = ()
    equipment_codes_any_of: tuple[str, ...] = ()
    location_codes_any_of: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (
            self.goal_codes_any_of or self.equipment_codes_any_of or self.location_codes_any_of
        )


class RetrievalCase(_Frozen):
    case_id: str = Field(pattern=r"^RQ-[A-Z]+-\d{3}$")
    description: str
    normalized_query_codes: tuple[str, ...] = Field(min_length=1)
    natural_language_query: str
    eligible_exercise_codes: tuple[str, ...] = Field(min_length=1)
    relevant_exercise_codes: tuple[str, ...] = Field(min_length=1)
    expected_metadata: ExpectedMetadata = ExpectedMetadata()
    previous_plan_exercise_codes: tuple[str, ...] = ()
    mandatory_exercise_codes: tuple[str, ...] = ()
    notes: str | None = None

    @model_validator(mode="after")
    def validate_case(self) -> Self:
        known = set(catalog.CATALOG)
        for label, codes in (
            ("eligible", self.eligible_exercise_codes),
            ("relevant", self.relevant_exercise_codes),
            ("previous", self.previous_plan_exercise_codes),
            ("mandatory", self.mandatory_exercise_codes),
        ):
            unknown = tuple(code for code in codes if code not in known)
            if unknown:
                raise ValueError(f"{label} references unknown exercises: {unknown}")
        if not set(self.relevant_exercise_codes).issubset(self.eligible_exercise_codes):
            raise ValueError("relevant exercises must be eligible")
        if not set(self.mandatory_exercise_codes).issubset(self.eligible_exercise_codes):
            raise ValueError("mandatory exercises must be eligible")
        return self

    def to_request(self, *, catalog_version: str, envelope_hash: str) -> ExerciseRetrievalRequest:
        return ExerciseRetrievalRequest(
            catalog_version=catalog_version,
            constraint_envelope_hash=envelope_hash,
            eligible_exercise_ids=catalog.ids_for(self.eligible_exercise_codes),
            mandatory_exercise_ids=catalog.ids_for(self.mandatory_exercise_codes),
            previous_plan_exercise_ids=catalog.ids_for(self.previous_plan_exercise_codes),
            normalized_query_codes=tuple(sorted(set(self.normalized_query_codes))),
            retrieval_mode=RetrievalModeCode.VECTOR_RANKED,
            requested_limit=min(DEFAULT_REQUESTED_LIMIT, len(self.eligible_exercise_codes)),
        )


class RetrievalDataset(_Frozen):
    dataset_id: str
    schema_version: str
    description: str
    cases: tuple[RetrievalCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> Self:
        if self.schema_version != RETRIEVAL_SCHEMA_VERSION:
            raise ValueError(f"unsupported retrieval schema version: {self.schema_version}")
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate retrieval case_id")
        return self


def load_retrieval_dataset() -> RetrievalDataset:
    text = (DATASETS_DIR / "retrieval_cases.json").read_text(encoding="utf-8")
    return RetrievalDataset.model_validate_json(text)


@dataclass(frozen=True, slots=True)
class CaseScore:
    """One query's ranking quality plus the filter guarantees it must satisfy."""

    case_id: str
    ranked_exercise_ids: tuple[UUID, ...]
    relevant_exercise_ids: frozenset[UUID]
    recall_at: dict[int, float]
    reciprocal_rank: float
    eligibility_respected: bool
    previous_plan_excluded: bool
    mandatory_retained: bool
    metadata_match_rate: float | None
    retrieval_status_code: str
    fallback_used: bool

    @property
    def filters_held(self) -> bool:
        """The guarantees the retriever owns, as opposed to how well it ranked."""

        return (
            self.eligibility_respected and self.previous_plan_excluded and self.mandatory_retained
        )

    @property
    def first_relevant_rank(self) -> int | None:
        for position, exercise_id in enumerate(self.ranked_exercise_ids, start=1):
            if exercise_id in self.relevant_exercise_ids:
                return position
        return None


@dataclass
class RetrievalReport:
    embedding_provider_code: str
    embedding_model_version: str
    query_mode: str
    is_semantic: bool
    scores: list[CaseScore] = field(default_factory=list)

    def mean_recall_at(self, depth: int) -> float | None:
        values = [score.recall_at[depth] for score in self.scores if depth in score.recall_at]
        return round(sum(values) / len(values), 4) if values else None

    @property
    def mean_reciprocal_rank(self) -> float | None:
        if not self.scores:
            return None
        return round(sum(score.reciprocal_rank for score in self.scores) / len(self.scores), 4)

    @property
    def metadata_filter_accuracy(self) -> float | None:
        values = [
            score.metadata_match_rate
            for score in self.scores
            if score.metadata_match_rate is not None
        ]
        return round(sum(values) / len(values), 4) if values else None

    @property
    def filter_guarantee_pass_rate(self) -> float | None:
        if not self.scores:
            return None
        held = sum(1 for score in self.scores if score.filters_held)
        return round(held / len(self.scores), 4)

    def to_json(self) -> dict[str, object]:
        return {
            "embedding_provider_code": self.embedding_provider_code,
            "embedding_model_version": self.embedding_model_version,
            "query_mode": self.query_mode,
            "is_semantic": self.is_semantic,
            "interpretation": (
                "Qdrant ranks a set PostgreSQL already approved; a low recall means a "
                "useful movement was ordered below other approved ones, never that an "
                "unsafe or unavailable exercise was offered."
                if self.is_semantic
                else "Vectors are hash-derived and carry no meaning. These numbers "
                "validate the wiring only and must not be reported as retrieval quality."
            ),
            "case_count": len(self.scores),
            "recall_at_1": self.mean_recall_at(1),
            "recall_at_3": self.mean_recall_at(3),
            "recall_at_5": self.mean_recall_at(5),
            "mrr": self.mean_reciprocal_rank,
            "metadata_filter_accuracy": self.metadata_filter_accuracy,
            "filter_guarantee_pass_rate": self.filter_guarantee_pass_rate,
            "cases": [
                {
                    "case_id": score.case_id,
                    "returned": len(score.ranked_exercise_ids),
                    "recall_at_1": score.recall_at.get(1),
                    "recall_at_3": score.recall_at.get(3),
                    "recall_at_5": score.recall_at.get(5),
                    "reciprocal_rank": round(score.reciprocal_rank, 4),
                    "first_relevant_rank": score.first_relevant_rank,
                    "eligibility_respected": score.eligibility_respected,
                    "previous_plan_excluded": score.previous_plan_excluded,
                    "mandatory_retained": score.mandatory_retained,
                    "metadata_match_rate": score.metadata_match_rate,
                    "retrieval_status_code": score.retrieval_status_code,
                    "fallback_used": score.fallback_used,
                }
                for score in self.scores
            ],
        }

    def dumps(self) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, indent=2, sort_keys=True)


def _metadata_match_rate(case: RetrievalCase, ranked: tuple[UUID, ...], depth: int) -> float | None:
    """Share of the top-k results that carry the attributes the case asked for."""

    expected = case.expected_metadata
    if expected.is_empty or not ranked:
        return None
    top = ranked[:depth]
    matches = 0
    for exercise_id in top:
        record = catalog.BY_ID[exercise_id]
        ok = True
        if expected.goal_codes_any_of:
            ok = ok and bool(set(expected.goal_codes_any_of) & set(record.goal_codes))
        if expected.equipment_codes_any_of:
            ok = ok and bool(set(expected.equipment_codes_any_of) & set(record.equipment_codes))
        if expected.location_codes_any_of:
            ok = ok and bool(set(expected.location_codes_any_of) & set(record.location_codes))
        matches += int(ok)
    return round(matches / len(top), 4)


def score_case(case: RetrievalCase, result: ExerciseRetrievalResult) -> CaseScore:
    """Turn one retrieval result into ranking metrics and filter guarantees."""

    ranked = result.ranked_exercise_ids
    relevant = frozenset(catalog.ids_for(case.relevant_exercise_codes))
    eligible = set(catalog.ids_for(case.eligible_exercise_codes))
    mandatory = set(catalog.ids_for(case.mandatory_exercise_codes))
    previous = set(catalog.ids_for(case.previous_plan_exercise_codes)) - mandatory

    recall_at: dict[int, float] = {}
    for depth in RECALL_DEPTHS:
        found = len(relevant & set(ranked[:depth]))
        recall_at[depth] = round(found / len(relevant), 4) if relevant else 0.0

    reciprocal = 0.0
    for position, exercise_id in enumerate(ranked, start=1):
        if exercise_id in relevant:
            reciprocal = 1.0 / position
            break

    return CaseScore(
        case_id=case.case_id,
        ranked_exercise_ids=ranked,
        relevant_exercise_ids=relevant,
        recall_at=recall_at,
        reciprocal_rank=reciprocal,
        eligibility_respected=set(ranked).issubset(eligible),
        previous_plan_excluded=not (set(ranked) & previous),
        mandatory_retained=mandatory.issubset(set(ranked)) if mandatory else True,
        metadata_match_rate=_metadata_match_rate(case, ranked, depth=3),
        retrieval_status_code=result.retrieval_status_code.value,
        fallback_used=result.fallback_used,
    )


def is_successful(result: ExerciseRetrievalResult) -> bool:
    return (
        result.retrieval_status_code is RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
        and not result.fallback_used
    )


__all__ = [
    "DEFAULT_REQUESTED_LIMIT",
    "RECALL_DEPTHS",
    "RETRIEVAL_SCHEMA_VERSION",
    "CaseScore",
    "ExpectedMetadata",
    "RetrievalCase",
    "RetrievalDataset",
    "RetrievalReport",
    "is_successful",
    "load_retrieval_dataset",
    "score_case",
]
