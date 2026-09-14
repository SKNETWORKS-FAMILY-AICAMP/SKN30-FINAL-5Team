"""PHASE 7: compare two plans head to head without telling the judge whose they are.

A pointwise score cannot settle a close call: PHASE 6 put C at 4.40 and B at 4.08
on a five-point scale, which is a gap small enough to be an artefact of how each
plan happened to land against a rubric. Asking one judge to choose between two
plans it sees side by side removes that calibration question.

It introduces a different one -- **position bias**. A judge that simply prefers
whichever plan it read first would produce a clean-looking win rate that means
nothing. So every pair is judged twice, in both orders, and the two verdicts are
compared:

* they name the same *plan* -> a real preference
* they name the same *slot* -> the judge followed position, not content
* one is a tie -> recorded as its own outcome, never rounded toward a winner

Only the first kind is counted as a win. The second is reported as the bias rate,
which is the number that says how much the first kind can be trusted.

**Blinding is verified, not assumed.** The payload already drops the one field
that structurally identifies the architecture (`advisory_codes`), but
`decision_codes` are written by the model and could name their own pipeline.
`redact_revealing_codes` removes any that do, and the count is reported, so a
silent leak becomes a visible number.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.tests.evaluation.judge.rubric import JudgeCriterion, rubric_text

PAIRWISE_PROMPT_VERSION: Final = "service-quality-pairwise-prompt-v1"
PAIRWISE_OUTPUT_SCHEMA_VERSION: Final = "service-quality-pairwise-output-v1"

# Substrings that would tell the judge which pipeline wrote a plan. Matched
# against model-authored decision codes only; every other payload field is a
# server-owned projection.
_REVEALING_FRAGMENTS: Final[tuple[str, ...]] = (
    "AGENT",
    "COORDINATOR",
    "SPECIALIST",
    "TRAINING",
    "RECOVERY_AGENT",
    "FEASIBILITY",
    "SINGLE",
    "MULTI",
    "PIPELINE",
    "ORCHESTRAT",
)


class PairwiseChoice(StrEnum):
    PLAN_ONE = "PLAN_ONE"
    PLAN_TWO = "PLAN_TWO"
    TIE = "TIE"


class CriterionPreference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    criterion: JudgeCriterion
    choice: PairwiseChoice


class PairwiseVerdict(BaseModel):
    """What the pairwise judge is asked to return, and nothing else."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: str = PAIRWISE_OUTPUT_SCHEMA_VERSION
    criterion_preferences: tuple[CriterionPreference, ...] = Field(min_length=6, max_length=6)
    overall_choice: PairwiseChoice
    rationale: str = Field(min_length=1, max_length=400)

    @model_validator(mode="after")
    def validate_verdict(self) -> Self:
        criteria = tuple(item.criterion for item in self.criterion_preferences)
        if set(criteria) != set(JudgeCriterion) or len(set(criteria)) != len(criteria):
            raise ValueError("each rubric criterion must be preferred exactly once")
        return self

    def choice_for(self, criterion: JudgeCriterion) -> PairwiseChoice:
        return next(
            item.choice for item in self.criterion_preferences if item.criterion is criterion
        )


class PairwiseJudgeModel(Protocol):
    def compare(self, *, system: str, payload: dict[str, Any]) -> PairwiseVerdict: ...

    @property
    def model_label(self) -> str: ...


SYSTEM_INSTRUCTION: Final = (
    "당신은 운동 추천 품질을 평가하는 심사자다. "
    "두 개의 계획을 비교해 어느 쪽이 이 사용자에게 더 나은 추천인지 고른다. "
    "제공된 구조화 데이터만 사용하고 추가 정보를 가정하지 마라. "
    "두 계획이 어떤 시스템에서 나왔는지는 알 수 없으며 추측하지 마라. "
    "안전성은 이미 결정적 규칙이 판정했으므로 다시 판정하지 마라. "
    "의학적 진단이나 처방 표현을 쓰지 마라. "
    "실질적인 차이가 없으면 TIE를 고르고, 무승부를 피하려고 억지로 고르지 마라. "
    "근거는 짧은 한국어 문장 하나로 쓰고 요청된 스키마 외의 내용을 반환하지 마라."
)


