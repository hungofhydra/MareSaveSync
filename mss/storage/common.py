"""Pieces shared by the storage backends: cloud layout names, locking, playtime records."""
from __future__ import annotations

import json
import os
import stat
import threading
import time
from pathlib import Path

from ..core.util import TMP_SUFFIX

CONFIG_NAME = "savesync.json"
ART_SUB = "art"
PLAYTIME_SUB = "playtime"
ART_JSON = "art.json"
INFO_JSON = "info.json"           # game info (name, description, …) in the game's folder
LEGACY_STATS_DIR = ".mss-stats"   # older versions: one playtime file per PC for all games
LEGACY_ART_DIR = ".mss-art"       # older versions: one art folder per game, outside the game's folder


class Locked:
    """Serialises every backend call so background threads can share one connection safely."""

    def __init__(self, inner):
        self._inner = inner
        self._lock = threading.RLock()

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def call(*a, **k):
            with self._lock:
                return attr(*a, **k)
        return call


def _replace(tmp: Path, dest: Path) -> None:
    try:
        os.replace(tmp, dest)
    except PermissionError:                      # read-only target on Windows
        os.chmod(dest, stat.S_IWRITE | stat.S_IREAD)
        os.replace(tmp, dest)


def _playtime_entry(game, device_id, doc, st) -> dict:
    return {"game": game, "device_id": device_id, "device": doc.get("device", ""),
            "updated": doc.get("updated", time.time()),
            "seconds": st.get("seconds", 0), "last_played": st.get("last_played", 0)}


def _group_playtime(entries, legacy) -> list[dict]:
    """Per-game playtime entries (plus older per-PC files) -> one {"device_id", "device", "games"} doc per PC,
    which is what the app works with."""
    docs: dict[str, dict] = {}

    def add(dev, devname, game, st):
        d = docs.setdefault(dev, {"device_id": dev, "device": devname, "games": {}})
        d["device"] = d["device"] or devname
        g = d["games"].setdefault(game, {"seconds": 0, "last_played": 0})
        for k in g:
            g[k] = max(g[k], float(st.get(k) or 0))

    for doc in legacy:
        for game, st in (doc.get("games") or {}).items():
            add(doc.get("device_id"), doc.get("device", ""), game, st)
    for e in entries:
        add(e.get("device_id"), e.get("device", ""), e["game"], e)
    return list(docs.values())


def _write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + TMP_SUFFIX)
    tmp.write_text(json.dumps(data, indent=2), "utf-8")
    _replace(tmp, p)
