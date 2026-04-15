from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.tools import tool

from phone_gateway import ConnectedDeviceSession, DeviceGateway, DeviceGatewayError


def _dump_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False)


def _require_session(gateway: DeviceGateway, device_id: str | None) -> ConnectedDeviceSession:
    if device_id:
        return gateway.get_device(device_id)
    return gateway.get_default_device()


def create_phone_tools(gateway: DeviceGateway) -> list[Any]:
    async def send(message: str, data: Any, device_id: str | None = None) -> str:
        session = _require_session(gateway, device_id)
        result = await session.send_command(message, data)
        return _dump_result(result)

    @tool("observe", description="获取当前手机页面的截图和UI树。")
    async def observe(device_id: str | None = None) -> str:
        return await send("observe", None, device_id)

    @tool("launch", description="启动指定包名的应用。package 是 Android 包名。")
    async def launch(package: str, device_id: str | None = None) -> str:
        return await send("launch", {"package": package}, device_id)

    @tool("tap", description="点击屏幕坐标。x/y 都是像素坐标。")
    async def tap(x: int, y: int, device_id: str | None = None) -> str:
        return await send("tap", {"x": x, "y": y}, device_id)

    @tool("type", description="向当前已聚焦的输入框输入文本。")
    async def type_text(text: str, device_id: str | None = None) -> str:
        return await send("type", {"text": text}, device_id)

    @tool("swipe", description="从起点坐标滑动到终点坐标。")
    async def swipe(
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        device_id: str | None = None,
    ) -> str:
        return await send(
            "swipe",
            {"startX": start_x, "startY": start_y, "endX": end_x, "endY": end_y},
            device_id,
        )

    @tool("long_press", description="长按指定坐标。")
    async def long_press(x: int, y: int, device_id: str | None = None) -> str:
        return await send("longPress", {"x": x, "y": y}, device_id)

    @tool("double_tap", description="双击指定坐标。")
    async def double_tap(x: int, y: int, device_id: str | None = None) -> str:
        return await send("doubleTap", {"x": x, "y": y}, device_id)

    @tool("back", description="执行返回操作。")
    async def back(device_id: str | None = None) -> str:
        return await send("back", None, device_id)

    @tool("home", description="回到手机桌面。")
    async def home(device_id: str | None = None) -> str:
        return await send("home", None, device_id)

    @tool("wait", description="等待若干秒，让页面加载完成。")
    async def wait(duration: float, device_id: str | None = None) -> str:
        return await send("wait", {"duration": duration}, device_id)

    @tool("interact", description="当存在多个合理候选项时，请求用户选择。")
    async def interact(message: str, device_id: str | None = None) -> str:
        return await send("interact", {"message": message}, device_id)

    @tool("take_over", description="当需要用户接管操作时调用。")
    async def take_over(message: str, device_id: str | None = None) -> str:
        return await send("takeOver", {"message": message}, device_id)

    @tool("finish", description="任务完成时调用，并给出最终结果说明。")
    async def finish(message: str, device_id: str | None = None) -> str:
        return await send("finish", {"message": message}, device_id)

    return [
        observe,
        launch,
        tap,
        type_text,
        swipe,
        long_press,
        double_tap,
        back,
        home,
        wait,
        interact,
        take_over,
        finish,
    ]

