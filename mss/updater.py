"""Updating the portable app from its GitHub releases.

1. check() asks GitHub for the latest release and whether it's newer than this build.
2. download() saves its zip in data/update/ (checked against the SHA-256 GitHub publishes) and unpacks it.
3. start_finish() starts the NEW exe from there with --finish-update; this copy then closes.
4. finish() runs in that new exe: once this copy has closed, it swaps MareSaveSync.exe and _internal in the
   app folder for the new ones (the old ones are kept in data/update/old until it worked) and starts the app
   again. The data folder is never touched. If anything fails, the old version is put back.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from . import BUILD, VERSION
from .paths import APP_HOME, FROZEN
from .providers import UA

REPO = "hungofhydra/MareSaveSync"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
FINISH = "--finish-update"
APP_DIR_NAME = "MareSaveSync"        # the folder inside the release zip
EXE_NAME = "MareSaveSync.exe"


class UpdateError(Exception):
    pass


def parse(tag: str) -> tuple[int, ...]:
    """"v3.0.57" → (3, 0, 57)."""
    try:
        return tuple(int(x) for x in tag.strip().lstrip("vV").split("."))
    except ValueError:
        return ()


def current() -> tuple[int, ...]:
    return parse(VERSION) + ((BUILD,) if BUILD is not None else ())


def current_text() -> str:
    return f"v{VERSION}.{BUILD}" if BUILD is not None else f"v{VERSION}"


def can_update() -> bool:
    """Only a released build can update itself (one run from source or built on this PC doesn't know which
    release it is)."""
    return FROZEN and BUILD is not None


def check() -> dict | None:
    """The latest release if it's newer than this build: {"tag", "name", "url", "asset_url", "size", "sha256"}."""
    req = urllib.request.Request(API, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        rel = json.loads(r.read().decode("utf-8"))
    tag = rel.get("tag_name") or ""
    asset = next((a for a in rel.get("assets") or [] if a.get("name", "").endswith("-windows.zip")), None)
    if not asset or parse(tag) <= current():
        return None
    digest = asset.get("digest") or ""
    return {"tag": tag, "name": rel.get("name") or tag, "url": rel.get("html_url") or "",
            "asset_url": asset["browser_download_url"], "size": asset.get("size") or 0,
            "sha256": digest[7:] if digest.startswith("sha256:") else ""}


def update_dir() -> Path:
    return APP_HOME / "data" / "update"


def download(info: dict, progress=lambda done, total: None) -> Path:
    """Download and unpack the release. Returns the new app folder (with MareSaveSync.exe and _internal)."""
    d = update_dir()
    shutil.rmtree(d / "new", ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    zpath = d / "update.zip"
    h, done, total = hashlib.sha256(), 0, info.get("size") or 0
    req = urllib.request.Request(info["asset_url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(zpath, "wb") as f:
        total = total or int(r.headers.get("Content-Length") or 0)
        while chunk := r.read(1 << 16):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            progress(done, total)
    if info.get("sha256") and h.hexdigest() != info["sha256"].lower():
        zpath.unlink(missing_ok=True)
        raise UpdateError("The download is damaged (its checksum doesn't match). Try again.")
    try:
        with zipfile.ZipFile(zpath) as z:
            z.extractall(d / "new")
    except zipfile.BadZipFile:
        raise UpdateError("The download isn't a valid zip file. Try again.") from None
    finally:
        zpath.unlink(missing_ok=True)
    new = d / "new" / APP_DIR_NAME
    if not (new / EXE_NAME).is_file() or not (new / "_internal").is_dir():
        raise UpdateError(f"The update doesn't contain {APP_DIR_NAME}\\{EXE_NAME}.")
    return new


def start_finish(new: Path, restart_args=()) -> None:
    """Start the new exe to finish the update once this process has exited."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(new / EXE_NAME), FINISH, str(APP_HOME), str(os.getpid()), *restart_args],
                     cwd=str(new), creationflags=flags, close_fds=True)


# ------------------------------------------------------------------ in the new exe
def _log(target: Path, msg: str):
    try:
        with open(target / "data" / "update" / "update.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
    except OSError:
        pass


def _wait_for(pid: int, timeout=60):
    try:
        import psutil
        psutil.Process(pid).wait(timeout=timeout)
    except ImportError:
        time.sleep(5)
    except Exception:           # already gone (NoSuchProcess) or still running after the timeout
        pass


def _retry(fn, *args):
    """Files can stay locked for a moment after a program closes (or while antivirus looks at them)."""
    for i in range(40):
        try:
            return fn(*args)
        except OSError:
            if i == 39:
                raise
            time.sleep(0.5)


def _copy(src: Path, dest: Path):
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)


def _remove(p: Path):
    if p.is_dir():
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()


def finish(argv: list[str]) -> None:
    """--finish-update <app folder> <pid of the old copy> [arguments to restart it with]."""
    target, pid, restart = Path(argv[0]), int(argv[1]), argv[2:]
    new = Path(sys.executable).resolve().parent
    old = target / "data" / "update" / "old"
    items = [p.name for p in new.iterdir() if p.name != "data"]
    _wait_for(pid)
    _log(target, f"Updating {target} from {new}")
    moved, copied = [], []
    try:
        if old.exists():
            _retry(shutil.rmtree, old)
        old.mkdir(parents=True)
        for name in items:
            if (target / name).exists():
                _retry(os.replace, target / name, old / name)
                moved.append(name)
        for name in items:
            copied.append(name)
            _copy(new / name, target / name)
        _log(target, "Updated")
    except Exception as ex:
        _log(target, f"Update failed, putting the old version back: {ex!r}")
        for name in copied:
            try:
                _remove(target / name)
            except OSError:
                pass
        for name in moved:
            try:
                _retry(os.replace, old / name, target / name)
            except OSError as ex2:
                _log(target, f"Couldn't put back {name}: {ex2!r}")
        _error(f"The update couldn't be installed:\n{ex}\n\nThe old version is kept. "
               f"Details: {target / 'data' / 'update' / 'update.log'}")
    try:                                    # the new version, or the old one put back
        subprocess.Popen([str(target / EXE_NAME), *restart], cwd=str(target),
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0), close_fds=True)
    except OSError as ex:
        _log(target, f"Couldn't start {target / EXE_NAME}: {ex!r}")


def _error(text: str):
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Mare Save Sync update", text, parent=root)
        root.destroy()
    except Exception:
        pass


def cleanup() -> None:
    """After an update: remove the unpacked update and the old version (some files may still be in use by
    the updater for a moment; whatever is left goes next time)."""
    d = update_dir()
    if FROZEN and d.is_dir() and not Path(sys.executable).resolve().is_relative_to(d.resolve()):
        for name in ("new", "old", "update.zip"):
            p = d / name
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
