"""Local image cache. Images are named by a hash of their URL (or "custom:" id for your own files)."""
from __future__ import annotations

import hashlib
import os
import urllib.parse
import urllib.request
from pathlib import Path

from ..paths import app_dir
from ..providers import UA


def cache_path(url: str) -> Path:
    d = app_dir() / "art"
    d.mkdir(exist_ok=True)
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".img"
    return d / (hashlib.sha1(url.encode()).hexdigest()[:24] + ext)


CUSTOM = "custom:"


def is_custom(ident: str) -> bool:
    return bool(ident) and ident.startswith(CUSTOM)


def import_image(src) -> str:
    """Copy a local image into the cache. Returns an id ("custom:<hash>.<ext>") used in place of a URL."""
    data = Path(src).read_bytes()
    ident = f"{CUSTOM}{hashlib.sha1(data).hexdigest()[:24]}{Path(src).suffix.lower() or '.img'}"
    p = cache_path(ident)
    if not p.is_file():
        tmp = p.with_suffix(p.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, p)
    return ident


def fetch(url: str) -> Path | None:
    """Download an image once; later calls return the cached file."""
    if not url:
        return None
    p = cache_path(url)
    if p.is_file() and p.stat().st_size > 0:
        return p
    if is_custom(url):
        raise FileNotFoundError("custom image isn't on this PC yet")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    tmp = p.with_suffix(p.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, p)
    return p
