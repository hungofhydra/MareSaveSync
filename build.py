"""Build the portable app into dist/MareSaveSync/ (MareSaveSync.exe + _internal/).

Used by build_exe.bat and the GitHub release workflow, so both build the same thing.
A .env next to this file (Google sign-in client, see .env_example) is built in when present.
An existing dist/MareSaveSync/data folder (settings of a copy you ran from there) is kept across rebuilds.

    python build.py            build
    python build.py --version  print the app version (used to name releases)
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "MareSaveSync"
KEEP = ROOT / "dist" / "data.keep"


def version() -> str:
    sys.path.insert(0, str(ROOT))
    from mss import VERSION
    return VERSION


def build() -> int:
    sep = os.pathsep
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
            "--name", "MareSaveSync", "--icon", "assets/icon.ico", "--add-data", f"assets{sep}assets",
            "--collect-data", "googleapiclient", "--hidden-import", "google_auth_oauthlib.flow",
            "--hidden-import", "PIL.ImageTk", "--hidden-import", "pystray._win32"]
    if (ROOT / ".env").is_file():
        args += ["--add-data", f".env{sep}."]
    else:
        print("No .env found: the exe will have no Google sign-in built in. See .env_example.")

    if KEEP.exists():
        print(f"{KEEP} is left over from an earlier failed build: move it back to {DIST / 'data'} first.")
        return 1
    if (DIST / "data").is_dir():                 # a rebuild replaces dist/MareSaveSync
        shutil.move(str(DIST / "data"), str(KEEP))
    try:
        return subprocess.call(args + ["app.py"], cwd=ROOT)
    finally:
        if KEEP.exists():
            DIST.mkdir(parents=True, exist_ok=True)
            shutil.move(str(KEEP), str(DIST / "data"))


if __name__ == "__main__":
    if "--version" in sys.argv:
        print(version())
        sys.exit(0)
    sys.exit(build())
