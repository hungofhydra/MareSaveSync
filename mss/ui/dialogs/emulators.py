"""Setting up emulators on this PC: each has a name, its program and the arguments that start a ROM ({rom})."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

from ...core import emulators
from ..theme import MONO, T
from ..widgets import Btn, label, window

if TYPE_CHECKING:
    from ..app import App


class EmulatorsDialog(tk.Toplevel):
    def __init__(self, app: App, on_close=None):
        super().__init__(app)
        self.app, self.on_close = app, on_close
        self.title("Emulators — Mare Save Sync")
        self.configure(bg=T["desk"])
        self.resizable(False, False)
        self.transient(app)
        outer, _bar, body = window(self, "Emulators on this PC", app.icon16)
        outer.pack(fill="both", expand=True, padx=10, pady=10)
        label(body, "A game can be started by an emulator with its ROM: choose the emulator and the ROM on the\n"
                    "game's Game tab. Emulators are set up on each PC (their programs are in different places).",
              justify="left").pack(anchor="w", pady=(2, 8))

        row = tk.Frame(body, bg=T["face"])
        row.pack(fill="both", expand=True)
        lf = tk.Frame(row, bg=T["face"])
        lf.pack(side="left", fill="y")
        self.listbox = tk.Listbox(lf, width=22, height=10, exportselection=False, activestyle="none",
                                  **app._field(lf))
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._show())
        Btn(lf, "Add emulator…", self._add).pack(fill="x", pady=(6, 0))

        form = tk.Frame(row, bg=T["face"], padx=12)
        form.pack(side="left", fill="both", expand=True)
        self.name, self.exe, self.args = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for text, var, browse in (("Name:", self.name, None), ("Program:", self.exe, self._browse),
                                  ("Arguments:", self.args, None)):
            r = tk.Frame(form, bg=T["face"])
            r.pack(fill="x", pady=(0, 6))
            label(r, text, width=11, anchor="w").pack(side="left")
            field = app._field(r, font=MONO) if var is self.args else app._field(r)
            tk.Entry(r, textvariable=var, width=52, **field).pack(side="left", fill="x", expand=True)
            if browse:
                Btn(r, "Browse…", browse).pack(side="left", padx=(6, 0))
        label(form, "{rom} is replaced by the game's ROM, e.g.   -L \"cores\\snes9x_libretro.dll\" \"{rom}\"\n"
                    "The game's own launch options are added at the end. Relative paths start in the "
                    "emulator's folder.", muted=True, justify="left").pack(anchor="w")
        bf = tk.Frame(form, bg=T["face"])
        bf.pack(fill="x", pady=(10, 0))
        self.save_btn = Btn(bf, "Save", self._save, kind="default")
        self.save_btn.pack(side="left")
        self.del_btn = Btn(bf, "Remove", self._remove, kind="danger")
        self.del_btn.pack(side="left", padx=6)

        Btn(body, "Close", self._close, padx=18).pack(anchor="e", pady=(10, 0))
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.editing: str | None = None
        self._fill()
        self.grab_set()

    @property
    def profiles(self) -> dict:
        return self.app.settings.data.setdefault("emulators", {})

    def _fill(self, select=None):
        self.listbox.delete(0, "end")
        names = sorted(self.profiles, key=str.lower)
        for n in names:
            self.listbox.insert("end", f"  {n}")
        if select in names:
            self.listbox.selection_set(names.index(select))
        elif names:
            self.listbox.selection_set(0)
        self._show()

    def _show(self):
        sel = self.listbox.curselection()
        names = sorted(self.profiles, key=str.lower)
        self.editing = names[sel[0]] if sel else None
        p = self.profiles.get(self.editing, {})
        self.name.set(self.editing or "")
        self.exe.set(p.get("exe", ""))
        self.args.set(p.get("args", ""))
        on = lambda b, ok: b.state(["!disabled"] if ok else ["disabled"])  # noqa: E731
        on(self.save_btn, self.editing is not None)
        on(self.del_btn, self.editing is not None)

    def _pick_program(self):
        return filedialog.askopenfilename(parent=self, title="Emulator program",
                                          filetypes=[("Programs", "*.exe"), ("All files", "*.*")])

    def _browse(self):
        p = self._pick_program()
        if p:
            self.exe.set(str(Path(p)))

    def _add(self):
        p = self._pick_program()
        if not p:
            return
        name, args = emulators.preset_for(p)
        base, n = name, 2
        while name in self.profiles:
            name, n = f"{base} {n}", n + 1
        self.profiles[name] = {"exe": str(Path(p)), "args": args}
        self.app.settings.save()
        self.app.log(f"Emulator “{name}” added: {p}")
        self._fill(select=name)
        if "CORE" in args:
            messagebox.showinfo("Emulators", "RetroArch needs to know which core to use: change CORE in the "
                                "arguments to the core's file name (see RetroArch's cores folder), or add one "
                                "RetroArch profile per core.", parent=self)

    def _save(self):
        old, name = self.editing, self.name.get().strip()
        if not old or not name:
            return
        if name != old and name in self.profiles:
            messagebox.showerror("Emulators", f"There's already an emulator called “{name}”.", parent=self)
            return
        self.profiles.pop(old)
        self.profiles[name] = {"exe": self.exe.get().strip().strip('"'), "args": self.args.get().strip()}
        if name != old:                          # the games using it follow the new name
            for gs in self.app.settings.data.get("games", {}).values():
                if gs.get("emulator") == old:
                    gs["emulator"] = name
        self.app.settings.save()
        self._fill(select=name)

    def _remove(self):
        name = self.editing
        users = [g for g, gs in self.app.settings.data.get("games", {}).items() if gs.get("emulator") == name]
        if not name or not messagebox.askyesno(
                "Emulators", f"Remove the emulator “{name}”?" + (
                    f"\n\n{len(users)} game(s) use it and will need another one: {', '.join(users[:5])}"
                    if users else ""), parent=self):
            return
        self.profiles.pop(name, None)
        self.app.settings.save()
        self._fill()

    def _close(self):
        self.destroy()
        if self.on_close:
            self.on_close()
