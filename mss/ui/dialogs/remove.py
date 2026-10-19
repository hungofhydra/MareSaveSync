"""Remove a game from the library, optionally purging its cloud data."""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from ..theme import T
from ..widgets import Btn, TitleBar, center_modal, check, label

if TYPE_CHECKING:
    from ..app import App


class RemoveDialog(tk.Toplevel):
    """Remove a game from the library. result: None (cancelled), False (just hide it) or True (purge all data)."""

    def __init__(self, app: App, game):
        super().__init__(app)
        self.result = None
        self.title("Remove from library")
        self.configure(bg=T["face"])
        self.resizable(False, False)
        self.transient(app)
        TitleBar(self, "Remove from library", app.icon16).pack(fill="x", padx=2, pady=2)
        f = tk.Frame(self, bg=T["face"], padx=14, pady=10)
        f.pack(fill="both", expand=True)
        label(f, f"Remove “{game}” from the library?", bold=True).pack(anchor="w")
        label(f, "Its cloud saves, artwork and playtime are kept, and come back if you add the game again\n"
                 "with the same name. Files on this PC are never touched.", justify="left").pack(anchor="w", pady=(2, 8))
        self.purge = tk.BooleanVar(value=False)
        check(f, "Purge all data", self.purge, self._update).pack(anchor="w")
        trash = "moved to your Google Drive trash" if app.backend.kind == "gdrive" else "deleted"
        self.warn = label(f, f"Cloud saves, cover art, playtime and exclusions for this game are {trash}\n"
                             "for every PC.", justify="left", fg="#b3261e")
        b = tk.Frame(f, bg=T["face"])
        b.pack(fill="x", side="bottom", pady=(10, 0))
        Btn(b, "Cancel", self.destroy).pack(side="right")
        self.ok = Btn(b, "Remove", self._done, kind="default")
        self.ok.pack(side="right", padx=6)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        center_modal(self, app)

    def _update(self):
        if self.purge.get():
            self.warn.pack(anchor="w", padx=(22, 0))
            self.ok.configure(text="Purge and remove")
        else:
            self.warn.pack_forget()
            self.ok.configure(text="Remove")

    def _done(self):
        self.result = self.purge.get()
        self.destroy()
