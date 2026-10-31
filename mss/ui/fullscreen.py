"""Fullscreen mode: a controller-friendly launcher for handheld PCs, in the spirit of Steam Big Picture and the
Xbox full screen experience.

Home fills the screen with the selected game's art and shows the library as a shelf of covers along the bottom.
A opens a game's page (Play, Sync up, Sync down, Check saves), X plays straight away, ☰ opens the menu and
LB / RB page through the shelf. It works with an Xbox controller (gamepad.py), the keyboard (arrows, Enter,
Esc, Tab for the menu) and touch or mouse. Adding games, folders and settings stay in desktop mode.

Open it with --fullscreen (what AnyFSE runs), View → Fullscreen mode, F11, or "Start in Fullscreen mode".
Questions asked while it's open (conflicts, sync confirmations, errors) appear inside it so the controller
can answer them: use confirm() / tell() / ask_conflict() instead of messagebox for anything on the play path.
"""
from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox

from .. import APP_TITLE
from ..core.diff import EXCLUDED, SAME
from ..core.playtime import fmt_ago, fmt_play_long
from ..info import format as info_format
from . import gamepad
from .dialogs.conflict import ConflictDialog
from .theme import WIN

try:
    from PIL import ImageTk
    from . import theme_art
except Exception:            # Pillow missing: plain background, the library's small covers
    ImageTk = theme_art = None

try:
    import psutil
except ImportError:
    psutil = None

FS = dict(bg="#06081e", panel="#0c1030", card="#151a3c", line="#2e3670", button="#232a55", ink="#ffffff",
          sub="#c3c9ee", dim="#8088bf", focus="#ffffff", focus_ink="#0a0d26", glow="#7fb2ff",
          green="#2f9e4f", amber="#b98010", red="#c8443a")
PAD_COLORS = {"a": "#3fae2a", "b": "#d6392f", "x": "#2f7bd6", "y": "#e0aa1e"}
FAMILY = ("Segoe UI", "Segoe UI Semibold") if WIN else ("Helvetica", "Helvetica")
KEYS = {"Left": "left", "Right": "right", "Up": "up", "Down": "down", "Return": "a", "KP_Enter": "a",
        "space": "a", "Escape": "b", "BackSpace": "b", "x": "x", "Tab": "start", "F10": "start",
        "Prior": "lb", "Next": "rb"}
if WIN:
    KEYS["App"] = "start"                       # the keyboard's menu key


