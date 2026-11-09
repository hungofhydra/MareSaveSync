"""IGDB (Twitch): find a game, its cover, artwork/screenshots as banners, and its description, developers, genres.

IGDB needs a Twitch application: the key is "client_id:client_secret" (dev.twitch.tv/console → Register Your
Application → Client ID and a New Secret). A short-lived app token is fetched with them and kept in memory.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import UA

API = "https://api.igdb.com/v4"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IMG = "https://images.igdb.com/igdb/image/upload/t_{size}/{image_id}.jpg"
FIELDS = ("name,first_release_date,summary,storyline,url,cover.image_id,artworks.image_id,screenshots.image_id,"
          "genres.name,platforms.name,involved_companies.developer,involved_companies.publisher,"
          "involved_companies.company.name,websites.url,websites.category,external_games.category,"
          "external_games.uid")
STEAM_CATEGORY = 1                  # external_games.category for Steam

_tokens: dict[str, tuple[str, float]] = {}      # client id -> (token, expires at)
_lock = threading.Lock()


class IGDBError(Exception):
    pass


def _image(image_id: str, size: str) -> str:
    return IMG.format(size=size, image_id=image_id)


class IGDB:
    def __init__(self, key: str):
        cid, _, secret = (key or "").strip().partition(":")
        self.client_id, self.secret = cid.strip(), secret.strip()
        if not (self.client_id and self.secret):
            raise IGDBError("No IGDB key set. Enter it as client_id:client_secret (Settings → Artwork).")

    # ------------------------------------------------------------ http
    def _token(self) -> str:
        with _lock:
            tok, exp = _tokens.get(self.client_id, ("", 0))
            if tok and exp > time.time() + 60:
                return tok
            body = urllib.parse.urlencode({"client_id": self.client_id, "client_secret": self.secret,
                                           "grant_type": "client_credentials"}).encode()
            try:
                with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body, headers={"User-Agent": UA}),
                                            timeout=20) as r:
                    data = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as ex:
                if ex.code in (400, 401, 403):
                    raise IGDBError("Twitch rejected the IGDB client id or secret. Check them in Settings → "
                                    "Artwork.") from None
                raise IGDBError(f"Twitch error {ex.code}") from None
            except urllib.error.URLError as ex:
                raise IGDBError(f"Can't reach Twitch: {ex.reason}") from None
            tok = data.get("access_token", "")
            _tokens[self.client_id] = (tok, time.time() + int(data.get("expires_in", 3600)))
            return tok

    def _post(self, endpoint: str, query: str):
        req = urllib.request.Request(f"{API}/{endpoint}", data=query.encode("utf-8"), headers={
            "Client-ID": self.client_id, "Authorization": f"Bearer {self._token()}", "User-Agent": UA,
            "Accept": "application/json", "Content-Type": "text/plain"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8")) or []
        except urllib.error.HTTPError as ex:
            if ex.code == 401:
                _tokens.pop(self.client_id, None)
                raise IGDBError("IGDB rejected the login. Check the key in Settings → Artwork.") from None
            if ex.code == 429:
                raise IGDBError("IGDB: too many requests, try again in a moment.") from None
            raise IGDBError(f"IGDB error {ex.code}") from None
        except urllib.error.URLError as ex:
            raise IGDBError(f"Can't reach IGDB: {ex.reason}") from None

    # ------------------------------------------------------------ games
    def search(self, term: str) -> list[dict]:
        """[{id, name, release_date}] best matches first."""
        term = term.strip().replace("\\", "\\\\").replace('"', '\\"')
        rows = self._post("games", f'search "{term}"; fields name,first_release_date; limit 20;')
        return [{"id": r["id"], "name": r.get("name", "?"), "release_date": r.get("first_release_date") or 0}
                for r in rows]

    def game(self, game_id: int) -> dict:
        """Everything the info source needs, as IGDB gives it (see FIELDS)."""
        rows = self._post("games", f"fields {FIELDS}; where id = {int(game_id)};")
        return rows[0] if rows else {}

    # ------------------------------------------------------------ images (same shape as sgdb.SGDB.images)
    def images(self, kind: str, game_id: int) -> list[dict]:
        """kind: "grids" (the cover) or "heroes" (artworks, then screenshots). "logos": IGDB has none."""
        if kind == "logos":
            return []
        g = self.game(game_id)
        if kind == "grids":
            c = (g.get("cover") or {}).get("image_id")
            return [{"url": _image(c, "cover_big_2x"), "thumb": _image(c, "cover_big")}] if c else []
        out = []
        for im in (g.get("artworks") or []) + (g.get("screenshots") or []):
            if im.get("image_id"):
                out.append({"url": _image(im["image_id"], "1080p"), "thumb": _image(im["image_id"], "screenshot_med")})
        return out

    def art_for(self, game_id: int, name: str = "", grid_url: str | None = None,
                hero_url: str | None = None) -> dict:
        art = {"igdb_id": game_id, "igdb_name": name}
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
