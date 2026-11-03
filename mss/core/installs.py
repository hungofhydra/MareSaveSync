"""Where a game is installed on this PC and which .exe starts it, from what Steam, the Epic Games Launcher and
GOG Galaxy record. Used to set up a game without a file browser (fullscreen mode, with a controller).

Epic and GOG record the exact .exe. Steam only records the install folder, so its .exe files are ranked by
how much they look like the game's main program (name, Unity's <name>_Data folder, how deep they are).
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
from pathlib import Path

from ..providers.ludusavi import norm
from .detect import steam_libraries

# .exe files that are never the game itself
JUNK = re.compile(r"unins|setup|install|redist|prereq|crash|report|dxsetup|directx|dotnet|easyanticheat|eac_|"
                  r"battleye|be_service|uploader|updater|helper|cefprocess|launcherpatcher", re.I)
SKIP_DIRS = {"_commonredist", "commonredist", "redist", "_redist", "redistributables", "directx", "__installer",
             "easyanticheat", "battleye", "support", "vcredist", "dotnetfx", "engine", "prereqs"}
MAX_DEPTH = 2                       # folders below the install folder to look in
MAX_EXES = 5


def steam_folder(appid) -> Path | None:
    """A Steam game's install folder, from its appmanifest."""
    for lib in steam_libraries():
        try:
            text = (lib / "steamapps" / f"appmanifest_{int(appid)}.acf").read_text("utf-8", errors="replace")
        except (OSError, ValueError, TypeError):
            continue
        m = re.search(r'"installdir"\s+"([^"]+)"', text)
        d = lib / "steamapps" / "common" / m.group(1) if m else None
        if d and d.is_dir():
            return d
    return None


def epic_games() -> list[tuple[str, Path, Path | None]]:
    """[(name, install folder, .exe)] of the games the Epic Games Launcher installed."""
    if sys.platform != "win32":
        return []
    d = Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData") / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    out = []
    for item in d.glob("*.item") if d.is_dir() else []:
        try:
            m = json.loads(item.read_text("utf-8", errors="replace"))
            folder = Path(m["InstallLocation"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        exe = folder / m["LaunchExecutable"] if m.get("LaunchExecutable") else None
        out.append((m.get("DisplayName") or folder.name, folder, exe))
    return out


def gog_games() -> list[tuple[str, Path, Path | None]]:
    """[(name, install folder, .exe)] of the games GOG Galaxy (or a GOG installer) installed."""
    if sys.platform != "win32":
        return []
    import winreg
    out = []
    for path in (r"SOFTWARE\WOW6432Node\GOG.com\Games", r"SOFTWARE\GOG.com\Games"):
        try:
            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
        except OSError:
            continue
        with root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as k:
                        v = lambda n: winreg.QueryValueEx(k, n)[0]  # noqa: E731
                        folder = Path(v("path"))
                        try:
                            exe = Path(v("exe"))
                        except OSError:
                            exe = None
                        out.append((v("gameName"), folder, exe if exe is None or exe.is_absolute() else folder / exe))
                except OSError:
                    continue
        if out:
            break
    return out


def game_exes(folder: Path, names) -> list[Path]:
    """The .exe files in an install folder, most likely the game's own first."""
    wanted = [norm(n) for n in [*names, folder.name] if n]
    found = []
    for d, dirs, files in os.walk(folder):
        depth = len(Path(d).relative_to(folder).parts)
        dirs[:] = [x for x in dirs if x.lower() not in SKIP_DIRS and depth < MAX_DEPTH]
        for f in files:
            if f.lower().endswith(".exe") and not JUNK.search(f):
                found.append((Path(d) / f, depth))

    def score(item):
        exe, depth = item
        stem = norm(exe.stem)
        s = max((difflib.SequenceMatcher(None, stem, w).ratio() for w in wanted), default=0)
        if (exe.parent / f"{exe.stem}_Data").is_dir():       # a Unity game's own program
            s += 0.5
        return s - 0.15 * depth
    return [exe for exe, _ in sorted(found, key=score, reverse=True)]


def find(names, steam_ids=(), dir_names=()) -> tuple[Path | None, list[Path]]:
    """(install folder or None, likely .exe files best first) for a game known by these names / Steam ids.
    dir_names: install folder names to look for in the Steam libraries (from Ludusavi's list)."""
    wanted = {norm(n) for n in names if n}
    folders: list[Path] = []
    exact: list[Path] = []
    for sid in steam_ids:
        d = steam_folder(sid) if sid else None
        if d:
            folders.append(d)
    for name, folder, exe in epic_games() + gog_games():
        if norm(name) in wanted and folder.is_dir():
            folders.append(folder)
            if exe and exe.is_file():
                exact.append(exe)
    if not folders:
        for lib in steam_libraries():
            folders += [d for d in (lib / "steamapps" / "common" / n for n in dir_names) if d.is_dir()]
    exes = list(exact)
    for f in dict.fromkeys(folders):
        exes += game_exes(f, names)
    exes = list({os.path.normcase(str(e)): e for e in exes}.values())    # each once, best first
    return (folders[0] if folders else None), exes[:MAX_EXES]
