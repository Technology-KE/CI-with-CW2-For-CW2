"""CI × CW2 联动 —— CW2 端的 TCP 服务。

协议：一行一个 JSON（UTF-8，换行分隔）。
- 连接建立后先握手：{"type":"hello","app":"cw2","token":...}
- 之后双方随时发送 {"type":"state"|"cmd"|"ack"|"ping"|"pong", ...}
- 只绑定 127.0.0.1，并用共享设置里的 token 校验，避免被本机其它程序误连。
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from typing import Callable

from loguru import logger

from ciwc_common import APP_CW2

MAX_MESSAGE_BYTES = 4 * 1024 * 1024


class LinkBridge:
    """CW2 端的监听服务；同一时刻只保留一条有效连接。"""

    def __init__(
        self,
        on_message: Callable[[dict], None],
        on_status: Callable[[], None] | None = None,
        app_version: str = "",
    ) -> None:
        self._on_message = on_message
        self._on_status = on_status or (lambda: None)
        self._app_version = app_version

        self._lock = threading.RLock()
        self._running = False
        self._port = 0
        self._token = ""
        self._server: socket.socket | None = None
        self._conn: socket.socket | None = None
        self._peer: str | None = None
        self._peer_version = ""
        self._peer_exe = ""
        self._last_rx = 0.0
        self._threads: list[threading.Thread] = []
        self._generation = 0

    # ------------------------------ 生命周期 ------------------------------
    def start(self, port: int, token: str) -> None:
        with self._lock:
            if self._running:
                if port == self._port and token == self._token:
                    return
                self._shutdown_locked()
            self._running = True
            self._port = port
            self._token = token
            self._server = None
            self._generation += 1
            generation = self._generation
        server_thread = threading.Thread(
            target=self._server_loop, args=(generation,), name="ciwc-server", daemon=True
        )
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, args=(generation,), name="ciwc-heartbeat", daemon=True
        )
        self._threads = [server_thread, heartbeat_thread]
        server_thread.start()
        heartbeat_thread.start()
        logger.info("联动服务已启动：127.0.0.1:{}", port)

    def stop(self) -> None:
        with self._lock:
            self._shutdown_locked()

    def _shutdown_locked(self) -> None:
        self._running = False
        self._generation += 1
        server = self._server
        self._server = None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        self._close_conn_locked(notify=False)
        self._port = 0
        self._token = ""

    # ------------------------------ 状态 ------------------------------
    def status(self) -> dict:
        with self._lock:
            connected = self._conn is not None
            return {
                "connected": connected,
                "peer": self._peer if connected else None,
                "peer_version": self._peer_version if connected else "",
                "peer_exe": self._peer_exe if connected else "",
                "last_rx_ms": int(self._last_rx * 1000) if self._last_rx else 0,
                "port": self._port,
            }

    # ------------------------------ 发送 ------------------------------
    def send(self, payload: dict) -> bool:
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        with self._lock:
            conn = self._conn
            if conn is None:
                return False
            try:
                conn.sendall(data)
                return True
            except OSError:
                self._close_conn_locked()
                return False

    # ------------------------------ 服务线程 ------------------------------
    def _server_loop(self, generation: int) -> None:
        while True:
            with self._lock:
                if not self._running or generation != self._generation:
                    return
                port, token = self._port, self._token

            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind(("127.0.0.1", port))
                server.listen(4)
                server.settimeout(0.5)
            except OSError as error:
                try:
                    server.close()
                except OSError:
                    pass
                logger.warning("联动端口 {} 暂不可用（{}），1 秒后重试", port, error)
                time.sleep(1.0)
                continue

            with self._lock:
                if not self._running or port != self._port:
                    try:
                        server.close()
                    except OSError:
                        pass
                    continue
                self._server = server

            while True:
                with self._lock:
                    if not self._running or generation != self._generation or port != self._port:
                        break
                try:
                    conn, address = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                hello = self._handshake(conn, token)
                if hello is None:
                    continue
                with self._lock:
                    if not self._running or generation != self._generation or port != self._port:
                        try:
                            conn.close()
                        except OSError:
                            pass
                        break
                    self._close_conn_locked(notify=False)
                    self._conn = conn
                    self._peer = hello.get("app")
                    self._peer_version = hello.get("version", "")
                    self._peer_exe = str(hello.get("exe") or "")
                    self._last_rx = time.time()
                logger.info("已连接对端：{}（{}）", self._peer, address[0])
                self._on_status()
                threading.Thread(
                    target=self._reader_loop,
                    args=(conn,),
                    name="ciwc-reader",
                    daemon=True,
                ).start()

            try:
                server.close()
            except OSError:
                pass
            with self._lock:
                if self._server is server:
                    self._server = None

    def _handshake(self, conn: socket.socket, token: str) -> dict | None:
        conn.settimeout(3.0)
        buffer = b""
        try:
            while b"\n" not in buffer and len(buffer) <= MAX_MESSAGE_BYTES:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buffer += chunk
            line = buffer.split(b"\n", 1)[0]
            hello = json.loads(line.decode("utf-8"))
        except Exception:
            try:
                conn.close()
            except OSError:
                pass
            return None

        if not isinstance(hello, dict) or hello.get("type") != "hello":
            conn.close()
            return None
        if str(hello.get("token", "")) != token:
            logger.warning("拒绝联动连接：token 不匹配")
            conn.close()
            return None
        peer = str(hello.get("app", "")).strip()
        if peer == APP_CW2 or not peer:
            conn.close()
            return None

        reply = {
            "type": "hello",
            "app": APP_CW2,
            "version": self._app_version,
            "exe": os.path.abspath(sys.executable),
            "pid": os.getpid(),
            "ts": int(time.time() * 1000),
        }
        try:
            conn.sendall((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError:
            conn.close()
            return None
        conn.settimeout(1.0)
        return hello

    def _reader_loop(self, conn: socket.socket) -> None:
        buffer = b""
        try:
            while True:
                with self._lock:
                    if not self._running or self._conn is not conn:
                        return
                try:
                    chunk = conn.recv(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > MAX_MESSAGE_BYTES:
                    logger.warning("联动消息过大，断开连接")
                    break
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        message = json.loads(line.decode("utf-8"))
                    except Exception:
                        logger.warning("忽略无法解析的联动消息")
                        continue
                    if not isinstance(message, dict):
                        continue
                    with self._lock:
                        self._last_rx = time.time()
                    if message.get("type") == "ping":
                        self.send({"type": "pong", "ts": int(time.time() * 1000)})
                        continue
                    if message.get("type") == "pong":
                        continue
                    try:
                        self._on_message(message)
                    except Exception:
                        logger.exception("处理联动消息失败")
        finally:
            with self._lock:
                if self._conn is conn:
                    self._close_conn_locked()
            try:
                conn.close()
            except OSError:
                pass
            self._on_status()

    def _heartbeat_loop(self, generation: int) -> None:
        while True:
            time.sleep(1.0)
            with self._lock:
                if not self._running or generation != self._generation:
                    return
                conn = self._conn
                last_rx = self._last_rx
            now = time.time()
            if conn is not None and last_rx and now - last_rx > 12.0:
                logger.warning("联动连接超时，主动断开")
                with self._lock:
                    if self._conn is conn:
                        self._close_conn_locked()
                try:
                    conn.close()
                except OSError:
                    pass
                self._on_status()
            elif conn is not None and now - last_rx > 4.0:
                self.send({"type": "ping", "ts": int(now * 1000)})

    # ------------------------------ 连接清理 ------------------------------
    def _close_conn_locked(self, notify: bool = True) -> None:
        conn = self._conn
        self._conn = None
        self._peer = None
        self._peer_version = ""
        self._peer_exe = ""
        self._last_rx = 0.0
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass
        if notify:
            self._on_status()
