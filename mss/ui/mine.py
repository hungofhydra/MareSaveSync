"""Your own game info (status, tags, notes): the "My notes" tab, saving it to the cloud, the library filter.

The data and its rules are in core/mine.py. Changes are shown at once and written to the game's cloud config by a
background thread; what the cloud has is read back whenever a game's saves are checked.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core import mine
from .theme import UI, T
from .widgets import label

NONE = "No status"
CHIP = {"backlog": "#5b5b8a", "playing": "#1f4fbf", "on_hold": "#8a5a00", "completed": "#1d7a2e",
        "dropped": "#7a3030"}


class MineMixin:
    """Part of App (see ui/app.py)."""

    show_key = ""                       # the library's Show filter: "", "status:playing", "tag:rpg"
    fs_show = ""                        # fullscreen mode's: "" or "status:…"

    def mine(self, g) -> dict:
        return self.settings.data["mine_cache"].get(g) or {}

    # ------------------------------------------------------------ changing and saving
    def set_mine(self, g, **changes):
        """Change a game's status / tags / notes: used at once, written to the cloud in the background."""
        if g not in self.all_games:
            return
        new = mine.clean({**self.mine(g), **changes})
        if new == self.mine(g):
            return
        self._store_mine(g, new)
        self._mine_pending[g] = self._mine_pending.get(g, 0) + 1
        self.mine_q.put(g)
        self._mine_changed(g)

    def _store_mine(self, g, new):
        cache = self.settings.data["mine_cache"]
        if new:
            cache[g] = new
        else:
            cache.pop(g, None)
        self.settings.save()

    def _mine_worker(self):
        while True:
            g = self.mine_q.get()
            b, err = self.backend, None
            try:
                if b is None:
                    raise RuntimeError("not connected")
                cfg = b.get_game_config(g)
                entry = self.mine(g)
                if entry:
                    cfg["mine"] = entry
                else:
                    cfg.pop("mine", None)
                b.set_game_config(g, cfg)
            except Exception as ex:
                err = ex
            self.q.put(("mine_saved", g, err))

    def _mine_saved(self, g, err):
        left = self._mine_pending.get(g, 1) - 1
        if left > 0:
            self._mine_pending[g] = left
        else:
            self._mine_pending.pop(g, None)
        unsent = self.settings.data["mine_unsent"]
        if err is None and not self._mine_pending.get(g):
            if g in unsent:
                unsent.remove(g)
                self.settings.save()
        elif err is not None:
            if g not in unsent:
                unsent.append(g)
                self.settings.save()
            self.note(f"Couldn't save your notes for {g} to the cloud: {err}. They're kept on this PC and "
                      "sent again at the next check.")

    def _remember_mine(self, g, from_cloud):
        """What the cloud has for a game (read with its saves): replaces the cached copy, unless a change of ours
        is still on its way there (or failed to get there: then it is sent again instead)."""
        if g not in self.all_games or self._mine_pending.get(g):
            return
        if g in self.settings.data["mine_unsent"]:
            self._mine_pending[g] = 1
            self.mine_q.put(g)
            return
        new = mine.clean(from_cloud)
        if new != self.mine(g):
            self._store_mine(g, new)
            self._mine_changed(g)

    def _mine_changed(self, g):
        self._refresh_show_box()
        self._apply_filter(keep_open=True)
        if self.game == g:
            self._render_mine()
        self._fs_refresh()

    def forget_mine(self, g):
        self.settings.data["mine_cache"].pop(g, None)
        if g in self.settings.data["mine_unsent"]:
            self.settings.data["mine_unsent"].remove(g)
        self._refresh_show_box()

    # ------------------------------------------------------------ the library's Show box
    def _refresh_show_box(self):
        choices = mine.filter_choices([self.mine(g) for g in self.all_games])
        self._show_choices = dict(choices)
        if self.show_key not in self._show_choices:
            self.show_key = ""
        box = getattr(self, "show_box", None)
        if box is not None:
            box.configure(values=list(self._show_choices.values()))
            self.show_var.set(self._show_choices[self.show_key])

    def _set_show(self):
        names = {v: k for k, v in self._show_choices.items()}
        self.show_key = names.get(self.show_var.get(), "")
        self.show_box.selection_clear()
        self._apply_filter()

    # ------------------------------------------------------------ the "My notes" tab
    def _build_mine_tab(self, nb):
        mt = tk.Frame(nb, bg=T["face"], padx=12, pady=10)
        nb.add(mt, text="My notes")
        self._mine_game = None
        row = tk.Frame(mt, bg=T["face"])
        row.pack(fill="x")
        label(row, "Status:").pack(side="left")
        self.mine_status = tk.StringVar()
        box = ttk.Combobox(row, textvariable=self.mine_status, values=[NONE] + list(mine.STATUSES.values()),
                           state="readonly", width=12, font=UI)
        box.pack(side="left", padx=(6, 18))
        box.bind("<<ComboboxSelected>>", lambda e: (self._save_mine_status(), box.selection_clear()))
        label(row, "Tags:").pack(side="left")
        self.mine_tags = tk.StringVar()
        te = self.mine_tags_entry = tk.Entry(row, textvariable=self.mine_tags, **self._field(row))
        te.pack(side="left", fill="x", expand=True, padx=6)
        te.bind("<KeyRelease>", lambda e: self._debounce("mine_tags", 800, self._save_mine_tags))
        te.bind("<FocusOut>", lambda e: self._save_mine_tags())
        te.bind("<Return>", lambda e: self._save_mine_tags())
        label(row, "separate with commas", muted=True).pack(side="left")
        nf = tk.Frame(mt, bg=T["face"], relief="sunken", bd=2)
        nf.pack(fill="both", expand=True, pady=(8, 0))
        self.mine_notes = tk.Text(nf, bg=T["field"], fg=T["ink"], bd=0, highlightthickness=0, font=(UI[0], UI[1] + 1),
                                  wrap="word", padx=10, pady=8, height=5, undo=True, insertbackground=T["ink"])
        sb = ttk.Scrollbar(nf, orient="vertical", command=self.mine_notes.yview)
        self.mine_notes.configure(yscrollcommand=sb.set)
        self.mine_notes.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.mine_notes.bind("<KeyRelease>", lambda e: self._debounce("mine_notes", 800, self._save_mine_notes))
        self.mine_notes.bind("<FocusOut>", lambda e: self._save_mine_notes())
        label(mt, "Notes, tags and status are only for you. They're saved with the game in the cloud, so your other "
                  "PCs have them too.", muted=True, justify="left").pack(anchor="w", pady=(6, 0))

    def _render_mine(self):
        g = self.game
        if not g:
            return
        m = self.mine(g)
        switched = self._mine_game != g
        self._mine_game = g
        self.mine_status.set(mine.STATUSES.get(m.get("status"), NONE))
        focus = self.focus_get()
        if switched or focus is not self.mine_notes:        # not while the notes are being typed
            self.mine_notes.delete("1.0", "end")
            self.mine_notes.insert("end", m.get("notes", ""))
            self.mine_notes.edit_reset()
        if switched or focus is not self.mine_tags_entry:
            self.mine_tags.set(mine.tags_text(m))

    # what is typed always goes to the game the tab was showing, not the one just opened
    def _save_mine_status(self):
        key = next((k for k, v in mine.STATUSES.items() if v == self.mine_status.get()), None)
        if self._mine_game:
            self.set_mine(self._mine_game, status=key)

    def _save_mine_tags(self):
        if self._mine_game:
            self.set_mine(self._mine_game, tags=mine.parse_tags(self.mine_tags.get()))

    def _save_mine_notes(self):
        if self._mine_game:
            self.set_mine(self._mine_game, notes=self.mine_notes.get("1.0", "end"))
