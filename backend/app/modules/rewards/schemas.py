from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.modules.rewards.codes import BananaSpendActionCode, BananaTransactionType


class DailyRewardStatus(BaseModel):
    local_date: date
    reward_amount: int = Field(ge=1)
    is_claimable: bool
    is_claimed: bool
    claimed_at: datetime | None = None


class BananaWalletResponse(BaseModel):
    balance: int = Field(ge=0)
    daily_reward: DailyRewardStatus


class BananaTransactionResponse(BaseModel):
    transaction_id: str
    transaction_type: BananaTransactionType
    amount: int
    balance_after: int = Field(ge=0)
    created_at: datetime


class DailyRewardClaimResponse(BananaWalletResponse):
    transaction: BananaTransactionResponse


class BananaSpendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_code: BananaSpendActionCode
    house_item_code: str | None = Field(default=None, pattern=r"^[a-z][a-z_]{0,63}$")

    @model_validator(mode="after")
    def validate_item(self) -> "BananaSpendRequest":
        if self.action_code is BananaSpendActionCode.PURCHASE_HOUSE_ITEM:
            if self.house_item_code is None:
                raise ValueError("house_item_code is required for purchases")
        elif self.house_item_code is not None:
            raise ValueError("house_item_code is only valid for purchases")
        return self


class BananaSpendResponse(BananaWalletResponse):
    transaction: BananaTransactionResponse
