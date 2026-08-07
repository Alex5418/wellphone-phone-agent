"""socket 客户端（HARNESS-SPEC §1）。

一次请求一次连接（短连接），不做会话状态管理 —— 设备侧重启、adb 重连都不需要清理。
`adb forward` 在设备重连后会失效（已知坑），所以连接失败时自动重建一次再重试。
"""

from __future__ import annotations

import json
import socket
import subprocess
import uuid
from typing import Any

from . import config
from .models import Locator


class TransportError(RuntimeError):
    def __init__(self, code: str, msg: str):
        super().__init__(f"{code}: {msg}")
        self.code = code
        self.msg = msg


def adb(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", *args], capture_output=True, text=True, check=check, timeout=20,
    )


def ensure_forward(port: int = config.ADB_FORWARD_PORT) -> None:
    adb("forward", f"tcp:{port}", f"localabstract:{config.SOCKET_NAME}")


class Transport:
    def __init__(self, port: int = config.ADB_FORWARD_PORT,
                 timeout: float = config.REQUEST_TIMEOUT_S):
        self.port = port
        self.timeout = timeout
        self.last_request: dict | None = None
        self.last_response: dict | None = None

    # ---------------------------------------------------------------- 底层

    def _send(self, payload: dict) -> dict:
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with socket.create_connection(("127.0.0.1", self.port), timeout=self.timeout) as s:
            s.settimeout(self.timeout)
            s.sendall(line.encode("utf-8"))
            chunks: list[bytes] = []
            while True:
                b = s.recv(65536)
                if not b:
                    break
                chunks.append(b)
                if b.endswith(b"\n"):
                    break
        data = b"".join(chunks).decode("utf-8", errors="replace").strip()
        if not data:
            raise TransportError("EMPTY", "device closed connection without a response")
        return json.loads(data)

    def call(self, cmd: str, **args: Any) -> dict:
        req = {"cmd": cmd, "req_id": uuid.uuid4().hex[:12], "args": args}
        self.last_request = req
        last_err: Exception | None = None
        for attempt in range(config.CONNECT_RETRY + 1):
            try:
                resp = self._send(req)
                break
            except (ConnectionError, socket.timeout, OSError) as e:
                last_err = e
                # adb forward 失效是最常见的原因，重建一次再试
                ensure_forward(self.port)
        else:
            raise TransportError("UNREACHABLE",
                                 f"cannot reach device on 127.0.0.1:{self.port} ({last_err})")
        self.last_response = resp
        if not resp.get("ok"):
            err = resp.get("error") or {}
            raise TransportError(err.get("code", "UNKNOWN"), err.get("msg", ""))
        return resp.get("data") or {}

    # ---------------------------------------------------------------- 命令

    def ping(self) -> dict:
        return self.call("ping")

    def state(self) -> dict:
        return self.call("state")

    def observe(self, display: int) -> dict:
        return self.call("observe", display=display)

    def act(self, display: int, locator: Locator | None, action: str,
            value: str | None = None, restore: bool = True,
            verify_read: bool = True) -> dict:
        # locator 可以是 None：BACK 走 performGlobalAction，没有目标节点
        return self.call(
            "act", display=display,
            locator=locator.to_json() if locator else None,
            action=action.upper(), value=value,
            restore=restore, verify_read=verify_read,
        )

    def probe(self, display: int, locator: Locator) -> dict:
        return self.call("probe", display=display, locator=locator.to_json())