def redact_revealing_codes(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Strip model-authored codes that would name the pipeline that wrote them.

    Returns the cleaned payload and how many codes were removed, so the report
    can state that blinding held rather than assume it.
    """

    codes = payload.get("decision_codes")
    if not isinstance(codes, list):
        return payload, 0
    kept = [
        code
        for code in codes
        if not any(fragment in str(code).upper() for fragment in _REVEALING_FRAGMENTS)
    ]
    if len(kept) == len(codes):
        return payload, 0
    cleaned = dict(payload)
    cleaned["decision_codes"] = kept
    return cleaned, len(codes) - len(kept)


def pairwise_request_text(
    *, user_context: dict[str, Any], plan_one: dict[str, Any], plan_two: dict[str, Any]
) -> str:
    """Render the request body. The two plans are labelled by slot, never by source."""

    return json.dumps(
        {
            "prompt_version": PAIRWISE_PROMPT_VERSION,
            "output_schema_version": PAIRWISE_OUTPUT_SCHEMA_VERSION,
            "rubric": rubric_text(),
            "input": {
                "user_context": user_context,
                "PLAN_ONE": plan_one,
                "PLAN_TWO": plan_two,
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _plan_body(payload: dict[str, Any]) -> dict[str, Any]:
    """Everything about one plan except the shared user context."""

    return {
        key: value
        for key, value in payload.items()
        if key not in {"user_context", "schema_version"}
    }


def first_slot_holder(case_id: str, left: str, right: str) -> str:
    """Which architecture is presented first, decided reproducibly per case.

    The master specification asks for the positions to be randomised. A hash of
    the case and the pair gives an arrangement that varies across cases but is
    identical on a re-run, so a disagreement between two runs is the judge's and
    not the shuffle's.
    """

    digest = hashlib.sha256(f"{case_id}|{left}|{right}".encode()).digest()
    return left if digest[0] % 2 == 0 else right


@dataclass(frozen=True, slots=True)
class PairwiseOutcome:
    """One case, one pair, judged in both orders."""

    case_id: str
    category: str
    left: str
    right: str
    first_presented: str
    verdict_order_one: PairwiseVerdict
    verdict_order_two: PairwiseVerdict
    redacted_code_count: int

    @staticmethod
    def _winner_for(choice: PairwiseChoice, *, slot_one: str, slot_two: str) -> str | None:
        """Map a slot choice back to the architecture that filled that slot."""

        if choice is PairwiseChoice.TIE:
            return None
        return slot_one if choice is PairwiseChoice.PLAN_ONE else slot_two

    @staticmethod
    def _winner(verdict: PairwiseVerdict, *, slot_one: str, slot_two: str) -> str | None:
        return PairwiseOutcome._winner_for(
            verdict.overall_choice, slot_one=slot_one, slot_two=slot_two
        )

    @property
    def second_presented(self) -> str:
        return self.right if self.first_presented == self.left else self.left

    @property
    def winner_order_one(self) -> str | None:
        return self._winner(
            self.verdict_order_one,
            slot_one=self.first_presented,
            slot_two=self.second_presented,
        )

    @property
    def winner_order_two(self) -> str | None:
        # The orders are swapped, so slot one now holds the other architecture.
        return self._winner(
            self.verdict_order_two,
            slot_one=self.second_presented,
            slot_two=self.first_presented,
        )

    @property
    def agreed(self) -> bool:
        """Both readings named the same architecture, or both said tie."""

        return self.winner_order_one == self.winner_order_two

    @property
    def followed_position(self) -> bool:
        """The judge chose the same slot twice while the plans swapped.

        This is the failure mode pairwise judging exists to expose: a verdict
        that tracks where a plan appeared rather than what it contains.
        """

        if self.verdict_order_one.overall_choice is PairwiseChoice.TIE:
            return False
        return self.verdict_order_one.overall_choice is self.verdict_order_two.overall_choice

    @property
    def consensus_winner(self) -> str | None:
        """The architecture both readings preferred, or None if they disagreed."""

        return self.winner_order_one if self.agreed else None

    def criterion_consensus(self, criterion: JudgeCriterion) -> str | None:
        """The architecture both readings preferred on one criterion, if any.

        Same agreement rule as the overall verdict: a criterion only counts when
        the two orders name the same architecture, so a position-driven
        preference cannot contribute to a per-criterion tally either.
        """

        winner_one = self._winner_for(
            self.verdict_order_one.choice_for(criterion),
            slot_one=self.first_presented,
            slot_two=self.second_presented,
        )
        winner_two = self._winner_for(
            self.verdict_order_two.choice_for(criterion),
            slot_one=self.second_presented,
            slot_two=self.first_presented,
        )
        return winner_one if winner_one == winner_two else None

    def to_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "pair": [self.left, self.right],
            "first_presented": self.first_presented,
            "winner_order_one": self.winner_order_one,
            "winner_order_two": self.winner_order_two,
            "agreed": self.agreed,
            "followed_position": self.followed_position,
            "consensus_winner": self.consensus_winner,
            "redacted_code_count": self.redacted_code_count,
            "rationale_order_one": self.verdict_order_one.rationale,
            "rationale_order_two": self.verdict_order_two.rationale,
        }


@dataclass
class PairResult:
    """Every outcome for one architecture pair, aggregated the way PHASE 7 asks."""

    left: str
    right: str
    outcomes: list[PairwiseOutcome] = field(default_factory=list)
    unjudgeable: list[dict[str, str]] = field(default_factory=list)

    @property
    def judged(self) -> int:
        return len(self.outcomes)

    def tally(self) -> dict[str, int]:
        """Win / tie / win over the pairs both readings agreed on."""

        counts = {self.left: 0, self.right: 0, "TIE": 0, "DISAGREED": 0}
        for outcome in self.outcomes:
            if not outcome.agreed:
                counts["DISAGREED"] += 1
            elif outcome.consensus_winner is None:
                counts["TIE"] += 1
            else:
                counts[outcome.consensus_winner] += 1
        return counts

    @property
    def position_bias_rate(self) -> float | None:
        """Share of pairs where the judge picked the same slot in both orders."""

        if not self.outcomes:
            return None
        biased = sum(1 for item in self.outcomes if item.followed_position)
        return round(biased / len(self.outcomes), 4)

    @property
    def agreement_rate(self) -> float | None:
        if not self.outcomes:
            return None
        return round(sum(1 for item in self.outcomes if item.agreed) / len(self.outcomes), 4)

    def by_category(self) -> dict[str, dict[str, int]]:
        buckets: dict[str, dict[str, int]] = {}
        for outcome in self.outcomes:
            bucket = buckets.setdefault(
                outcome.category, {self.left: 0, self.right: 0, "TIE": 0, "DISAGREED": 0}
            )
            if not outcome.agreed:
                bucket["DISAGREED"] += 1
            elif outcome.consensus_winner is None:
                bucket["TIE"] += 1
            else:
                bucket[outcome.consensus_winner] += 1
        return buckets

    def by_criterion(self) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for criterion in JudgeCriterion:
            bucket = {self.left: 0, self.right: 0, "TIE_OR_DISAGREED": 0}
            for outcome in self.outcomes:
                winner = outcome.criterion_consensus(criterion)
                if winner is None:
                    bucket["TIE_OR_DISAGREED"] += 1
                else:
                    bucket[winner] += 1
            result[criterion.value] = bucket
        return result

    def to_json(self) -> dict[str, object]:
        return {
            "pair": f"{self.left} vs {self.right}",
            "judged_cases": self.judged,
            "unjudgeable": self.unjudgeable,
            "tally": self.tally(),
            "agreement_rate": self.agreement_rate,
            "position_bias_rate": self.position_bias_rate,
            "by_category": self.by_category(),
            "by_criterion": self.by_criterion(),
            "outcomes": [item.to_json() for item in self.outcomes],
        }


def compare_pair(
    model: PairwiseJudgeModel,
    *,
    case_id: str,
    category: str,
    left: str,
    right: str,
    payloads: dict[str, dict[str, Any]],
) -> PairwiseOutcome:
    """Judge one pair twice, in both orders, and keep both verdicts."""

    first = first_slot_holder(case_id, left, right)
    second = right if first == left else left

    cleaned: dict[str, dict[str, Any]] = {}
    redacted = 0
    for name in (first, second):
        body, count = redact_revealing_codes(payloads[name])
        cleaned[name] = body
        redacted += count

    user_context = payloads[first]["user_context"]
    order_one = model.compare(
        system=SYSTEM_INSTRUCTION,
        payload={
            "user_context": user_context,
            "plan_one": _plan_body(cleaned[first]),
            "plan_two": _plan_body(cleaned[second]),
        },
    )
    order_two = model.compare(
        system=SYSTEM_INSTRUCTION,
        payload={
            "user_context": user_context,
            "plan_one": _plan_body(cleaned[second]),
            "plan_two": _plan_body(cleaned[first]),
        },
    )
    return PairwiseOutcome(
        case_id=case_id,
        category=category,
        left=left,
        right=right,
        first_presented=first,
        verdict_order_one=order_one,
        verdict_order_two=order_two,
        redacted_code_count=redacted,
    )


__all__ = [
    "PAIRWISE_OUTPUT_SCHEMA_VERSION",
    "PAIRWISE_PROMPT_VERSION",
    "SYSTEM_INSTRUCTION",
    "CriterionPreference",
    "PairResult",
    "PairwiseChoice",
    "PairwiseJudgeModel",
    "PairwiseOutcome",
    "PairwiseVerdict",
    "compare_pair",
    "first_slot_holder",
    "pairwise_request_text",
    "redact_revealing_codes",
]
