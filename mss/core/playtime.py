"""Playtime formatting and merging the per-PC numbers."""
from __future__ import annotations

import time


def fmt_play_short(sec) -> str:
    m = int((sec or 0) // 60)
    if m < 60:
        return f"{m}m"
    h = m / 60
    return (f"{h:.1f}".rstrip("0").rstrip(".") if h < 10 else str(int(h))) + "h"


def fmt_play_long(sec) -> str:
    m = int((sec or 0) // 60)
    if m < 120:
        return f"{m} minute{'s' if m != 1 else ''}"
    return f"{m // 60} h {m % 60} min"


def fmt_ago(ts) -> str:
    if not ts or ts < 1e9:
        return "never"
    d = time.time() - ts
    if d < 90:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)} minutes ago"
    if d < 7200:
        return "about 1 hour ago"
    if d < 86400:
        return f"about {int(d // 3600)} hours ago"
    if d < 172800:
        return "yesterday"
    if d < 30 * 86400:
        return f"{int(d // 86400)} days ago"
    return time.strftime("%d %b %Y", time.localtime(ts))


def aggregate_stats(files: list) -> dict:
    """Merge every device's stats file: {game: {"seconds": total, "last_played": newest}}."""
    out: dict = {}
    for f in files:
        for game, st in (f.get("games") or {}).items():
            o = out.setdefault(game, {"seconds": 0, "last_played": 0})
            o["seconds"] += float(st.get("seconds", 0))
            o["last_played"] = max(o["last_played"], float(st.get("last_played", 0)))
    return out
