"""Adding a game in fullscreen mode, with a controller: type its name, pick which game it is (SteamGridDB or IGDB), pick
the .exe from where Steam, Epic or GOG installed it (core/installs.py), then the save folder is looked for
(savefind.py). Each step's question appears inside fullscreen mode; anything skipped can be done later.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..core import installs
from ..info import sources
from ..providers import ludusavi

MATCHES = 5                 # search results offered


class FsAddMixin:
    """Part of App (see ui/app.py)."""

    def fs_add_game(self):
        if self.backend is None:
            self._fs_toast("Connect to your storage first (☰ menu).")
            return
        if self.busy:
            self._fs_toast("Please wait for the current task to finish.")
            return
        name = self.fs_type("Add game", hint="Type the game's name. It's used to find its cover, info, "
                                             "program and save folder.")
        if not name:
            return
        asrc = self.art_source()
        key = self.settings.data.get(asrc.key_setting)
        if not key:
            self._fs_add_create(name, None)
            return
        self.run_bg("Looking up the game", lambda: asrc.make(key).search(name)[:MATCHES],
                    lambda res: self._fs_add_pick(name, res),
                    failed=lambda ex: self._fs_add_pick(name, [], ex))

    def _fs_add_pick(self, name, results, error=None):
        def label(r):
            year = time.gmtime(r["release_date"]).tm_year if r.get("release_date") else None
            return f"{r.get('name')} ({year})" if year else r.get("name")
        choices = [(label(r), r) for r in results]
        if results:
            text = f"Which game is it? Its cover and info come from {self.art_source().name}."
            choices.append((f"None of these: add it as “{name}”", "typed"))
        else:
            text = (f"{self.art_source().name} found nothing for “{name}”" + (f" ({error})" if error else "")
                    + ". Add it anyway? Its cover can be chosen later in desktop mode.")
            choices.append((f"Add “{name}”", "typed"))
        choices.append(("Cancel", "cancel"))
        pick = self._fs_ask("Add game", text, choices, cancel="cancel")
        if pick != "cancel":
            self._fs_add_create(name, None if pick == "typed" else pick)

    def _fs_add_create(self, name, pick):
        g = ((pick or {}).get("name") or name).strip()
        if g in self.all_games:
            self.tell("Add game", f"“{g}” is already in the library.")
            self._fs_focus, self._fs_query = g, ""
            return
        asrc = self.art_source()
        key = self.settings.data.get(asrc.key_setting)
        src = sources.SOURCES.get(asrc.name) or sources.SOURCES[sources.DEFAULT]       # info from the same service
        info_key = self.settings.data.get(src.key_setting)

        def work():
            self.backend.create_game(g)
            art = info = None
            if pick and key:
                try:
                    art = asrc.make(key).art_for(pick["id"], pick.get("name", ""))
                except asrc.error as ex:
                    self.log_ts(f"Artwork for {g}: {ex}")
            if pick and info_key:
                try:
                    info = src.make(info_key).fetch(g, pick["id"])
                except Exception as ex:          # looked up again in the background
                    self.log_ts(f"Game info for {g}: {ex}")
            self._store_meta(g, art, info)
            return self._list_games(self.backend), art, info

        def done(r):
            games, art, info = r
            self.log(f"Added {g!r}")
            self._set_games(games)
            self._show_meta(g, art, info)
            if not (art and info):
                self.fetch_meta(g)
            self._fs_focus, self._fs_query, self._fs_view = g, "", "home"
            self._fs_render()
            self.when_idle(lambda: self.fs_set_exe(g, lambda ok: self.when_idle(lambda: self._fs_add_saves(g))))
        self.run_bg("Adding game", work, done)

    def _fs_add_saves(self, g):
        def then(found):
            self.note(f"{g} added" + ("" if found else " — its save folder can be set from its page"))
            self._fs_open(g)
            self._fs_render()
        self.find_saves(g, then)

    # ------------------------------------------------------------ the .exe, without a file browser
    def fs_set_exe(self, g, then=lambda ok: None):
        """Offer the programs found where the game is installed. then(True) once one is set."""
        info = self.game_info(g)
        names = [g, info.get("name")]
        steam = [info.get("steam_appid")]

        def work():
            dirs = []
            idx = ludusavi.load(self.log_ts)
            hit = ludusavi.find(idx, names, steam) if idx else None
            if hit:
                steam.extend(hit[1].get("s", []))
                dirs = hit[1].get("d", [])
            return installs.find(names, steam, dirs)

        def done(r):
            folder, exes = r
            if not exes:
                self.tell("Game program", f"Couldn't find where {g} is installed on this PC (looked in Steam, "
                          "Epic and GOG).\n\nIf it's installed somewhere else, set its .exe in desktop mode: "
                          "its Game tab → Browse.")
                then(False)
                return
            shown = [(str(e.relative_to(folder)) if folder and e.is_relative_to(folder) else str(e), e)
                     for e in exes]
            exe = self._fs_ask("Game program", f"Which program starts {g}?\n\nFound in {folder or exes[0].parent}",
                               shown + [("Set it later in desktop mode", None)], cancel=None)
            if not exe:
                then(False)
                return
            self.settings.game(g)["exe"] = str(Path(exe))
            self.settings.save()
            self.log(f"{g}: executable set to {exe}")
            if self.game == g:
                self._render_header()
            then(True)

        def failed(ex):
            self.log(f"{g}: looking for its program failed: {ex}")
            then(False)
        self.run_bg("Looking for the game's program", work, done, failed=failed)
