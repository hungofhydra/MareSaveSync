"""Finding a game's save folders by itself.

Where each save folder is goes into the game's cloud config as a template (its "where", see
core/savepaths.py), so once one PC knows it, the other PCs fill it in themselves. For a game no PC has set up
yet, Ludusavi's list of save locations (providers/ludusavi.py) says where to look.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..core import detect, folders, savepaths
from ..core.playtime import fmt_ago
from ..providers import ludusavi


class SaveFindMixin:
    """Part of App (see ui/app.py)."""

    # ------------------------------------------------- shared with other PCs (background threads)
    def _shared_folders(self, g, cfg) -> dict:
        """{folder id: path on this PC} of the game's save folders that aren't set here yet, but whose place
        another PC has shared."""
        roots = self._roots(g, cfg)
        wheres = {folders.MAIN: cfg.get("where"), **{f["id"]: f.get("where") for f in folders.extra_folders(cfg)}}
        out: dict = {}
        for fid, t in wheres.items():
            p = None if roots.get(fid) else savepaths.expand(t)
            if p and not any(r and folders.overlaps(r, p) for r in [*roots.values(), *out.values()]):
                out[fid] = p
        return out

    @staticmethod
    def _share_where(cfg, paths, replace=True) -> bool:
        """Put the templates of this PC's folders {folder id: path} into cfg; the caller saves it.
        replace=False only fills in folders that have none yet. True if cfg changed."""
        changed = False
        for fid, p in paths.items():
            t = p and savepaths.portable(p)
            holder = cfg if fid == folders.MAIN else next(
                (f for f in cfg.get("folders", []) if f.get("id") == fid), None)
            if t and holder is not None and holder.get("where") != t and (replace or not holder.get("where")):
                holder["where"] = t
                changed = True
        return changed

    def _adopt_folders(self, g, found):
        """Use the shared places {folder id: path} for the folders not set on this PC yet."""
        gs = self.settings.game(g)
        paths = gs.setdefault("folders", {})
        for fid, p in found.items():
            if fid == folders.MAIN and not gs.get("local_path"):
                gs["local_path"], gs["base"] = p, {}
            elif fid and not paths.get(fid):
                paths[fid] = p
            else:
                continue
            self.note(f"{g}: save folder found — {p}")
        self.settings.save()
        self._layout_grid()
        if self.game == g:
            self._render_header()

    # ------------------------------------------------------------------ looking for them
    def find_saves(self, g, then=None, explicit=False):
        """Look for the game's save folders on this PC and offer what's found. then(found) afterwards.
        explicit: asked for with "Find automatically" (may replace the folder that's set, and says so when
        nothing is found)."""
        then = then or (lambda found: None)
        if not explicit and self._local_path(g):
            then(True)
            return
        gs = self.settings.data["games"].get(g, {})
        info = self.game_info(g)
        names, steam, exe = [g, info.get("name")], [info.get("steam_appid")], gs.get("exe")

        def work():
            cfg = self.backend.get_game_config(g)
            shared = self._shared_folders(g, cfg)
            if folders.MAIN in shared and not explicit:
                return cfg, shared, None, []
            idx = ludusavi.load(self.log_ts)
            hit = ludusavi.find(idx, names, steam) if idx else None
            return cfg, shared, hit, detect.find_folders(hit[1], exe) if hit else []

        def done(r):
            cfg, shared, hit, found = r
            if not explicit:
                if shared:
                    self._adopt_folders(g, shared)
                if self._local_path(g):
                    then(True)
                    return
            if not found:
                if explicit:
                    self.tell("Find save folder", self._not_found_text(g, hit))
                then(False)
                return
            main = found[0]
            extras = [f for f in found[1:] if f.exists] if main.exists and not folders.extra_folders(cfg) else []
            cur = self._local_path(g)
            if cur and os.path.normcase(cur) == os.path.normcase(main.path) and not extras:
                self.tell("Find save folder", f"{g} already uses the save folder that was found:\n\n{cur}")
                then(True)
                return
            other = next((p for fid, p in self._roots(g, cfg).items()
                          if fid and p and folders.overlaps(p, main.path)), None)
            if other:
                self.tell("Find save folder", f"Found {main.path}\nbut it overlaps another save folder of {g}:\n"
                          f"{other}", "warning")
                then(False)
                return
            if not self.confirm("Save folder", self._found_text(g, hit, main, extras, cur)):
                self.settings.game(g)["find_declined"] = True     # Play doesn't ask again
                self.settings.save()
                then(False)
                return
            self._use_found(g, main, extras, then)

        def failed(ex):
            self.log(f"{g}: looking for save folders failed: {ex}")
            then(False)
        self.run_bg("Looking for save folders", work, done, failed=failed)

    @staticmethod
    def _not_found_text(g, hit):
        if hit and hit[1].get("r") and not hit[1].get("f"):
            return (f"{g} keeps its saves in the Windows registry, which can't be synced.")
        if hit:
            return (f"No save folder of {g} was found on this PC (looked it up as “{hit[0]}”).\n\n"
                    "If the game has never been played here, play it once, or choose the folder yourself.")
        return (f"{g} isn't in the list of save locations, so its save folder can't be found automatically. "
                "Choose it yourself.")

    @staticmethod
    def _found_text(g, hit, main, extras, cur):
        def where(f):
            return f"   {f.path}\n   ({f.files} file{'s' if f.files != 1 else ''}, last changed {fmt_ago(f.newest)})"
        if main.exists:
            lines = [f"Found where {g} keeps its saves on this PC:", "", where(main)]
        else:
            lines = [f"{g} hasn't saved anything on this PC yet. Its saves go in:", "", f"   {main.path}"]
        if extras:
            lines += ["", "and in:"] + [where(f) for f in extras]
        if hit[1].get("r"):
            lines += ["", "It also keeps some saves in the Windows registry, which isn't synced."]
        if cur:
            lines += ["", f"The save folder now is {cur}"]
        ask = "these folders" if extras else "this folder"
        lines += ["", f"Use {ask}{' instead' if cur else ''}?"
                  + ("" if main.exists else " Sync down puts your saves there.")]
        lines += [f"(From Ludusavi's list of save locations: “{hit[0]}”.)"]
        return "\n".join(lines)

    def _use_found(self, g, main, extras, then):
        def work():
            cfg = self.backend.get_game_config(g)
            ids = {}
            for f in extras:
                fid = folders.new_id(cfg)
                cfg["folders"] = folders.extra_folders(cfg) + [{"id": fid, "name": self._folder_name(f.path, cfg)}]
                ids[fid] = f.path
            self._share_where(cfg, {folders.MAIN: main.path, **ids})
            self.backend.set_game_config(g, cfg)
            return ids

        def done(ids):
            gs = self.settings.game(g)
            if gs.get("local_path") != main.path:
                gs["base"] = {}                 # new folder → forget the previous sync baseline
            gs["local_path"] = main.path
            gs.setdefault("folders", {}).update(ids)
            gs.pop("find_declined", None)
            self.settings.save()
            for p in [main.path, *ids.values()]:
                self.log(f"{g}: save folder on this PC set to {p}")
            self.note(f"{g}: save folder set")
            self._layout_grid()
            if self.game == g:
                self._render_header()
                self.when_idle(self.refresh_diff)
            then(True)

        def failed(ex):
            self.tell("Save folder", f"Couldn't save the save folders of {g}:\n{ex}", "error")
            then(False)
        self.run_bg("Saving save folders", work, done, failed=failed)

    @staticmethod
    def _folder_name(path, cfg):
        """A name for an extra folder that the game's other folders don't have yet."""
        p = Path(path)
        taken = {(f.get("name") or "").casefold() for f in folders.extra_folders(cfg)}
        for name in (p.name, f"{p.parent.name} {p.name}".strip()):
            if name.casefold() not in taken:
                return name
        return str(p)
