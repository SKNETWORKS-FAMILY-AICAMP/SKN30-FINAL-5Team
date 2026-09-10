"""Allow a MINI_GAME banana transaction.

Revision ID: 0052_banana_mini_game
Revises: 0051_plan_candidate_routine_name
Create Date: 2026-09-09

The house mini-game advertises "하루 1회 플레이 가능" but paid nothing: the game
reported no score to the house, and the rewards API exposed only balance,
daily-claim and spend. `POST /api/v1/rewards/mini-game/claim` adds the earn side,
and its transactions need a type the check constraint accepts.

Only the CHECK is widened. No column, index or row changes, and every existing
transaction type keeps its meaning, so this is additive for stored data.

Rollback narrows the constraint back and **fails if any payout has been made**,
because PostgreSQL validates existing rows when the narrower constraint is added.
That is the intended behaviour: `banana_transactions` is a ledger whose
`balance_after` chain backs the wallet balance, so deleting the offending rows to
force a downgrade through would leave every affected wallet disagreeing with its
own history. The forward fix is to re-apply this migration rather than to prune
the ledger; a genuine rollback needs the payouts reversed as compensating
transactions first, which is a product decision and not a schema one.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0052_banana_mini_game"
down_revision: str | None = "0051_plan_candidate_routine_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "banana_transactions"
_CONSTRAINT = "ck_banana_transactions_type"

_WITHOUT_MINI_GAME = (
    "transaction_type IN ('DAILY_REWARD','WORKOUT_COMPLETED','WORKOUT_PARTIAL',"
    "'WORKOUT_SAFETY_STOPPED','WORKOUT_DAILY_QUEST','HOUSE_FEED','HOUSE_ITEM_PURCHASE')"
)
_WITH_MINI_GAME = (
    "transaction_type IN ('DAILY_REWARD','WORKOUT_COMPLETED','WORKOUT_PARTIAL',"
    "'WORKOUT_SAFETY_STOPPED','WORKOUT_DAILY_QUEST','HOUSE_FEED','HOUSE_ITEM_PURCHASE',"
    "'MINI_GAME')"
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _WITH_MINI_GAME)


def downgrade() -> None:
    # Deliberately no DELETE: see the module docstring. This raises rather than
    # silently unbalancing a wallet against its own transaction history.
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _WITHOUT_MINI_GAME)
