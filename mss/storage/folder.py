"""Storage in a plain folder (e.g. your Google Drive for desktop folder)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .. import CLOUD_ROOT, LEGACY_CLOUD_ROOT
from ..core.scan import scan_folder
from ..core.util import TMP_SUFFIX, prune_empty_dirs, safe_name
from .common import (ART_JSON, ART_SUB, CONFIG_NAME, INFO_JSON, LEGACY_ART_DIR, LEGACY_STATS_DIR, PLAYTIME_SUB,
                     _group_playtime, _playtime_entry, _replace, _write_json)


class FolderBackend:
    """Stores everything in <root>/MareSaveSync/<game>/ (saves in files/, plus art/ and playtime/).

    Point it at your Google Drive for desktop folder (e.g. G:\\My Drive) and the
    Drive client does the actual uploading.
    """

    kind = "folder"

    def __init__(self, root):
        if not root or not Path(root).is_dir():
            raise FileNotFoundError(f"Storage folder not found: {root!r}. Check Settings.")
        self.root = Path(root) / CLOUD_ROOT
        old = Path(root) / LEGACY_CLOUD_ROOT
        if not self.root.exists() and old.is_dir():
            try:
                old.rename(self.root)              # older versions' folder: carry everything over
            except OSError:                        # e.g. locked by the Drive client: keep using it for now
                self.root = old
        self.root.mkdir(exist_ok=True)
        self._dirs: dict[str, Path] = {}          # every game folder, removed ones included
        self._removed: set[str] = set()
        self._pt_seen: dict[tuple, tuple] = {}    # (game, device) -> (seconds, last_played) in the cloud

    def describe(self) -> str:
        return f"Folder: {self.root}"

    def list_games(self):
        self._dirs, self._removed = {}, set()
        for d in self.root.iterdir():
            if d.name.startswith("."):
                continue
            cfg = d / CONFIG_NAME
            if d.is_dir() and cfg.is_file():
                try:
                    data = json.loads(cfg.read_text("utf-8"))
                except (OSError, ValueError):
                    data = {}
                name = data.get("name", d.name)
                self._dirs[name] = d
                if data.get("removed"):
                    self._removed.add(name)
        return sorted((g for g in self._dirs if g not in self._removed), key=str.lower)

    def _dir(self, game) -> Path:
        if game not in self._dirs:
            self.list_games()
        if game not in self._dirs:
            raise KeyError(f"Game {game!r} not found in storage")
        return self._dirs[game]

    def create_game(self, name):
        if name in self.list_games():
            raise ValueError(f"A game called {name!r} already exists.")
        if name in self._removed:                 # added again: bring back its playtime, art and exclusions
            cfg = self.get_game_config(name)
            cfg.pop("removed", None)
            self.set_game_config(name, cfg)
            self._removed.discard(name)
            (self._dir(name) / "files").mkdir(exist_ok=True)
            return
        d, n = self.root / safe_name(name), 2
        while d.exists():
            d, n = self.root / f"{safe_name(name)} ({n})", n + 1
        (d / "files").mkdir(parents=True)
        self._dirs[name] = d
        self.set_game_config(name, {"excludes": []})

    def delete_game(self, name, purge=False):
        """Hides the game from the library, keeping everything. purge: delete its whole folder instead
        (saves, artwork, playtime, exclusions)."""
        if purge:
            shutil.rmtree(self._dir(name))
            self._dirs.pop(name, None)
            self._removed.discard(name)
            return
        cfg = self.get_game_config(name)
        cfg["removed"] = True
        self.set_game_config(name, cfg)
        self._removed.add(name)

    def get_game_config(self, name):
        p = self._dir(name) / CONFIG_NAME
        cfg = json.loads(p.read_text("utf-8")) if p.is_file() else {}
        cfg.setdefault("excludes", [])
        return cfg

    def set_game_config(self, name, cfg):
        _write_json(self._dir(name) / CONFIG_NAME, dict(cfg, name=name))

    def list_files(self, name):
        return scan_folder(self._dir(name) / "files")

    def upload(self, name, rel, src, mtime):
        dest = self._dir(name) / "files" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + TMP_SUFFIX)
        shutil.copy2(src, tmp)
        _replace(tmp, dest)

    def download(self, name, rel, dest):
        dest = Path(dest)
        tmp = dest.with_name(dest.name + TMP_SUFFIX)
        shutil.copy2(self._dir(name) / "files" / rel, tmp)
        _replace(tmp, dest)

    def delete(self, name, rel):
        files = self._dir(name) / "files"
        p = files / rel
        p.unlink(missing_ok=True)
        prune_empty_dirs(p.parent, files)

    def read_bytes(self, name, rel):
        return (self._dir(name) / "files" / rel).read_bytes()

    def clear_saves(self, name):
        files = self._dir(name) / "files"
        shutil.rmtree(files, ignore_errors=True)
        files.mkdir()

    # ------------------------------------------------------------ playtime
    def read_all_stats(self):
        self.list_games()
        entries, legacy = [], []
        for game, d in self._dirs.items():
            for p in (d / PLAYTIME_SUB).glob("*.json"):
                try:
                    e = dict(json.loads(p.read_text("utf-8")), game=game)
                except (OSError, ValueError):
                    continue
                entries.append(e)
                self._pt_seen[(game, e.get("device_id"))] = (e.get("seconds", 0), e.get("last_played", 0))
        old = self.root / LEGACY_STATS_DIR
        for p in old.glob("*.json") if old.is_dir() else []:
            try:
                legacy.append(json.loads(p.read_text("utf-8")))
            except (OSError, ValueError):
                pass
        return _group_playtime(entries, legacy)

    def write_stats(self, device_id, doc):
        """Writes this PC's playtime into each game's playtime/ folder (only games that changed)."""
        for game, st in (doc.get("games") or {}).items():
            e = _playtime_entry(game, device_id, doc, st)
            if self._pt_seen.get((game, device_id)) == (e["seconds"], e["last_played"]):
                continue
            try:
                d = self._dir(game)
            except KeyError:                       # no folder for it (e.g. removed by an older version)
                continue
            _write_json(d / PLAYTIME_SUB / f"{device_id}.json", e)
            self._pt_seen[(game, device_id)] = (e["seconds"], e["last_played"])

    # ------------------------------------------------------------- artwork
    def _art_dir(self, name) -> Path:
        d = self._dir(name) / ART_SUB
        old = self.root / LEGACY_ART_DIR / safe_name(name)
        if not d.is_dir() and old.is_dir():
            shutil.move(str(old), str(d))
        return d

    def read_art(self, name):
        p = self._art_dir(name) / ART_JSON
        try:
            return json.loads(p.read_text("utf-8")).get("art") if p.is_file() else None
        except (OSError, ValueError):
            return None

    def write_art(self, name, art):
        _write_json(self._art_dir(name) / ART_JSON, {"name": name, "art": art})

    def art_files(self, name):
        d = self._art_dir(name)
        return {p.name for p in d.iterdir() if p.is_file() and p.name != ART_JSON} if d.is_dir() else set()

    def upload_art_file(self, name, fname, src):
        d = self._art_dir(name)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / (fname + TMP_SUFFIX)
        shutil.copyfile(src, tmp)
        _replace(tmp, d / fname)

    def download_art_file(self, name, fname, dest):
        dest = Path(dest)
        tmp = dest.with_name(dest.name + TMP_SUFFIX)
        shutil.copyfile(self._art_dir(name) / fname, tmp)
        _replace(tmp, dest)

    def delete_art_file(self, name, fname):
        (self._art_dir(name) / fname).unlink(missing_ok=True)

    # ----------------------------------------------------------- game info
    def read_info(self, name):
        p = self._dir(name) / INFO_JSON
        try:
            return json.loads(p.read_text("utf-8")).get("info") if p.is_file() else None
        except (OSError, ValueError):
            return None

    def write_info(self, name, info):
        _write_json(self._dir(name) / INFO_JSON, {"name": name, "info": info})
