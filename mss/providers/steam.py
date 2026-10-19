"""Steam store: public game details (description, developers, genres). No API key needed."""
from __future__ import annotations

import json
import urllib.request

from . import UA

STORE_API = "https://store.steampowered.com/api/appdetails"


def app_details(appid, lang: str = "english") -> dict | None:
    """The store's data for one app id (name, short_description, developers, genres, …), or None."""
    url = f"{STORE_API}?appids={int(appid)}&l={lang}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        entry = (json.loads(r.read().decode("utf-8")) or {}).get(str(int(appid))) or {}
    return entry.get("data") if entry.get("success") else None
