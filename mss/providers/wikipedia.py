"""Wikipedia: a game's description when no store has one (Epic exclusives, console games run in emulators, …).
No API key needed."""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request

from . import UA

API = "https://en.wikipedia.org/w/api.php"
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8")) or {}


def _norm(title: str) -> str:
    """"Schrödinger's Call (video game)" -> "schrodingerscall", to compare titles with the game's name."""
    title = re.sub(r"\s*\([^)]*\)\s*$", "", title)
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", title.lower())


def game_summary(name: str) -> dict | None:
    """{"title", "description", "url"} of the article about the video game called `name`, or None.

    Only an article whose title is the game's name (give or take "(2016 video game)", accents and punctuation)
    and that Wikipedia itself calls a video game is used, so "Doom" doesn't get the franchise's article.
    """
    want = _norm(name)
    if not want:
        return None
    q = _get(API + "?" + urllib.parse.urlencode({"action": "query", "list": "search", "format": "json",
                                                 "srsearch": f"{name} video game", "srlimit": 5}))
    for hit in (q.get("query") or {}).get("search") or []:
        if _norm(hit.get("title", "")) != want:
            continue
        s = _get(SUMMARY + urllib.parse.quote(hit["title"].replace(" ", "_"), safe=""))
        if "game" in (s.get("description") or "").lower() and s.get("extract"):
            return {"title": s.get("title") or hit["title"], "description": s["extract"].strip(),
                    "url": ((s.get("content_urls") or {}).get("desktop") or {}).get("page", "")}
    return None
