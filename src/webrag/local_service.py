"""Lifecycle of the desktop-owned loopback HTTP server."""
from __future__ import annotations

import socket
import threading
import time


class LocalService:
    def __init__(self, config_provider, port=8077):
        self.config_provider = config_provider
        self.port = port
        self.server = None
        self.thread = None
        self.socket = None

    def start(self):
        if self.thread and self.thread.is_alive() and self.server.started:
            return f"http://127.0.0.1:{self.port}"
        import uvicorn
        from .server import create_app
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(("127.0.0.1", self.port))
            sock.listen(128)
        except OSError as exc:
            sock.close()
            raise RuntimeError(f"A porta {self.port} está ocupada ou indisponível. Feche o serviço que a utiliza e tente novamente.") from exc
        self.socket = sock
        self.port = sock.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(
            create_app(self.config_provider(), config_provider=self.config_provider),
            host="127.0.0.1", port=self.port, log_config=None, access_log=False,
            timeout_graceful_shutdown=3))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                self.stop()
                raise RuntimeError("O servidor de busca não iniciou. Consulte o log do aplicativo.")
            time.sleep(0.05)
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=5)
        if self.socket:
            self.socket.close()
        self.server = self.thread = self.socket = None
