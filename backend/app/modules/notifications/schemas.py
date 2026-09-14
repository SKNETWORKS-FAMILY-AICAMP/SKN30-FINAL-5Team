from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    notification_id: UUID
    type: Literal["DAILY_REWARD", "WEEKLY_GOAL_REMINDER", "KIKKI_RETURN"]
    title: str
    message: str
    created_at: datetime
    read_at: datetime | None
    is_read: bool
    action_type: str | None
    payload: dict[str, Any] = Field(default_factory=dict)


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    unread_count: int = Field(ge=0)


__all__ = ["NotificationListResponse", "NotificationResponse"]
