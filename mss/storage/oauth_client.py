"""Google OAuth client built into Mare Save Sync.

Copy .env_example to .env (not committed — see .gitignore) and fill in your own "Desktop app" OAuth client:

    GOOGLE_CLIENT_ID=1234567890-abc123.apps.googleusercontent.com
    GOOGLE_CLIENT_SECRET=GOCSPX-...

build_exe.bat builds .env into the exe. See README → "Google sign-in setup".
Real environment variables win over .env; a .env next to the exe also works.
Without any of these, users can still load a credentials.json in Settings.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..paths import APP_HOME, FROZEN, RES_DIR


def _env_files() -> list[Path]:
    if FROZEN:
        return [APP_HOME / ".env", RES_DIR / ".env"]     # next to the exe, then the one built in by build_exe.bat
    return [APP_HOME / ".env"]


def _read_env(p: Path) -> dict[str, str]:
    out = {}
    try:
        lines = p.read_text("utf-8-sig").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip().removeprefix("export ").strip()] = v
    return out


def _setting(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name].strip()
    for p in _env_files():
        v = _read_env(p).get(name)
        if v:
            return v
    return ""


CLIENT_ID = _setting("GOOGLE_CLIENT_ID")
CLIENT_SECRET = _setting("GOOGLE_CLIENT_SECRET")
