"""Build the portable app into dist/MareSaveSync/ (MareSaveSync.exe + _internal/).

Used by build_exe.bat and the GitHub release workflow, so both build the same thing.
A .env next to this file (Google sign-in client, see .env_example) is built in when present.
An existing dist/MareSaveSync/data folder (settings of a copy you ran from there) is kept across rebuilds.

    python build.py            build
    python build.py --version  print the app version (major.minor, VERSION in mss/__init__.py)
    python build.py --release  print this commit's release version: <major>.<minor>.<patch>

Releases are v<major>.<minor>.<patch>. The patch is how many commits there are on this branch (following
first parents, i.e. main's own history) since VERSION was last changed: the commit that sets 3.1 is v3.1.0, the
next v3.1.1, and so on. To start a new minor or major version, change VERSION.

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


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def _version_at(sha: str) -> str | None:
    try:
        text = _git("show", f"{sha}:mss/__init__.py")
    except subprocess.CalledProcessError:
        return None
    m = re.search(r'^VERSION = "([^"]+)"', text, re.M)
    return m.group(1) if m else None


def release() -> str:
    """<major>.<minor>.<patch> of the commit that's checked out (needs the full history: fetch-depth 0)."""
    v = version()
    patch = 0
    for sha in _git("rev-list", "--first-parent", "HEAD").split()[1:]:
        if _version_at(sha) != v:
            break
        patch += 1
    return f"{v}.{patch}"


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
