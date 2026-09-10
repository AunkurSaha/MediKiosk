from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditTrailItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime
    actor_type: str
    actor_user_id: str | None
    action: str
    entity_type: str
    entity_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditTrailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    total: int
    items: list[AuditTrailItem] = Field(default_factory=list)
