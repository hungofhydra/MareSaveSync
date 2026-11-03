"""Scanning a save folder into {relative path: FileInfo}."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .util import TMP_SUFFIX, md5_file

# {(path, size, mtime_ns): md5}: an unchanged file isn't read again (the library is checked every 30 minutes)
_md5_cache: dict[tuple, str] = {}


def _md5(path: Path, st) -> str:
    key = (str(path), st.st_size, st.st_mtime_ns)
    md5 = _md5_cache.get(key)
    if md5 is None:
        md5 = _md5_cache[key] = md5_file(path)
    return md5


@dataclass
class FileInfo:
    path: str      # relative, forward slashes
    size: int
    md5: str
    mtime: float


def scan_file(path, rel: str, errors: list | None = None) -> FileInfo | None:
    """One file as `rel` (a save location that's a single file), None if it isn't there."""
    p = Path(path)
    try:
        st = p.stat()
        if not p.is_file():
            return None
        return FileInfo(rel, st.st_size, _md5(p, st), st.st_mtime)
    except FileNotFoundError:
        return None
    except OSError as ex:
        if errors is not None:
            errors.append(f"{rel}: {ex}")
        return None


def scan_folder(root, errors: list | None = None) -> dict[str, FileInfo]:
    out: dict[str, FileInfo] = {}
    if not root:
        return out
    root = Path(root)
    if not root.is_dir():
        return out
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn.endswith(TMP_SUFFIX):
                continue
            full = Path(dirpath, fn)
            rel = full.relative_to(root).as_posix()
            try:
                st = full.stat()
                out[rel] = FileInfo(rel, st.st_size, _md5(full, st), st.st_mtime)
            except OSError as ex:          # e.g. file locked by the running game
                if errors is not None:
                    errors.append(f"{rel}: {ex}")
    return out
