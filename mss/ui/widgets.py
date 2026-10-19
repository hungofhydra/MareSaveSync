"""Reusable classic-looking widgets and small UI helpers."""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path

from .theme import UI, UIB, WIN, T

try:
    from PIL import Image, ImageTk
except Exception:            # Pillow missing: no image resizing
    Image = ImageTk = None


def open_in_explorer(path: Path):
    path = Path(path)
    if WIN:
        if path.is_file():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if path.is_file() else ["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path if path.is_dir() else path.parent)])


def _mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def menu(parent):
    return tk.Menu(parent, tearoff=0, bg=T["face"], fg=T["ink"], activebackground=T["navy"],
                   activeforeground=T["hi"], font=UI, bd=1, relief="raised")


class Btn(tk.Button):
    """Raised classic button. kind: "" | "default" (bold, black frame) | "danger"."""

    def __init__(self, master, text="", command=None, kind="", **kw):
        fg = T["danger"] if kind == "danger" else T["ink"]
        opts = dict(text=text, command=command, bg=T["face"], fg=fg, activebackground=T["face"],
                    activeforeground=fg, disabledforeground=T["shadow"], relief="raised", bd=2,
                    font=UIB if kind == "default" else UI, padx=10, pady=1, cursor="hand2",
                    highlightthickness=1 if kind == "default" else 0,
                    highlightbackground=T["dark"], highlightcolor=T["dark"])
        opts.update(kw)
        super().__init__(master, **opts)

    def state(self, spec):          # ttk-style API used by the app logic
        self.configure(state="disabled" if "disabled" in spec else "normal",
                       cursor="arrow" if "disabled" in spec else "hand2")


def check(master, text, var, command=None):
    return tk.Checkbutton(master, text=text, variable=var, command=command, bg=T["face"], fg=T["ink"],
                          activebackground=T["face"], selectcolor=T["field"], font=UI, bd=0,
                          highlightthickness=0)


def label(master, text="", muted=False, bold=False, **kw):
    opts = dict(text=text, bg=T["face"], fg=T["muted"] if muted else T["ink"], font=UIB if bold else UI)
    opts.update(kw)
    return tk.Label(master, **opts)


def sunken_label(master, text="", **kw):
    opts = dict(text=text, bg=T["face"], fg=T["ink"], font=UI, relief="sunken", bd=1, anchor="w", padx=6)
    opts.update(kw)
    return tk.Label(master, **opts)


class TitleBar(tk.Canvas):
    """Gradient title bar with an icon, a title and optional working window buttons."""

    def __init__(self, master, text, icon=None, buttons=None, active=True):
        super().__init__(master, width=60, height=22, highlightthickness=0, bd=0, bg=T["t1"])
        self.text, self.icon, self.buttons, self.active = text, icon, buttons or [], active
        self.bind("<Configure>", lambda e: self._draw())

    def set_text(self, text):
        self.text = text
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = max(self.winfo_width(), 50), 22
        c1, c2 = (T["t1"], T["t2"]) if self.active else (T["t1i"], T["t2i"])
        n = 48
        for i in range(n):
            self.create_rectangle(w * i / n, 0, w * (i + 1) / n + 1, h, fill=_mix(c1, c2, i / (n - 1)), width=0)
        x = 5
        if self.icon:
            self.create_image(x, h // 2, image=self.icon, anchor="w")
            x += 21
        self.create_text(x, h // 2, text=self.text, fill=T["hi"], font=UIB, anchor="w")
        bx = w - 4
        for glyph, cmd in reversed(self.buttons):
            bx -= 16
            tag = f"b{bx}"
            y0 = 4
            self.create_rectangle(bx, y0, bx + 15, y0 + 13, fill=T["face"], outline=T["face"], tags=tag)
            self.create_line(bx, y0 + 13, bx, y0, bx + 15, y0, fill=T["hi"], tags=tag)
            self.create_line(bx + 15, y0, bx + 15, y0 + 13, bx, y0 + 13, fill=T["dark"], tags=tag)
            self.create_text(bx + 8, y0 + 7, text=glyph, font=(UI[0], 7, "bold"), fill=T["ink"], tags=tag)
            self.tag_bind(tag, "<Button-1>", lambda e, c=cmd: c())
            if glyph == "×":
                bx -= 2


def window(parent, title, icon=None, buttons=None):
    """A classic window: raised silver frame + gradient title bar. Returns (outer, bar, body)."""
    outer = tk.Frame(parent, bg=T["face"], relief="raised", bd=2)
    bar = TitleBar(outer, title, icon, buttons)
    bar.pack(fill="x", padx=1, pady=1)
    body = tk.Frame(outer, bg=T["face"])
    body.pack(fill="both", expand=True, padx=4, pady=(2, 4))
    return outer, bar, body


def load_photo(path, max_w=None, max_h=None, square=None):
    """PhotoImage from a file, resized to fit (needs Pillow for anything but PNG/GIF at 1:1)."""
    if Image is not None:
        im = Image.open(path).convert("RGBA")
        if square:
            side = min(im.size)
            l, t = (im.width - side) // 2, 0
            im = im.crop((l, t, l + side, t + side)).resize((square, square), Image.LANCZOS)
        elif max_w and max_h:
            im.thumbnail((max_w, max_h), Image.LANCZOS)
        return ImageTk.PhotoImage(im)
    ph = tk.PhotoImage(file=str(path))
    if max_w and max_h:
        f = max(1, -(-ph.width() // max_w), -(-ph.height() // max_h))
        if f > 1:
            ph = ph.subsample(f, f)
    return ph


def center_modal(win, parent):
    """Place a dialog over its parent, make it modal and wait until it closes."""
    win.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_reqwidth()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_reqheight()) // 3
    win.geometry(f"+{max(0, x)}+{max(0, y)}")
    win.grab_set()
    win.wait_window()
