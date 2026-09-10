import asyncio
from typing import Any

from fastapi import WebSocket


class TriageNotifier:
    """Manages active WebSocket connections to the triage feed."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept(subprotocol="medikiosk")
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> int:
        async def deliver(connection: WebSocket) -> bool:
            try:
                await asyncio.wait_for(connection.send_json(message), timeout=1.0)
                return True
            except Exception:
                self.disconnect(connection)
                return False

        results = await asyncio.gather(*(deliver(c) for c in list(self.active_connections)))
        # Transport writes are not evidence that a human saw or acted on an alert.
        return sum(results)


notifier = TriageNotifier()
