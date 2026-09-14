"""One budget for every way the user can ask for a different routine today.

The regeneration limit already in place is per lineage: it counts regenerations of one
root decision and stops at two. Redoing the check-in raises `daily_context_version`,
which starts a new root, and the lineage count starts again at zero. So a user could
alternate "edit check-in, regenerate" indefinitely and never meet a limit.

This is the day-level budget the product actually promises: at most two adjustments per
day, counting a successful regeneration and a check-in revision the same. It does not
replace the lineage limit; both apply, and the stricter one is what the user meets first.

The count comes from rows that already exist -- completed regenerated runs, and the
check-in's own version number -- rather than a counter table, so the budget cannot drift
away from the evidence it is supposed to describe. Both mutation paths take the same
user/date transaction lock before reading it, preventing concurrent requests from each
spending the last slot.
"""

from __future__ import annotations

from typing import Final

DAILY_ADJUSTMENT_LIMIT: Final = 2
DAILY_ADJUSTMENT_POLICY_VERSION: Final = "daily-adjustment-policy-v1"


class DailyAdjustmentLimitReachedError(Exception):
    """The day's combined regeneration and check-in-revision budget is spent."""


__all__ = [
    "DAILY_ADJUSTMENT_LIMIT",
    "DAILY_ADJUSTMENT_POLICY_VERSION",
    "DailyAdjustmentLimitReachedError",
]
