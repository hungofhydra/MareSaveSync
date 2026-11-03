"""Save folder paths that work on every PC.

A folder under a well-known place (your user folder, AppData, Documents, …) is stored as a template like
"<home>/AppData/LocalLow/Team Cherry/Hollow Knight", the same placeholders Ludusavi's manifest uses. Another
PC expands it to its own user folder, so a game's save folder only has to be found once.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WIN = sys.platform == "win32"

FOLDERID_DOCUMENTS = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"


def _known_folder(guid: str) -> str | None:
    """A Windows known folder's real location (Documents may be moved, e.g. into OneDrive)."""
    if not WIN:
        return None
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        u = uuid.UUID(guid)
        g = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
        p = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) != 0:
            return None
        try:
            return p.value
        finally:
            ctypes.windll.ole32.CoTaskMemFree(p)
    except Exception:
        return None


_places: dict[str, str] | None = None


def places() -> dict[str, str]:
    """{placeholder: folder on this PC} for the placeholders that mean the same thing on every PC."""
    global _places
    if _places is None:
        home = str(Path.home())
        env = os.environ.get
        p = {"<home>": home,
             "<winAppData>": env("APPDATA") or os.path.join(home, "AppData", "Roaming"),
             "<winLocalAppData>": env("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"),
             "<winDocuments>": _known_folder(FOLDERID_DOCUMENTS) or os.path.join(home, "Documents"),
             "<winProgramData>": env("PROGRAMDATA") or r"C:\ProgramData",
             "<winPublic>": env("PUBLIC") or r"C:\Users\Public",
             "<winDir>": env("WINDIR") or r"C:\Windows"}
        _places = {k: os.path.normpath(v) for k, v in p.items()}
    return _places


def user_name() -> str:
    return os.environ.get("USERNAME") or Path.home().name


def expand(template: str) -> str | None:
    """The folder a template means on this PC, or None if it has a placeholder this PC can't fill in."""
    if not template:
        return None
    t = template.replace("<osUserName>", user_name())
    for k, v in places().items():
        if t == k or t.startswith(k + "/"):
            t = v + t[len(k):]
            break
    if "<" in t:
        return None
    return os.path.normpath(t)


def portable(path) -> str | None:
    """The template for a folder on this PC, or None if it isn't under a well-known place (e.g. D:\\Games)."""
    p = os.path.normpath(str(path))
    key = os.path.normcase(p)
    for k, v in sorted(places().items(), key=lambda kv: -len(kv[1])):    # most specific place first
        base = os.path.normcase(v)
        if k != "<winDir>" and (key == base or key.startswith(base.rstrip(os.sep) + os.sep)):
            rest = p[len(v):].strip("\\/").replace("\\", "/")
            return f"{k}/{rest}" if rest else k
    return None


def too_broad(path) -> bool:
    """A well-known folder itself (Documents, AppData, …), one that holds them (C:\\Users) or Windows itself:
    never a game's save folder."""
    key = os.path.normcase(os.path.normpath(str(path)))
    pl = places()
    broad = [v for k, v in pl.items() if k != "<winDir>"]
    broad += [os.path.join(pl["<home>"], *x) for x in (
        ("AppData",), ("AppData", "LocalLow"), ("Saved Games",), ("Documents", "My Games"))]
    broad += [os.path.join(pl["<winDocuments>"], "My Games"), os.path.join(pl["<winLocalAppData>"], "Packages"),
              os.path.join(pl["<winProgramData>"], "Packages")]
    broad = [os.path.normcase(b) for b in broad]
    win = os.path.normcase(pl["<winDir>"])
    return (key in broad or any(b.startswith(key.rstrip(os.sep) + os.sep) for b in broad)
            or key == win or key.startswith(win + os.sep))
