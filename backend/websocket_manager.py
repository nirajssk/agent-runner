"""
WebSocket connection manager.

Connections are keyed by run_id so multiple browser tabs can subscribe
to the same run's live message stream simultaneously.
"""

import json
from typing import Dict, List

from fastapi import WebSocket


class WebSocketManager:
    """Tracks active WebSocket connections per run and broadcasts messages."""

    def __init__(self) -> None:
        self.connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, run_id: str, ws: WebSocket) -> None:
        """Accept the WebSocket handshake and register the connection."""
        await ws.accept()
        if run_id not in self.connections:
            self.connections[run_id] = []
        self.connections[run_id].append(ws)

    def disconnect(self, run_id: str, ws: WebSocket) -> None:
        """Remove a WebSocket from the registry (called on disconnect)."""
        if run_id in self.connections:
            self.connections[run_id] = [
                c for c in self.connections[run_id] if c is not ws
            ]
            if not self.connections[run_id]:
                del self.connections[run_id]

    async def broadcast(self, run_id: str, data: dict) -> None:
        """
        Send *data* as JSON to every active subscriber of *run_id*.

        Dead connections are silently removed so one broken client
        does not interrupt the rest.
        """
        if run_id not in self.connections:
            return

        dead: List[WebSocket] = []
        for ws in list(self.connections[run_id]):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(run_id, ws)
