"""The log file (applog.py), with a button that copies what a bug report needs."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import TYPE_CHECKING

from ... import applog
from ..theme import MONO, T
from ..widgets import Btn, check, label, open_in_explorer, window

if TYPE_CHECKING:
    from ..app import App

SHOWN_LINES = 3000


class LogWindow(tk.Toplevel):
    def __init__(self, app: App):
        super().__init__(app)
        self.app = app
        self.title("Log — Mare Save Sync")
        self.geometry("1100x680")
        self.configure(bg=T["desk"])
        outer, _bar, body = window(self, "Log", app.icon16)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        top = tk.Frame(body, bg=T["face"])
        top.pack(fill="x", pady=(2, 6))
        label(top, "Everything the app did, kept across restarts. When something goes wrong, Copy for bug "
                   "report and paste it into a GitHub issue.", justify="left").pack(side="left")
        self.errors_only = tk.BooleanVar(value=False)
        check(top, "Errors only", self.errors_only, self.reload).pack(side="right")

        frame = tk.Frame(body, bg=T["face"], relief="sunken", bd=2)
        frame.pack(fill="both", expand=True)
        self.txt = tk.Text(frame, bg=T["field"], fg=T["ink"], bd=0, highlightthickness=0, font=MONO,
                           wrap="none", padx=8, pady=6)
        vs = ttk.Scrollbar(frame, orient="vertical", command=self.txt.yview)
        hs = ttk.Scrollbar(frame, orient="horizontal", command=self.txt.xview)
        self.txt.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side="right", fill="y")
        hs.pack(side="bottom", fill="x")
        self.txt.pack(side="left", fill="both", expand=True)
        self.txt.tag_configure("error", foreground="#a01828")
        self.txt.tag_configure("start", foreground=T["hi"], background=T["navy"])

        bot = tk.Frame(body, bg=T["face"])
        bot.pack(fill="x", pady=(8, 0))
        Btn(bot, "Copy for bug report", self.copy_report, kind="default").pack(side="left")
        Btn(bot, "Report a problem on GitHub…", lambda: webbrowser.open(applog.ISSUES_URL)).pack(side="left", padx=6)
        Btn(bot, "Open log folder", lambda: open_in_explorer(applog.log_dir())).pack(side="left")
        Btn(bot, "Close", self.destroy, padx=18).pack(side="right")
        Btn(bot, "Refresh", self.reload).pack(side="right", padx=6)
        self.info = label(bot, "", muted=True, anchor="w")      # packed last: the buttons keep their room
        self.info.pack(side="left", padx=10, fill="x", expand=True)
        self.reload()

    def reload(self):
        lines = applog.tail(SHOWN_LINES)
        if self.errors_only.get():
            keep, inside = [], False
            for ln in lines:                    # an error's traceback lines don't start with a date
                starts = ln[:4].isdigit()
                if starts:
                    inside = " ERROR " in ln[:40] or "=====" in ln
                if inside:
                    keep.append(ln)
            lines = keep
        t = self.txt
        t.configure(state="normal")
        t.delete("1.0", "end")
        tag = ""
        for ln in lines:
            if ln[:4].isdigit():
                tag = "start" if "=====" in ln else "error" if " ERROR " in ln[:40] else ""
            t.insert("end", ln + "\n", tag)
        if not lines:
            t.insert("end", "No errors logged." if self.errors_only.get() else "The log is empty.")
        t.configure(state="disabled")
        t.see("end")
        self.info.configure(text=f"data\\logs\\{applog.LOG_NAME}")

    def copy_report(self):
        a = self.app
        storage = ("Google Drive" if a.backend.kind == "gdrive" else "Synced folder") if a.backend is not None \
            else f"not connected ({a.settings.data.get('backend') or 'not set up'})"
        report = applog.bug_report(storage, len(a.all_games))
        self.clipboard_clear()
        self.clipboard_append(report)
        self.info.configure(text=f"Copied ({len(report.splitlines())} lines, your user name taken out) — "
                                 "paste it into the issue")
