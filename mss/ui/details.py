"""Game page: header, save folder, the file diff and exclusions."""
from __future__ import annotations

import os
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..art import images
from ..core.diff import CHANGED, CLOUD_ONLY, EXCLUDED, LOCAL_ONLY, SAME, compute_diff
from ..core.excludes import matching_patterns
from ..core.playtime import fmt_ago, fmt_play_long
from ..core.scan import scan_folder
from ..core.util import escape_pattern, fmt_time, human_size
from .dialogs.metadata import MetadataDialog
from .dialogs.diff_window import DiffWindow
from .theme import HERO_BAR, HERO_H, MONO, UI, UIB, C, T
from .widgets import Btn, check, label, menu, open_in_explorer

try:
    from PIL import ImageTk
    from . import theme_art
except Exception:
    ImageTk = theme_art = None

STATUS_LABEL = {SAME: "Same", LOCAL_ONLY: "Only on this PC", CLOUD_ONLY: "Only in cloud",
                CHANGED: "Different", EXCLUDED: "Excluded"}


class DetailsMixin:
    """Part of App (see ui/app.py)."""

    def _build_details(self, parent):
        f = tk.Frame(parent, bg=T["face"])
        top = tk.Frame(f, bg=T["face"])
        top.pack(fill="x", pady=(2, 6))
        Btn(top, "◀  Library", self.show_library).pack(side="left")
        self.d_title = label(top, "", font=(UI[0], UI[1] + 4, "bold"))
        self.d_title.pack(side="left", padx=12)

        hf = tk.Frame(f, relief="sunken", bd=2, bg=T["dark"])
        hf.pack(fill="x")
        self.hero_c = tk.Canvas(hf, width=200, height=HERO_H, highlightthickness=0, bd=0, bg=T["t1"])
        self.hero_c.pack(fill="x")
        self.hero_c.bind("<Configure>", lambda e: self._debounce("hero", 100, self._draw_hero))
        self.play_btn = Btn(self.hero_c, "▶  Play", self.play_current, kind="default", padx=18, pady=3)
        self.down_btn = Btn(self.hero_c, "▼ Sync down", lambda: self.sync("down"), pady=3)
        self.up_btn = Btn(self.hero_c, "▲ Sync up", lambda: self.sync("up"), pady=3)
        self.opt_btn = Btn(self.hero_c, "Options ▾", self._options_menu, pady=3)

        nb = ttk.Notebook(f)
        nb.pack(fill="both", expand=True, pady=(8, 0))
        self._build_about_tab(nb)

        # saves tab
        dt = tk.Frame(nb, bg=T["face"], padx=6, pady=6)
        nb.add(dt, text="Saves")
        pr = tk.Frame(dt, bg=T["face"])
        pr.pack(fill="x")
        label(pr, "Save folder on this PC:").pack(side="left")
        self.path_lbl = tk.Label(pr, text="—", bg=T["field"], fg=T["ink"], font=UI, relief="sunken", bd=2,
                                 anchor="w", padx=4)
        self.path_lbl.pack(side="left", fill="x", expand=True, padx=6, ipady=1)
        self.choose_btn = Btn(pr, "Choose…", self.choose_folder_menu)
        self.choose_btn.pack(side="left")
        self.open_btn = Btn(pr, "Open", lambda: open_in_explorer(Path(self._local_path())))
        self.open_btn.pack(side="left", padx=(4, 0))
        ft = tk.Frame(dt, bg=T["face"])
        ft.pack(fill="x", pady=6)
        self.mirror_var = tk.BooleanVar(value=self.settings.data.get("mirror_deletes", True))
        check(ft, "Mirror deletions", self.mirror_var, self._save_mirror).pack(side="left")
        self.show_same = tk.BooleanVar(value=True)
        self.show_excl = tk.BooleanVar(value=True)
        check(ft, "Show unchanged", self.show_same, self.render_diff).pack(side="left", padx=(14, 0))
        check(ft, "Show excluded", self.show_excl, self.render_diff).pack(side="left", padx=10)
        self.refresh_btn = Btn(ft, "Refresh diff", self.refresh_diff)
        self.refresh_btn.pack(side="right")
        tf = tk.Frame(dt, bg=T["face"], relief="sunken", bd=2)
        tf.pack(fill="both", expand=True)
        cols = ("status", "lsize", "ltime", "csize", "ctime", "hint")
        self.tree = ttk.Treeview(tf, columns=cols, show="tree headings", selectmode="browse", height=5)
        self.tree.heading("#0", text="File", anchor="w")
        self.tree.column("#0", width=200, minwidth=120, anchor="w", stretch=True)
        for col, title, w, anchor in [("status", "Status", 98, "w"), ("lsize", "This PC", 62, "e"),
                                      ("ltime", "PC modified", 120, "w"), ("csize", "Cloud", 62, "e"),
                                      ("ctime", "Cloud modified", 120, "w"), ("hint", "Note", 150, "w")]:
            self.tree.heading(col, text=title, anchor=anchor)
            self.tree.column(col, width=w, minwidth=40, anchor=anchor, stretch=col == "hint")
        vs = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        for tag, color in ((SAME, "#7a7a7a"), (LOCAL_ONLY, "#1d7a2e"), (CLOUD_ONLY, "#1f4fbf"),
                           (CHANGED, "#a35400"), (EXCLUDED, "#a8a8a8"), ("conflict", "#c0182b")):
            self.tree.tag_configure(tag, foreground=color)
        self.tree.bind("<Double-1>", self.on_tree_double)
        self.tree.bind("<Button-3>", self.on_tree_menu)
        self.tree.bind("<Button-2>", self.on_tree_menu)
        self.menu = menu(self)
        bot = tk.Frame(dt, bg=T["face"])
        bot.pack(fill="x", pady=(4, 0))
        self.summary_lbl = label(bot, "", anchor="w")
        self.summary_lbl.pack(side="left")
        label(bot, "Double-click: compare  ·  Right-click: exclude", muted=True).pack(side="right")

        # exclusions tab
        et = tk.Frame(nb, bg=T["face"], padx=8, pady=8)
        nb.add(et, text="Exclusions")
        label(et, "Excluded files and folders are never uploaded, downloaded or deleted. The list is stored "
                  "with the game in the cloud, so every PC uses it.", justify="left",
              wraplength=760).pack(anchor="w", pady=(0, 6))
        ef = tk.Frame(et, bg=T["face"])
        ef.pack(fill="both", expand=True)
        self.excl_list = tk.Listbox(ef, selectmode="extended", activestyle="none", height=5,
                                    **self._field(ef, font=MONO))
        self.excl_list.pack(side="left", fill="both", expand=True)
        eb = tk.Frame(ef, bg=T["face"], padx=8)
        eb.pack(side="left", fill="y")
        self.excl_btns = [Btn(eb, "Add file…", self.exclude_pick_file),
                          Btn(eb, "Add folder…", self.exclude_pick_folder),
                          Btn(eb, "Add pattern…", self.exclude_pattern),
                          Btn(eb, "Remove", self.exclude_remove, kind="danger")]
        for b in self.excl_btns:
            b.pack(fill="x", pady=(0, 4))
        label(et, "/Player.log  /Screenshots → relative to the save folder     *.log  Cache → that name anywhere"
                  "     * ? → wildcards", muted=True).pack(anchor="w", pady=(6, 0))

        # game tab
        gt = tk.Frame(nb, bg=T["face"], padx=10, pady=8)
        nb.add(gt, text="Game")
        r = tk.Frame(gt, bg=T["face"])
        r.pack(fill="x")
        label(r, "Game executable on this PC:", width=24, anchor="w").pack(side="left")
        self.exe_lbl = tk.Label(r, text="—", bg=T["field"], fg=T["ink"], font=UI, relief="sunken", bd=2,
                                anchor="w", padx=4)
        self.exe_lbl.pack(side="left", fill="x", expand=True, padx=6, ipady=1)
        self.exe_btn = Btn(r, "Browse…", lambda: self.pick_exe(self.game))
        self.exe_btn.pack(side="left")
        r = tk.Frame(gt, bg=T["face"])
        r.pack(fill="x", pady=(6, 0))
        label(r, "Launch options:", width=24, anchor="w").pack(side="left")
        self.args_var = tk.StringVar()
        ae = tk.Entry(r, textvariable=self.args_var, **self._field(r))
        ae.pack(side="left", fill="x", expand=True, padx=6)
        ae.bind("<FocusOut>", lambda e: self._save_args())
        ae.bind("<Return>", lambda e: self._save_args())
        self.auto_var = tk.BooleanVar(value=True)
        check(gt, "Sync automatically: download saves before playing, upload them after the game closes",
              self.auto_var, self._save_auto).pack(anchor="w", pady=(8, 0))
        self.play_info = label(gt, "", muted=True, justify="left")
        self.play_info.pack(anchor="w", pady=(8, 0))
        r = tk.Frame(gt, bg=T["face"])
        r.pack(fill="x", pady=(10, 0))
        Btn(r, "Game info & artwork…", lambda: MetadataDialog(self, self.game)).pack(side="left")
        self.art_lbl = label(r, "", muted=True)
        self.art_lbl.pack(side="left", padx=8)
        Btn(r, "Remove from library…", lambda: self.remove_game(self.game), kind="danger").pack(side="right")
        self.clear_btn = Btn(r, "Delete cloud saves…", lambda: self.clear_saves(self.game), kind="danger")
        self.clear_btn.pack(side="right", padx=6)

        # log tab
        lt = tk.Frame(nb, bg=T["face"], padx=6, pady=6)
        nb.add(lt, text="Log")
        lwf = tk.Frame(lt, bg=T["face"], relief="sunken", bd=2)
        lwf.pack(fill="both", expand=True)
        self.log_txt = tk.Text(lwf, bg=T["field"], fg=T["ink"], bd=0, highlightthickness=0, font=MONO,
                               state="disabled", wrap="none", padx=6, pady=4, height=6)
        lsb = ttk.Scrollbar(lwf, orient="vertical", command=self.log_txt.yview)
        self.log_txt.configure(yscrollcommand=lsb.set)
        self.log_txt.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        return f

    def _draw_hero(self):
        c, g = self.hero_c, self.game
        c.delete("all")
        if not g:
            return
        w, h = max(c.winfo_width(), 300), HERO_H
        art = self.art_info(g)
        hero, logo = self._art_file(art.get("hero")), self._art_file(art.get("logo"))
        if theme_art is not None:
            self._hero_img = ImageTk.PhotoImage(theme_art.hero_image(hero, logo, w, h, g, HERO_BAR))
            c.create_image(0, 0, image=self._hero_img, anchor="nw")
        st = self.stats_all.get(g, {})
        y = h - HERO_BAR // 2
        played = fmt_play_long(st.get("seconds", 0))
        c.create_text(18, y - 9, text=f"Played for {played}", fill="#ffffff", font=UIB, anchor="w")
        c.create_text(18, y + 10, text=f"Last played {fmt_ago(st.get('last_played'))}",
                      fill="#c9cdf2", font=UI, anchor="w")
        x = w - 14
        for b in (self.opt_btn, self.up_btn, self.down_btn, self.play_btn):
            c.create_window(x, y, window=b, anchor="e")
            x -= b.winfo_reqwidth() + (14 if b is self.down_btn else 6)
        chip = {"synced": ("☁  Synchronized", "#1d7a2e"), "changes": ("●  Not synced", "#8a5a00"),
                "conflict": ("⚠  Conflict", "#b3261e")}.get(self.settings.data["games"].get(g, {}).get("state"))
        if g in self.sessions:
            chip = ("▶  Playing now", "#1d7a2e")
        if chip:
            t = c.create_text(w - 20, 18, text=chip[0], fill="#ffffff", font=UIB, anchor="ne")
            x1, y1, x2, y2 = c.bbox(t)
            r = c.create_rectangle(x1 - 8, y1 - 4, x2 + 8, y2 + 4, fill=chip[1], outline="#ffffff")
            c.tag_raise(t, r)

    def _options_menu(self):
        g = self.game
        m = menu(self)
        m.add_command(label="Set game executable…", command=lambda: self.pick_exe(g))
        m.add_command(label="Choose save folder…", command=self.browse_folder)
        m.add_command(label="Game info & artwork…", command=lambda: MetadataDialog(self, g))
        m.add_command(label="Reload artwork", command=lambda: self.art_q.put((g, True)))
        m.add_command(label="Reload game info", command=lambda: self.reload_info(g))
        if g in self.sessions:
            m.add_separator()
            m.add_command(label="Game has closed (stop tracking)", command=lambda: self.sessions[g].stop_tracking())
        m.add_separator()
        m.add_command(label="Delete cloud saves…", command=lambda: self.clear_saves(g))
        m.add_command(label="Remove from library…", command=lambda: self.remove_game(g))
        m.tk_popup(self.opt_btn.winfo_rootx(), self.opt_btn.winfo_rooty() + self.opt_btn.winfo_height())

    def show_library(self):
        self.det_view.pack_forget()
        self.lib_view.pack(fill="both", expand=True)
        self.game = None
        self.lib_title.set_text("Library")
        self.last_note("")
        self._update_controls()
        self._layout_grid()

    def show_details(self, g):
        if self.busy or g not in self.all_games:
            return
        self.selected = g
        self._open_game(g)
        self.lib_view.pack_forget()
        self.det_view.pack(fill="both", expand=True)
        self.lib_title.set_text(f"Library  ›  {g}")

    def _open_game(self, name):
        self.game = name
        self.cfg, self.local_scan, self.cloud_scan = {"excludes": []}, {}, {}
        self.tree.delete(*self.tree.get_children())
        self.excl_list.delete(0, "end")
        self.summary_lbl.configure(text="")
        self._render_header()
        self._update_controls()
        if name:
            self._draw_hero()
            self.refresh_diff()

    def _render_header(self):
        g = self.game
        if not g:
            return
        gs = self.settings.data["games"].get(g, {})
        self.d_title.configure(text=g)
        p = gs.get("local_path")
        if not p:
            self.path_lbl.configure(text="Not set on this PC — choose where this game keeps its saves")
        elif not Path(p).is_dir():
            self.path_lbl.configure(text=f"{p}   (folder not found — Sync down will create it)")
        else:
            self.path_lbl.configure(text=p)
        exe = gs.get("exe")
        self.exe_lbl.configure(text=exe if exe else "Not set — choose the game's .exe to use Play")
        self.args_var.set(gs.get("args", ""))
        self.auto_var.set(gs.get("auto_sync", True))
        mine = self.settings.data.get("my_stats", {}).get(g, {}).get("seconds", 0)
        allp = self.stats_all.get(g, {}).get("seconds", 0)
        self.play_info.configure(text=f"Playtime on all PCs: {fmt_play_long(allp)}     "
                                      f"on this PC: {fmt_play_long(mine)}\n"
                                      "Playtime is kept separately from saves: deleting saves or removing the "
                                      "game doesn't erase it (only “Purge all data” does).")
        art = self.art_info(g)
        self.art_lbl.configure(text="Custom cover" if images.is_custom(art.get("grid", ""))
                               else f"SteamGridDB: {art['sgdb_name']}" if art.get("sgdb_name")
                               else "No artwork yet" if not self.settings.data.get("sgdb_key")
                               else "Artwork: searching…" if not art else "No artwork found")
        ls = gs.get("last_sync")
        self.last_note(f"Last sync from this PC: {'▲ up' if ls['direction'] == 'up' else '▼ down'}, "
                       f"{fmt_time(ls['time'])}" if ls else "Never synced from this PC")
        self.play_btn.configure(text="■  Playing…" if g in self.sessions else "▶  Play")
        self._render_about()

    def last_note(self, text):
        self.backend_lbl.configure(text=text or self._backend_desc)

    def choose_folder_menu(self):
        m = tk.Menu(self, tearoff=0, bg=C["panel2"], fg=C["fg"], activebackground=C["sel"],
                    activeforeground=C["fg"])
        m.add_command(label="Browse…", command=self.browse_folder)
        m.add_command(label="Type or paste a path…  (supports %USERPROFILE% etc.)", command=self.type_folder)
        x, y = self.choose_btn.winfo_rootx(), self.choose_btn.winfo_rooty() + self.choose_btn.winfo_height()
        m.tk_popup(x, y)

    def browse_folder(self):
        cur = self._local_path()
        d = filedialog.askdirectory(parent=self, title=f"Save folder for {self.game} on this PC",
                                    initialdir=cur if cur and Path(cur).is_dir() else str(Path.home()))
        if d:
            self._set_local_path(d)

    def type_folder(self):
        d = simpledialog.askstring(
            "Save folder", "Full path of the save folder on this PC, e.g.\n"
            r"%USERPROFILE%\AppData\LocalLow\Studio\Game", parent=self, initialvalue=self._local_path() or "")
        if d and d.strip():
            self._set_local_path(os.path.expanduser(os.path.expandvars(d.strip().strip('"'))))

    def _set_local_path(self, d):
        d = str(Path(d))
        g = self.settings.game(self.game)
        if g.get("local_path") != d:
            g["base"] = {}            # new folder → forget the previous sync baseline
        g["local_path"] = d
        self.settings.save()
        self.log(f"{self.game}: save folder on this PC set to {d}")
        self._layout_grid()
        self._render_header()
        self._update_controls()
        self.refresh_diff()

    def _scan(self, game, path):
        cfg = self.backend.get_game_config(game)
        errors: list = []
        local = scan_folder(path, errors) if path else {}
        for e in errors:
            self.log_ts(f"Could not read {e}  (is the game still running?)")
        cloud = self.backend.list_files(game)
        return cfg, local, cloud

    def refresh_diff(self):
        if not self.game:
            return
        game, path = self.game, self._local_path()
        self.run_bg(f"Comparing {game}", lambda: self._scan(game, path),
                    lambda r: self._apply_scan(game, r))

    def _apply_scan(self, game, res):
        if game != self.game:
            return
        self.cfg, self.local_scan, self.cloud_scan = res
        self.cfg.setdefault("excludes", [])
        self._render_excludes()
        self.render_diff()

    def render_diff(self):
        if not self.game:
            return
        base = self.settings.data.get("games", {}).get(self.game, {}).get("base", {})
        self.diff = compute_diff(self.local_scan, self.cloud_scan, self.cfg.get("excludes", []), base)
        if self._local_path():
            self._set_state(self.game, self._state_from(self.diff))
        self.tree.delete(*self.tree.get_children())
        self.entries = {}
        for e in self.diff:
            if (e.status == SAME and not self.show_same.get()) or \
               (e.status == EXCLUDED and not self.show_excl.get()):
                continue
            l, c = e.local, e.cloud
            tags = [e.status]
            hint = e.hint
            if e.changed_side == "both":
                tags.append("conflict")
                hint = "⚠ " + hint
            self.tree.insert("", "end", iid=e.path, text="  " + e.path, tags=tags, values=(
                STATUS_LABEL[e.status], human_size(l.size) if l else "—", fmt_time(l.mtime) if l else "",
                human_size(c.size) if c else "—", fmt_time(c.mtime) if c else "", hint))
            self.entries[e.path] = e
        cnt = Counter(e.status for e in self.diff)
        inc = [e for e in self.diff if e.status != EXCLUDED]
        lsum = sum(e.local.size for e in inc if e.local)
        csum = sum(e.cloud.size for e in inc if e.cloud)
        ndiff = cnt[CHANGED] + cnt[LOCAL_ONLY] + cnt[CLOUD_ONLY]
        state = "In sync ✓" if ndiff == 0 and inc else (f"{ndiff} difference(s)" if inc else "No files yet")
        self.summary_lbl.configure(text=(
            f"This PC {sum(1 for e in inc if e.local)} files, {human_size(lsum)}   ·   "
            f"Cloud {sum(1 for e in inc if e.cloud)} files, {human_size(csum)}   ·   "
            f"{cnt[EXCLUDED]} excluded   ·   {state}"))

    def on_tree_double(self, ev):
        iid = self.tree.identify_row(ev.y)
        if iid in self.entries:
            self.show_file_diff(self.entries[iid])

    def on_tree_menu(self, ev):
        iid = self.tree.identify_row(ev.y)
        if iid not in self.entries or self.busy:
            return
        self.tree.selection_set(iid)
        e = self.entries[iid]
        m = self.menu
        m.delete(0, "end")
        m.add_command(label="Compare contents…", command=lambda: self.show_file_diff(e))
        m.add_separator()
        if e.status == EXCLUDED:
            hits = matching_patterns(e.path, self.cfg.get("excludes", []))
            m.add_command(label=f"Stop excluding (remove {', '.join(hits)})",
                          command=lambda: self._save_excludes(
                              [p for p in self.cfg["excludes"] if p not in hits]))
        else:
            m.add_command(label="Exclude this file", command=lambda: self.add_excludes(
                ["/" + escape_pattern(e.path)]))
            if "/" in e.path:
                parent = e.path.rsplit("/", 1)[0]
                m.add_command(label=f"Exclude folder  {parent}/", command=lambda: self.add_excludes(
                    ["/" + escape_pattern(parent)]))
            ext = Path(e.path).suffix
            if ext:
                m.add_command(label=f"Exclude all *{ext} files",
                              command=lambda: self.add_excludes(["*" + escape_pattern(ext)]))
        if e.local and self._local_path():
            m.add_separator()
            m.add_command(label="Show in folder",
                          command=lambda: open_in_explorer(Path(self._local_path()) / e.path))
        m.tk_popup(ev.x_root, ev.y_root)

    def show_file_diff(self, e):
        game, root = self.game, self._local_path()

        def work():
            cloud = self.backend.read_bytes(game, e.path) if e.cloud else None
            local = (Path(root) / e.path).read_bytes() if e.local and root else None
            return cloud, local
        self.run_bg(f"Loading {e.path}", work, lambda r: DiffWindow(self, e, r[0], r[1]))

    def _render_excludes(self):
        self.excl_list.delete(0, "end")
        for p in self.cfg.get("excludes", []):
            self.excl_list.insert("end", f"  {p}")

    def add_excludes(self, pats):
        ex = list(self.cfg.get("excludes", []))
        new = [p for p in pats if p and p not in ex]
        if new:
            self._save_excludes(ex + new)

    def _save_excludes(self, ex):
        game = self.game
        def work():
            cfg = self.backend.get_game_config(game)
            cfg["excludes"] = ex
            self.backend.set_game_config(game, cfg)
            return cfg

        def done(c):
            self.log(f"{game}: exclusions saved ({len(ex)} rule(s))")
            if game == self.game:
                self.cfg = c
                self._render_excludes()
                self.render_diff()
        self.run_bg("Saving exclusions", work, done)

    def _rel_to_root(self, p):
        root = Path(self._local_path()).resolve()
        try:
            rel = Path(p).resolve().relative_to(root).as_posix()
        except ValueError:
            messagebox.showerror("Exclusions", f"{p}\nis not inside the save folder\n{root}", parent=self)
            return None
        return rel if rel != "." else None

    def exclude_pick_file(self):
        files = filedialog.askopenfilenames(parent=self, title="Files to exclude",
                                            initialdir=self._local_path())
        rels = [r for r in (self._rel_to_root(f) for f in files) if r]
        self.add_excludes(["/" + escape_pattern(r) for r in rels])

    def exclude_pick_folder(self):
        d = filedialog.askdirectory(parent=self, title="Folder to exclude", initialdir=self._local_path())
        if d:
            rel = self._rel_to_root(d)
            if rel:
                self.add_excludes(["/" + escape_pattern(rel)])

    def exclude_pattern(self):
        p = simpledialog.askstring("Add pattern", "Pattern to exclude, e.g.  *.log   Cache   /Screenshots",
                                   parent=self)
        if p and p.strip():
            self.add_excludes([p.strip()])

    def exclude_remove(self):
        sel = set(self.excl_list.curselection())
        if sel:
            self._save_excludes([p for i, p in enumerate(self.cfg.get("excludes", [])) if i not in sel])
