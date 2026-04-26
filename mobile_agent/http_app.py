"""Custom LangGraph HTTP app routes for mobile and system tool websockets."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from .phone_gateway import DeviceGatewayError
from .runtime import phone_gateway, system_gateway
from .system_gateway import SystemGatewayError


async def adb_websocket(websocket: WebSocket) -> None:
    await phone_gateway.starlette_handler(websocket)


async def system_websocket(websocket: WebSocket) -> None:
    await system_gateway.starlette_handler(websocket)


async def adb_status(request: Request) -> JSONResponse:
    try:
        session = phone_gateway.get_session()
    except DeviceGatewayError:
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


async def system_status(request: Request) -> JSONResponse:
    try:
        client = system_gateway.get_default_client()
    except SystemGatewayError:
        return JSONResponse({"connected": False})

    return JSONResponse(
        {
            "connected": True,
            "path": client.info.path,
            "remoteAddress": str(client.info.remote_address),
        }
    )


app = Starlette(
    routes=[
        WebSocketRoute("/adb", adb_websocket),
        WebSocketRoute("/system", system_websocket),
        Route("/adb/status", adb_status, methods=["GET"]),
        Route("/system/status", system_status, methods=["GET"]),
    ]
)
