"""Settings and a game's save files in fullscreen mode, so a handheld doesn't need desktop mode for them.

☰ → Settings is a list: A switches a setting on or off, or types it with the on-screen keyboard (fs_keyboard.py).
A game's page has "More": its own options and Show save files, the file comparison of the desktop Saves tab as a
list (differences first); A on a file shows both sides and can exclude it. Up / down move, LB / RB page, B goes back.
"""
from __future__ import annotations

from .. import launcher, updater
from ..core.diff import CHANGED, CLOUD_ONLY, EXCLUDED, LOCAL_ONLY, SAME
from ..core.util import escape_pattern, fmt_time, human_size
from .fullscreen import FS

STATUS = {CHANGED: ("Different", FS["amber"]), LOCAL_ONLY: ("▲  Only on this PC", FS["blue"]),
          CLOUD_ONLY: ("▼  Only in cloud", FS["blue"]), SAME: ("Same", FS["button"]),
          EXCLUDED: ("Excluded", FS["button"])}
ORDER = {CHANGED: 0, LOCAL_ONLY: 1, CLOUD_ONLY: 1, SAME: 2, EXCLUDED: 3}


class FsSettingsMixin:
    """Part of App (see ui/app.py)."""

    _fs_row = 0                 # focused row of the settings / files list
    _fs_top = 0                 # first row shown

    # ------------------------------------------------------------ settings
    def fs_open_settings(self):
        self._fs_view, self._fs_row, self._fs_top = "settings", 0, 0
        self._fs_render()

    def _fs_settings_rows(self):
        """[(label, value shown, action or None)]."""
        d = self.settings.data
        on = lambda v: "On" if v else "Off"  # noqa: E731
        rows = [("Start in Fullscreen mode", on(d.get("start_fullscreen")), self._fs_toggle("start_fullscreen")),
                ("Start with Windows (minimized)", on(launcher.get_startup()), self._fs_toggle_startup),
                ("Mirror deletions when syncing", on(self.mirror_var.get()), self._fs_toggle_mirror),
                ("Check for updates automatically", on(d.get("check_updates", True)),
                 self._fs_toggle("check_updates", True)),
                ("Check for updates now", updater.current_text(), self.check_updates_now),
                ("SteamGridDB API key", "Set" if d.get("sgdb_key") else "Not set — covers and game info need it",
                 self._fs_edit_key),
                ("This PC's name", d.get("device_name") or "—", self._fs_edit_name)]
        n = len(d.get("emulators", {}))
        rows.append(("Emulators", f"{n} set up" if n else "None", None))
        storage = ("Google Drive" if self.backend.kind == "gdrive" else "Synced folder") if self.backend else \
            "Not connected"
        rows.append(("Storage", storage, None))
        return rows

    def _fs_toggle(self, key, default=False):
        def flip():
            self.settings.data[key] = not self.settings.data.get(key, default)
            self.settings.save()
        return flip

    def _fs_toggle_startup(self):
        try:
            launcher.set_startup(not launcher.get_startup())
        except OSError as ex:
            self.tell("Start with Windows", str(ex), "error")

    def _fs_toggle_mirror(self):
        self.mirror_var.set(not self.mirror_var.get())
        self._save_mirror()

    def _fs_edit_key(self):
        key = self.fs_type("SteamGridDB API key", self.settings.data.get("sgdb_key", ""),
                           "From steamgriddb.com → Preferences → API. Typing it is easier with a keyboard.")
        if key is not None:
            self.settings.data["sgdb_key"] = key
            self.settings.save()
            for g in self.all_games:
                self.fetch_meta(g)
            self.note("SteamGridDB key saved — fetching artwork and game info" if key else "SteamGridDB key removed")

    def _fs_edit_name(self):
        name = self.fs_type("This PC's name", self.settings.data.get("device_name", ""),
                            "Shown in the playtime stats, so you can tell your PCs apart.")
        if name:
            self.settings.data["device_name"] = name
            self.settings.save()
            self.when_idle(self._push_stats)        # the other PCs see the new name with its playtime

    def _fs_settings_input(self, b):
        rows = self._fs_settings_rows()
        if b == "b":
            self._fs_view = "home"
        elif b in ("up", "down"):
            self._fs_row = (self._fs_row + (1 if b == "down" else -1)) % len(rows)
        elif b == "a":
            action = rows[min(self._fs_row, len(rows) - 1)][2]
            if action:
                self.after_idle(lambda: (action(), self._fs_render()))
            return
        self._fs_render()

    def _fs_settings_page(self, W, H):
        c, p = self._fs_c, self._fs_px
        self._fs_page_title("Settings", "More settings are in desktop mode (☰ → Desktop mode).", W)
        rows = self._fs_settings_rows()
        f, vf = self._fs_font(21, semi=True), self._fs_font(19)
        x1, x2, y = p(96), W - p(96), p(210)
        h = p(66)
        first, last = self._fs_scroll(len(rows), (H - p(84) - p(24) - y) // (h + p(10)))
        if len(rows) > last - first:
            c.create_text(x2, p(190), text=f"{first + 1}–{last} of {len(rows)}", anchor="e", fill=FS["dim"],
                          font=self._fs_font(15))
        for i in range(first, last):
            label, value, action = rows[i]
            focused = i == self._fs_row
            tag = f"set{i}"
            self._fs_rrect(x1, y, x2, y + h, p(12), tags=tag, outline="" if focused else FS["line"],
                           fill=FS["focus"] if focused else FS["card"])
            ink = FS["focus_ink"] if focused else FS["ink"] if action else FS["sub"]
            c.create_text(x1 + p(28), y + h // 2, text=label, anchor="w", fill=ink, font=f, tags=tag)
            c.create_text(x2 - p(28), y + h // 2, text=value, anchor="e", font=vf, tags=tag,
                          fill=FS["focus_ink"] if focused else FS["sub"] if action else FS["dim"])
            c.tag_bind(tag, "<Button-1>", lambda e, i=i: self._fs_tap_row(i))
            y += h + p(10)

    def _fs_scroll(self, count, fits):
        """(first, last + 1) rows of a list to show so the focused one is in view; keeps _fs_top."""
        n = max(1, fits)
        self._fs_rows_shown = n
        self._fs_row = max(0, min(self._fs_row, count - 1))
        self._fs_top = max(0, min(self._fs_top, self._fs_row, max(0, count - n)))
        if self._fs_row >= self._fs_top + n:
            self._fs_top = self._fs_row - n + 1
        return self._fs_top, min(count, self._fs_top + n)

    def _fs_tap_row(self, i):
        if not self._fs_prompts and self._fs_menu is None:
            self._fs_row = i
            self._fs_input("a")

    def _fs_page_title(self, title, sub, W):
        c, p = self._fs_c, self._fs_px
        scrim = self._fs_scrim(W, self._fs_c.winfo_height())
        if scrim is not None:
            c.create_image(0, 0, image=scrim, anchor="nw")
        t = c.create_text(p(96), p(118), text=title, anchor="nw", fill=FS["ink"], font=self._fs_font(44, bold=True))
        c.create_text(c.bbox(t)[2] + p(30), p(118) + p(30), text=sub, anchor="w", fill=FS["sub"],
                      font=self._fs_font(18), width=W - c.bbox(t)[2] - p(150))

    # ------------------------------------------------------------ a game's options
    def fs_game_more(self, g):
        gs = self.settings.data["games"].get(g, {})
        auto = gs.get("auto_sync", True)
        choices = [("Show save files", "files"),
                   (f"Sync automatically when playing: {'On' if auto else 'Off'}", "auto"),
                   (f"Launch options: {gs.get('args') or 'none'}", "args")]
        if gs.get("local_path") and self.backend is not None:
            choices.append(("Look for the save folder again", "find"))
        choices.append(("Close", None))
        pick = self._fs_ask(g, "", choices, cancel=None)
        if pick == "files":
            self.fs_open_files(g)
        elif pick == "auto":
            self.settings.game(g)["auto_sync"] = not auto
            self.settings.save()
            if self.game == g:
                self.auto_var.set(not auto)
            self._fs_toast(f"{g}: sync automatically {'off' if auto else 'on'}")
        elif pick == "args":
            args = self.fs_type(f"Launch options — {g}", gs.get("args", ""),
                                "Added to the game's command line when it starts (e.g. -windowed).")
            if args is not None:
                self.settings.game(g)["args"] = args
                self.settings.save()
                if self.game == g:
                    self.args_var.set(args)
        elif pick == "find":
            self.when_idle(lambda: self.find_saves(g, explicit=True))

    # ------------------------------------------------------------ save files
    def fs_open_files(self, g):
        if not self._fs_select(g):
            self._fs_toast("Please wait for the current task to finish.")
            return
        self._fs_view, self._fs_row, self._fs_top = "files", 0, 0
        self.refresh_diff()                     # compare afresh; the list fills in when it's done
        self._fs_render()

    def _fs_files(self):
        return sorted(self.diff, key=lambda e: (ORDER.get(e.status, 4), e.path.lower())) if self.game else []

    def _fs_files_input(self, b):
        files = self._fs_files()
        if b == "b":
            self._fs_view = "game"
        elif files and b in ("up", "down", "lb", "rb"):
            step = {"up": -1, "down": 1, "lb": -self._fs_rows_shown, "rb": self._fs_rows_shown}[b]
            self._fs_row = max(0, min(len(files) - 1, self._fs_row + step))
        elif b == "x":
            self.after_idle(lambda: self._fs_sync(self.game, None))
        elif b == "a" and files:
            e = files[min(self._fs_row, len(files) - 1)]
            self.after_idle(lambda: self._fs_file_detail(e))
            return
        self._fs_render()

    def _fs_file_detail(self, e):
        def side(name, fi):
            return f"{name}:  {human_size(fi.size)},  changed {fmt_time(fi.mtime)}" if fi else f"{name}:  —"
        text = "\n".join([STATUS.get(e.status, (e.status,))[0] + (f"  ·  {e.hint}" if e.hint else ""), "",
                          side("This PC", e.local), side("Cloud", e.cloud)])
        choices = []
        if e.status != EXCLUDED:
            choices.append(("Exclude this file (never synced)", "file"))
            if "/" in e.path:
                choices.append((f"Exclude its folder  {e.path.rsplit('/', 1)[0]}/", "folder"))
        choices.append(("Close", None))
        pick = self._fs_ask(e.path, text, choices, cancel=None)
        if pick == "file":
            self.add_excludes(["/" + escape_pattern(e.path)])
        elif pick == "folder":
            self.add_excludes(["/" + escape_pattern(e.path.rsplit("/", 1)[0])])

    _fs_rows_shown = 8

    def _fs_files_page(self, W, H):
        c, p = self._fs_c, self._fs_px
        g = self.game
        files = self._fs_files()
        pending = [e for e in files if e.status not in (SAME, EXCLUDED)]
        if self.busy and not files:
            sub = "Comparing this PC with the cloud…"
        elif not files:
            sub = "No save files on either side yet."
        else:
            sub = (f"{len(pending)} difference{'s' if len(pending) != 1 else ''}" if pending else "In sync ✓") + \
                f"   ·   {len(files)} files"
        self._fs_page_title(g or "", sub, W)
        x1, x2, y, bottom = p(96), W - p(96), p(210), H - p(84) - p(24)
        h, gap = p(64), p(8)
        first, last = self._fs_scroll(len(files), (bottom - y) // (h + gap))
        n = last - first
        f, sf = self._fs_font(19, semi=True), self._fs_font(15)
        for i in range(first, last):
            e = files[i]
            focused = i == self._fs_row
            tag = f"file{i}"
            self._fs_rrect(x1, y, x2, y + h, p(12), tags=tag, outline="" if focused else FS["line"],
                           fill=FS["focus"] if focused else FS["card"])
            label, color = STATUS.get(e.status, (e.status, FS["button"]))
            if e.changed_side == "both":
                label, color = "⚠  Changed on both sides", FS["red"]
            right = self._fs_chip(x1 + p(20), y + h // 2, label, color)
            c.create_text(right + p(20), y + h // 2, text=e.path, anchor="w", font=f, tags=tag,
                          fill=FS["focus_ink"] if focused else FS["ink"] if e.status != EXCLUDED else FS["dim"])
            meta = "   ".join(x for x in (
                f"PC {human_size(e.local.size)}" if e.local else "", f"cloud {human_size(e.cloud.size)}" if e.cloud
                else "") if x)
            c.create_text(x2 - p(24), y + h // 2, text=meta, anchor="e", font=sf, tags=tag,
                          fill=FS["focus_ink"] if focused else FS["dim"])
            c.tag_bind(tag, "<Button-1>", lambda e_, i=i: self._fs_tap_row(i))
            y += h + gap
        if len(files) > n:
            c.create_text(x2, p(190), text=f"{first + 1}–{last} of {len(files)}", anchor="e", fill=FS["dim"],
                          font=self._fs_font(15))
