"""The main window. Its features live in mixins: library, details, artwork, play and sync."""
from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox, ttk

from .. import APP_TITLE, VERSION, storage
from ..core import folders
from ..core.diff import EXCLUDED, SAME, auto_direction, compute_diff
from ..core.playtime import aggregate_stats
from ..core.settings import Settings
from .. import launcher
from ..paths import ASSETS, PortableError, app_dir
from .artwork import ArtworkMixin
from .details import DetailsMixin
from .dialogs.settings import SettingsDialog
from .info import InfoMixin
from .library import LibraryMixin
from .play import PlayMixin
from .sync import SyncMixin
from .theme import SMALL, UI, UIB, WIN, T
from .tray import TrayMixin
from .widgets import Btn, _mix, label, load_photo, menu, open_in_explorer, sunken_label, window

try:
    from PIL import ImageTk
    from . import theme_art
except Exception:            # Pillow missing: plain gradient banner, no mascot resizing
    ImageTk = theme_art = None


class App(LibraryMixin, DetailsMixin, ArtworkMixin, InfoMixin, PlayMixin, SyncMixin, TrayMixin, tk.Tk):
    def __init__(self, start_minimized=False):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1360x900")
        self.minsize(1080, 740)
        self.configure(bg=T["desk"])
        self.option_add("*Font", UI)

        self.icon16 = tk.PhotoImage(file=str(ASSETS / "icon16.png"))
        self.icon32 = tk.PhotoImage(file=str(ASSETS / "icon32.png"))
        self._apply_window_icon(None)

        self.settings = Settings()
        self.settings.data.setdefault("art_cache", {})
        self.settings.data.setdefault("info_cache", {})
        self.backend = None
        self.all_games: list[str] = []
        self.games: list[str] = []
        self.game: str | None = None          # game open in the details page
        self.selected: str | None = None      # highlighted cover in the library
        self.cfg: dict = {"excludes": []}
        self.local_scan: dict = {}
        self.cloud_scan: dict = {}
        self.diff: list = []
        self.entries: dict = {}
        self.stats_all: dict = aggregate_stats([{"games": self.settings.data.get("my_stats", {})}])
        self.sessions: dict = {}
        self.busy = False
        self.q: queue.Queue = queue.Queue()
        self.art_q: queue.Queue = queue.Queue()
        self.info_q: queue.Queue = queue.Queue()
        self._info_pending: set = set()         # games whose info is being reloaded
        self.photos: dict = {}
        self._tile_games: dict = {}
        self._jobs: dict = {}
        self._banner_img = self._mascot_img = self._hero_img = None

        self._style()
        self._build()
        self.load_mascot()
        self._start_tray()
        threading.Thread(target=self._art_worker, daemon=True).start()
        threading.Thread(target=self._info_worker, daemon=True).start()
        threading.Thread(target=self._watch_games, daemon=True).start()
        self.after(100, self._poll)
        self.after(300, self.connect)
        if start_minimized:
            self.minimize()

    def _apply_window_icon(self, photo):
        if WIN and (ASSETS / "icon.ico").is_file():
            try:
                self.iconbitmap(default=str(ASSETS / "icon.ico"))
            except tk.TclError:
                pass
        self.iconphoto(True, photo or self.icon32)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=T["face"], foreground=T["ink"], font=UI, bordercolor=T["shadow"],
                    lightcolor=T["hi"], darkcolor=T["shadow"], troughcolor="#d8d8d8", focuscolor=T["face"])
        s.configure("Treeview", background=T["field"], fieldbackground=T["field"], foreground=T["ink"],
                    rowheight=22, borderwidth=0, font=UI)
        s.configure("Treeview.Heading", background=T["face"], foreground=T["ink"], relief="raised",
                    borderwidth=2, padding=(4, 2), font=UI)
        s.map("Treeview.Heading", background=[("active", "#d0d0d0")])
        s.map("Treeview", background=[("selected", T["navy"])], foreground=[("selected", T["hi"])])
        s.configure("TNotebook", background=T["face"], borderwidth=0, tabmargins=(2, 4, 2, 0))
        s.configure("TNotebook.Tab", background=T["face"], foreground=T["ink"], padding=(12, 3),
                    borderwidth=2, lightcolor=T["hi"], bordercolor=T["shadow"], font=UI)
        s.map("TNotebook.Tab", background=[("selected", T["face"])], expand=[("selected", (2, 2, 2, 0))],
              font=[("selected", UIB)])
        s.configure("TCombobox", fieldbackground=T["field"], background=T["face"], arrowcolor=T["ink"])
        s.map("TCombobox", fieldbackground=[("readonly", T["field"])], foreground=[("readonly", T["ink"])],
              selectbackground=[("readonly", T["field"])], selectforeground=[("readonly", T["ink"])])
        for o in ("Vertical", "Horizontal"):
            s.configure(f"{o}.TScrollbar", background=T["face"], troughcolor="#dcdcdc", arrowcolor=T["ink"],
                        bordercolor=T["shadow"], lightcolor=T["hi"], darkcolor=T["shadow"], arrowsize=15)
            s.map(f"{o}.TScrollbar", background=[("active", T["face"])])

    def _field(self, parent, **kw):
        opts = dict(bg=T["field"], fg=T["ink"], selectbackground=T["navy"], selectforeground=T["hi"],
                    relief="sunken", bd=2, highlightthickness=0, font=UI)
        opts.update(kw)
        return opts

    def _debounce(self, key, ms, fn):
        if key in self._jobs:
            self.after_cancel(self._jobs[key])
        self._jobs[key] = self.after(ms, fn)

    def _build(self):
        self._build_taskbar()
        self.desk = tk.Frame(self, bg=T["desk"])
        self.desk.pack(fill="both", expand=True)
        self.desk.columnconfigure(0, weight=1)
        self.desk.rowconfigure(0, weight=1)
        content = tk.Frame(self.desk, bg=T["desk"])
        content.grid(row=0, column=0, sticky="nsew", padx=16, pady=(14, 10))
        self.mascot_lbl = tk.Label(self.desk, bg=T["desk"], bd=0, cursor="hand2")
        self.mascot_lbl.bind("<Button-1>", lambda e: self.about())

        def toggle_max():
            try:
                self.state("normal" if self.state() == "zoomed" else "zoomed")
            except tk.TclError:
                self.attributes("-zoomed", not self.attributes("-zoomed"))
        top, _bar, body = window(content, APP_TITLE, self.icon16,
                                 [("_", self.minimize), ("□", toggle_max), ("×", self.destroy)])
        top.pack(fill="x")

        mb = tk.Frame(body, bg=T["face"])
        mb.pack(fill="x")
        for name, items in (("File", [("Add game…", self.new_game), ("Settings…", self.open_settings),
                                      None, ("Exit", self.destroy)]),
                            ("View", [("Library", self.show_library), ("Refresh library", self.reload_games),
                                      None, ("Open backups folder", self.open_backups)]),
                            ("Help", [("About Mare Save Sync", self.about)])):
            m = menu(self)
            for it in items:
                if it is None:
                    m.add_separator()
                else:
                    m.add_command(label=it[0], command=lambda f=it[1]: f() if not self.busy else None)
            tk.Menubutton(mb, text=name, menu=m, bg=T["face"], fg=T["ink"], activebackground=T["navy"],
                          activeforeground=T["hi"], font=UI, padx=7, pady=1, relief="flat").pack(side="left")

        sr = tk.Frame(body, bg=T["face"], relief="groove", bd=2)
        sr.pack(fill="x", pady=(2, 4))
        label(sr, "Find game:").pack(side="left", padx=(6, 4), pady=4)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._apply_filter())
        e = tk.Entry(sr, textvariable=self.search_var, **self._field(sr))
        e.pack(side="left", fill="x", expand=True, pady=4)
        e.bind("<Return>", lambda ev: self._apply_filter(open_first=True))
        Btn(sr, "Go", lambda: self._apply_filter(open_first=True), padx=14).pack(side="left", padx=6, pady=3)

        bf = tk.Frame(body, bg=T["face"], relief="sunken", bd=2)
        bf.pack(fill="x")
        self.banner = tk.Canvas(bf, width=200, height=66, highlightthickness=0, bd=0, bg=T["t1"])
        self.banner.pack(fill="x")
        self.banner.bind("<Configure>", lambda e: self._debounce("banner", 120, self._draw_banner))

        st = tk.Frame(body, bg=T["face"])
        st.pack(fill="x", pady=(5, 0))
        self.status = sunken_label(st, "Ready", width=36)
        self.status.pack(side="left")
        self.count_lbl = sunken_label(st, "", width=12)
        self.count_lbl.pack(side="left", padx=3)
        self.backend_lbl = sunken_label(st, "Not connected")
        self.backend_lbl.pack(side="left", fill="x", expand=True)
        self.settings_btn = Btn(st, "Settings…", self.open_settings)
        self.settings_btn.pack(side="right", padx=(4, 0))
        self.signin_btn = Btn(st, "Sign in with Google", lambda: self.connect(interactive=True), kind="default")

        lw, self.lib_title, lbody = window(content, "Library", self.icon16)
        lw.pack(fill="both", expand=True, pady=(12, 0))
        self.lib_view = self._build_library(lbody)
        self.det_view = self._build_details(lbody)
        self.lib_view.pack(fill="both", expand=True)
        self._update_controls()

    def _build_taskbar(self):
        tb = tk.Frame(self, bg=T["face"], relief="raised", bd=2)
        tb.pack(side="bottom", fill="x")
        self.start_btn = Btn(tb, " Start", self._start_menu, image=self.icon16, compound="left",
                             font=UIB, padx=6)
        self.start_btn.pack(side="left", padx=2, pady=2)
        tk.Frame(tb, bg=T["shadow"], width=2).pack(side="left", fill="y", padx=4, pady=3)
        tk.Label(tb, text=" " + APP_TITLE, image=self.icon16, compound="left", bg="#d8d8d8", fg=T["ink"],
                 font=UIB, relief="sunken", bd=2, padx=8, anchor="w", width=180).pack(side="left", pady=2)
        self.task_game = tk.Label(tb, text="", bg=T["face"], fg=T["ink"], font=UI, relief="raised", bd=2,
                                  padx=8, anchor="w")
        self.clock = sunken_label(tb, "", padx=10)
        self.clock.pack(side="right", padx=2, pady=2)
        self._tick()

    def _tick(self):
        self.clock.configure(text=time.strftime("%I:%M %p").lstrip("0"))
        self.after(15000, self._tick)

    def _start_menu(self):
        m = menu(self)
        m.add_command(label="Add game…", command=self.new_game)
        recent = sorted(self.all_games, key=lambda g: -self.stats_all.get(g, {}).get("last_played", 0))[:6]
        if recent:
            m.add_separator()
            for g in recent:
                m.add_command(label=f"▶  {g}", command=lambda g=g: self.play(g))
        m.add_separator()
        m.add_command(label="Settings…", command=self.open_settings)
        m.add_command(label="Open backups folder", command=self.open_backups)
        m.add_command(label="About Mare Save Sync", command=self.about)
        m.add_separator()
        m.add_command(label="Exit", command=self.destroy)
        m.update_idletasks()
        m.tk_popup(self.start_btn.winfo_rootx(), self.start_btn.winfo_rooty() - m.winfo_reqheight())

    def _draw_banner(self):
        c = self.banner
        w, h = c.winfo_width(), c.winfo_height()
        c.delete("all")
        if theme_art is not None:
            self._banner_img = ImageTk.PhotoImage(theme_art.render_banner(w, h, APP_TITLE))
            c.create_image(0, 0, image=self._banner_img, anchor="nw")
        else:
            for i in range(48):
                c.create_rectangle(w * i / 48, 0, w * (i + 1) / 48 + 1, h, width=0,
                                   fill=_mix("#0d0b70", "#2f64d6", i / 47))
            c.create_text(w // 2, int(h * 0.36), text=APP_TITLE, fill=T["hi"], font=(UI[0], 18, "bold"))
        c.create_text(w // 2, int(h * 0.78), fill="#e6ebff", font=SMALL,
                      text="Your games, your saves, every PC — press Play and the dream picks up where you left off.")

    def load_mascot(self):
        s = self.settings.data
        p = s.get("mascot_path")
        self._mascot_img = None
        if p and Path(p).is_file():
            try:
                self._mascot_img = load_photo(p, 220, 440)
                self.mascot_lbl.configure(image=self._mascot_img)
                self.mascot_lbl.grid(row=0, column=1, sticky="se", padx=(0, 10), pady=(0, 4))
                if s.get("mascot_icon"):
                    self._mascot_icon = load_photo(p, square=64)
                    self._apply_window_icon(self._mascot_icon)
                else:
                    self._apply_window_icon(None)
                return
            except Exception as ex:
                self.log(f"Could not load mascot image: {ex}")
        self.mascot_lbl.grid_remove()
        self._apply_window_icon(None)

    def open_backups(self):
        d = app_dir() / "backups"
        d.mkdir(exist_ok=True)
        open_in_explorer(d)

    def about(self):
        messagebox.showinfo(f"About {APP_TITLE}", f"{APP_TITLE}  v{VERSION}\n\n"
                            "A small game launcher that keeps your saves and playtime in sync across PCs "
                            "through Google Drive.\n\nCover art: SteamGridDB.\n"
                            "Title font: Pixelify Sans (SIL Open Font License).", parent=self)

    _backend_desc = "Not connected"

    def log(self, msg: str):
        self.log_txt.configure(state="normal")
        self.log_txt.insert("end", f"{time.strftime('%H:%M:%S')}  {msg}\n")
        self.log_txt.see("end")
        self.log_txt.configure(state="disabled")

    def log_ts(self, msg: str):
        self.q.put(("log", msg))

    def note(self, msg):
        self.log(msg)
        self.status.configure(text=msg if len(msg) < 60 else msg[:57] + "…")
        self.after(6000, lambda: self.status.configure(text="Ready") if not self.busy else None)

    def run_bg(self, label_, fn, done=None, failed=None):
        if self.busy:
            messagebox.showinfo(APP_TITLE, "Please wait for the current task to finish.", parent=self)
            return
        self._set_busy(True, label_)

        def worker():
            try:
                self.q.put(("done", done, fn()))
            except Exception as ex:
                self.q.put(("error", label_, ex, traceback.format_exc(), failed))
        threading.Thread(target=worker, daemon=True).start()

    def when_idle(self, fn):
        if self.busy:
            self.after(700, lambda: self.when_idle(fn))
        else:
            fn()

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log(item[1])
                elif kind == "art":
                    self._remember_art(item[1], item[2])
                elif kind == "info":
                    self._remember_info(item[1], item[2])
                elif kind == "tray":
                    self._tray_event(item[1])
                elif kind == "game_detected":
                    self._on_game_detected(item[1], item[2])
                elif kind == "game_end":
                    self._on_game_end(*item[1:])
                elif kind == "done":
                    self._set_busy(False)
                    if item[1]:
                        try:
                            item[1](item[2])
                        except Exception as ex:
                            self.log(f"Error: {ex}")
                            traceback.print_exc()
                else:
                    _, label_, ex, tb, failed = item
                    self._set_busy(False)
                    print(tb, file=sys.stderr)
                    self.log(f"{label_} failed: {ex}")
                    if failed:
                        failed(ex)
                    else:
                        messagebox.showerror(f"{label_} failed", str(ex), parent=self)
                    if label_ == "Connecting" and self.backend is None:
                        if self.settings.data.get("backend") == "gdrive":
                            self._show_signed_out()
                        else:
                            self._set_backend_desc("Not connected")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _set_busy(self, busy, label_=""):
        self.busy = busy
        self.status.configure(text=f"{label_}…" if busy else "Ready")
        self.configure(cursor="watch" if busy else "")
        self._update_controls()

    def _update_controls(self):
        connected = self.backend is not None and not self.busy
        g = self.game
        has_game = connected and g is not None
        has_path = has_game and bool(self._local_path())
        on = lambda b, ok: b.state(["!disabled"] if ok else ["disabled"])  # noqa: E731
        on(self.new_btn, connected)
        on(self.reload_btn, connected)
        on(self.play_btn, g is not None and not self.busy)
        for b in (self.refresh_btn, self.clear_btn):
            on(b, has_game)
        for b in (self.up_btn, self.down_btn):
            on(b, has_path and g not in self.sessions)
        for b, ok in self.folder_btns:
            on(b, has_game and ok)
        on(self.excl_btns[0], has_path)
        on(self.excl_btns[1], has_path)
        on(self.excl_btns[2], has_game)
        on(self.excl_btns[3], has_game)

    def _local_path(self, g=None):
        g = g or self.game
        if not g:
            return None
        return self.settings.data.get("games", {}).get(g, {}).get("local_path")

    def _roots(self, g, cfg) -> dict:
        """{folder id: path on this PC or None} of every save folder of the game (see core/folders.py)."""
        return folders.local_roots(self.settings.data.get("games", {}).get(g, {}), cfg)

    def _diff(self, g, cfg, local, cloud):
        gs = self.settings.data.get("games", {}).get(g, {})
        return compute_diff(local, cloud, cfg.get("excludes", []), gs.get("base", {}),
                            folders.unset_prefixes(gs, cfg))

    def _save_mirror(self):
        self.settings.data["mirror_deletes"] = self.mirror_var.get()
        self.settings.save()

    def _save_args(self):
        if self.game:
            self.settings.game(self.game)["args"] = self.args_var.get().strip()
            self.settings.save()

    def _save_auto(self):
        if self.game:
            self.settings.game(self.game)["auto_sync"] = self.auto_var.get()
            self.settings.save()

    def _set_state(self, g, state):
        gs = self.settings.game(g)
        if gs.get("state") != state:
            gs["state"] = state
            self.settings.save()
        if self.game == g:
            self._draw_hero()
        elif self.lib_view.winfo_ismapped():
            self._debounce("grid", 100, self._layout_grid)

    def _state_from(self, diff):
        pending = [e for e in diff if e.status not in (SAME, EXCLUDED)]
        if not pending:
            return "synced"
        return "conflict" if auto_direction(diff) == "ask" else "changes"

    def _set_backend_desc(self, text):
        self._backend_desc = text
        if not self.game:
            self.backend_lbl.configure(text=text)

    def connect(self, interactive=False):
        s = self.settings.data
        if s.get("backend") not in ("gdrive", "folder"):
            self.open_settings(first_run=True)
            return
        self.signin_btn.pack_forget()

        def work():
            if s["backend"] == "gdrive":
                b = storage.DriveBackend(storage.find_client_config(), app_dir() / "token.json",
                                          interactive=interactive)
            else:
                b = storage.FolderBackend(s.get("folder_root", ""))
            b = storage.Locked(b)
            return b, b.describe(), b.list_games(), b.read_all_stats()

        def done(res):
            self.backend, desc, games, stats = res
            self._set_backend_desc(f"Connected  ·  {desc}")
            self.log(f"Connected to {desc}")
            self._merge_stats(stats)
            self._set_games(games)
            for g in games:
                self.fetch_meta(g)

        if s["backend"] == "gdrive" and not interactive and not (app_dir() / "token.json").is_file():
            self._show_signed_out()
            return
        self._set_backend_desc("Waiting for Google sign-in in your browser…"
                               if interactive and s["backend"] == "gdrive" else "Connecting…")
        self.run_bg("Connecting", work, done)

    def _show_signed_out(self):
        self.backend = None
        self._set_backend_desc("Not signed in")
        self.signin_btn.pack(side="right", padx=(4, 0), before=self.settings_btn)
        self._update_controls()

    def open_settings(self, first_run=False):
        SettingsDialog(self, first_run)


def main():
    if WIN:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MareSaveSync")
        except Exception:
            pass
    try:
        app_dir()                              # the portable exe refuses to keep data anywhere but its folder
    except PortableError as ex:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, str(ex), parent=root)
        root.destroy()
        return
    launcher.refresh_startup()                 # the folder may have moved since "Start with Windows" was set
    App(start_minimized="--minimized" in sys.argv).mainloop()
