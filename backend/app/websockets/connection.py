"""
WebSocket connection manager for handling real-time call sessions.
"""

from fastapi import WebSocket
from app.models import CallMetadata


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts."""

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str) -> None:
        """Remove a connection from the active pool."""
        self.active_connections.pop(session_id, None)

    async def send_metadata(self, session_id: str, metadata: CallMetadata) -> None:
        """Send call metadata to a specific session."""
        websocket = self.active_connections.get(session_id)
        if websocket:
            await websocket.send_json(metadata.model_dump())

    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all active connections."""
        for ws in self.active_connections.values():
            await ws.send_json(message)


manager = ConnectionManager()
