"""Side-by-side comparison of one save file."""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from tkinter import ttk

from ...core.compare import decode_text, hex_diff_lines, text_diff_lines
from ...core.util import fmt_time, human_size
from ..theme import MONO, T
from ..widgets import Btn, label, window

if TYPE_CHECKING:
    from ..app import App


class DiffWindow(tk.Toplevel):
    def __init__(self, app: App, e, cloud: bytes | None, local: bytes | None):
        super().__init__(app)
        self.title(f"Compare — {e.path}")
        self.geometry("1060x680")
        self.configure(bg=T["desk"])
        outer, _bar, body = window(self, f"Compare  {e.path}", app.icon16)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        def side(name, fi):
            if fi is None:
                return f"{name}:  (file does not exist)"
            return f"{name}:  {human_size(fi.size)}    modified {fmt_time(fi.mtime)}    md5 {fi.md5[:12]}…"
        info = tk.Frame(body, bg=T["face"])
        info.pack(fill="x", pady=(2, 6))
        label(info, side("Cloud", e.cloud), fg="#a01828").pack(anchor="w")
        label(info, side("This PC", e.local), fg="#1d7a2e").pack(anchor="w")
        note = label(info, "", muted=True)
        note.pack(anchor="w", pady=(4, 0))

        frame = tk.Frame(body, bg=T["face"], relief="sunken", bd=2)
        frame.pack(fill="both", expand=True)
        txt = tk.Text(frame, bg=T["field"], fg=T["ink"], bd=0, highlightthickness=0, font=MONO,
                      wrap="none", padx=8, pady=6)
        vs = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        hs = ttk.Scrollbar(frame, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side="right", fill="y")
        hs.pack(side="bottom", fill="x")
        txt.pack(side="left", fill="both", expand=True)
        txt.tag_configure("add", foreground="#0f5e1f", background="#dcf3dc")
        txt.tag_configure("rem", foreground="#8f1020", background="#fbe0e2")
        txt.tag_configure("hunk", foreground=T["hi"], background=T["navy"])
        txt.tag_configure("meta", foreground="#707070")

        a, b = cloud or b"", local or b""
        ta, tb = decode_text(a), decode_text(b)
        if (ta or not a) and (tb or not b):
            sa, pa = ta or ("", False)
            sb, pb = tb or ("", False)
            lines = text_diff_lines(sa, sb)
            kind = "Text comparison" + (" (JSON pretty-printed)" if pa or pb else "")
            note.configure(text=f"{kind}.  Red lines (-) are only in the cloud, green lines (+) only on this PC."
                           if lines else f"{kind}: contents are identical.")
        else:
            summary, lines = hex_diff_lines(a, b)
            note.configure(text="Binary file.  " + summary)
        for ln, tag in lines:
            txt.insert("end", ln + "\n", tag)
        if not lines:
            txt.insert("end", "No differences.", "meta")
        txt.configure(state="disabled")
        Btn(body, "Close", self.destroy, kind="default", padx=18).pack(anchor="e", pady=(8, 0))
