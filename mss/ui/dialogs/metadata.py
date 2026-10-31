"""Pick which game this is (for its name and description) and its cover and banner: search a source or use your
own images.

Used for "Game info & artwork…" on an existing game, and when adding a game (add=True): then nothing is
saved here; .result says what was chosen and the caller creates the game with it.
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING

from ...art import images
from ...art import sources as art_sources
from ...info import format as info_format
from ...info import sources as info_sources
from ..theme import GRID_BG, UI, T
from ..widgets import Btn, TitleBar, check, label

try:
    from PIL import ImageTk
    from .. import theme_art
except Exception:
    ImageTk = theme_art = None

if TYPE_CHECKING:
    from ..app import App


# The images you can pick: art key -> what the source calls them, and how they're laid out (8 per page).
KINDS = {
    "grid": dict(api="grids", noun="cover", w=100, h=150, cols=4),
    "hero": dict(api="heroes", noun="banner", w=212, h=68, cols=2),
}


class MetadataDialog(tk.Toplevel):
    """result (add mode only): None = cancelled, {} = add without choosing (looked up automatically later),
    or {"name": library name, "art": art dict or None, "info": info dict or None}."""

    def __init__(self, app: App, game, add=False):
        super().__init__(app)
        self.app, self.game, self.add = app, game, add
        self.result = None
        title = f"Add game — {game}" if add else f"Game info & artwork — {game}"
        self.title(title)
        self.configure(bg=T["face"])
        self.resizable(False, False)
        self.transient(app)
        self.q: queue.Queue = queue.Queue()
        self.results: list = []
        self.thumbs: list = []
        self.infos: dict = {}       # result id -> info dict (None while loading / if the lookup failed)
        self.kind = "grid"          # which images are showing: "grid" (covers) or "hero" (banners)
        self.imgs = {k: [] for k in KINDS}
        self.loaded = {k: None for k in KINDS}      # game id the images in .imgs are (being) loaded for
        self.chosen = {k: None for k in KINDS}
        self.custom = {k: None for k in KINDS}      # an image picked from a file: {"url": "custom:…", "_file": path}
        self.offer_name = None      # add mode: official name offered instead of the typed one
        self.api = self.info_api = None
        self.gen = 0                # bumped on source change so late replies from the old source are dropped
        TitleBar(self, title, app.icon16).pack(fill="x", padx=2, pady=2)
        f = tk.Frame(self, bg=T["face"], padx=12, pady=10)
        f.pack(fill="both", expand=True)
        if add:
            label(f, "Which game is this? Pick it on the left for its name and description, then click a cover "
                  "and a banner.",
                  bold=True).pack(anchor="w", pady=(0, 6))
        r = tk.Frame(f, bg=T["face"])
        r.pack(fill="x")
        label(r, "Source:").pack(side="left")
        names = list(art_sources.SOURCES)
        cur = app.settings.data.get("art_source")
        self.source = tk.StringVar(value=cur if cur in names else art_sources.DEFAULT)
        cb = ttk.Combobox(r, textvariable=self.source, values=names, state="readonly", width=16, font=UI)
        cb.pack(side="left", padx=(6, 12))
        cb.bind("<<ComboboxSelected>>", lambda e: self._set_source())
        label(r, "Search:").pack(side="left")
        self.term = tk.StringVar(value=game)
        en = tk.Entry(r, textvariable=self.term, width=40, **app._field(r))
        en.pack(side="left", padx=6, fill="x", expand=True)
        en.bind("<Return>", lambda e: self.search())
        Btn(r, "Search", self.search).pack(side="left")

        body = tk.Frame(f, bg=T["face"])
        body.pack(fill="both", expand=True, pady=8)
        self.res_list = tk.Listbox(body, width=34, height=14, activestyle="none", exportselection=False,
                                   **app._field(body))
        self.res_list.pack(side="left", fill="y")
        self.res_list.bind("<<ListboxSelect>>", lambda e: self._on_select())
        rc = tk.Frame(body, bg=T["face"])
        rc.pack(side="left", fill="both", expand=True, padx=(8, 0))
        kr = tk.Frame(rc, bg=T["face"])
        kr.pack(fill="x", pady=(0, 4))
        self.kind_var = tk.StringVar(value=self.kind)
        for k, spec in KINDS.items():
            tk.Radiobutton(kr, text=spec["noun"].capitalize(), variable=self.kind_var, value=k, indicatoron=0,
                           command=self._set_kind, bg=T["face"], fg=T["ink"], activebackground=T["face"],
                           selectcolor=T["field"], font=UI, bd=2, padx=12, cursor="hand2").pack(side="left")
        tf = tk.Frame(rc, bg=GRID_BG, relief="sunken", bd=2)
        tf.pack(fill="both", expand=True)
        g = KINDS["grid"]
        self.canvas = tk.Canvas(tf, bg=GRID_BG, width=g["cols"] * (g["w"] + 12) + 12, height=2 * (g["h"] + 12) + 12,
                                highlightthickness=0)
        self.canvas.pack()

        pv = tk.LabelFrame(f, text=" Game info ", bg=T["face"], fg=T["ink"], font=UI, bd=2, relief="groove",
                           padx=8, pady=6)
        pv.pack(fill="x")
        self.pv_name = label(pv, "", bold=True, anchor="w")
        self.pv_name.pack(fill="x")
        self.pv_meta = label(pv, "", muted=True, anchor="w", justify="left")
        self.pv_meta.pack(fill="x")
        self.pv_desc = label(pv, "", anchor="w", justify="left", wraplength=880)
        self.pv_desc.pack(fill="x", pady=(4, 0))
        self.use_official = tk.BooleanVar(value=True)
        self.official_chk = check(pv, "", self.use_official)

        self.status = label(f, "", muted=True)
        self.status.pack(anchor="w", pady=(6, 0))
        b = tk.Frame(f, bg=T["face"])
        b.pack(fill="x", pady=(8, 0))
        self.page = 0
        Btn(b, "◀", lambda: self._turn(-1)).pack(side="left")
        Btn(b, "▶", lambda: self._turn(1)).pack(side="left", padx=4)
        Btn(b, "Use image from file…", self.pick_file).pack(side="left", padx=(12, 0))
        Btn(b, "Cancel", self.destroy).pack(side="right")
        if add:
            Btn(b, "Skip", self._skip).pack(side="right", padx=(6, 0))
        self.ok_btn = Btn(b, "Add game" if add else "Use this", self.apply, kind="default")
        self.ok_btn.pack(side="right", padx=6)
        self._show_preview(None)
        self.grab_set()
        self.after(100, self._pump)
        self._set_source()
        if add:
            self.wait_window()

    # ------------------------------------------------------------- sources
    def _set_source(self):
        name = self.source.get()
        src = art_sources.SOURCES[name]
        if self.app.settings.data.get("art_source") != name:
            self.app.settings.data["art_source"] = name
            self.app.settings.save()
        self.gen += 1
        self.results, self.infos, self.page = [], {}, 0
        for k in KINDS:
            self._reset_kind(k)
        self.res_list.delete(0, "end")
        self._render()
        self._show_preview(None)
        key = self.app.settings.data.get(src.key_setting)
        if not key:
            self.api = self.info_api = None
            self.status.configure(text=f"Add your {name} API key in Settings → Artwork to search. "
                                       "You can still use an image from a file.")
            return
        self.api = src.make(key)
        isrc = info_sources.SOURCES.get(name)            # the same service's game info, if it has any
        self.info_api = isrc.make(self.app.settings.data.get(isrc.key_setting)) if isrc else None
        self.search()

    def _bg(self, fn, done):
        gen = self.gen

        def w():
            try:
                self.q.put((gen, done, fn(), None))
            except Exception as ex:
                self.q.put((gen, done, None, ex))
        threading.Thread(target=w, daemon=True).start()

    def _pump(self):
        try:
            while True:
                gen, done, res, ex = self.q.get_nowait()
                if gen != self.gen:
                    continue
                if ex:
                    self.status.configure(text=f"Error: {ex}")
                    self.ok_btn.state(["!disabled"])
                else:
                    done(res)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._pump)

    def search(self):
        if not self.api:
            return
        self.status.configure(text="Searching…")
        self._bg(lambda: self.api.search(self.term.get()), self._show_results)

    def _show_results(self, res):
        self.results = res
        self.res_list.delete(0, "end")
        for r in res:
            year = time.strftime(" (%Y)", time.gmtime(r["release_date"])) if r.get("release_date") else ""
            self.res_list.insert("end", f" {r.get('name', '?')}{year}")
        self.status.configure(text=f"{len(res)} result(s)." if res else "Nothing found — try another name.")
        if res:
            self.res_list.selection_set(0)
            self._on_select()

    def _selected(self):
        sel = self.res_list.curselection()
        return self.results[sel[0]] if sel and self.api else None

    def _on_select(self):
        r = self._selected()
        if not r:
            return
        for k in KINDS:
            if self.loaded[k] != r["id"]:
                self._reset_kind(k)
        self._load_images(self.kind, r["id"])
        self._load_info(r)

    # ---------------------------------------------------------- game info
    def _load_info(self, r):
        gid = r["id"]
        if gid in self.infos or not self.info_api:
            self._show_preview(self.infos.get(gid), r)
            return
        self.infos[gid] = None
        self.pv_name.configure(text=r.get("name", ""))
        self.pv_meta.configure(text="")
        self.pv_desc.configure(text="Looking up game info…")

        def done(info):
            self.infos[gid] = info
            if (self._selected() or {}).get("id") == gid:
                self._show_preview(info, r)
        self._bg(lambda: self.info_api.fetch(self.game, gid), done)

    def _show_preview(self, info, r=None):
        if not r:
            self.pv_name.configure(text=self.game)
            self.pv_meta.configure(text="")
            self.pv_desc.configure(text="Pick a game from the search results to see its name and description.")
            self.offer_name = None
            self.official_chk.pack_forget()
            return
        name = (info or {}).get("name") or r.get("name") or self.game
        self.pv_name.configure(text=name)
        if info_format.found(info):
            meta, tags = info_format.summary(info)
            self.pv_meta.configure(text="\n".join(x for x in (meta, tags) if x))
            self.pv_desc.configure(text=info.get("description") or "No description available for this game.")
        else:
            self.pv_meta.configure(text="")
            self.pv_desc.configure(text="No game info available.")
        self.offer_name = name if self.add and info_format.found(info) and name != self.game else None
        if self.offer_name:
            self.official_chk.configure(text=f"Call it “{name}” in the library (you typed “{self.game}”)")
            self.official_chk.pack(anchor="w", pady=(6, 0))
        else:
            self.official_chk.pack_forget()

    # ------------------------------------------------------ covers & banners
    def _reset_kind(self, k):
        self.imgs[k], self.loaded[k] = [], None
        self.chosen[k] = self.custom[k]["url"] if self.custom[k] else None

    def _set_kind(self):
        self.kind, self.page = self.kind_var.get(), 0
        r = self._selected()
        if r and self.loaded[self.kind] != r["id"]:
            self._load_images(self.kind, r["id"])
        else:
            self._image_status()
        self._render()

    def _load_images(self, k, gid):
        self.loaded[k] = gid
        self.status.configure(text=f"Loading {KINDS[k]['noun']}s…")

        def work():
            imgs = self.api.images(KINDS[k]["api"], gid)[:24]
            for im in imgs:
                try:
                    im["_file"] = str(images.fetch(im.get("thumb") or im["url"]))
                except Exception:
                    im["_file"] = None
            return imgs

        def done(imgs):
            if self.loaded[k] != gid:       # another game was picked meanwhile
                return
            self.imgs[k] = imgs
            self.chosen[k] = self.custom[k]["url"] if self.custom[k] else imgs[0]["url"] if imgs else None
            if k == self.kind:
                self.page = 0
                self._render()
                self._image_status()
        self._bg(work, done)

    def _image_status(self):
        noun, other = KINDS[self.kind]["noun"], "banner" if self.kind == "grid" else "cover"
        n = len(self.imgs[self.kind])
        if not self._selected():
            return
        self.status.configure(text=f"{n} {noun}(s). Click one to choose it." if n
                              else f"No {noun}s for this game — the {other} and logo will still be used.")

    def pick_file(self):
        k, noun = self.kind, KINDS[self.kind]["noun"]
        p = filedialog.askopenfilename(parent=self, title=f"{noun.capitalize()} image for {self.game}",
                                       filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                                                  ("All files", "*.*")])
        if not p:
            return
        try:
            if theme_art is not None:
                from PIL import Image
                with Image.open(p) as im:
                    im.verify()
            ident = images.import_image(p)
        except Exception as ex:
            self.status.configure(text=f"Can't use that image: {ex}")
            return
        self.custom[k] = {"url": ident, "_file": str(images.cache_path(ident))}
        self.chosen[k], self.page = ident, 0
        self._render()
        self.status.configure(text=f"Your image is the {noun}. Anything you don't pick comes from the game "
                                   "chosen on the left, if any.")

    def _tiles(self):
        k = self.kind
        return ([self.custom[k]] if self.custom[k] else []) + self.imgs[k]

    def _turn(self, d):
        tiles = self._tiles()
        if tiles:
            self.page = max(0, min((len(tiles) - 1) // 8, self.page + d))
            self._render()

    def _render(self):
        c = self.canvas
        c.delete("all")
        self.thumbs = []
        spec = KINDS[self.kind]
        tw, th, cols = spec["w"], spec["h"], spec["cols"]
        for i, im in enumerate(self._tiles()[self.page * 8:self.page * 8 + 8]):
            x, y = 12 + (i % cols) * (tw + 12), 12 + (i // cols) * (th + 12)
            if theme_art is not None:
                tile = (theme_art.cover_tile(im.get("_file"), tw, th, self.game) if self.kind == "grid"
                        else theme_art.banner_tile(im.get("_file"), tw, th))
                ph = ImageTk.PhotoImage(tile)
                self.thumbs.append(ph)
                c.create_image(x, y, image=ph, anchor="nw", tags=f"g{i}")
            if im["url"] == self.chosen[self.kind]:
                c.create_rectangle(x - 4, y - 4, x + tw + 3, y + th + 3, outline="#ffe27a", width=3)
            c.tag_bind(f"g{i}", "<Button-1>", lambda e, u=im["url"]: self._choose(u))

    def _choose(self, url):
        self.chosen[self.kind] = url
        self._render()

    # ------------------------------------------------------------- finish
    def _skip(self):
        self.result = {}
        self.destroy()

    def apply(self):
        r = self._selected()
        custom = {k: v for k, v in self.chosen.items() if images.is_custom(v or "")}
        if not r and not custom:
            if self.add:
                self._skip()
            return
        self.ok_btn.state(["disabled"])
        self.status.configure(text="Getting banner and logo…" if r else "Saving…")

        def build():
            if not r:            # own images only, nothing to look up: keep the rest of the current art
                keep = {} if self.add else {k: v for k, v in self.app.art_info(self.game).items() if k != "none"}
                return dict(keep, **custom), None
            art = self.api.art_for(r["id"], r.get("name", ""), self.chosen["grid"], self.chosen["hero"])
            info = self.infos.get(r["id"])
            if info is None and self.info_api:
                info = self.info_api.fetch(self.game, r["id"])
            return art, info

        def done(res):
            art, info = res
            if self.add:
                name = self.offer_name if self.offer_name and self.use_official.get() else self.game
                self.result = {"name": name, "art": art, "info": info}
            else:
                self.app.save_meta(self.game, art, info)
            self.destroy()
        self._bg(build, done)
