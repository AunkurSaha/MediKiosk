"""Single-use, short-lived WebSocket admission for the existing local demo identity.

Tickets travel in a WebSocket subprotocol, never in URLs/access logs. This is
process-local admission, not production authentication or a multi-worker service.
"""

import secrets
import time

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app import models
from app.core.config import CORS_ORIGINS, demo_enabled

_tickets: dict[str, tuple[str, float]] = {}


def issue_ticket(user_id: str) -> str:
    now = time.monotonic()
    for key, (_, expiry) in list(_tickets.items()):
        if expiry <= now:
            _tickets.pop(key, None)
    if len(_tickets) >= 1000:
        _tickets.pop(next(iter(_tickets)))
    token = secrets.token_urlsafe(32)
    _tickets[token] = (user_id, now + 30)
    return token


async def admit_websocket(websocket: WebSocket, db: Session) -> bool:
    protocols = websocket.scope.get("subprotocols", [])
    entry = (
        _tickets.pop(protocols[1], None)
        if len(protocols) == 2 and protocols[0] == "medikiosk"
        else None
    )
    origin = websocket.headers.get("origin")
    if (
        not demo_enabled()
        or origin not in CORS_ORIGINS
        or not entry
        or entry[1] <= time.monotonic()
    ):
        await websocket.close(code=1008)
        return False
    user = db.get(models.User, entry[0])
    if user is None or not user.is_active or user.role not in ("triage", "doctor"):
        await websocket.close(code=1008)
        return False
    db.close()  # Do not hold a transaction/connection for the socket lifetime.
    return True
