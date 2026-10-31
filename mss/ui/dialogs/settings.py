"""Settings: storage, startup, artwork key, appearance."""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
import json
from pathlib import Path
from tkinter import filedialog, messagebox

from ... import APP_TITLE, launcher, storage
from ...paths import app_dir
from ..theme import UIB, T
from ..widgets import Btn, TitleBar, check, label

if TYPE_CHECKING:
    from ..app import App


class SettingsDialog(tk.Toplevel):
    def __init__(self, app: App, first_run=False):
        super().__init__(app)
        self.app = app
        self.title(f"{APP_TITLE} — Settings")
        self.configure(bg=T["face"])
        self.resizable(False, False)
        self.transient(app)
        s = app.settings.data
        self.root = tk.StringVar(value=s.get("folder_root", ""))
        self.mascot = tk.StringVar(value=s.get("mascot_path", ""))
        self.mascot_icon = tk.BooleanVar(value=s.get("mascot_icon", False))
        self.key = tk.StringVar(value=s.get("sgdb_key", ""))
        self.startup = tk.BooleanVar(value=launcher.get_startup())
        self.start_fs = tk.BooleanVar(value=s.get("start_fullscreen", False))

        bar = TitleBar(self, "Welcome to Mare Save Sync" if first_run else "Settings", app.icon16)
        bar.pack(fill="x", padx=2, pady=2)
        cols = tk.Frame(self, bg=T["face"], padx=12, pady=10)
        cols.pack(fill="both", expand=True)
        left = tk.Frame(cols, bg=T["face"])
        left.pack(side="left", fill="both", anchor="n")
        right = tk.Frame(cols, bg=T["face"])
        right.pack(side="left", fill="both", anchor="n", padx=(12, 0))

        def group(parent, title):
            g = tk.LabelFrame(parent, text=f" {title} ", bg=T["face"], fg=T["ink"], font=UIB, bd=2,
                              relief="groove", padx=10, pady=8)
            g.pack(fill="x", pady=(0, 10))
            return g

        g = group(left, "Storage: Google Drive")
        label(g, "Saves and playtime go to a MareSaveSync folder in your My Drive.\n"
                 "The app can only see files it created.", justify="left").pack(anchor="w", pady=(0, 6))
        token = app_dir() / "token.json"
        has_client = storage.find_client_config() is not None
        row = tk.Frame(g, bg=T["face"])
        row.pack(fill="x")
        self.google_btn = Btn(row, "Sign in with Google", self._use_google, kind="default")
        self.google_btn.pack(side="left")
        if token.is_file():
            Btn(row, "Sign out", self._sign_out).pack(side="left", padx=(6, 0))
            if s.get("backend") == "gdrive":
                label(row, "✓ Signed in", fg="#1d7a2e").pack(side="left", padx=10)
        if not has_client:
            self.google_btn.state(["disabled"])
            label(g, "No Google client ID built in. Load a credentials.json once:", muted=True).pack(anchor="w", pady=(8, 4))
            Btn(g, "Load credentials.json…", self._load_client).pack(anchor="w")

        d = group(left, "Storage: a synced folder")
        label(d, "For example your Google Drive for desktop folder (G:\\My Drive).").pack(anchor="w", pady=(0, 6))
        row = tk.Frame(d, bg=T["face"])
        row.pack(fill="x")
        tk.Entry(row, textvariable=self.root, width=34, **app._field(row)).pack(side="left", fill="x", expand=True)
        Btn(row, "Browse…", self._pick_root).pack(side="left", padx=(6, 0))
        Btn(row, "Use", self._use_folder).pack(side="left", padx=(6, 0))

        st = group(left, "Startup")
        check(st, "Start Mare Save Sync with Windows (minimized)", self.startup, self._toggle_startup).pack(anchor="w")

        a = group(right, "Artwork (SteamGridDB)")
        label(a, "Covers and banners come from SteamGridDB. Get a free API key:\n"
                 "steamgriddb.com → log in → Preferences → API.", justify="left").pack(anchor="w", pady=(0, 6))
        row = tk.Frame(a, bg=T["face"])
        row.pack(fill="x")
        tk.Entry(row, textvariable=self.key, width=36, show="•", **app._field(row)).pack(side="left", fill="x", expand=True)
        Btn(row, "Save key", self._save_key).pack(side="left", padx=(6, 0))

        ap = group(right, "Appearance")
        label(ap, "Mascot image for the corner of the desktop\n(PNG with transparency looks best).",
              justify="left").pack(anchor="w", pady=(0, 6))
        row = tk.Frame(ap, bg=T["face"])
        row.pack(fill="x")
        tk.Entry(row, textvariable=self.mascot, width=30, **app._field(row)).pack(side="left", fill="x", expand=True)
        Btn(row, "Browse…", self._pick_mascot).pack(side="left", padx=(6, 0))
        Btn(row, "Clear", lambda: self.mascot.set("")).pack(side="left", padx=(6, 0))
        check(ap, "Also use it as the window and taskbar icon", self.mascot_icon).pack(anchor="w", pady=(6, 0))
        Btn(ap, "Apply appearance", self._apply_appearance).pack(anchor="e", pady=(6, 0))

        fs = group(right, "Fullscreen mode")
        label(fs, "A full-screen view for handheld PCs, made for an Xbox controller\n"
                  "(like Steam Big Picture). F11 switches it on and off.", justify="left").pack(anchor="w", pady=(0, 6))
        check(fs, "Start in Fullscreen mode", self.start_fs, self._save_start_fs).pack(anchor="w")
        exe, args = launcher.app_command()
        args = " ".join(f'"{a}"' for a in args + ["--fullscreen"]).replace('"--fullscreen"', "--fullscreen")
        label(fs, f"AnyFSE: choose a Custom launcher with this program and the\nargument  {args}",
              muted=True, justify="left", wraplength=380).pack(anchor="w", pady=(6, 2))
        row = tk.Frame(fs, bg=T["face"])
        row.pack(fill="x")
        e = tk.Entry(row, width=30, **app._field(row))
        e.insert(0, exe)
        e.configure(state="readonly", readonlybackground=T["field"])
        e.pack(side="left", fill="x", expand=True)
        Btn(row, "Copy", lambda: (self.clipboard_clear(), self.clipboard_append(exe))).pack(side="left", padx=(6, 0))
        Btn(fs, "Open Fullscreen mode", self._open_fullscreen, kind="default").pack(anchor="e", pady=(8, 0))

        Btn(right, "Close", self.destroy, padx=18).pack(anchor="e", side="bottom")
        self.grab_set()

    def _toggle_startup(self):
        try:
            launcher.set_startup(self.startup.get())
        except OSError as ex:
            self.startup.set(False)
            messagebox.showerror("Startup", str(ex), parent=self)

    def _save_start_fs(self):
        self.app.settings.data["start_fullscreen"] = self.start_fs.get()
        self.app.settings.save()

    def _open_fullscreen(self):
        self.destroy()
        self.app.enter_fullscreen()

    def _save_key(self):
        self.app.settings.data["sgdb_key"] = self.key.get().strip()
        self.app.settings.save()
        for g in self.app.all_games:
            self.app.fetch_meta(g)
        self.app.note("SteamGridDB key saved — fetching artwork and game info")

    def _pick_root(self):
        p = filedialog.askdirectory(parent=self, title="Storage folder")
        if p:
            self.root.set(p)

    def _pick_mascot(self):
        p = filedialog.askopenfilename(parent=self, title="Mascot image", filetypes=[
            ("Images", "*.png *.gif *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")])
        if p:
            self.mascot.set(p)

    def _apply_appearance(self):
        p = self.mascot.get().strip()
        if p and not Path(p).is_file():
            messagebox.showerror("Appearance", "That image file doesn't exist.", parent=self)
            return
        self.app.settings.data.update(mascot_path=p, mascot_icon=self.mascot_icon.get())
        self.app.settings.save()
        self.app.load_mascot()

    def _load_client(self):
        p = filedialog.askopenfilename(parent=self, title="credentials.json",
                                       filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not p:
            return
        try:
            data = json.loads(Path(p).read_text("utf-8"))
            assert "installed" in data or "web" in data
        except Exception:
            messagebox.showerror("Settings", "That isn't an OAuth client file from Google Cloud.", parent=self)
            return
        (app_dir() / "credentials.json").write_text(json.dumps(data), "utf-8")
        self.destroy()
        SettingsDialog(self.app)

    def _sign_out(self):
        (app_dir() / "token.json").unlink(missing_ok=True)
        if self.app.settings.data.get("backend") == "gdrive":
            self.app.show_library()
            self.app._set_games([])
            self.app._show_signed_out()
        self.destroy()
        SettingsDialog(self.app)

    def _apply(self, **kw):
        self.app.settings.data.update(kw)
        self.app.settings.save()
        self.destroy()
        self.app.backend = None
        self.app.show_library()
        self.app._set_games([])

    def _use_google(self):
        self._apply(backend="gdrive")
        self.app.connect(interactive=True)

    def _use_folder(self):
        if not Path(self.root.get()).is_dir():
            messagebox.showerror("Settings", "Choose an existing folder.", parent=self)
            return
        self._apply(backend="folder", folder_root=self.root.get())
        self.app.connect()
