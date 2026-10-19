"""Game info (name, description, …) on the details page's About tab, kept in sync with the cloud."""
from __future__ import annotations

import tkinter as tk

from ..info import format as info_format
from ..info import sources
from ..providers import sgdb
from .theme import UI, T
from .widgets import Btn, label


class InfoMixin:
    """Part of App (see ui/app.py)."""

    def game_info(self, g) -> dict:
        return self.settings.data["info_cache"].get(g) or {}

    def fetch_meta(self, g, force=False):
        """Queue a look-up of the game's artwork and info (from the cloud, else online)."""
        self.art_q.put((g, force))
        self.info_q.put((g, force))

    def reload_info(self, g):
        if g:
            self._info_pending.add(g)
            self._render_about()
            self.info_q.put((g, True))

    def _info_worker(self):
        """Background: read each game's info from the cloud; look it up online if there's none yet (or on
        reload) and store it in the cloud so other PCs don't have to."""
        while True:
            g, force = self.info_q.get()
            b = self.backend
            if b is None:
                continue
            try:
                info = b.read_info(g)
                src = sources.SOURCES.get(self.settings.data.get("info_source", sources.DEFAULT),
                                          sources.SOURCES[sources.DEFAULT])
                key = self.settings.data.get(src.key_setting)
                if key and (force or info is None):
                    sgdb_id = (self.art_info(g) or {}).get("sgdb_id")     # same game the artwork came from
                    try:
                        info = src.make(key).fetch(g, sgdb_id) or {"none": True}
                        b.write_info(g, info)
                    except sgdb.SGDBError as ex:
                        self.log_ts(f"Game info for {g}: {ex}")
                self.q.put(("info", g, info or {}))
            except Exception as ex:
                self.log_ts(f"Game info for {g} failed: {ex}")
                self.q.put(("info", g, self.game_info(g)))

    def _remember_info(self, g, info):
        self._info_pending.discard(g)
        if self.settings.data["info_cache"].get(g) != info:
            self.settings.data["info_cache"][g] = info
            self.settings.save()
        if self.game == g:
            self._render_about()

    # ------------------------------------------------------------ about tab
    def _build_about_tab(self, nb):
        at = tk.Frame(nb, bg=T["face"], padx=12, pady=10)
        nb.add(at, text="About")
        self.info_name = label(at, "", font=(UI[0], UI[1] + 5, "bold"), anchor="w", justify="left")
        self.info_name.pack(fill="x")
        self.info_meta = label(at, "", muted=True, anchor="w", justify="left")
        self.info_meta.pack(fill="x", pady=(2, 0))
        self.info_tags = label(at, "", muted=True, anchor="w", justify="left")
        self.info_tags.pack(fill="x")
        df = tk.Frame(at, bg=T["face"], relief="sunken", bd=2)
        df.pack(fill="both", expand=True, pady=(8, 0))
        self.info_desc = tk.Text(df, bg=T["field"], fg=T["ink"], bd=0, highlightthickness=0, font=(UI[0], UI[1] + 1),
                                 wrap="word", padx=10, pady=8, height=5, cursor="arrow")
        self.info_desc.pack(fill="both", expand=True)
        self.info_desc.configure(state="disabled")
        bot = tk.Frame(at, bg=T["face"])
        bot.pack(fill="x", pady=(6, 0))
        self.info_src = label(bot, "", muted=True)
        self.info_src.pack(side="left")
        Btn(bot, "Reload info", lambda: self.reload_info(self.game)).pack(side="right")

    def _render_about(self):
        g = self.game
        if not g:
            return
        info = self.game_info(g)
        found = info_format.found(info)
        self.info_name.configure(text=info.get("name") or g if found else g)
        meta, tags = info_format.summary(info) if found else ("", "")
        self.info_meta.configure(text=meta)
        self.info_tags.configure(text=tags)

        src = sources.SOURCES.get(self.settings.data.get("info_source", sources.DEFAULT),
                                  sources.SOURCES[sources.DEFAULT])
        if g in self._info_pending or (not info and self.settings.data.get(src.key_setting)):
            desc = "Looking up game info…"
        elif found:
            desc = info.get("description") or "No description available for this game."
        elif info.get("none"):
            desc = f"No game info found for “{g}”. Pick the right game under Game info & artwork…"
        else:
            desc = f"Add your {src.name} API key in Settings → Artwork to look up the game's name and description."
        t = self.info_desc
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", desc)
        t.configure(state="disabled")
        self.info_src.configure(text=f"Source: {info['source']}" + (
            f"   ·   {info['website']}" if info.get("website") else "") if found else "")
