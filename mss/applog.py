"""The app's log file, kept across restarts for bug reports: data/logs/MareSaveSync.log (about the last 3 MB,
in up to 3 files). Everything the app shows in its Log tab goes here too, plus the tracebacks of errors, which
the windowed exe has nowhere else to put.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import re
import sys
import threading
from pathlib import Path

from . import APP_TITLE
from .paths import FROZEN, app_dir

LOG_NAME = "MareSaveSync.log"
MAX_BYTES, BACKUPS = 1_000_000, 2
ISSUES_URL = "https://github.com/hungofhydra/MareSaveSync/issues/new"
REPORT_LINES = 300                      # log lines in a bug report

log = logging.getLogger("mss")


def log_dir() -> Path:
    return app_dir() / "logs"


def log_file() -> Path:
    return log_dir() / LOG_NAME


def setup() -> None:
    """Start writing the log file, and send uncaught errors (any thread) to it."""
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    log.propagate = False
    try:
        log_dir().mkdir(exist_ok=True)
        h = logging.handlers.RotatingFileHandler(log_file(), maxBytes=MAX_BYTES, backupCount=BACKUPS,
                                                 encoding="utf-8", delay=True)
    except OSError:
        log.addHandler(logging.NullHandler())
        return
    h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(h)

    def hook(exc_type, exc, tb):
        log.error("Unexpected error", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = hook
    threading.excepthook = lambda a: log.error(f"Unexpected error in thread {a.thread.name if a.thread else '?'}",
                                               exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    log.info(f"===== {APP_TITLE} {version_text()} started  ({system_text()})")


def version_text() -> str:
    from . import updater
    return updater.current_text() + ("" if FROZEN else " (from source)")


def system_text() -> str:
    win = platform.win32_ver()
    os_text = f"Windows {win[0]} {win[1]}" if win[0] else platform.platform()
    return f"{os_text}, Python {platform.python_version()}"


def tail(lines: int) -> list[str]:
    """The last `lines` lines of the log, across the rotated files."""
    out: list[str] = []
    for p in [log_file()] + [log_file().with_name(f"{LOG_NAME}.{i}") for i in range(1, BACKUPS + 1)]:
        try:
            out = p.read_text("utf-8", errors="replace").splitlines() + out
        except OSError:
            continue
        if len(out) >= lines:
            break
    return out[-lines:]


def redact(text: str) -> str:
    """Take the user's name out of paths, so a log can be shared."""
    home = str(Path.home())
    for h in {home, home.replace("\\", "/")}:
        text = re.sub(re.escape(h), "%USERPROFILE%", text, flags=re.I)
    user = os.environ.get("USERNAME") or Path.home().name
    if len(user) >= 3:
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(user)}(?![A-Za-z0-9])", "<user>", text, flags=re.I)
    return text


def bug_report(storage: str, games: int) -> str:
    """Text to paste into a bug report: versions, storage kind and the end of the log, with names taken out."""
    head = [f"{APP_TITLE} {version_text()}", system_text(), f"Storage: {storage}", f"Games in library: {games}",
            "", f"Last {REPORT_LINES} lines of the log:", "```"]
    return redact("\n".join(head + tail(REPORT_LINES) + ["```"]))
