"""Turning an info dict into display lines (shared by the About tab and the picker's preview)."""
from __future__ import annotations

import time


def found(info: dict | None) -> bool:
    return bool(info) and not info.get("none")


def summary(info: dict) -> tuple[str, str]:
    """("Released … · Developer: …", "Genres: … · On: …") for an info dict ("" parts are left out)."""
    meta, tags = [], []
    rel = info.get("release_text") or (time.strftime("%d %b %Y", time.gmtime(info["release_date"]))
                                       if info.get("release_date") else "")
    if rel:
        meta.append(f"Released {rel}")
    if info.get("developers"):
        meta.append("Developer: " + ", ".join(info["developers"]))
    if info.get("publishers") and info["publishers"] != info.get("developers"):
        meta.append("Publisher: " + ", ".join(info["publishers"]))
    if info.get("genres"):
        tags.append("Genres: " + ", ".join(info["genres"]))
    if info.get("platforms"):
        tags.append("On: " + ", ".join(info["platforms"]))
    return "   ·   ".join(meta), "   ·   ".join(tags)
