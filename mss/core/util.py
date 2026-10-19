"""Small helpers shared by the core and the storage backends."""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

TMP_SUFFIX = ".sstmp"


def safe_name(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return s or "game"


def human_size(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def fmt_time(ts) -> str:
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(ts)) if ts else ""


def norm_rel(p: str) -> str:
    return p.replace("\\", "/").strip("/")


def escape_pattern(rel: str) -> str:
    """Escape wildcard characters so a real file name is matched literally."""
    return re.sub(r"([*?\[])", r"[\1]", rel)


def md5_file(path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def prune_empty_dirs(d: Path, stop: Path) -> None:
    d, stop = Path(d), Path(stop)
    while d != stop and stop in d.parents:
        try:
            d.rmdir()
        except OSError:
            break
        d = d.parent