class FullscreenMixin:
    """Part of App (see ui/app.py)."""

    _fs_c = None
    _fs_pad = None

    # ------------------------------------------------------------ entering / leaving
    def enter_fullscreen(self):
        if self.fs_on:
            return
        self.fs_on = True
        if self._fs_c is None:
            self._fs_build()
        self._fs_view, self._fs_menu, self._fs_btn, self._fs_start = "home", None, 0, 0
        self._fs_focus = self.game or self.selected
        self._fs_c.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lift(self._fs_c)            # Canvas.lift() raises canvas items, not the widget
        self.attributes("-fullscreen", True)
        self._fs_c.focus_set()
        self._fs_pad = gamepad.Gamepad(lambda b: self.q.put(("pad", b)), self._fs_pad_active)
        self._fs_pad.start()
        self._fs_refresh()

    def leave_fullscreen(self):
        if not self.fs_on or self._fs_prompts:
            return
        self.fs_on = False
        self._fs_pad.stop()
        self._fs_c.place_forget()
        self.attributes("-fullscreen", False)
        self.focus_set()
        self._layout_grid()

    def toggle_fullscreen(self):
        self.leave_fullscreen() if self.fs_on else self.enter_fullscreen()

    def _fs_build(self):
        c = self._fs_c = tk.Canvas(self, bg=FS["bg"], highlightthickness=0, bd=0, cursor="arrow")
        self._fs_imgs: dict = {}            # covers, logos, icons and the scrim, by size
        self._fs_bgs: dict = {}             # the few most recent backdrops
        self._fs_bg_want = self._fs_last_bg = None
        self._fs_bg_making: set = set()
        self._fs_fonts: dict = {}
        self._fs_toast_msg, self._fs_toast_until = "", 0.0
        self._fs_hwnd = 0
        c.bind("<Configure>", lambda e: self._debounce("fs", 60, self._fs_render))
        for key, b in KEYS.items():
            c.bind(f"<KeyPress-{key}>", lambda e, b=b: (self._fs_input(b), "break")[1])
        c.bind("<MouseWheel>", lambda e: self._fs_input("left" if e.delta > 0 else "right"))
        c.bind("<Motion>", lambda e: c.cget("cursor") == "none" and c.configure(cursor="arrow"))

    def _fs_pad_active(self):
        """Called from the controller thread: only steer while fullscreen mode is the window being used."""
        return self.fs_on and gamepad.is_foreground(self._fs_hwnd)

    def _fs_refresh(self):
        if self.fs_on:
            self._debounce("fs", 120, self._fs_render)

    def _fs_toast(self, msg):
        self._fs_toast_msg, self._fs_toast_until = msg, time.time() + 5
        self._fs_refresh()
        self.after(5100, self._fs_refresh)

    # ------------------------------------------------------------ questions (fullscreen or desktop)
    def confirm(self, title, text, warn=False) -> bool:
        if self.fs_on:
            return self._fs_ask(title, text, [("Yes", True), ("No", False)], cancel=False)
        return messagebox.askyesno(title, text, icon="warning" if warn else "question", parent=self)

    def tell(self, title, text, kind="info"):
        """kind: "info" | "warning" | "error"."""
        if self.fs_on:
            self._fs_ask(title, text, [("OK", None)], cancel=None)
            return
        {"info": messagebox.showinfo, "warning": messagebox.showwarning,
         "error": messagebox.showerror}[kind](title, text, parent=self)

    def ask_conflict(self, g, diff, moment):
        """Which saves win when both sides changed: "up", "down", "skip" or "cancel" (see ConflictDialog)."""
        if not self.fs_on:
            return ConflictDialog(self, g, diff, moment).result
        pending = [e for e in diff if e.status not in (SAME, EXCLUDED)]
        newest_local = max((e.local.mtime for e in pending if e.local), default=0)
        newest_cloud = max((e.cloud.mtime for e in pending if e.cloud), default=0)
        when = "before starting the game" if moment == "before" else "after you played"
        lines = [f"This PC and the cloud both have different saves ({when}). "
                 "The other side's files are zipped to a backup first."]
        if newest_local != newest_cloud:
            lines.append("This PC has the newest file." if newest_local > newest_cloud
                         else "The cloud has the newest file.")
        lines.append("")
        lines += [f"•  {e.path}" for e in pending[:6]]
        if len(pending) > 6:
            lines.append(f"…and {len(pending) - 6} more")
        up, down = ("Keep this PC's saves (upload)", "up"), ("Keep cloud saves (download)", "down")
        choices = [up, down] if newest_local >= newest_cloud else [down, up]
        if moment == "before":
            choices += [("Play without syncing", "skip"), ("Cancel launch", "cancel")]
        else:
            choices.append(("Decide later", "skip"))
        return self._fs_ask(f"Save conflict — {g}", "\n".join(lines), choices,
                            cancel="cancel" if moment == "before" else "skip")

    def _fs_ask(self, title, text, choices, cancel):
        """Show a question inside fullscreen mode and wait for the answer: the chosen value, or `cancel` for B."""
        lines = text.splitlines()
        if len(lines) > 16:
            text = "\n".join(lines[:15] + ["…"])
        var = tk.IntVar(self, -2)
        pr = dict(title=title, text=text, choices=choices, focus=0, var=var)
        self._fs_prompts.append(pr)
        self.show_window()
        self._fs_render()
        try:
            self.wait_variable(var)
            i = var.get()
        except tk.TclError:                   # the app is closing
            return cancel
        finally:
            self._fs_prompts.remove(pr)
        if self.fs_on:
            self._fs_render()
        return choices[i][1] if i >= 0 else cancel

    # ------------------------------------------------------------ input
    def _fs_input(self, b):
        if not self.fs_on:
            return
        self._fs_c.configure(cursor="none")   # steering with the controller: hide the mouse pointer
        if self._fs_prompts:
            pr = self._fs_prompts[-1]
            n = len(pr["choices"])
            if b in ("up", "left"):
                pr["focus"] = (pr["focus"] - 1) % n
            elif b in ("down", "right"):
                pr["focus"] = (pr["focus"] + 1) % n
            elif b == "a":
                pr["var"].set(pr["focus"])
                return
            elif b == "b":
                pr["var"].set(-1)
                return
            self._fs_render()
            return
        if self._fs_menu is not None:
            items = self._fs_menu_items()
            if b == "up":
                self._fs_menu = (self._fs_menu - 1) % len(items)
            elif b == "down":
                self._fs_menu = (self._fs_menu + 1) % len(items)
            elif b in ("b", "start", "back"):
                self._fs_menu = None
            elif b == "a":
                fn = items[min(self._fs_menu, len(items) - 1)][1]
                self._fs_menu = None
                self._fs_render()
                fn()
                return
            self._fs_render()
            return
        if b in ("start", "back"):
            self._fs_menu = 0
            self._fs_render()
            return
        games = self._fs_games()
        g = self._fs_focus
        if g not in games:
            return
        if self._fs_view == "game":
            actions = self._fs_actions(g)
            if b == "left":
                self._fs_btn = max(0, self._fs_btn - 1)
            elif b == "right":
                self._fs_btn = min(len(actions) - 1, self._fs_btn + 1)
            elif b == "a":
                _text, fn, ok = actions[self._fs_btn]
                if ok:
                    fn()
            elif b == "x":
                self._fs_play(g)
            elif b == "b":
                self._fs_view = "home"
        else:
            i = games.index(g)
            page = max(1, getattr(self, "_fs_page", 1))
            step = {"left": -1, "right": 1, "lb": -page, "rb": page}.get(b)
            if step:
                self._fs_focus = games[max(0, min(len(games) - 1, i + step))]
            elif b == "a":
                self._fs_open(g)
            elif b == "x":
                self._fs_play(g)
        self._fs_render()

    def _fs_games(self):
        """The library, most recently played first."""
        return sorted(self.all_games, key=lambda g: (-(self.stats_all.get(g, {}).get("last_played") or 0),
                                                     g.lower()))

    def _fs_open(self, g):
        self._fs_view, self._fs_btn, self._fs_focus = "game", 0, g
        self._fs_select(g)

    def _fs_select(self, g):
        """Open the game in the desktop page underneath too: Sync and Check saves work on self.game."""
        if self.game != g and not self.busy:
            self.show_details(g)
        return self.game == g

    def _fs_actions(self, g):
        """[(text, action, enabled)] of a game's page."""
        gs = self.settings.data["games"].get(g, {})
        playing = g in self.sessions
        can_sync = self.backend is not None and bool(gs.get("local_path")) and not playing
        return [("■  Stop tracking" if playing else "▶  Play", lambda: self._fs_play(g), True),
                ("▲  Sync up", lambda: self._fs_sync(g, "up"), can_sync),
                ("▼  Sync down", lambda: self._fs_sync(g, "down"), can_sync),
                ("↻  Check saves", lambda: self._fs_sync(g, None), can_sync)]

    def _fs_play(self, g):
        if g in self.sessions:
            if self.confirm(APP_TITLE, f"Has {g} closed?\n\nStop tracking it now: playtime is saved and the "
                                       "saves are uploaded.") and g in self.sessions:
                self.sessions[g].stop_tracking()
        elif self.busy:
            self._fs_toast("Please wait for the current task to finish.")
        else:
            self.play(g)

    def _fs_sync(self, g, direction):
        """Sync up / down, or just compare (direction None) to show whether the saves are in sync."""
        if self.busy or not self._fs_select(g):
            self._fs_toast("Please wait for the current task to finish.")
        elif direction:
            self.sync(direction)
        else:
            self.refresh_diff()

    def _fs_menu_items(self):
        items = [("Resume", lambda: None)]
        if self.backend is not None:
            items.append(("Refresh library", self.reload_games))
        elif self.settings.data.get("backend") == "gdrive":
            items.append(("Sign in with Google", lambda: self.connect(interactive=True)))
        else:
            items.append(("Connect", self.connect))
        return items + [("Desktop mode", self.leave_fullscreen), (f"Exit {APP_TITLE}", self._fs_exit)]

    def _fs_exit(self):
        if self.sessions and not self.confirm(
                APP_TITLE, f"{', '.join(self.sessions)} is still being tracked. If you exit now, its playtime "
                           "isn't counted and its saves aren't uploaded when it closes.\n\nExit anyway?", warn=True):
            return
        self.destroy()

    def _fs_click_tile(self, g):
        if self._fs_prompts or self._fs_menu is not None:
            return
        if g == self._fs_focus and self._fs_view == "home":
            self._fs_open(g)
        else:
            self._fs_view, self._fs_focus = "home", g
        self._fs_render()

    def _fs_click_button(self, i):
        if not self._fs_prompts and self._fs_menu is None:
            self._fs_btn = i
            self._fs_input("a")

    def _fs_click_menu(self, i):
        if not self._fs_prompts:
            self._fs_menu = i
            self._fs_input("a")

    # ------------------------------------------------------------ images and fonts
    def _fs_px(self, v):
        return int(v * self._fs_s)

    def _fs_font(self, size, bold=False, semi=False):
        px = max(9, self._fs_px(size))
        key = (px, bold, semi)
        if key not in self._fs_fonts:
            self._fs_fonts[key] = tkfont.Font(self, family=FAMILY[1] if semi else FAMILY[0], size=-px,
                                              weight="bold" if bold else "normal")
        return self._fs_fonts[key]

    def _fs_image(self, key, make):
        if key not in self._fs_imgs:
            if len(self._fs_imgs) > 160:
                self._fs_imgs.clear()
            self._fs_imgs[key] = ImageTk.PhotoImage(make())
        return self._fs_imgs[key]

    def _fs_cover(self, g, w, h):
        if theme_art is None:
            return self.cover_photo(g)
        url = self.art_info(g).get("grid") or ""
        f = self._art_file(url)
        return self._fs_image(("cover", g, url, bool(f), w, h), lambda: theme_art.cover_tile(f, w, h, g))

    def _fs_logo(self, path, w, h):
        def make():
            from PIL import Image
            im = Image.open(path).convert("RGBA")
            im.thumbnail((w, h), Image.LANCZOS)
            return im
        try:
            return self._fs_image(("logo", str(path), w, h), make)
        except Exception:
            return None

    def _fs_scrim(self, W, H):
        if theme_art is None:
            return None
        from PIL import Image
        return self._fs_image(("scrim", W, H), lambda: Image.new("RGBA", (W, H), (2, 3, 16, 175)))

    def _fs_bg(self, g, W, H):
        """The backdrop for g. Made in the background (it's big): until it's ready the previous one stays up."""
        if theme_art is None:
            return None
        hero = self._art_file(self.art_info(g).get("hero")) if g else None
        key = (str(hero), W, H)
        if key in self._fs_bgs:
            self._fs_last_bg = self._fs_bgs[key]
            return self._fs_last_bg
        self._fs_bg_want = key

        def make():
            if key != self._fs_bg_want or key in self._fs_bg_making:
                return
            self._fs_bg_making.add(key)
            threading.Thread(target=lambda: self.q.put(("fsbg", key, theme_art.fs_background(hero, W, H))),
                             daemon=True).start()
        self._debounce("fsbg", 0 if self._fs_last_bg is None else 180, make)
        return self._fs_last_bg

    def _fs_bg_ready(self, key, img):
        """(Tk thread) a backdrop made by _fs_bg's thread."""
        self._fs_bg_making.discard(key)
        self._fs_bgs[key] = ImageTk.PhotoImage(img)
        while len(self._fs_bgs) > 4:
            self._fs_bgs.pop(next(iter(self._fs_bgs)))
        self._fs_refresh()

    # ------------------------------------------------------------ drawing
    def _fs_render(self):
        if not self.fs_on:
            return
        c = self._fs_c
        W, H = c.winfo_width(), c.winfo_height()
        if W < 100 or H < 100:
            return
        self._fs_s = min(W / 1600, H / 900)
        try:
            self._fs_hwnd = int(self.wm_frame(), 16)
        except (tk.TclError, ValueError):
            self._fs_hwnd = 0
        c.delete("all")
        games = self._fs_games()
        if self._fs_focus not in games:
            self._fs_focus = games[0] if games else None
        g = self._fs_focus
        if g is None:
            self._fs_view = "home"
        bg = self._fs_bg(g, W, H)
        if bg is not None:
            c.create_image(0, 0, image=bg, anchor="nw")
        self._fs_topbar(W)
        if g is None:
            self._fs_empty(W, H)
        elif self._fs_view == "game":
            self._fs_game_page(g, W, H)
        else:
            self._fs_home(g, games, W, H)
        self._fs_footer(W, H)
        if self._fs_toast_msg and time.time() < self._fs_toast_until:
            self._fs_draw_toast(W)
        if self._fs_menu is not None:
            self._fs_draw_menu(W, H)
        if self._fs_prompts:
            self._fs_draw_prompt(self._fs_prompts[-1], W, H)

    def _fs_rrect(self, x1, y1, x2, y2, r, **kw):
        r = max(1, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self._fs_c.create_polygon(pts, smooth=True, **kw)

    def _fs_chip(self, x, y, text, color):
        """A rounded label with its left edge at x, centred on y. Returns its right edge."""
        p, f = self._fs_px, self._fs_font(17, semi=True)
        w = f.measure(text) + p(32)
        self._fs_rrect(x, y - p(18), x + w, y + p(18), p(18), fill=color, outline="")
        self._fs_c.create_text(x + w // 2, y, text=text, fill=FS["ink"], font=f)
        return x + w

    def _fs_glyph(self, right, y, b):
        """A controller button (A, B, X, Y, LB, RB, ☰) ending at `right`. Returns its left edge."""
        c, p = self._fs_c, self._fs_px
        r = p(15)
        if b in ("lb", "rb"):
            left = right - p(42)
            self._fs_rrect(left, y - r, right, y + r, p(9), fill=FS["button"], outline=FS["dim"])
        else:
            left = right - 2 * r
            c.create_oval(left, y - r, right, y + r, fill=PAD_COLORS.get(b, FS["button"]),
                          outline=FS["dim"] if b == "start" else "")
        c.create_text((left + right) // 2, y, text={"start": "☰"}.get(b, b.upper()), fill=FS["ink"],
                      font=self._fs_font(14, bold=True))
        return left

    def _fs_topbar(self, W):
        c, p = self._fs_c, self._fs_px
        x, y = p(56), p(46)
        if theme_art is not None:
            n = p(40)
            icon = self._fs_image(("icon", n), lambda: theme_art.icon_image(n))
        else:
            icon = self.icon32
        c.create_image(x, y, image=icon, anchor="w")
        c.create_text(x + p(54), y, text=APP_TITLE, fill=FS["ink"], font=self._fs_font(24, semi=True), anchor="w")
        t = c.create_text(W - p(56), y, text=time.strftime("%I:%M %p").lstrip("0"), fill=FS["ink"],
                          font=self._fs_font(24, semi=True), anchor="e")
        right = c.bbox(t)[0] - p(30)
        bat = self._fs_battery()
        if bat:
            right = self._fs_draw_battery(right, y, *bat) - p(30)
        if self.backend is not None:
            text, color = "☁  " + ("Google Drive" if self.backend.kind == "gdrive" else "Synced folder"), FS["sub"]
        else:
            text, color = self._backend_desc, FS["dim"]
        c.create_text(right, y, text=text, fill=color, font=self._fs_font(18), anchor="e")

    @staticmethod
    def _fs_battery():
        try:
            b = psutil.sensors_battery() if psutil is not None else None
        except Exception:
            b = None
        return (int(b.percent), bool(b.power_plugged)) if b else None

    def _fs_draw_battery(self, right, y, percent, plugged):
        c, p = self._fs_c, self._fs_px
        w, h = p(36), p(18)
        x1 = right - w - p(4)
        c.create_rectangle(right - p(4), y - p(5), right, y + p(5), fill=FS["sub"], outline="")
        c.create_rectangle(x1, y - h // 2, right - p(4), y + h // 2, outline=FS["sub"], width=max(1, p(2)))
        fill = FS["red"] if percent <= 15 and not plugged else FS["green"] if plugged else FS["sub"]
        inner = max(1, int((w - p(8)) * percent / 100))
        c.create_rectangle(x1 + p(3), y - h // 2 + p(3), x1 + p(3) + inner, y + h // 2 - p(3) + 1, fill=fill,
                           outline="")
        t = c.create_text(x1 - p(10), y, text=("⚡ " if plugged else "") + f"{percent}%", fill=FS["sub"],
                          font=self._fs_font(18), anchor="e")
        return c.bbox(t)[0]

    def _fs_chips(self, g):
        out = []
        if g in self.sessions:
            out.append(("▶  Playing now", FS["green"]))
        gs = self.settings.data["games"].get(g, {})
        chip = {"synced": ("☁  Synced", FS["green"]), "changes": ("●  Not synced", FS["amber"]),
                "conflict": ("⚠  Conflict", FS["red"])}.get(gs.get("state"))
        if chip:
            out.append(chip)
        if not gs.get("exe"):
            out.append(("No .exe set on this PC", FS["button"]))
        return out

    def _fs_info(self, g, x, y, width, bottom, long):
        """The game's logo or name, playtime, status chips and description, from (x, y) down to `bottom`."""
        c, p = self._fs_c, self._fs_px
        width = int(width)
        logo = self._art_file(self.art_info(g).get("logo")) if theme_art is not None else None
        img = self._fs_logo(logo, int(width * 0.8), p(170)) if logo else None
        info = self.game_info(g)
        found = info_format.found(info)
        if img is not None:
            c.create_image(x, y, image=img, anchor="nw")
            y += img.height() + p(24)
        else:
            title = (info.get("name") or g) if found else g
            c.create_text(x + p(3), y + p(3), text=title, width=width, anchor="nw", fill="#000000",
                          font=self._fs_font(56, bold=True))
            t = c.create_text(x, y, text=title, width=width, anchor="nw", fill=FS["ink"],
                              font=self._fs_font(56, bold=True))
            y = c.bbox(t)[3] + p(16)
        st = self.stats_all.get(g, {})
        meta = (f"Played for {fmt_play_long(st['seconds'])}   ·   Last played {fmt_ago(st.get('last_played'))}"
                if st.get("seconds") else "Not played yet")
        t = c.create_text(x, y, text=meta, anchor="nw", fill=FS["sub"], font=self._fs_font(20, semi=True))
        y = c.bbox(t)[3] + p(30)
        chips = self._fs_chips(g)
        cx = x
        for text, color in chips:
            cx = self._fs_chip(cx, y, text, color) + p(12)
        if chips:
            y += p(40)
        if not found:
            return
        lines = []
        if long:
            lines = [ln for ln in info_format.summary(info) if ln]
        desc = info.get("description") or ""
        size = 19 if long else 18
        for ln in lines:
            if y > bottom - p(40):
                return
            t = c.create_text(x, y, text=ln, width=width, anchor="nw", fill=FS["dim"], font=self._fs_font(16))
            y = c.bbox(t)[3] + p(6)
        y += p(10)
        f = self._fs_font(size)
        room = (bottom - y) // max(1, f.metrics("linespace"))
        chars = int(room * width / max(1, f.measure("abcdefghijklmnopqrstuvwxyz") / 26) * 0.92)
        if room < 1 or not desc:
            return
        if len(desc) > chars:
            desc = desc[:max(0, chars)].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
        c.create_text(x, y, text=desc, width=width, anchor="nw", fill=FS["sub"], font=f)

    def _fs_home(self, g, games, W, H):
        c, p = self._fs_c, self._fs_px
        tw, th, gap, x0 = p(170), p(255), p(30), p(96)
        top = H - p(84) - p(66) - th                      # top of the covers
        self._fs_info(g, x0, p(132), W * 0.5, top - p(76), long=False)

        n = max(1, (W - 2 * x0 + gap) // (tw + gap))
        self._fs_page = n
        i = games.index(g)
        self._fs_start = max(0, min(self._fs_start, i, len(games) - n))
        if i >= self._fs_start + n:
            self._fs_start = i - n + 1
        start = self._fs_start
        c.create_text(x0, top - p(40), text=f"LIBRARY   ·   {len(games)} game{'s' if len(games) != 1 else ''}",
                      anchor="w", fill=FS["sub"], font=self._fs_font(16, semi=True))
        if start > 0:
            c.create_text(x0 - p(30), top + th // 2, text="◀", fill=FS["sub"], font=self._fs_font(22))
        if start + n < len(games):
            c.create_text(W - x0 + p(30), top + th // 2, text="▶", fill=FS["sub"], font=self._fs_font(22))
        for k, name in enumerate(games[start:start + n]):
            x = x0 + k * (tw + gap)
            tag = f"tile{start + k}"
            if name == g:
                continue                                 # drawn last, on top of its neighbours
            c.create_image(x, top, image=self._fs_cover(name, tw, th), anchor="nw", tags=tag)
            if name in self.sessions:
                self._fs_rrect(x + p(8), top + p(8), x + p(40), top + p(40), p(16), fill=FS["green"], outline="",
                               tags=tag)
                c.create_text(x + p(24), top + p(24), text="▶", fill=FS["ink"], font=self._fs_font(14), tags=tag)
            c.tag_bind(tag, "<Button-1>", lambda e, name=name: self._fs_click_tile(name))
        k = i - start
        grow = p(18)
        fw, fh = tw + grow, th + grow * 3 // 2
        fx, fy = x0 + k * (tw + gap) - grow // 2, top - grow
        tag = f"tile{i}"
        c.create_rectangle(fx - p(8), fy - p(8), fx + fw + p(8), fy + fh + p(8), outline=FS["glow"],
                           width=p(3), tags=tag)
        c.create_rectangle(fx - p(4), fy - p(4), fx + fw + p(4), fy + fh + p(4), outline=FS["focus"],
                           width=p(4), tags=tag)
        c.create_image(fx, fy, image=self._fs_cover(g, fw, fh), anchor="nw", tags=tag)
        c.tag_bind(tag, "<Button-1>", lambda e: self._fs_click_tile(g))
        name_x = min(max(fx + fw // 2, x0 + tw), W - x0 - tw)
        c.create_text(name_x, fy + fh + p(30), text=g, fill=FS["ink"], font=self._fs_font(19, semi=True),
                      width=2 * tw + gap, justify="center")

    def _fs_game_page(self, g, W, H):
        c, p = self._fs_c, self._fs_px
        cw, ch = p(290), p(435)
        cx, cy = W - p(96) - cw, p(126)
        c.create_rectangle(cx - p(3), cy - p(3), cx + cw + p(3), cy + ch + p(3), outline=FS["line"], width=p(3))
        c.create_image(cx, cy, image=self._fs_cover(g, cw, ch), anchor="nw")
        by = H - p(84) - p(70) - p(72)                   # top of the buttons
        self._fs_info(g, p(96), p(132), min(W * 0.56, cx - p(180)), by - p(40), long=True)

        actions = self._fs_actions(g)
        self._fs_btn = max(0, min(self._fs_btn, len(actions) - 1))
        f = self._fs_font(20, semi=True)
        x = p(96)
        for i, (text, _fn, ok) in enumerate(actions):
            focused = i == self._fs_btn
            w = max(p(200), f.measure(text) + p(64))
            tag = f"btn{i}"
            if focused:
                self._fs_rrect(x - p(5), by - p(5), x + w + p(5), by + p(72) + p(5), p(16), fill="",
                               outline=FS["glow"], width=p(3), tags=tag)
            self._fs_rrect(x, by, x + w, by + p(72), p(12), tags=tag, outline="" if focused else FS["line"],
                           fill=FS["focus"] if focused else FS["button"])
            c.create_text(x + w // 2, by + p(36), text=text, font=f, tags=tag,
                          fill=FS["focus_ink"] if focused else FS["ink"] if ok else FS["dim"])
            c.tag_bind(tag, "<Button-1>", lambda e, i=i: self._fs_click_button(i))
            x += w + p(18)
        gs = self.settings.data["games"].get(g, {})
        hint = ""
        if g in self.sessions:
            hint = "Saves are uploaded automatically when the game closes."
        elif not gs.get("local_path"):
            hint = "To sync this game's saves, choose its save folder in desktop mode (☰ → Desktop mode)."
        elif self.backend is None:
            hint = "Not connected to the cloud — sign in from the menu (☰)."
        elif gs.get("last_sync"):
            ls = gs["last_sync"]
            hint = f"Last synced {'up' if ls.get('direction') == 'up' else 'down'} {fmt_ago(ls.get('time'))}."
        if hint:
            c.create_text(p(96), by + p(72) + p(30), text=hint, anchor="w", fill=FS["dim"], font=self._fs_font(17))

    def _fs_empty(self, W, H):
        c, p = self._fs_c, self._fs_px
        if self.backend is None:
            title = "Connecting…" if self.busy else "Not connected"
            text = ("Open the menu (☰) to sign in or connect. Storage is set up in desktop mode → Settings."
                    if not self.busy else "")
        else:
            title = "Your library is empty"
            text = "Add games in desktop mode: open the menu (☰) and choose Desktop mode."
        c.create_text(W // 2, H // 2 - p(30), text=title, fill=FS["ink"], font=self._fs_font(44, bold=True))
        c.create_text(W // 2, H // 2 + p(36), text=text, fill=FS["sub"], font=self._fs_font(20), width=W * 0.6,
                      justify="center")

    def _fs_footer(self, W, H):
        c, p = self._fs_c, self._fs_px
        top = H - p(84)
        c.create_rectangle(0, top, W, H, fill=FS["panel"], outline="")
        c.create_line(0, top, W, top, fill=FS["line"])
        y = top + p(42)
        status = self.status.cget("text")
        if self.busy or (status and status != "Ready"):
            c.create_text(p(56), y, text=("⟳  " if self.busy else "") + status, anchor="w", fill=FS["sub"],
                          font=self._fs_font(18))
        if self._fs_prompts:
            hints = [("a", "Select"), ("b", "Cancel")]
        elif self._fs_menu is not None:
            hints = [("a", "Select"), ("b", "Close")]
        elif self._fs_focus is None:
            hints = [("start", "Menu")]
        elif self._fs_view == "game":
            hints = [("a", "Select"), ("x", "Play"), ("b", "Back"), ("start", "Menu")]
        else:
            hints = [("a", "Open"), ("x", "Play"), ("lb rb", "Page"), ("start", "Menu")]
        x = W - p(56)
        for b, text in reversed(hints):
            t = c.create_text(x, y, text=text, anchor="e", fill=FS["ink"], font=self._fs_font(18))
            x = c.bbox(t)[0] - p(10)
            for one in reversed(b.split()):
                x = self._fs_glyph(x, y, one) - p(6)
            x -= p(30)

    def _fs_draw_toast(self, W):
        c, p = self._fs_c, self._fs_px
        f = self._fs_font(18)
        text = self._fs_toast_msg if len(self._fs_toast_msg) < 110 else self._fs_toast_msg[:107] + "…"
        w = f.measure(text) + p(56)
        y = p(104)
        self._fs_rrect(W // 2 - w // 2, y, W // 2 + w // 2, y + p(52), p(26), fill=FS["card"], outline=FS["line"])
        c.create_text(W // 2, y + p(26), text=text, fill=FS["ink"], font=f)

    def _fs_draw_menu(self, W, H):
        c, p = self._fs_c, self._fs_px
        scrim = self._fs_scrim(W, H)
        if scrim is not None:
            c.create_image(0, 0, image=scrim, anchor="nw", tags="scrim")
        c.tag_bind("scrim", "<Button-1>", lambda e: (setattr(self, "_fs_menu", None), self._fs_render()))
        pw = min(p(520), W // 2)
        x = W - pw
        c.create_rectangle(x, 0, W, H, fill=FS["panel"], outline="")
        c.create_line(x, 0, x, H, fill=FS["line"], width=p(2))
        t = c.create_text(x + p(48), p(44), text="Menu", anchor="nw", fill=FS["ink"],
                          font=self._fs_font(34, bold=True))
        desc = self._backend_desc if len(self._backend_desc) < 140 else self._backend_desc[:137] + "…"
        t = c.create_text(x + p(48), c.bbox(t)[3] + p(8), text=desc, anchor="nw", fill=FS["dim"],
                          font=self._fs_font(16), width=pw - p(96))
        items = self._fs_menu_items()
        self._fs_menu = min(self._fs_menu, len(items) - 1)
        y = c.bbox(t)[3] + p(32)
        f = self._fs_font(21, semi=True)
        for i, (text, _fn) in enumerate(items):
            focused = i == self._fs_menu
            tag = f"menu{i}"
            self._fs_rrect(x + p(32), y, W - p(32), y + p(66), p(12), tags=tag, outline="",
                           fill=FS["focus"] if focused else FS["panel"])
            c.create_text(x + p(60), y + p(33), text=text, anchor="w", font=f, tags=tag,
                          fill=FS["focus_ink"] if focused else FS["ink"])
            c.tag_bind(tag, "<Button-1>", lambda e, i=i: self._fs_click_menu(i))
            y += p(76)
        sessions = ", ".join(self.sessions)
        if sessions:
            c.create_text(x + p(48), H - p(120), text=f"▶  Playing: {sessions}", anchor="w", fill=FS["sub"],
                          font=self._fs_font(17), width=pw - p(96))

    def _fs_draw_prompt(self, pr, W, H):
        c, p = self._fs_c, self._fs_px
        scrim = self._fs_scrim(W, H)
        if scrim is not None:
            c.create_image(0, 0, image=scrim, anchor="nw")
        cw = min(p(960), W - p(120))
        x, pad = (W - cw) // 2, p(44)
        y = pad
        first = c.create_text(x + pad, y, text=pr["title"], anchor="nw", width=cw - 2 * pad, fill=FS["ink"],
                              font=self._fs_font(30, bold=True), tags="prompt")
        y = c.bbox(first)[3] + p(16)
        t = c.create_text(x + pad, y, text=pr["text"], anchor="nw", width=cw - 2 * pad, fill=FS["sub"],
                          font=self._fs_font(18), tags="prompt")
        y = c.bbox(t)[3] + p(30)
        f = self._fs_font(20, semi=True)
        for i, (text, _value) in enumerate(pr["choices"]):
            focused = i == pr["focus"]
            tag = f"choice{i}"
            self._fs_rrect(x + pad, y, x + cw - pad, y + p(62), p(12), tags=("prompt", tag), outline="",
                           fill=FS["focus"] if focused else FS["button"])
            c.create_text(W // 2, y + p(31), text=text, font=f, tags=("prompt", tag),
                          fill=FS["focus_ink"] if focused else FS["ink"])
            c.tag_bind(tag, "<Button-1>", lambda e, i=i: pr["var"].set(i))
            y += p(74)
        bottom = y - p(12) + pad
        card = self._fs_rrect(x, 0, x + cw, bottom, p(20), fill=FS["card"], outline=FS["line"], tags="prompt")
        c.tag_lower(card, first)
        c.move("prompt", 0, max(p(24), (H - p(84) - bottom) // 2))
