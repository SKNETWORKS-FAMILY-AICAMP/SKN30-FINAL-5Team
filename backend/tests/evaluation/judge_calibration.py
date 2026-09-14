"""How much weight the judge can carry, checked without new human labels.

PHASE 10 calibrated the judge against 24 human-scored outputs and found the
overall means almost equal while the per-case agreement was poor: Pearson
-0.0890, and a per-architecture bias that cancelled in the total (Multi-Agent
scored +0.33 above the humans, Single LLM -0.40 below). That calibration was
taken on the tuning set with unblinded payloads, so it cannot simply be
subtracted from the held-out numbers, which are blind and drawn from a
different catalog.

What can be checked for free is whether the held-out judge scores behave the
way a usable measure would:

* **Discrimination.** Roughly a third of held-out runs fell back to the
  deterministic template composer. A template is not a model's plan, the judge
  was blind to which it was reading, and it should prefer the model's. If it
  cannot separate those, it cannot separate architectures either.
* **Groundedness in an objective fact.** FEASIBILITY should track how close the
  plan lands to the requested duration, which the compiler measures exactly.
* **Paired preference.** Comparing architecture means across cases confounds
  the architecture with case difficulty. The same 29 cases were run through
  every architecture, so the comparison can be made within case.

None of these establish agreement with human judgement. They bound how much a
judge-score difference is worth on its own.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

# Below this many paired cases a sign test says nothing worth reporting.
MINIMUM_PAIRS: Final = 8


@dataclass(frozen=True, slots=True)
class GroupScores:
    """Judge means for two groups of runs, and the gap between them."""

    label_a: str
    label_b: str
    mean_a: float | None
    mean_b: float | None
    count_a: int
    count_b: int

    @property
    def difference(self) -> float | None:
        if self.mean_a is None or self.mean_b is None:
            return None
        return round(self.mean_a - self.mean_b, 4)

    def to_json(self) -> dict[str, object]:
        return {
            "label_a": self.label_a,
            "label_b": self.label_b,
            "mean_a": self.mean_a,
            "mean_b": self.mean_b,
            "count_a": self.count_a,
            "count_b": self.count_b,
            "difference": self.difference,
        }


@dataclass(frozen=True, slots=True)
class PairedPreference:
    """A sign test over cases judged under both architectures."""

    wins_a: int
    wins_b: int
    ties: int
    mean_difference: float | None

    @property
    def decided(self) -> int:
        return self.wins_a + self.wins_b

    @property
    def p_value(self) -> float | None:
        """Two-sided exact binomial, ties dropped. None when too few pairs.

        Reported so a 15-13 split is not read as a preference. There is no
        scipy here, and an exact binomial over tens of cases needs none.
        """

        if self.decided < MINIMUM_PAIRS:
            return None
        n, k = self.decided, min(self.wins_a, self.wins_b)
        tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
        return round(min(1.0, 2 * tail), 4)

    def to_json(self) -> dict[str, object]:
        return {
            "wins_a": self.wins_a,
            "wins_b": self.wins_b,
            "ties": self.ties,
            "decided": self.decided,
            "mean_difference": self.mean_difference,
            "p_value": self.p_value,
            "note": (
                "Two-sided exact binomial sign test over cases judged under both "
                f"architectures; ties dropped, None below {MINIMUM_PAIRS} decided pairs."
            ),
        }


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def compare_groups(
    *,
    label_a: str,
    values_a: Sequence[float],
    label_b: str,
    values_b: Sequence[float],
) -> GroupScores:
    return GroupScores(
        label_a=label_a,
        label_b=label_b,
        mean_a=_mean(values_a),
        mean_b=_mean(values_b),
        count_a=len(values_a),
        count_b=len(values_b),
    )


def paired_preference(
    scores_a: Mapping[str, float], scores_b: Mapping[str, float]
) -> PairedPreference:
    """Compare two architectures case by case, not mean against mean."""

    shared = sorted(set(scores_a) & set(scores_b))
    wins_a = sum(1 for case in shared if scores_a[case] > scores_b[case])
    wins_b = sum(1 for case in shared if scores_a[case] < scores_b[case])
    differences = [scores_a[case] - scores_b[case] for case in shared]
    return PairedPreference(
        wins_a=wins_a,
        wins_b=wins_b,
        ties=len(shared) - wins_a - wins_b,
        mean_difference=_mean(differences),
    )


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    """Correlation, or None when one side has no spread to correlate with."""

    if len(left) != len(right) or len(left) < 2:
        return None
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    covariance = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right, strict=True))
    spread_left = math.sqrt(sum((a - mean_left) ** 2 for a in left))
    spread_right = math.sqrt(sum((b - mean_right) ** 2 for b in right))
    if spread_left == 0 or spread_right == 0:
        return None
    return round(covariance / (spread_left * spread_right), 4)


__all__ = [
    "MINIMUM_PAIRS",
    "GroupScores",
    "PairedPreference",
    "compare_groups",
    "paired_preference",
    "pearson",
]
