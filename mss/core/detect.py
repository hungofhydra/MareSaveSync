"""Finding a game's save folders on this PC from its save path patterns (see providers/ludusavi.py).

A pattern names save files, e.g. "<home>/AppData/LocalLow/Team Cherry/Hollow Knight/*.dat"; the app syncs
folders, so the folder is the pattern up to its first wildcard. "<base>" is the game's install folder: the
one its .exe is in, or its folder in a Steam library. "<storeUserId>" (a Steam/Ubisoft account id) matches
whichever ids are on this PC.
"""
from __future__ import annotations

import glob
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import savepaths

WILD = re.compile(r"[*?\[]")
UID = "\x01"                    # stands for <storeUserId> while a pattern is being expanded
MAX_COUNT = 5000                # stop counting files in a folder after this many


@dataclass
class Found:
    path: str
    files: int = 0              # save files found in it
    newest: float = 0           # newest file's modification time
    exists: bool = True         # False: where the game would save, but it hasn't on this PC yet


def steam_libraries() -> list[Path]:
    """Steam's library folders on this PC (where steamapps/common is)."""
    if sys.platform != "win32":
        return []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            root = Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        return []
    libs = [root]
    try:
        text = (root / "steamapps" / "libraryfolders.vdf").read_text("utf-8", errors="replace")
        libs += [Path(m.group(1).replace("\\\\", "\\")) for m in re.finditer(r'"path"\s+"([^"]+)"', text)]
    except OSError:
        pass
    return list({os.path.normcase(str(p)): p for p in libs}.values())


def install_dirs(entry: dict, exe=None) -> list[str]:
    """Where the game may be installed: around its .exe, and its folder in each Steam library."""
    names = entry.get("d") or []
    wanted = {n.casefold() for n in names}
    out = []
    if exe:
        here = Path(exe).parent
        out.append(next((q for q in [here, *list(here.parents)[:4]] if q.name.casefold() in wanted), here))
    for lib in steam_libraries():
        out += [lib / "steamapps" / "common" / n for n in names]
    return list({os.path.normcase(str(p)): str(p) for p in out if p.is_dir()}.values())


def _expand(pattern: str, bases) -> list[str]:
    p = pattern.replace("<storeUserId>", UID)
    if p.startswith("<base>"):
        return [os.path.normpath(b + p[len("<base>"):]) for b in bases]
    e = savepaths.expand(p)
    return [e] if e else []


def _count(folder: str) -> tuple[int, float]:
    n, newest = 0, 0.0
    for d, _dirs, files in os.walk(folder):
        for f in files:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(d, f)))
            except OSError:
                continue
            n += 1
            if n >= MAX_COUNT:
                return n, newest
    return n, newest


def _from_pattern(path: str) -> list[Found]:
    """The folders on this PC one expanded pattern points at."""
    segs = re.split(r"[\\/]", path)
    j = next((i for i, s in enumerate(segs) if WILD.search(s)), len(segs))
    folder, rest = segs[:j], segs[j:]
    folder_glob = os.sep.join(glob.escape(s) for s in folder).replace(UID, "*")
    out = []
    for d in glob.glob(folder_glob):
        if not rest:
            if os.path.isdir(d):
                out.append(Found(d, *_count(d)))
            elif os.path.isfile(d):
                out.append(Found(os.path.dirname(d), 1, os.path.getmtime(d)))
            continue
        if not os.path.isdir(d):
            continue
        n, newest = 0, 0.0
        for m in glob.iglob(os.path.join(glob.escape(d), *rest), recursive=True):
            c, t = _count(m) if os.path.isdir(m) else (1, os.path.getmtime(m))
            n, newest = n + c, max(newest, t)
            if n >= MAX_COUNT:
                break
        if n:                                   # else: the folder is there but has none of this game's saves
            out.append(Found(d, n, newest))
    if not out and UID not in path:
        # Not on this PC yet: the folder the game will save to (Sync down puts the saves there).
        p = os.sep.join(folder)
        if not rest and os.path.splitext(folder[-1])[1]:
            p = os.path.dirname(p)              # a single save file
        out.append(Found(p, exists=False))
    return out


def find_folders(entry: dict, exe=None) -> list[Found]:
    """The game's save folders on this PC, best first: the ones with the newest saves, then the ones it would
    use. Folders inside another one are merged into it; folders that are far too broad are left out."""
    bases = install_dirs(entry, exe)
    skip = {os.path.normcase(b) for b in bases}
    found: dict[str, Found] = {}
    for pattern in entry.get("f") or []:
        for path in _expand(pattern, bases):
            for f in _from_pattern(path):
                f.path = os.path.normpath(f.path)
                key = os.path.normcase(f.path)
                if key in skip or savepaths.too_broad(f.path) or any(
                        b.startswith(key + os.sep) for b in skip):
                    continue
                old = found.get(key)
                if old is None:
                    found[key] = f
                elif f.exists:
                    old.files, old.newest, old.exists = max(old.files, f.files), max(old.newest, f.newest), True
    keys = sorted(found, key=len)
    for k in keys:                              # outer folders come first
        if k not in found:
            continue
        for inner in [x for x in found if x.startswith(k + os.sep)]:
            f = found.pop(inner)
            if f.exists:
                o = found[k]
                o.files, o.newest, o.exists = o.files + f.files, max(o.newest, f.newest), True
    have = [f for f in found.values() if f.exists]
    if have:
        return sorted(have, key=lambda f: (f.files > 0, f.newest, f.files), reverse=True)
    return list(found.values())
