from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field
from starlette.websockets import WebSocket
from websockets.asyncio.server import ServerConnection
from websockets.exceptions import ConnectionClosed

from .websocket_adapter import StarletteWebSocketConnection

VERBOSE_HEARTBEAT = os.getenv("VERBOSE_HEARTBEAT", "").lower() in {"1", "true", "yes"}


class DeviceGatewayError(RuntimeError):
    pass


class ProtocolViolation(DeviceGatewayError):
    pass


class MessageEnvelope(BaseModel):
    type: Literal["request", "response"]
    message: str
    data: Any = None
    requestId: int | None = Field(default=None, ge=1)


class ConnectData(BaseModel):
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    screenshot: str | None = None
    ui: str | None = None
    currentPackage: str | None = None
    activity: str | None = None
    token: str | None = None


class ErrorData(BaseModel):
    message: str
    screenshot: str | None = None
    ui: str | None = None
    currentPackage: str | None = None
    activity: str | None = None


@dataclass
class DeviceInfo:
    width: int
    height: int
    screenshot: str | None
    ui: str | None
    current_package: str | None
    activity: str | None
    token: str | None = None


class ConnectedDeviceSession:
    def __init__(self, websocket: ServerConnection | StarletteWebSocketConnection) -> None:
        self.websocket = websocket
        self.device_info: DeviceInfo | None = None
        self.ready = asyncio.Event()
        self.closed = asyncio.Event()
        self._request_id_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._pending_responses: dict[int, asyncio.Future[MessageEnvelope]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._next_request_id: int | None = None

    async def start(self) -> None:
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def stop(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

    async def wait_ready(self, timeout: float = 10.0) -> None:
        await asyncio.wait_for(self.ready.wait(), timeout=timeout)

    async def send_command(self, message: str, data: Any, timeout: float = 20.0) -> dict[str, Any]:
        if self.closed.is_set():
            raise DeviceGatewayError("Device is disconnected.")
        if not self.ready.is_set():
            raise DeviceGatewayError("Device has not completed connect.")

        loop = asyncio.get_running_loop()
        async with self._request_id_lock:
            request_id = self._consume_next_request_id()
            pending_response = loop.create_future()
            self._pending_responses[request_id] = pending_response
            payload = MessageEnvelope(
                type="request",
                message=message,
                data=data,
                requestId=request_id,
            )
        logger.info(
            f"-> requestId={request_id} message={payload.message} "
            f"data={_sanitize_log_payload(payload.data)}"
        )
        async with self._send_lock:
            await self.websocket.send(payload.model_dump_json(exclude_none=True) + "\n")
        try:
            response = await asyncio.wait_for(pending_response, timeout=timeout)
        finally:
            self._pending_responses.pop(request_id, None)

        logger.info(
            f"<- requestId={response.requestId} message={response.message} "
            f"data={_sanitize_log_payload(response.data)}"
        )
        if response.requestId != request_id:
            raise DeviceGatewayError(
                f"Expected response requestId {request_id}, got {response.requestId}."
            )

        if response.message == "error":
            error = ErrorData.model_validate(response.data)
            self._update_device_info(
                screenshot=error.screenshot,
                ui=error.ui,
                current_package=error.currentPackage,
                activity=error.activity,
            )
            raise DeviceGatewayError(error.message)

        if response.message != "actionResult":
            raise DeviceGatewayError(f"Expected 'actionResult', got {response.message!r}.")

        action_result = (
            response.data if isinstance(response.data, dict) else {"value": response.data}
        )
        self._update_device_info_from_payload(action_result)
        return action_result

    async def _reader_loop(self) -> None:
        try:
            async for raw in self.websocket:
                try:
                    envelope = self._parse(raw)
                    if envelope.type == "request":
                        await self._handle_client_request(envelope)
                    else:
                        self._handle_client_response(envelope)
                except ProtocolViolation as exc:
                    logger.warning(f"protocol violation: {exc}")
                    await self.websocket.close(code=1008, reason=str(exc))
                    break
        except ConnectionClosed:
            pass
        finally:
            self.closed.set()
            for future in list(self._pending_responses.values()):
                if not future.done():
                    future.set_exception(DeviceGatewayError("Device disconnected."))
            self._pending_responses.clear()

    async def _handle_client_request(self, envelope: MessageEnvelope) -> None:
        if not self.ready.is_set():
            if envelope.message != "connect":
                raise ProtocolViolation("The first client request must be 'connect'.")
            await self._handle_connect(envelope)
            return

        if envelope.message == "connect":
            raise ProtocolViolation("Duplicate 'connect' is not allowed on one websocket session.")

        if envelope.message == "ping":
            if envelope.requestId is not None:
                raise ProtocolViolation("'ping' must not carry requestId.")
            if VERBOSE_HEARTBEAT:
                logger.debug("<- heartbeat")
            response = MessageEnvelope(type="response", message="pong", data=None)
            await self.websocket.send(response.model_dump_json(exclude_none=True) + "\n")
            return

        response = MessageEnvelope(
            type="response",
            message="error",
            data=ErrorData(message=f"Unsupported client request: {envelope.message}").model_dump(),
            requestId=envelope.requestId,
        )
        await self.websocket.send(response.model_dump_json(exclude_none=True) + "\n")

    async def _handle_connect(self, envelope: MessageEnvelope) -> None:
        if envelope.requestId != 1:
            raise ProtocolViolation("'connect' must carry fixed requestId=1.")
        connect_data = ConnectData.model_validate(envelope.data)
        self.device_info = DeviceInfo(
            width=connect_data.width,
            height=connect_data.height,
            screenshot=connect_data.screenshot,
            ui=connect_data.ui,
            current_package=connect_data.currentPackage,
            activity=connect_data.activity,
            token=connect_data.token,
        )
        self._next_request_id = 2
        self.ready.set()
        logger.info(
            f"device connected: size={connect_data.width}x{connect_data.height} "
            f"requestIdStart={self._next_request_id}"
        )

    def _handle_client_response(self, envelope: MessageEnvelope) -> None:
        if not self.ready.is_set():
            raise ProtocolViolation("Received response before 'connect' completed.")
        if envelope.message == "pong":
            raise ProtocolViolation("Client must not send 'pong'.")
        if envelope.requestId is None:
            raise ProtocolViolation("Business response must carry requestId.")
        pending_response = self._pending_responses.get(envelope.requestId)
        if pending_response is None or pending_response.done():
            raise ProtocolViolation(
                f"Received unexpected response {envelope.message!r} with requestId={envelope.requestId}."
            )
        pending_response.set_result(envelope)

    def _consume_next_request_id(self) -> int:
        if self._next_request_id is None:
            raise DeviceGatewayError("Device has not initialized the requestId sequence.")
        current = self._next_request_id
        self._next_request_id += 1
        return current

    def _update_device_info(
        self,
        screenshot: str | None,
        ui: str | None,
        current_package: str | None,
        activity: str | None,
    ) -> None:
        if self.device_info is None:
            return
        if screenshot is not None:
            self.device_info.screenshot = screenshot
        if ui is not None:
            self.device_info.ui = ui
        if current_package is not None:
            self.device_info.current_package = current_package
        if activity is not None:
            self.device_info.activity = activity

    def _update_device_info_from_payload(self, payload: dict[str, Any]) -> None:
        self._update_device_info(
            screenshot=payload.get("screenshot"),
            ui=payload.get("ui"),
            current_package=payload.get("currentPackage"),
            activity=payload.get("activity"),
        )

    @staticmethod
    def _parse(raw: str | bytes) -> MessageEnvelope:
        line = raw if isinstance(raw, str) else bytes(raw).decode("utf-8")
        line = line.strip()
        if not line:
            raise ProtocolViolation("Received empty JSONL message.")
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProtocolViolation(f"Invalid JSON message: {exc}") from exc
        try:
            return MessageEnvelope.model_validate(payload)
        except Exception as exc:  # pydantic validation errors
            raise ProtocolViolation(f"Invalid envelope: {exc}") from exc


class DeviceGateway:
    def __init__(self, path_prefix: str = "/adb") -> None:
        self.path_prefix = path_prefix.rstrip("/")
        self._session: ConnectedDeviceSession | None = None
        self._lock = asyncio.Lock()

    def get_session(self) -> ConnectedDeviceSession:
        session = self._session
        if session is not None and not session.closed.is_set():
            return session
        raise DeviceGatewayError("No connected device is available.")

    async def handler(self, websocket: ServerConnection | StarletteWebSocketConnection) -> None:
        request = websocket.request
        if request is None:
            raise DeviceGatewayError("Missing websocket request metadata.")
        self._validate_path(request.path)
        session = ConnectedDeviceSession(websocket)

        async with self._lock:
            if self._session is not None and not self._session.closed.is_set():
                raise DeviceGatewayError("Only one device connection is supported.")

        await session.start()
        await session.wait_ready()
        async with self._lock:
            self._session = session
        try:
            await session.closed.wait()
        finally:
            async with self._lock:
                if self._session is session:
                    self._session = None
            await session.stop()

    def _validate_path(self, path: str) -> None:
        normalized_path = path.split("?", 1)[0]
        if normalized_path == self.path_prefix:
            return

        raise DeviceGatewayError(f"Invalid device path {path!r}. Expected {self.path_prefix!r}.")

    async def starlette_handler(self, websocket: WebSocket) -> None:
        await websocket.accept()
        await self.handler(StarletteWebSocketConnection(websocket))


def _sanitize_log_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"screenshot", "ui"}:
                sanitized[key] = "<omitted>"
            else:
                sanitized[key] = _sanitize_log_payload(value)
        return sanitized

    if isinstance(payload, list):
        return [_sanitize_log_payload(item) for item in payload]

    return payload
