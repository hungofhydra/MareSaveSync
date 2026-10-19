"""Asks which side's saves to keep when both changed."""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from tkinter import ttk

from ...core.diff import EXCLUDED, SAME
from ...core.util import fmt_time, human_size
from ..theme import T
from ..widgets import Btn, TitleBar, center_modal, label

if TYPE_CHECKING:
    from ..app import App


class ConflictDialog(tk.Toplevel):
    """Asks which side wins. result: "up", "down", "skip" or "cancel"."""

    def __init__(self, app: App, game, diff, moment):
        super().__init__(app)
        self.result = "cancel" if moment == "before" else "skip"
        self.title(f"Save conflict — {game}")
        self.configure(bg=T["face"])
        self.resizable(False, False)
        self.transient(app)
        TitleBar(self, f"Save conflict — {game}", app.icon16).pack(fill="x", padx=2, pady=2)
        f = tk.Frame(self, bg=T["face"], padx=14, pady=10)
        f.pack(fill="both", expand=True)
        when = "before starting the game" if moment == "before" else "after you played"
        label(f, f"This PC and the cloud both have different saves ({when}).", bold=True).pack(anchor="w")
        label(f, "Which saves do you want to keep? The other side's files are zipped to a backup first.",
              justify="left").pack(anchor="w", pady=(2, 8))
        tf = tk.Frame(f, bg=T["face"], relief="sunken", bd=2)
        tf.pack(fill="x")
        pending = [e for e in diff if e.status not in (SAME, EXCLUDED)]
        tv = ttk.Treeview(tf, columns=("pc", "cloud", "note"), show="tree headings",
                          height=min(8, max(3, len(pending))))
        tv.heading("#0", text="File", anchor="w")
        tv.column("#0", width=230)
        for col, t, w in (("pc", "This PC", 185), ("cloud", "Cloud", 185), ("note", "Note", 170)):
            tv.heading(col, text=t, anchor="w")
            tv.column(col, width=w, anchor="w")
        for e in pending:
            def side(fi):
                return f"{human_size(fi.size)} · {fmt_time(fi.mtime)}" if fi else "—"
            tv.insert("", "end", text="  " + e.path, values=(side(e.local), side(e.cloud), e.hint),
                      tags=("conflict",) if e.changed_side in ("both", None) else ())
        tv.tag_configure("conflict", foreground="#c0182b")
        tv.pack(fill="x")
        newest_local = max((e.local.mtime for e in pending if e.local), default=0)
        newest_cloud = max((e.cloud.mtime for e in pending if e.cloud), default=0)
        hint = ("This PC has the newest file." if newest_local > newest_cloud
                else "The cloud has the newest file." if newest_cloud > newest_local else "")
        if hint:
            label(f, hint, muted=True).pack(anchor="w", pady=(6, 0))
        b = tk.Frame(f, bg=T["face"])
        b.pack(fill="x", pady=(12, 0))
        Btn(b, "Keep this PC's saves (upload)", lambda: self._pick("up"),
            kind="default" if newest_local >= newest_cloud else "").pack(side="left")
        Btn(b, "Keep cloud saves (download)", lambda: self._pick("down"),
            kind="default" if newest_cloud > newest_local else "").pack(side="left", padx=6)
        if moment == "before":
            Btn(b, "Cancel launch", lambda: self._pick("cancel")).pack(side="right")
            Btn(b, "Play without syncing", lambda: self._pick("skip")).pack(side="right", padx=6)
        else:
            Btn(b, "Decide later", lambda: self._pick("skip")).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        center_modal(self, app)

    def _pick(self, r):
        self.result = r
        self.destroy()
