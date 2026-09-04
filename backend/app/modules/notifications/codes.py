from enum import StrEnum


class NotificationTypeCode(StrEnum):
    DAILY_REWARD = "DAILY_REWARD"
    WEEKLY_GOAL_REMINDER = "WEEKLY_GOAL_REMINDER"
    KIKKI_RETURN = "KIKKI_RETURN"


class NotificationActionType(StrEnum):
    OPEN_KIKKI_HOME = "OPEN_KIKKI_HOME"


NOTIFICATION_RETENTION_DAYS = 14
MAX_RECENT_NOTIFICATIONS = 20
WEEKLY_REMINDER_FIRST_WEEKDAY = 3  # Thursday, where Monday is zero.


__all__ = [
    "MAX_RECENT_NOTIFICATIONS",
    "NOTIFICATION_RETENTION_DAYS",
    "NotificationActionType",
    "NotificationTypeCode",
    "WEEKLY_REMINDER_FIRST_WEEKDAY",
]
