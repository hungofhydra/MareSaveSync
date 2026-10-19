"""Game-info sources. To add one, give it a class whose fetch(name, sgdb_id=None) returns an info dict
(see SteamGridDBInfo) and register it in SOURCES.

An info dict: {"source", "name", "description", "release_date" (timestamp, 0 if unknown), "release_text",
"developers", "publishers", "genres", "platforms", "website", plus source ids like "sgdb_id"/"steam_appid"}.
"""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from typing import Callable

from ..providers import sgdb, steam

PLATFORM_NAMES = {"steam": "Steam", "gog": "GOG", "egs": "Epic Games Store", "origin": "EA app",
                  "uplay": "Ubisoft Connect", "bnet": "Battle.net", "flashpoint": "Flashpoint"}


def _plain(text: str) -> str:
    """Store descriptions can contain HTML; keep just the text."""
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


class SteamGridDBInfo:
    """Name, release date and platforms come from SteamGridDB. SteamGridDB has no descriptions, so the
    description, developers, publishers and genres come from the Steam store page it links the game to."""

    name = "SteamGridDB"

    def __init__(self, key: str):
        self.api = sgdb.SGDB(key)

    def fetch(self, name: str, sgdb_id: int | None = None) -> dict | None:
        if not sgdb_id:
            res = self.api.search(name)
            if not res:
                return None
            sgdb_id = res[0]["id"]
        g = self.api.game(sgdb_id)
        info = {"source": self.name, "sgdb_id": sgdb_id, "name": g.get("name") or name,
                "release_date": g.get("release_date") or 0, "release_text": "", "description": "",
                "developers": [], "publishers": [], "genres": [], "website": "",
                "platforms": [PLATFORM_NAMES.get(t, t) for t in g.get("types") or []], "fetched": time.time()}
        apps = (g.get("external_platform_data") or {}).get("steam") or []
        if apps:
            info["steam_appid"] = apps[0].get("id")
            try:
                d = steam.app_details(apps[0]["id"])
            except Exception:           # the store being down shouldn't lose what SteamGridDB gave us
                d = None
            if d:
                info.update(source="SteamGridDB + Steam store",
                            description=_plain(d.get("short_description", "")),
                            developers=d.get("developers") or [], publishers=d.get("publishers") or [],
                            genres=[x.get("description", "") for x in d.get("genres") or []],
                            website=d.get("website") or "",
                            release_text=(d.get("release_date") or {}).get("date", ""))
        return info


@dataclass(frozen=True)
class Source:
    name: str
    key_setting: str            # settings key holding this source's API key
    make: Callable[[str], object]


SOURCES: dict[str, Source] = {s.name: s for s in (
    Source("SteamGridDB", "sgdb_key", SteamGridDBInfo),
)}
DEFAULT = "SteamGridDB"
