"""Real-time event bus: pushes agent traces, alerts and resource updates to WebSocket clients."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("medorchestra.events")


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, dict] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket, user: dict) -> None:
        await ws.accept()
        self._clients[ws] = user

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.pop(ws, None)

    @property
    def count(self) -> int:
        return len(self._clients)

    async def broadcast(self, event_type: str, data: Any, roles: list[str] | None = None) -> None:
        message = json.dumps(
            {"type": event_type, "data": data, "ts": datetime.now().isoformat()}, default=str
        )
        dead = []
        for ws, user in list(self._clients.items()):
            if roles and user.get("role") not in roles and user.get("role") != "admin":
                continue
            try:
                await ws.send_text(message)
            except Exception:  # client went away
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def publish(self, event_type: str, data: Any, roles: list[str] | None = None) -> None:
        """Fire-and-forget broadcast usable from sync code and worker threads."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        coro = self.broadcast(event_type, data, roles)
        if running is loop:
            loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, loop)


bus = ConnectionManager()
