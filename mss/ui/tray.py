"""System-tray icon (next to the clock). Minimizing hides the window there; click the icon to bring it back.
Its right-click menu also plays the recently played games, so the app can stay in the tray.
"""
from __future__ import annotations

import threading

from .. import APP_TITLE, applog
from ..paths import ASSETS

try:
    import pystray
    from PIL import Image
except Exception:            # no pystray/Pillow: minimizing goes to the taskbar as usual
    pystray = None

RECENT = 6                   # recently played games in the menu


class TrayMixin:
    """Part of App (see ui/app.py)."""

    _tray = None
    _tray_games: list = []   # [(game, playing)] the menu shows; worked out on the Tk thread

    def _start_tray(self):
        if pystray is None:
            return
        try:
            # On Windows pystray builds the menu once: refresh_tray_menu() has it rebuilt when the list changes
            self._tray = pystray.Icon("MareSaveSync", Image.open(ASSETS / "icon32.png"), APP_TITLE,
                                      pystray.Menu(self._tray_items))
            threading.Thread(target=self._tray.run, daemon=True).start()
        except Exception as ex:
            self._tray = None
            applog.log.warning(f"No tray icon: {ex}")
        self.bind("<Unmap>", self._on_unmap)

    def _tray_items(self):
        """The menu (called by pystray). Clicks arrive on the tray's thread, so they only post to the queue."""
        post = lambda what: lambda: self.q.put(("tray", what))  # noqa: E731
        yield pystray.MenuItem(f"Open {APP_TITLE}", post("show"), default=True)
        yield pystray.Menu.SEPARATOR
        for g, playing in list(self._tray_games):
            if playing:
                yield pystray.MenuItem(f"▶  {g}  (playing)", None, enabled=False)
            else:
                yield pystray.MenuItem(f"▶  {g}", post(("play", g)))
        yield pystray.Menu.SEPARATOR
        yield pystray.MenuItem("Fullscreen mode", post("fullscreen"))
        yield pystray.MenuItem("Exit", post("exit"))

    def refresh_tray_menu(self):
        """The recently played games changed (or one started / stopped): rebuild the tray menu, a moment later."""
        if self._tray is not None:
            self._debounce("tray", 300, self._update_tray_menu)

    def _update_tray_menu(self):
        self._tray_games = [(g, g in self.sessions) for g in self.recent_games(RECENT)]
        try:
            self._tray.update_menu()
        except Exception as ex:             # not running yet: it builds the menu itself when it starts
            applog.log.info(f"Tray menu not updated: {ex}")

    def minimize(self):
        """Hide the window to the tray (or to the taskbar when there's no tray icon)."""
        if self._tray is not None:
            self.withdraw()
        else:
            self.iconify()

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        if self.fs_on:                      # Windows forgets fullscreen while the window is hidden
            self.attributes("-fullscreen", True)
            self._fs_c.focus_set()

    def notify(self, text):
        """A Windows notification from the tray icon (does nothing without one)."""
        if self._tray is not None:
            try:
                self._tray.notify(text, APP_TITLE)
            except Exception:
                pass

    def set_tray_text(self, text=""):
        if self._tray is not None:
            self._tray.title = f"{APP_TITLE} — {text}" if text else APP_TITLE

    def _on_unmap(self, ev):
        # Windows' own minimize button (or Win+D …) also goes to the tray.
        if ev.widget is self and self._tray is not None and self.state() == "iconic":
            self.after(0, self.withdraw)

    def _tray_event(self, what):
        if what == "show":
            self.show_window()
        elif what == "exit":
            self.destroy()
        elif what == "fullscreen":
            self.show_window()
            self.enter_fullscreen()
        elif isinstance(what, tuple) and what[0] == "play":
            self._tray_play(what[1])

    def _tray_play(self, g):
        if g not in self.all_games or g in self.sessions:
            return
        if self.busy:
            self.notify(f"Can't start {g} yet: please wait for the current task to finish.")
            return
        if self.launch_command(g) is None:
            self.show_window()              # its .exe (or emulator / ROM) has to be chosen first
        self._fs_play(g) if self.fs_on else self.play(g)

    def destroy(self):
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
            self._tray = None
        super().destroy()
