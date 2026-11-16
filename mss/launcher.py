"""Launch a game (or notice one started elsewhere), wait until it has really closed, and the
start-with-Windows option."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .paths import APP_HOME, ASSETS, FROZEN, RES_DIR, SOURCE_ROOT

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
                if getattr(ex, "winerror", None) == 740 and sys.platform == "win32":
                    # The game needs administrator rights: ask Windows for the UAC prompt.
                    # Playtime is then tracked by watching the game folder (no process handle).
                    try:
                        import ctypes
                        with _no_bundle_dll_dir():
                            rc = ctypes.windll.shell32.ShellExecuteW(
                                None, "runas", str(exe), self.args or None, str(folder), 1)
                        if rc <= 32:
                            raise OSError("Administrator permission was declined or the game couldn't start.")
                    except OSError as ex2:
                        self.on_end(self.game, 0, ex2)
                        return
                else:
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


# ------------------------------------------------------------- desktop shortcuts
PLAY_ARG = "--play"                 # MareSaveSync.exe --play "<game>": play it through the app (see ui/app.py main)


def _guid(text: str):
    import ctypes
    import uuid
    return (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID(text).bytes_le)


def desktop_dir() -> Path:
    """This user's desktop folder, wherever Windows keeps it (OneDrive can move it)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        sh = ctypes.windll.shell32
        sh.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
                                            ctypes.POINTER(ctypes.c_wchar_p)]
        ptr = ctypes.c_wchar_p()
        folder = _guid("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")         # FOLDERID_Desktop
        if sh.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(ptr)) == 0:
            try:
                return Path(ptr.value)
            finally:
                ctypes.windll.ole32.CoTaskMemFree(ptr)
    return Path.home() / "Desktop"


def game_shortcut_path(game: str) -> Path:
    """Where the game's desktop shortcut goes: <desktop>/<game>.lnk, minus characters a file name can't have."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", game).strip(" .") or "Game"
    return desktop_dir() / f"{name}.lnk"


def _save_lnk(path: Path, target: str, args: str, folder: str, desc: str, icon: str) -> None:
    """Write a .lnk with the shell's own IShellLinkW (Unicode throughout: WScript.Shell goes through the ANSI
    code page and fails on names outside it)."""
    import ctypes
    from ctypes import HRESULT, c_int, c_void_p, c_wchar_p

    ole = ctypes.windll.ole32
    ole.CoCreateInstance.argtypes = [c_void_p, c_void_p, ctypes.c_ulong, c_void_p, ctypes.POINTER(c_void_p)]

    def method(obj, index, *argtypes):
        """The COM object's vtable entry `index`, callable as f(*args) -> HRESULT (raises OSError on failure)."""
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(c_void_p))).contents
        fn = ctypes.WINFUNCTYPE(HRESULT, c_void_p, *argtypes)(vtbl[index])
        return lambda *a: fn(obj, *a)

    init = ole.CoInitializeEx(None, 2)                  # apartment-threaded; fine if this thread already has it
    link = c_void_p()
    try:
        ole.CoCreateInstance(ctypes.byref(_guid("00021401-0000-0000-C000-000000000046")), None, 1,   # ShellLink
                             ctypes.byref(_guid("000214F9-0000-0000-C000-000000000046")),              # IShellLinkW
                             ctypes.byref(link))
        # IShellLinkW: 7 SetDescription, 9 SetWorkingDirectory, 11 SetArguments, 17 SetIconLocation, 20 SetPath
        method(link, 20, c_wchar_p)(target)
        method(link, 11, c_wchar_p)(args)
        method(link, 9, c_wchar_p)(folder)
        method(link, 7, c_wchar_p)(desc)
        method(link, 17, c_wchar_p, c_int)(icon, 0)
        persist = c_void_p()
        method(link, 0, c_void_p, ctypes.POINTER(c_void_p))(                                  # QueryInterface
            ctypes.byref(_guid("0000010B-0000-0000-C000-000000000046")), ctypes.byref(persist))  # IPersistFile
        try:
            method(persist, 6, c_wchar_p, c_int)(str(path), 1)                                   # Save
        finally:
            method(persist, 2)()                                                                 # Release
    finally:
        if link:
            method(link, 2)()
        if init in (0, 1):                              # S_OK / S_FALSE: this call initialized it
            ole.CoUninitialize()


def create_game_shortcut(game: str, icon: str | None = None) -> Path:
    """Put a shortcut on the desktop that plays `game` through this app, so its saves are synced and its playtime
    is counted as with Play. icon: a program to take the icon from (the game's .exe); else the app's. Replaces a
    shortcut already there. Returns its path; OSError if it couldn't be made."""
    if sys.platform != "win32":
        raise OSError("Desktop shortcuts are only available on Windows.")
    exe, pre = app_command()
    path = game_shortcut_path(game)
    _save_lnk(path, exe, subprocess.list2cmdline([*pre, PLAY_ARG, game]), str(APP_HOME),
              f"Play {game} with Mare Save Sync"[:259], icon or (exe if FROZEN else str(ASSETS / "icon.ico")))
    if not path.is_file():
        raise OSError("Windows didn't create the shortcut.")
    return path
