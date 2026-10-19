"""Library page: the cover grid, adding and removing games."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .. import APP_TITLE
from ..core.playtime import fmt_play_short
from .dialogs.metadata import MetadataDialog
from .dialogs.remove import RemoveDialog
from .theme import GRID_BG, TILE_H, TILE_W, UI, UIB, T
from .widgets import Btn, label, menu


class LibraryMixin:
    """Part of App (see ui/app.py)."""

    def _build_library(self, parent):
        f = tk.Frame(parent, bg=T["face"])
        tb = tk.Frame(f, bg=T["face"])
        tb.pack(fill="x", pady=(2, 6))
        self.new_btn = Btn(tb, "Add game…", self.new_game, kind="default")
        self.new_btn.pack(side="left")
        self.reload_btn = Btn(tb, "Refresh", self.reload_games)
        self.reload_btn.pack(side="left", padx=6)
        label(tb, "Double-click a cover to open it  ·  right-click for Play and more", muted=True).pack(side="right")
        gf = tk.Frame(f, relief="sunken", bd=2, bg=GRID_BG)
        gf.pack(fill="both", expand=True)
        self.grid_c = tk.Canvas(gf, bg=GRID_BG, highlightthickness=0, bd=0, width=200, height=200)
        sb = ttk.Scrollbar(gf, orient="vertical", command=self.grid_c.yview)
        self.grid_c.configure(yscrollcommand=sb.set)
        self.grid_c.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.grid_c.bind("<Configure>", lambda e: self._debounce("grid", 60, self._layout_grid))
        self.grid_c.bind("<MouseWheel>", lambda e: self.grid_c.yview_scroll(int(-e.delta / 120), "units"))
        self.grid_c.bind("<Button-4>", lambda e: self.grid_c.yview_scroll(-2, "units"))
        self.grid_c.bind("<Button-5>", lambda e: self.grid_c.yview_scroll(2, "units"))
        return f

    def _layout_grid(self):
        c = self.grid_c
        c.delete("all")
        self._tile_games = {}
        w = max(c.winfo_width(), 200)
        pad, cap = 24, 44
        cw = TILE_W + pad
        cols = max(1, (w - pad) // cw)
        x0 = (w - cols * cw + pad) // 2
        items = self.games + [None]
        for i, g in enumerate(items):
            r, k = divmod(i, cols)
            x, y = x0 + k * cw, pad + r * (TILE_H + cap + pad)
            self._draw_add_tile(x, y) if g is None else self._draw_tile(i, g, x, y)
        rows = (len(items) + cols - 1) // cols
        c.configure(scrollregion=(0, 0, w, pad + rows * (TILE_H + cap + pad)))

    def _chip(self, x, y, text, bg, fg="#ffffff", anchor="nw", tags=()):
        c = self.grid_c
        t = c.create_text(x + 6 if anchor == "nw" else x - 6, y + 3, text=text, fill=fg,
                          font=(UI[0], UI[1] - 1, "bold"), anchor=anchor, tags=tags)
        x1, y1, x2, y2 = c.bbox(t)
        r = c.create_rectangle(x1 - 4, y1 - 2, x2 + 4, y2 + 2, fill=bg, outline="#ffffff", tags=tags)
        c.tag_raise(t, r)

    def _draw_tile(self, i, g, x, y):
        c, tid = self.grid_c, f"tile{i}"
        self._tile_games[tid] = g
        c.create_rectangle(x - 4, y - 4, x + TILE_W + 3, y + TILE_H + 3, fill=T["face"], outline="", tags=tid)
        c.create_line(x - 4, y + TILE_H + 3, x - 4, y - 4, x + TILE_W + 3, y - 4, fill=T["hi"], tags=tid)
        c.create_line(x + TILE_W + 3, y - 4, x + TILE_W + 3, y + TILE_H + 3, x - 4, y + TILE_H + 3,
                      fill=T["dark"], tags=tid)
        c.create_image(x, y, image=self.cover_photo(g), anchor="nw", tags=tid)
        secs = self.stats_all.get(g, {}).get("seconds", 0)
        if g in self.sessions:
            self._chip(x + 4, y + 4, "▶ Playing", "#1d7a2e", tags=tid)
        elif secs:
            self._chip(x + 4, y + 4, fmt_play_short(secs), T["navy"], tags=tid)
        state = self.settings.data["games"].get(g, {}).get("state")
        if state == "synced":
            self._chip(x + TILE_W - 4, y + 4, "✓ Synced", "#1d7a2e", anchor="ne", tags=tid)
        elif state == "conflict":
            self._chip(x + TILE_W - 4, y + 4, "⚠ Conflict", "#b3261e", anchor="ne", tags=tid)
        elif state == "changes":
            self._chip(x + TILE_W - 4, y + 4, "● Changes", "#8a5a00", anchor="ne", tags=tid)
        gs = self.settings.data["games"].get(g, {})
        ready = gs.get("local_path") or gs.get("exe")
        t = c.create_text(x + TILE_W / 2, y + TILE_H + 12, text=g, width=TILE_W + 14, justify="center",
                          fill="#ffffff" if ready else "#9d9dd0", font=UI, anchor="n", tags=tid)
        if g == self.selected:
            x1, y1, x2, y2 = c.bbox(t)
            r = c.create_rectangle(x1 - 3, y1 - 1, x2 + 3, y2 + 1, fill="#c9bdf0", outline="#ffffff",
                                   dash=(1, 1), tags=tid)
            c.itemconfigure(t, fill=T["ink"])
            c.tag_raise(t, r)
        c.tag_bind(tid, "<Button-1>", lambda e, g=g: self._select_tile(g))
        c.tag_bind(tid, "<Double-1>", lambda e, g=g: self.show_details(g))
        c.tag_bind(tid, "<Button-3>", lambda e, g=g: self._tile_menu(e, g))
        c.tag_bind(tid, "<Button-2>", lambda e, g=g: self._tile_menu(e, g))

    def _draw_add_tile(self, x, y):
        c = self.grid_c
        c.create_rectangle(x, y, x + TILE_W, y + TILE_H, outline="#8f86d8", dash=(4, 3), width=2, tags="add")
        c.create_text(x + TILE_W / 2, y + TILE_H / 2 - 12, text="+", fill="#c9bdf0", font=(UI[0], 30), tags="add")
        c.create_text(x + TILE_W / 2, y + TILE_H / 2 + 22, text="Add game", fill="#c9bdf0", font=UIB, tags="add")
        c.tag_bind("add", "<Button-1>", lambda e: self.new_game() if not self.busy else None)

    def _select_tile(self, g):
        self.selected = g
        self._layout_grid()

    def _tile_menu(self, ev, g):
        self._select_tile(g)
        m = menu(self)
        m.add_command(label="▶  Play", command=lambda: self.play(g))
        m.add_command(label="Open details", command=lambda: self.show_details(g))
        m.add_separator()
        m.add_command(label="Set game executable…", command=lambda: self.pick_exe(g))
        m.add_command(label="Game info & artwork…", command=lambda: MetadataDialog(self, g))
        m.add_separator()
        m.add_command(label="Remove from library…", command=lambda: self.remove_game(g))
        m.tk_popup(ev.x_root, ev.y_root)

    def _set_games(self, games, select=None):
        self.all_games = list(games)
        if select and select not in self.games:
            self.search_var.set("")
        self._apply_filter()
        if self.game and self.game not in self.all_games:
            self.show_library()
        self._update_controls()

    def _apply_filter(self, open_first=False):
        q = self.search_var.get().strip().lower()
        self.games = [g for g in self.all_games if q in g.lower()] if q else list(self.all_games)
        n, t = len(self.games), len(self.all_games)
        self.count_lbl.configure(text=f"{t} game{'s' if t != 1 else ''}" if n == t else f"{n} of {t} games")
        if self.game is not None and q:
            self.show_library()
        self._layout_grid()
        if open_first and self.games:
            self.show_details(self.games[0])

    def reload_games(self):
        def work():
            return self.backend.list_games(), self.backend.read_all_stats()

        def done(r):
            games, stats = r
            self._merge_stats(stats)
            self._set_games(games)
            for g in games:
                self.fetch_meta(g)
        self.run_bg("Loading library", work, done)

    def new_game(self):
        if self.backend is None:
            messagebox.showinfo(APP_TITLE, "Connect to your storage first (Settings).", parent=self)
            return
        name = simpledialog.askstring("Add game", "Game name (used to find its info and cover art):", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.all_games:
            messagebox.showinfo("Add game", f"“{name}” is already in the library.", parent=self)
            return
        meta = MetadataDialog(self, name, add=True).result
        if meta is None:
            return                               # cancelled
        if meta.get("name"):
            name = meta["name"]
            if name in self.all_games:
                messagebox.showinfo("Add game", f"“{name}” is already in the library.", parent=self)
                return
        art, info = meta.get("art"), meta.get("info")

        def work():
            self.backend.create_game(name)
            self._store_meta(name, art, info)
            return self.backend.list_games()

        def done(games):
            self.log(f"Added {name!r}")
            self._set_games(games, select=name)
            self._show_meta(name, art, info)
            if not (art and info):
                self.fetch_meta(name)            # whatever wasn't picked is looked up automatically
            self.show_details(name)
            if messagebox.askyesno(
                    "Save folder", f"Choose where {name} keeps its saves on this PC?\n\n"
                    "• On the PC that has your saves: pick that folder.\n"
                    "• On other PCs: pick where the saves should go.", parent=self):
                self.choose_folder_menu()
            if messagebox.askyesno("Game executable", f"Choose the .exe that starts {name}, so Play works?",
                                   parent=self):
                self.pick_exe(name)
        self.run_bg("Adding game", work, done)

    def remove_game(self, g):
        if not g or g in self.sessions:
            return
        purge = RemoveDialog(self, g).result
        if purge is None:
            return

        def work():
            self.backend.delete_game(g, purge=purge)
            return self.backend.list_games()

        def done(games):
            d = self.settings.data
            d["art_cache"].pop(g, None)
            d["info_cache"].pop(g, None)
            if purge:                     # keep this PC's folder/exe choice when only hiding, so re-adding restores it
                d.get("games", {}).pop(g, None)
                d.get("my_stats", {}).pop(g, None)
                self.stats_all.pop(g, None)
            self.settings.save()
            self.note(f"{g}: all cloud data deleted" if purge else f"Removed {g} from the library")
            if self.game == g:
                self.show_library()
            self._set_games(games)
        self.run_bg("Removing game", work, done)

    def clear_saves(self, g):
        if not g:
            return
        if not messagebox.askyesno("Delete cloud saves", f"Delete all cloud saves of “{g}”?\n\n"
                                   "The game stays in the library with its artwork, exclusions and playtime. "
                                   "Files on this PC are not touched.", icon="warning", parent=self):
            return

        def done(_):
            gs = self.settings.game(g)
            gs["base"] = {}
            gs.pop("state", None)
            self.settings.save()
            self.note(f"{g}: cloud saves deleted")
            if self.game == g:
                self.refresh_diff()
        self.run_bg("Deleting cloud saves", lambda: self.backend.clear_saves(g), done)
