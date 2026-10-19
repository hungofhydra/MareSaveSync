"""Where things are: bundled assets, the source/exe folder, and the local data folder."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME

FROZEN = getattr(sys, "frozen", False)
SOURCE_ROOT = Path(__file__).resolve().parent.parent          # the folder with app.py, when running from source
RES_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))         # files bundled into the exe (assets, .env)
ASSETS = RES_DIR / "assets"
APP_HOME = Path(sys.executable).resolve().parent if FROZEN else SOURCE_ROOT   # next to the exe / app.py

_app_dir: Path | None = None


def user_data_dir() -> Path:
    """The per-user app-data folder (%APPDATA%\\SaveSync on Windows)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


class PortableError(OSError):
    """The exe's folder can't hold its data folder (e.g. it's in Program Files or on a read-only drive)."""


def app_dir() -> Path:
    """Where settings, the sign-in token, cached art and backups live.

    The built exe is portable: everything goes in the `data` folder next to it, never anywhere else (on its
    first run an existing %APPDATA%\\SaveSync from an older version is copied in). If that folder can't be
    written, PortableError is raised rather than quietly using another place. Running from source, it's the
    per-user app-data folder.
    """
    global _app_dir
    if _app_dir is None:
        if FROZEN:
            _app_dir = _portable_dir()
        else:
            _app_dir = user_data_dir()
            _app_dir.mkdir(parents=True, exist_ok=True)
    return _app_dir


def _portable_dir() -> Path:
    import shutil
    d = APP_HOME / "data"
    try:
        if not d.is_dir():
            old = user_data_dir()
            if old.is_dir():
                tmp = d.with_name("data.copying")
                shutil.rmtree(tmp, ignore_errors=True)
                shutil.copytree(old, tmp)
                os.replace(tmp, d)
            else:
                d.mkdir()
        probe = d / ".write-test"
        probe.write_text("")
        probe.unlink()
        return d
    except OSError as ex:
        raise PortableError(
            f"Mare Save Sync keeps all its settings in a “data” folder next to the program, but can't write to\n"
            f"{d}\n({ex.strerror or ex})\n\nMove the whole {APP_HOME.name} folder somewhere you can write to — "
            "your Documents, another drive or a USB stick (not Program Files) — and start it again.") from None
