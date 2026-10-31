"""Game-info sources. To add one, give it a class whose fetch(name, sgdb_id=None) returns an info dict
(see SteamGridDBInfo) and register it in SOURCES.

An info dict: {"source", "name", "description", "release_date" (timestamp, 0 if unknown), "release_text",
"developers", "publishers", "genres", "platforms", "website", plus source ids like "sgdb_id"/"steam_appid",
and "v": the INFO_VERSION it was made with}.
"""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from typing import Callable

from ..providers import sgdb, steam, wikipedia

# Info stored with an older version is looked up again once (2: descriptions from Wikipedia when no store has one).
INFO_VERSION = 2

PLATFORM_NAMES = {"steam": "Steam", "gog": "GOG", "egs": "Epic Games Store", "origin": "EA app",
                  "uplay": "Ubisoft Connect", "bnet": "Battle.net", "flashpoint": "Flashpoint"}


def _plain(text: str) -> str:
    """Store descriptions can contain HTML; keep just the text."""
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _wikipedia(*names) -> dict | None:
    for n in dict.fromkeys(x for x in names if x):        # each different name once, in order
        try:
            w = wikipedia.game_summary(n)
        except Exception:               # Wikipedia being unreachable shouldn't lose the rest
            w = None
        if w:
            return w
    return None


class SteamGridDBInfo:
    """Name, release date and platforms come from SteamGridDB. SteamGridDB has no descriptions, so the
    description, developers, publishers and genres come from the Steam store page it links the game to.
    Games with no Steam page (Epic exclusives, console games, …) get their description from Wikipedia."""

    name = "SteamGridDB"

    def __init__(self, key: str):
        self.api = sgdb.SGDB(key)

    def fetch(self, name: str, sgdb_id: int | None = None) -> dict | None:
        if not sgdb_id:
            res = self.api.search(name)
            if not res:
                w = _wikipedia(name)
                return dict(self._blank(name), source="Wikipedia", name=w["title"], description=w["description"],
                            website=w["url"]) if w else None
            sgdb_id = res[0]["id"]
        g = self.api.game(sgdb_id)
        info = dict(self._blank(g.get("name") or name), sgdb_id=sgdb_id, release_date=g.get("release_date") or 0,
                    platforms=[PLATFORM_NAMES.get(t, t) for t in g.get("types") or []])
        apps = (g.get("external_platform_data") or {}).get("steam") or []
        if apps:
            info["steam_appid"] = apps[0].get("id")
            try:
                d = steam.app_details(apps[0]["id"])
            except Exception:           # the store being down shouldn't lose what SteamGridDB gave us
                d = None
            if d:
                info.update(source="SteamGridDB + Steam store",
                            description=_plain(d.get("short_description", "")) or _short(d.get("about_the_game")),
                            developers=d.get("developers") or [], publishers=d.get("publishers") or [],
                            genres=[x.get("description", "") for x in d.get("genres") or []],
                            website=d.get("website") or "",
                            release_text=(d.get("release_date") or {}).get("date", ""))
        if not info["description"]:
            w = _wikipedia(info["name"], name)
            if w:
                info.update(source=info["source"] + " + Wikipedia", description=w["description"])
                info["website"] = info["website"] or w["url"]
        return info

    def _blank(self, name):
        return {"source": self.name, "name": name, "release_date": 0, "release_text": "", "description": "",
                "developers": [], "publishers": [], "genres": [], "website": "", "platforms": [],
                "fetched": time.time(), "v": INFO_VERSION}


def _short(html_text, limit=700) -> str:
    """The start of a long store description (some games leave the short one empty)."""
    text = re.sub(r"\n{3,}", "\n\n", _plain(html_text or ""))
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


@dataclass(frozen=True)
class Source:
    name: str
    key_setting: str            # settings key holding this source's API key
    make: Callable[[str], object]


SOURCES: dict[str, Source] = {s.name: s for s in (
    Source("SteamGridDB", "sgdb_key", SteamGridDBInfo),
)}
DEFAULT = "SteamGridDB"
