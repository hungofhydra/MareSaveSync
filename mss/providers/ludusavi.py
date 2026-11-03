"""Ludusavi's manifest: where thousands of PC games keep their saves (made from PCGamingWiki).
https://github.com/mtkennerly/ludusavi-manifest

The manifest is a big YAML file (~18 MB). It's downloaded once, boiled down to what this app uses (Windows
save paths, Steam ids, install folder names) and kept as ludusavi.json in the data folder. It's checked for
updates once a week; an unchanged manifest isn't downloaded again.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from . import UA
from ..paths import app_dir

MANIFEST_URL = "https://raw.githubusercontent.com/mtkennerly/ludusavi-manifest/master/data/manifest.yaml"
INDEX_NAME = "ludusavi.json"
INDEX_VERSION = 1
REFRESH_EVERY = 7 * 86400

_lock = threading.Lock()
_index: dict | None = None


def norm(name: str) -> str:
    """Names compared loosely: case, ™/®, punctuation and spacing don't matter."""
    return " ".join(re.sub(r"[^\w]+", " ", (name or "").replace("&", " and ").casefold()).split())


def _windows(entry: dict) -> bool:
    when = entry.get("when") or []
    return not when or any(w.get("os") in (None, "windows") for w in when)


def build_index(manifest: dict) -> dict:
    """The parts of the manifest this app uses. A game entry: {"f": [save path patterns], "s": [Steam ids],
    "d": [install folder names], "r": 1 if it keeps saves in the registry}."""
    games, aliases = {}, {}
    for name, e in manifest.items():
        e = e or {}
        if e.get("alias"):
            aliases[name] = e["alias"]
            continue
        # Only paths under a placeholder ("C:/Users/[User]/…" are notes, not paths). <root> is Steam Cloud's own
        # folder, left to Steam; <winDir> is Windows itself; …/SystemAppData/wgs are the Xbox app's own containers.
        files = [p for p, v in (e.get("files") or {}).items()
                 if _windows(v or {}) and ("save" in ((v or {}).get("tags") or ["save"]))
                 and p.startswith("<") and not p.startswith(("<root>", "<xdg", "<winDir>"))
                 and "/SystemAppData/wgs" not in p]
        registry = any(_windows(v or {}) and "save" in ((v or {}).get("tags") or ["save"])
                       for v in (e.get("registry") or {}).values())
        if not files and not registry:
            continue
        g: dict = {"f": files}
        steam = [(e.get("steam") or {}).get("id")] + list((e.get("id") or {}).get("steamExtra") or [])
        if any(steam):
            g["s"] = [int(x) for x in steam if x]
        if e.get("installDir"):
            g["d"] = list(e["installDir"])
        if registry:
            g["r"] = 1
        games[name] = g
    return {"v": INDEX_VERSION, "games": games, "aliases": aliases}


def _download(etag: str | None) -> tuple[dict | None, str]:
    """(parsed manifest, its ETag), or (None, etag) when it hasn't changed since `etag`."""
    import yaml
    req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": UA})
    if etag:
        req.add_header("If-None-Match", etag)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data, etag = r.read(), r.headers.get("ETag") or ""
    except urllib.error.HTTPError as ex:
        if ex.code == 304:
            return None, etag or ""
        raise
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)      # the C parser is ~10× faster
    return yaml.load(data, Loader=loader), etag


def _read(path) -> dict | None:
    try:
        idx = json.loads(path.read_text("utf-8"))
        return idx if idx.get("v") == INDEX_VERSION else None
    except (OSError, ValueError):
        return None


def load(log=print) -> dict | None:
    """The index, downloading or refreshing it when needed. None if it can't be had (offline on first use)."""
    global _index
    with _lock:
        path = app_dir() / INDEX_NAME
        idx = _index or _read(path)
        if idx and time.time() - idx.get("checked", 0) < REFRESH_EVERY:
            _index = idx
            return idx
        try:
            log("Downloading the list of game save locations (Ludusavi manifest)…" if not idx
                else "Checking the list of game save locations for updates…")
            manifest, etag = _download(idx.get("etag") if idx else None)
            if manifest is not None:
                idx = build_index(manifest)
            idx.update(etag=etag, checked=time.time())
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({k: v for k, v in idx.items() if not k.startswith("_")},
                                      separators=(",", ":")), "utf-8")
            os.replace(tmp, path)
        except Exception as ex:
            if not idx:
                log(f"Couldn't get the list of game save locations: {ex}")
                return None
            log(f"Couldn't update the list of game save locations ({ex}); using the one from before")
        _index = idx
        return idx


def find(idx: dict, names=(), steam_ids=()) -> tuple[str, dict] | None:
    """(manifest name, entry) of a game, by Steam id first, else by name."""
    games = idx["games"]
    ids = {int(s) for s in steam_ids if s}
    if ids:
        for name, g in games.items():
            if ids.intersection(g.get("s", ())):
                return name, g
    wanted = [norm(n) for n in names if n]
    if not wanted:
        return None
    by_norm = idx.get("_by_norm")
    if by_norm is None:
        by_norm = {norm(n): n for n in games}
        by_norm.update({norm(a): t for a, t in idx.get("aliases", {}).items() if t in games and norm(a) not in by_norm})
        idx["_by_norm"] = by_norm
    for w in wanted:
        if w in by_norm:
            return by_norm[w], games[by_norm[w]]
    return None
