from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.modules.identity.codes import UserStatusCode


class AccountDeletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deletion_request_id: UUID
    status_code: UserStatusCode
    operational_data_delete_by: datetime
    backup_expiry_days: int = 30


__all__ = ["AccountDeletionResponse"]
