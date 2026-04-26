from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect


class StarletteWebSocketConnection:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.request = SimpleNamespace(path=websocket.url.path)
        self.remote_address = websocket.client

    async def send(self, message: str, *args: Any, **kwargs: Any) -> None:
        await self.websocket.send_text(message)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        await self.websocket.close(code=code, reason=reason)

    def __aiter__(self) -> StarletteWebSocketConnection:
        return self

    async def __anext__(self) -> str:
        try:
            return await self.websocket.receive_text()
        except WebSocketDisconnect:
            raise StopAsyncIteration from None
