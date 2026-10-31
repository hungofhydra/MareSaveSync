"""One Mare Save Sync at a time. Starting it again hands the request ("show" / "fullscreen") to the copy that's
already running, which matters when a launcher such as AnyFSE starts it while it's waiting in the tray."""
from __future__ import annotations

import json
import os
import secrets
import socket
import threading

from .paths import app_dir


def _file():
    return app_dir() / "instance.json"


def send(message: str) -> bool:
    """Pass `message` to the running copy. False when there's none (then this one should start)."""
    try:
        info = json.loads(_file().read_text("utf-8"))
        with socket.create_connection(("127.0.0.1", int(info["port"])), timeout=2) as s:
            s.sendall(f"{info['token']} {message}\n".encode())
            return s.recv(8).startswith(b"ok")
    except (OSError, ValueError, KeyError, TypeError):
        return False


def serve(on_message) -> None:
    """Become the running copy: on_message(text) is called from a background thread for each later start."""
    try:
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))               # loopback only; the port is kept in the data folder
        srv.listen(4)
        token = secrets.token_hex(16)
        tmp = _file().with_suffix(".tmp")
        tmp.write_text(json.dumps({"port": srv.getsockname()[1], "token": token, "pid": os.getpid()}), "utf-8")
        os.replace(tmp, _file())
    except OSError as ex:
        print(f"Single-instance check unavailable: {ex}")
        return

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(2)
                    tok, _, msg = conn.recv(256).decode("utf-8", "replace").strip().partition(" ")
                    if secrets.compare_digest(tok, token):
                        conn.sendall(b"ok")
                        on_message(msg)
                except OSError:
                    pass
    threading.Thread(target=loop, daemon=True).start()
