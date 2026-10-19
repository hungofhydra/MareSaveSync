"""This PC's settings file (config.json in the data folder)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..paths import app_dir


class Settings:
    """Per-device settings (which backend, and where each game's saves live on THIS PC)."""

    def __init__(self, path=None):
        self.path = Path(path) if path else app_dir() / "config.json"
        self.data = {"backend": None, "credentials_path": "", "folder_root": "",
                     "mirror_deletes": True, "games": {}, "sgdb_key": "", "my_stats": {},
                     "device_id": "", "device_name": ""}
        if self.path.is_file():
            try:
                self.data.update(json.loads(self.path.read_text("utf-8")))
            except (OSError, ValueError):
                pass
        if not self.data.get("device_id"):
            import socket
            import uuid
            self.data["device_id"] = uuid.uuid4().hex[:16]
            self.data["device_name"] = socket.gethostname()
            self.save()

    def game(self, name: str) -> dict:
        return self.data.setdefault("games", {}).setdefault(name, {})

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), "utf-8")
        os.replace(tmp, self.path)
