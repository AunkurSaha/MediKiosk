from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .common import APIModel


class PacketMetadata(APIModel):
    packet_id: str
    session_id: str
    packet_version: str
    status: Literal["ACTIVE", "REVOKED", "EXPIRED"]
    created_at: datetime
    expires_at: datetime


class HandoffTokenIssued(PacketMetadata):
    handoff_token: str
    handoff_url: str
    handoff_token_expires_at: datetime


class HandoffResolution(APIModel):
    status: Literal["AUTH_REQUIRED"]


class PacketView(PacketMetadata):
    snapshot: dict[str, Any] = Field(default_factory=dict)
    live_queue: dict[str, Any] | None = None
