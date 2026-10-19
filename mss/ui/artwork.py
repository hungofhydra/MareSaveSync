"""Cover art: showing it, and keeping it in sync with the cloud."""
from __future__ import annotations

import tkinter as tk

from ..art import images
from ..providers import sgdb
from .theme import TILE_H, TILE_W

try:
    from PIL import ImageTk
    from . import theme_art
except Exception:
    ImageTk = theme_art = None


class ArtworkMixin:
    """Part of App (see ui/app.py)."""

    def art_info(self, g) -> dict:
        return self.settings.data["art_cache"].get(g) or {}

    @staticmethod
    def _art_file(url):
        if not url:
            return None
        p = images.cache_path(url)
        return p if p.is_file() else None

    def cover_photo(self, g):
        url = self.art_info(g).get("grid") or ""
        key = (g, url, bool(self._art_file(url)))
        if key not in self.photos:
            if theme_art is not None:
                self.photos[key] = ImageTk.PhotoImage(theme_art.cover_tile(self._art_file(url), TILE_W, TILE_H, g))
            else:
                ph = tk.PhotoImage(width=TILE_W, height=TILE_H)
                ph.put("#2a2a8a", to=(0, 0, TILE_W, TILE_H))
                self.photos[key] = ph
        return self.photos[key]

    def _art_worker(self):
        """Background: read each game's artwork from the cloud (.mss-art), auto-pick from SteamGridDB if there's
        none yet, and make sure the images are both cached here and stored in the cloud."""
        while True:
            g, force = self.art_q.get()
            b = self.backend
            if b is None:
                continue
            try:
                art = b.read_art(g)
                if art is None:                     # older versions kept the choice in the game's save folder
                    try:
                        art = b.get_game_config(g).get("art")
                    except KeyError:
                        art = None
                    if art:
                        b.write_art(g, art)
                key = self.settings.data.get("sgdb_key")
                if key and (force or not art):
                    try:
                        art = sgdb.SGDB(key).auto_art(g) or {"none": True}
                        b.write_art(g, art)
                    except sgdb.SGDBError as ex:
                        self.log_ts(f"Artwork for {g}: {ex}")
                if art:
                    self._sync_art_files(b, g, art)
                self.q.put(("art", g, art or {}))
            except Exception as ex:
                self.log_ts(f"Artwork for {g} failed: {ex}")

    def _sync_art_files(self, b, g, art):
        """Cache each image locally (from the cloud, else its URL) and keep the cloud copy matching the choice."""
        cloud = b.art_files(g)
        wanted = set()
        for k in ("grid", "hero", "logo"):
            ident = art.get(k)
            if not ident:
                continue
            p = images.cache_path(ident)
            wanted.add(p.name)
            try:
                if not (p.is_file() and p.stat().st_size > 0):
                    if p.name in cloud:
                        b.download_art_file(g, p.name, p)
                    else:
                        images.fetch(ident)
                if p.name not in cloud:
                    b.upload_art_file(g, p.name, p)
            except Exception as ex:
                self.log_ts(f"Couldn't get {k} image for {g}: {ex}")
        for name in cloud - wanted:
            try:
                b.delete_art_file(g, name)
            except Exception:
                pass

    def _remember_art(self, g, art):
        if self.settings.data["art_cache"].get(g) != art:
            self.settings.data["art_cache"][g] = art
            self.settings.save()
        if self.game == g:
            self._render_header()
            self._draw_hero()
        if self.lib_view.winfo_ismapped():
            self._debounce("grid", 150, self._layout_grid)

    def _store_meta(self, g, art=None, info=None):
        """Background part of saving a chosen artwork / game info to the cloud (either may be None)."""
        if info:
            self.backend.write_info(g, info)
        if art:
            self.backend.write_art(g, art)
            self._sync_art_files(self.backend, g, art)

    def _show_meta(self, g, art=None, info=None):
        if info:
            self._remember_info(g, info)
        if art:
            self._remember_art(g, art)

    def save_meta(self, g, art=None, info=None):
        """Save what was picked in the game info & artwork dialog (either may be None: left as it is)."""
        self.run_bg("Saving game info and artwork", lambda: self._store_meta(g, art, info),
                    lambda _: self._show_meta(g, art, info))
