"""System-tray icon (next to the clock). Minimizing hides the window there; click the icon to bring it back."""
from __future__ import annotations

import threading

from .. import APP_TITLE
from ..paths import ASSETS

try:
    import pystray
    from PIL import Image
except Exception:            # no pystray/Pillow: minimizing goes to the taskbar as usual
    pystray = None


class TrayMixin:
    """Part of App (see ui/app.py)."""

    _tray = None

    def _start_tray(self):
        if pystray is None:
            return
        try:
            menu = pystray.Menu(
                pystray.MenuItem(f"Open {APP_TITLE}", lambda: self.q.put(("tray", "show")), default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", lambda: self.q.put(("tray", "exit"))))
            self._tray = pystray.Icon("MareSaveSync", Image.open(ASSETS / "icon32.png"), APP_TITLE, menu)
            threading.Thread(target=self._tray.run, daemon=True).start()
        except Exception as ex:
            self._tray = None
            print(f"No tray icon: {ex}")
        self.bind("<Unmap>", self._on_unmap)

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

    def destroy(self):
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
            self._tray = None
        super().destroy()
