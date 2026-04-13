import argparse
import asyncio
import re
from contextlib import suppress

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

clients: set[ServerConnection] = set()
PATH_PATTERN = re.compile(r"^/ws/devices/(?P<device_id>[^/]+)$")


async def broadcast(message: str) -> None:
    if not clients:
        print("[系统] 当前没有已连接客户端")
        return

    disconnected = []
    for ws in clients:
        try:
            print("[广播] 发送消息给客户端:", message)
            # 一定要加上换行符，否则客户端无法正确接收消息
            await ws.send(message + "\n", text=True)
        except ConnectionClosed:
            disconnected.append(ws)

    for ws in disconnected:
        clients.discard(ws)


async def handle_client(websocket: ServerConnection) -> None:
    request = websocket.request
    if request is None:
        print("[拒绝] 无法获取连接请求信息")
        await websocket.close(code=1008, reason="invalid request")
        return

    path = request.path
    match = PATH_PATTERN.match(path)
    if not match:
        print(f"[拒绝] 非法连接路径: {path!r}")
        await websocket.close(code=1008, reason="invalid path")
        return

    device_id = match.group("device_id")
    clients.add(websocket)
    peer = websocket.remote_address
    print(f"[连接] 设备 {device_id} 已连接: {peer}")

    try:
        async for message in websocket:
            print(f"[客户端 {device_id}@{peer}] {message}")
            # await broadcast(f"[来自设备 {device_id}] {message}")
    except ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        print(f"[断开] 设备 {device_id} 已断开: {peer}")


async def console_input_loop(stop_event: asyncio.Event) -> None:
    print("[系统] 输入消息并回车可广播给所有客户端")
    print("[系统] 输入 /quit 关闭服务")

    while not stop_event.is_set():
        text = await asyncio.to_thread(input, "server> ")
        text = text.strip()

        if not text:
            continue
        if text == "/quit":
            stop_event.set()
            break

        await broadcast(text)


async def run_server(host: str, port: int) -> None:
    stop_event = asyncio.Event()

    async with serve(handle_client, host, port):
        print(f"[系统] WebSocket 服务已启动 ws://{host}:{port}/ws/device/{{deviceId}}")
        input_task = asyncio.create_task(console_input_loop(stop_event))

        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            print("\n[系统] 收到 Ctrl+C，正在关闭服务...")
        finally:
            input_task.cancel()
            with suppress(asyncio.CancelledError):
                await input_task


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="交互型 WebSocket 服务端")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        print("\n[系统] 服务已退出")


if __name__ == "__main__":
    main()
