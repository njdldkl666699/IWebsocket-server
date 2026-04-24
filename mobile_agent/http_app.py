"""Custom LangGraph HTTP app routes for the mobile device websocket."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from .runtime import gateway


async def adb_websocket(websocket: WebSocket) -> None:
    await gateway.starlette_handler(websocket)


async def adb_status(request: Request) -> JSONResponse:
    try:
        session = gateway.get_session()
    except Exception:
        return JSONResponse({"connected": False})

    device_info = session.device_info
    return JSONResponse(
        {
            "connected": True,
            "width": device_info.width if device_info else None,
            "height": device_info.height if device_info else None,
            "currentPackage": device_info.current_package if device_info else None,
            "activity": device_info.activity if device_info else None,
        }
    )


app = Starlette(
    routes=[
        WebSocketRoute("/adb", adb_websocket),
        Route("/adb/status", adb_status, methods=["GET"]),
    ]
)
