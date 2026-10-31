"""Launch a game (or notice one started elsewhere), wait until it has really closed, and the
start-with-Windows option."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .paths import FROZEN, RES_DIR, SOURCE_ROOT

try:
    import psutil
except ImportError:          # without psutil we can only wait for the process we started
    psutil = None

APP_RUN_NAME = "MareSaveSync"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def split_args(args: str) -> list[str]:
    if not args or not args.strip():
        return []
    return [a.strip('"') for a in shlex.split(args, posix=False)]


def _child_env() -> dict[str, str]:
    """Our environment minus PATH entries pointing into the bundle, so games never pick up our DLLs."""
    env = dict(os.environ)
    if FROZEN and env.get("PATH"):
        bundle = os.path.normcase(str(RES_DIR))
        env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep)
                                      if p and not os.path.normcase(os.path.abspath(p)).startswith(bundle))
    return env


@contextmanager
def _no_bundle_dll_dir():
    """The PyInstaller bootloader points SetDllDirectory at _internal and child processes inherit it, so a game
    would load our bundled vcruntime140.dll (RPCS3 refuses to start then). Clear it while spawning, then restore."""
    if not (FROZEN and sys.platform == "win32"):
        yield
        return
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.SetDllDirectoryW(None)
    try:
        yield
    finally:
        k32.SetDllDirectoryW(str(RES_DIR))


def running_under(folder: Path) -> bool:
    """True while any process whose executable lives inside `folder` is running.

    Catches launchers that start the real game and exit, and games that restart themselves.
    """
    if psutil is None:
        return False
    root = str(Path(folder).resolve()).lower().rstrip("\\/") + os.sep
    me = os.getpid()
    try:
        procs = list(psutil.process_iter())
    except Exception:
        return False
    for p in procs:
        try:
            if p.pid == me:
                continue
            exe = p.exe()           # can fail for system/protected processes; just skip those
            if exe and str(exe).lower().startswith(root):
                return True
        except Exception:
            continue
    return False


def find_running(exes: dict[str, str]) -> dict[str, float]:
    """Which of these games are running right now: {normalised exe path: game} -> {game: process start time}.

    Used to notice games started outside the app (from Steam, a desktop shortcut, …).
    """
    out: dict[str, float] = {}
    if psutil is None or not exes:
        return out
    try:
        procs = list(psutil.process_iter(["exe", "create_time"]))
    except Exception:
        return out
    for p in procs:
        exe = p.info.get("exe")
        game = exes.get(norm_exe(exe)) if exe else None
        if game:
            started = p.info.get("create_time") or time.time()
            out[game] = min(out.get(game, started), started)
    return out


def norm_exe(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


class GameSession(threading.Thread):
    """Runs one game. Calls on_end(game, seconds_played, error) from this thread when it's over.

    attach_started: the game is already running (started outside the app) since this time; don't launch it,
    just track it until it closes.
    """

    GRACE = 8          # seconds with nothing running before we decide the game has closed

    def __init__(self, game: str, exe: str, args: str, on_end, attach_started: float | None = None):
        super().__init__(daemon=True)
        self.game, self.exe, self.args, self.on_end = game, exe, args, on_end
        self.attach_started = attach_started
        self.stop_event = threading.Event()
        self.started = None

    def stop_tracking(self):
        self.stop_event.set()

    def run(self):
        exe = Path(self.exe)
        folder = exe.parent
        proc = None
        if self.attach_started:
            self.started = min(self.attach_started, time.time())
        else:
            self.started = time.time()
            try:
                with _no_bundle_dll_dir():
                    if exe.suffix.lower() in (".exe", ".bat", ".cmd") or sys.platform != "win32":
                        proc = subprocess.Popen([str(exe)] + split_args(self.args), cwd=str(folder),
                                                env=_child_env())
                    else:
                        os.startfile(str(exe))  # type: ignore[attr-defined]
            except OSError as ex:
                self.on_end(self.game, 0, ex)
                return
            time.sleep(3)
        idle_since = None
        while not self.stop_event.is_set():
            try:
                alive = (proc is not None and proc.poll() is None) or running_under(folder)
            except Exception:
                alive = proc is not None and proc.poll() is None
            if alive:
                idle_since = None
            elif idle_since is None:
                idle_since = time.time()
            elif time.time() - idle_since >= self.GRACE:
                break
            time.sleep(2)
        end = idle_since or time.time()
        self.on_end(self.game, max(0.0, end - self.started), None)


# ------------------------------------------------------------- start with Windows
def app_command() -> tuple[str, list[str]]:
    """The program that starts this app, and the arguments it needs before ours (app.py, from source)."""
    if FROZEN:
        return sys.executable, []
    pyw = Path(sys.executable).with_name("pythonw.exe")
    py = pyw if pyw.is_file() else Path(sys.executable)
    return str(py), [str(SOURCE_ROOT / "app.py")]


def startup_command() -> str:
    exe, args = app_command()
    return " ".join(f'"{a}"' for a in [exe, *args]) + " --minimized"


def get_startup() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_RUN_NAME)
            return True
    except OSError:
        return False


def refresh_startup() -> None:
    """If "Start with Windows" is on but points at another place (the portable folder was moved), point it here.
    Only the built exe does this, so running from source never takes over an installed copy's entry."""
    if sys.platform != "win32" or not FROZEN:
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            current = winreg.QueryValueEx(k, APP_RUN_NAME)[0]
        if current != startup_command():
            set_startup(True)
    except OSError:                 # not enabled (or no access): nothing to do
        pass


def set_startup(enabled: bool) -> None:
    if sys.platform != "win32":
        raise OSError("Start with Windows is only available on Windows.")
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, APP_RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(k, APP_RUN_NAME)
            except FileNotFoundError:
                pass
