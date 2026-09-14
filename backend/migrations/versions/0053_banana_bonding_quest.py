"""Allow a HOUSE_BONDING_QUEST banana transaction.

Revision ID: 0053_banana_bonding_quest
Revises: 0052_banana_mini_game
Create Date: 2026-09-10

The house shows three daily quests, but only two of them had a server payout:
접속하기 is the daily reward and 운동 완료하기 is WORKOUT_DAILY_QUEST, while
끼끼와 교감하기 paid only into the house's own stored number. Every house write
overwrites that number with the wallet balance, so the quest silently paid
nothing. `POST /api/v1/rewards/bonding-quest/claim` gives it a real payout, and
its transactions need a type the check constraint accepts.

Only the CHECK is widened -- no column, index or row changes, and every existing
transaction type keeps its meaning.

Rollback narrows it back and **fails if the quest has ever paid**, for the same
reason as 0052: `banana_transactions` is a ledger whose `balance_after` chain
backs the wallet, so deleting rows to force a downgrade through would leave
wallets disagreeing with their own history. The forward fix is to re-apply this
migration; a genuine rollback needs the payouts reversed as compensating
transactions first, which is a product decision rather than a schema one.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0053_banana_bonding_quest"
down_revision: str | None = "0052_banana_mini_game"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "banana_transactions"
_CONSTRAINT = "ck_banana_transactions_type"

_BASE = (
    "transaction_type IN ('DAILY_REWARD','WORKOUT_COMPLETED','WORKOUT_PARTIAL',"
    "'WORKOUT_SAFETY_STOPPED','WORKOUT_DAILY_QUEST','HOUSE_FEED','HOUSE_ITEM_PURCHASE',"
    "'MINI_GAME'"
)
_WITHOUT_BONDING = f"{_BASE})"
_WITH_BONDING = f"{_BASE},'HOUSE_BONDING_QUEST')"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _WITH_BONDING)


def downgrade() -> None:
    # Deliberately no DELETE: see the module docstring. This raises rather than
    # silently unbalancing a wallet against its own transaction history.
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _WITHOUT_BONDING)
