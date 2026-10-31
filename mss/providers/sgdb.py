"""SteamGridDB: find a game, its cover (grid), hero banner and logo, and which store pages it has."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import UA

API = "https://www.steamgriddb.com/api/v2"
_STATIC = {"mimes": "image/png,image/jpeg,image/webp", "types": "static", "nsfw": "false"}
PARAMS = {
    "grids": dict(_STATIC, dimensions="600x900,342x482,660x930"),   # portrait covers
    "heroes": dict(_STATIC),
    "logos": dict(_STATIC, mimes="image/png,image/webp"),
}


class SGDBError(Exception):
    pass


class SGDB:
    def __init__(self, key: str):
        self.key = (key or "").strip()
        if not self.key:
            raise SGDBError("No SteamGridDB API key set (Settings → Artwork).")

    def _get(self, path, params=None):
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.key}", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as ex:
            if ex.code == 401:
                raise SGDBError("SteamGridDB rejected the API key. Check it in Settings → Artwork.") from None
            if ex.code == 404:
                return []
            raise SGDBError(f"SteamGridDB error {ex.code}") from None
        except urllib.error.URLError as ex:
            raise SGDBError(f"Can't reach SteamGridDB: {ex.reason}") from None
        if not data.get("success", False):
            raise SGDBError("; ".join(map(str, data.get("errors", []))) or "SteamGridDB request failed")
        return data.get("data") or []

    def search(self, term: str) -> list[dict]:
        return self._get("/search/autocomplete/" + urllib.parse.quote(term.strip(), safe=""))

    def game(self, game_id: int, platforms: str = "steam,gog,egs") -> dict:
        """id, name, release_date, types (platforms) and external_platform_data (store ids, e.g. Steam app id)."""
        return self._get(f"/games/id/{game_id}", {"platformdata": platforms}) or {}

    def images(self, kind: str, game_id: int) -> list[dict]:
        return self._get(f"/{kind}/game/{game_id}", PARAMS[kind])

    def art_for(self, game_id: int, name: str = "", grid_url: str | None = None,
                hero_url: str | None = None) -> dict:
        art = {"sgdb_id": game_id, "sgdb_name": name}
        picked = {"grid": grid_url, "hero": hero_url}
        for kind, key in (("grids", "grid"), ("heroes", "hero"), ("logos", "logo")):
            if picked.get(key):
                art[key] = picked[key]
                continue
            imgs = self.images(kind, game_id)
            art[key] = imgs[0]["url"] if imgs else ""
        return art

    def auto_art(self, name: str) -> dict | None:
        res = self.search(name)
        return self.art_for(res[0]["id"], res[0].get("name", "")) if res else None
