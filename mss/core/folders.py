"""A game can keep its saves in several folders.

The first (main) folder is the root of the game's cloud saves, as in older versions. Each extra folder is
stored under its own top-level cloud folder "@<id>/". The list of extra folders ({"id", "name"}) is kept in
the game's cloud config so every PC knows it; where each folder is on this PC is in this PC's settings
(the main one in "local_path", the extra ones in "folders": {id: path}).
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .scan import FileInfo, scan_folder

MAIN = ""                # id of the main folder


def extra_folders(cfg) -> list[dict]:
    return [f for f in (cfg or {}).get("folders", []) if f.get("id")]


def cloud_prefix(fid: str) -> str:
    return f"@{fid}/" if fid else ""


def new_id(cfg) -> str:
    used = [int(f["id"]) for f in extra_folders(cfg) if str(f["id"]).isdigit()]
    return str(max(used, default=1) + 1)


def local_roots(gs: dict, cfg) -> dict[str, str | None]:
    """{folder id: path on this PC or None} for the main folder and every extra folder of the game."""
    paths = gs.get("folders") or {}
    return {MAIN: gs.get("local_path") or None, **{f["id"]: paths.get(f["id"]) or None for f in extra_folders(cfg)}}


def unset_prefixes(gs: dict, cfg) -> dict[str, str]:
    """{cloud prefix: folder name} of the extra folders that have no path on this PC (never synced here)."""
    paths = gs.get("folders") or {}
    return {cloud_prefix(f["id"]): f.get("name") or f["id"] for f in extra_folders(cfg) if not paths.get(f["id"])}


def folder_of(rel: str, ids) -> str:
    """Which folder a cloud path belongs to (MAIN unless it starts with a known extra folder's prefix)."""
    head = rel.split("/", 1)[0]
    return head[1:] if head.startswith("@") and "/" in rel and head[1:] in ids else MAIN


def scan_local(roots: dict, errors: list | None = None) -> dict[str, FileInfo]:
    """Every save folder on this PC as one tree of cloud paths."""
    out: dict[str, FileInfo] = {}
    for fid, path in roots.items():
        if not path:
            continue
        pre = cloud_prefix(fid)
        for rel, fi in scan_folder(path, errors).items():
            out[pre + rel] = replace(fi, path=pre + rel) if pre else fi
    return out


def local_file(roots: dict, rel: str) -> tuple[Path, Path]:
    """(folder root, file) on this PC for a cloud path. The folder must be set on this PC."""
    fid = folder_of(rel, roots)
    root = Path(roots[fid])
    return root, root / rel[len(cloud_prefix(fid)):]


def to_cloud_rel(roots: dict, path) -> str | None:
    """Cloud path of a file or folder on this PC ("" for the main folder itself), None if it's in none of them."""
    p = Path(path).resolve()
    for fid, root in roots.items():
        if not root:
            continue
        try:
            rel = p.relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            continue
        return (cloud_prefix(fid) + ("" if rel == "." else rel)).rstrip("/")
    return None


def overlaps(a, b) -> bool:
    a, b = Path(a).resolve(), Path(b).resolve()
    return a == b or a in b.parents or b in a.parents
