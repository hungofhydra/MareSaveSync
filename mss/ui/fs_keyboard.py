"""An on-screen keyboard for fullscreen mode, so a game's name can be typed with a controller.

fs_type() shows it and waits, like _fs_ask(): it's one of fullscreen mode's prompts ({"kind": "keyboard"}).
A types the focused key, X deletes, Y is a space, LB is Shift, ☰ is Done and B cancels. A real keyboard
types into it too (Enter is Done), and the keys can be tapped or clicked.
"""
from __future__ import annotations

import tkinter as tk

from .fullscreen import FS

# Each row is 10 units wide; a key is (label, what it does, units). Shift works for one character (like a phone)
# and is on for the first one.
CHARS = [("1234567890", "!?&()+#/@_"), ("qwertyuiop", "QWERTYUIOP"), ("asdfghjkl'", 'ASDFGHJKL"'),
         ("zxcvbnm-:.", "ZXCVBNM,;*")]
SPECIAL = [("⇧  Shift", "shift", 2), ("Space", " ", 4), ("⌫", "back", 2), ("Done", "done", 2)]
MAX_LEN = 80


class FsKeyboardMixin:
    """Part of App (see ui/app.py)."""

    def fs_type(self, title, text="", hint=""):
        """Ask for some text in fullscreen mode. The text (stripped), or None if cancelled."""
        var = tk.IntVar(self, -2)
        kb = dict(kind="keyboard", title=title, hint=hint, text=text, row=1, unit=0, shift=not text, var=var)
        self._fs_prompts.append(kb)
        self.show_window()
        self._fs_render()
        try:
            self.wait_variable(var)
            done = var.get() == 1
        except tk.TclError:                   # the app is closing
            return None
        finally:
            self._fs_prompts.remove(kb)
        if self.fs_on:
            self._fs_render()
        return kb["text"].strip() if done else None

    @staticmethod
    def _kb_rows(kb):
        rows = [[(ch, ch, 1) for ch in (shifted if kb["shift"] else plain)] for plain, shifted in CHARS]
        return rows + [SPECIAL]

    @staticmethod
    def _kb_index(row, unit):
        """Which key of a row covers this unit."""
        x = 0
        for i, (_label, _act, w) in enumerate(row):
            if x <= unit < x + w:
                return i
            x += w
        return len(row) - 1

    def _kb_press(self, kb, act):
        if act == "done":
            kb["var"].set(1)
            return
        if act == "shift":
            kb["shift"] = not kb["shift"]
        elif act == "back":
            kb["text"] = kb["text"][:-1]
            if not kb["text"]:
                kb["shift"] = True              # empty again: the next letter starts it, capitalised
        elif len(kb["text"]) < MAX_LEN:
            kb["text"] += act
            kb["shift"] = False
        self._fs_render()

    def _kb_input(self, kb, b):
        """A controller button (or an arrow / Enter key) while the keyboard is open."""
        rows = self._kb_rows(kb)
        row = rows[kb["row"]]
        i = self._kb_index(row, kb["unit"])
        if b in ("left", "right"):
            i = (i + (1 if b == "right" else -1)) % len(row)
            kb["unit"] = sum(w for _l, _a, w in row[:i])
        elif b in ("up", "down"):
            kb["row"] = (kb["row"] + (1 if b == "down" else -1)) % len(rows)
        elif b == "a":
            self._kb_press(kb, row[i][1])
            return
        elif b == "x":
            self._kb_press(kb, "back")
            return
        elif b == "y":
            self._kb_press(kb, " ")
            return
        elif b == "lb":
            self._kb_press(kb, "shift")
            return
        elif b == "start":
            self._kb_press(kb, "done")
            return
        elif b == "b":
            kb["var"].set(-1)
            return
        self._fs_render()

    def _fs_key(self, e, b):
        """A key on a real keyboard. While the on-screen keyboard is open, letters type into it."""
        kb = self._fs_prompts[-1] if self._fs_prompts else None
        if kb is None or kb.get("kind") != "keyboard":
            if b is None:
                return None                     # not ours: let F11 and the like through
            self._fs_input(b)
            return "break"
        ks = e.keysym
        if ks in ("Return", "KP_Enter"):
            self._kb_press(kb, "done")
        elif ks == "BackSpace":
            self._kb_press(kb, "back")
        elif ks == "Escape":
            kb["var"].set(-1)
        elif ks in ("Left", "Right", "Up", "Down"):
            self._kb_input(kb, b)
        elif e.char and e.char.isprintable() and len(kb["text"]) < MAX_LEN:
            kb["text"] += e.char
            kb["shift"] = False
            self._fs_render()
        return "break"

    def _kb_click(self, kb, r, i):
        kb["row"], kb["unit"] = r, sum(w for _l, _a, w in self._kb_rows(kb)[r][:i])
        self._kb_press(kb, self._kb_rows(kb)[r][i][1])

    def _kb_draw(self, kb, W, H):
        c, p = self._fs_c, self._fs_px
        scrim = self._fs_scrim(W, H)
        if scrim is not None:
            c.create_image(0, 0, image=scrim, anchor="nw")
        cw = min(p(1180), W - p(80))
        x, pad = (W - cw) // 2, p(40)
        gap, kh = p(10), p(66)
        ch = 2 * pad + p(56) + (p(34) if kb["hint"] else 0) + p(92) + 5 * (kh + gap) - gap
        top = max(p(24), (H - p(84) - ch) // 2)
        y = top + pad
        self._fs_rrect(x, top, x + cw, top + ch, p(20), fill=FS["card"], outline=FS["line"])
        c.create_text(x + pad, y, text=kb["title"], anchor="nw", fill=FS["ink"], font=self._fs_font(30, bold=True))
        y += p(56)
        if kb["hint"]:
            c.create_text(x + pad, y, text=kb["hint"], anchor="nw", fill=FS["dim"], font=self._fs_font(17),
                          width=cw - 2 * pad)
            y += p(34)
        self._fs_rrect(x + pad, y, x + cw - pad, y + p(64), p(10), fill=FS["bg"], outline=FS["glow"])
        f = self._fs_font(26, semi=True)
        shown = kb["text"]
        while shown and f.measure(shown + "▏") > cw - 2 * pad - p(40):
            shown = shown[1:]                   # long text: show its end
        c.create_text(x + pad + p(20), y + p(32), text=shown + "▏", anchor="w", fill=FS["ink"], font=f)
        y += p(64) + p(28)

        unit_w = (cw - 2 * pad - 9 * gap) / 10
        kf, sf = self._fs_font(24, semi=True), self._fs_font(19, semi=True)
        rows = self._kb_rows(kb)
        focus_i = self._kb_index(rows[kb["row"]], kb["unit"])
        for r, row in enumerate(rows):
            kx = x + pad
            for i, (label, act, w) in enumerate(row):
                kw = w * unit_w + (w - 1) * gap
                focused = r == kb["row"] and i == focus_i
                on = act == "shift" and kb["shift"]
                tag = f"key{r}_{i}"
                self._fs_rrect(int(kx), y, int(kx + kw), y + kh, p(10), tags=tag, outline="",
                               fill=FS["focus"] if focused else FS["blue"] if on else FS["button"])
                c.create_text(int(kx + kw / 2), y + kh // 2, text=label, tags=tag, font=kf if w == 1 else sf,
                              fill=FS["focus_ink"] if focused else FS["ink"])
                c.tag_bind(tag, "<Button-1>", lambda e, r=r, i=i: self._kb_click(kb, r, i))
                kx += kw + gap
            y += kh + gap
