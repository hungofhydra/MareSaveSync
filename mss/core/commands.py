"""A game's own commands: one that runs before it starts, one after it has closed.

They are written as on a command line (Windows' own shell runs them), for things like switching the audio
device or the display mode, closing an overlay, or starting a helper program. They are per PC, like the
game's launch options.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..launcher import _child_env, _no_bundle_dll_dir

TIMEOUT = 120          # seconds a command may run before it's stopped
SHOWN = 600            # characters of its output kept for messages


@dataclass
class Result:
    command: str
    code: int | None       # the exit code; None if it didn't finish in time or couldn't be started
    output: str            # what it printed (and any error text)
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.code == 0

    def problem(self) -> str:
        """Why it counts as failed, in a sentence (empty when it worked)."""
        if self.ok:
            return ""
        why = (f"didn't finish within {TIMEOUT} seconds, so it was stopped" if self.timed_out
               else f"ended with code {self.code}" if self.code is not None else "couldn't be started")
        return f"{why}.\n{self.output}" if self.output else f"{why}."


def run(command: str, cwd: str | Path | None = None, env: dict[str, str] | None = None,
        timeout: float = TIMEOUT) -> Result:
    """Run `command` through the shell, wait for it, and say how it went. Never raises."""
    command = command.strip()
    folder = str(cwd) if cwd and Path(cwd).is_dir() else None
    environ = _child_env()
    environ.update(env or {})
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Its output goes to a file, not a pipe: a program it starts that keeps running would otherwise hold the
    # pipe open and we'd wait for it forever.
    with tempfile.TemporaryFile() as out:
        try:
            with _no_bundle_dll_dir():
                proc = subprocess.Popen(command, shell=True, cwd=folder, env=environ, stdin=subprocess.DEVNULL,
                                        stdout=out, stderr=subprocess.STDOUT, creationflags=flags)
        except OSError as ex:
            return Result(command, None, str(ex))
        timed_out = False
        try:
            code = proc.wait(timeout)
        except subprocess.TimeoutExpired:
            timed_out, code = True, None
            _kill_tree(proc)
        out.seek(0)
        text = out.read().decode(errors="replace").strip()
    return Result(command, code, text[-SHOWN:], timed_out)


def _kill_tree(proc: subprocess.Popen) -> None:
    """Stop the command and what it started (the shell alone would leave those running)."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        pass


def game_env(game: str, program: str | None, seconds: float | None = None) -> dict[str, str]:
    """Variables the command can use: %MSS_GAME%, %MSS_PROGRAM% and, after the game, %MSS_SECONDS% played."""
    env = {"MSS_GAME": game, "MSS_PROGRAM": str(program or "")}
    if seconds is not None:
        env["MSS_SECONDS"] = str(int(seconds))
    return env


def start_folder(program: str | None) -> str | None:
    """The folder commands run in: the game's (or its emulator's) own."""
    return os.path.dirname(program) if program else None
