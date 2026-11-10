"""Build the portable app into dist/MareSaveSync/ (MareSaveSync.exe + _internal/).

Used by build_exe.bat and the GitHub release workflow, so both build the same thing.
A .env next to this file (Google sign-in client, see .env_example) is built in when present.
An existing dist/MareSaveSync/data folder (settings of a copy you ran from there) is kept across rebuilds.

    python build.py            build
    python build.py --version  print the app version (major.minor, VERSION in mss/__init__.py)
    python build.py --release  print the next release's version: <major>.<minor>.<patch>

Releases are v<major>.<minor>.<patch>. The patch is one more than the highest v<major>.<minor>.* release tag
there is (0 for the first): the first release of 3.1 is v3.1.0, the next v3.1.1, and so on, and a build that
fails doesn't use up a number. To start a new minor or major version, change VERSION.

The release workflow sets MSS_BUILD to the patch: the exe knows which release it is and can update itself
(mss/updater.py). Without it (a build made on this PC) the exe doesn't update itself.
"""
import os
import re
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


def release() -> str:
    """The next release's <major>.<minor>.<patch>, from the release tags (the workflow fetches them)."""
    v = version()
    tags = subprocess.run(["git", "tag", "--list", f"v{v}.*"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.split()
    patches = [int(m.group(1)) for t in tags if (m := re.fullmatch(rf"v{re.escape(v)}\.(\d+)", t))]
    return f"{v}.{max(patches) + 1 if patches else 0}"


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
    build_file = ROOT / "mss" / "_build.py"
    if os.environ.get("MSS_BUILD", "").isdigit():
        build_file.write_text(f"BUILD = {int(os.environ['MSS_BUILD'])}\n", "utf-8")
    try:
        return subprocess.call(args + ["app.py"], cwd=ROOT)
    finally:
        build_file.unlink(missing_ok=True)       # running from source has no release number
        if KEEP.exists():
            DIST.mkdir(parents=True, exist_ok=True)
            shutil.move(str(KEEP), str(DIST / "data"))


if __name__ == "__main__":
    if "--version" in sys.argv:
        print(version())
        sys.exit(0)
    if "--release" in sys.argv:
        print(release())
        sys.exit(0)
    sys.exit(build())
