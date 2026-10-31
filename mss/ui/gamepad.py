"""Xbox controller input for fullscreen mode, read through XInput (Windows only; elsewhere it does nothing).

Handhelds (ROG Ally, Legion Go, …) present their built-in controls as an Xbox controller too.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time

# XInput button bits -> the names fullscreen mode understands
BUTTONS = {0x0001: "up", 0x0002: "down", 0x0004: "left", 0x0008: "right", 0x0010: "start", 0x0020: "back",
           0x0100: "lb", 0x0200: "rb", 0x1000: "a", 0x2000: "b", 0x4000: "x", 0x8000: "y"}
REPEAT = {"up", "down", "left", "right"}      # held directions repeat, like a held arrow key
DELAY, RATE = 0.40, 0.11                       # seconds before the first repeat, and between repeats
STICK = 16000                                  # left-stick push (of 32767) that counts as a direction


class _Pad(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


class _State(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_ulong), ("Gamepad", _Pad)]


def _load():
    if sys.platform != "win32":
        return None
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            dll = ctypes.WinDLL(name)
        except OSError:
            continue
        dll.XInputGetState.argtypes = [ctypes.c_uint, ctypes.POINTER(_State)]
        dll.XInputGetState.restype = ctypes.c_uint
        return dll
    return None


def is_foreground(hwnd: int) -> bool:
    """True when this window is the one the user is using (so a controller used in a game is ignored)."""
    if sys.platform != "win32" or not hwnd:
        return True
    return ctypes.windll.user32.GetForegroundWindow() == hwnd


class Gamepad(threading.Thread):
    """Polls the first connected controller and calls on_press(name) for every press, from this thread.

    Only while active() is true: buttons already held when it becomes true must be let go and pressed again.
    """

    def __init__(self, on_press, active):
        super().__init__(daemon=True)
        self.on_press, self.active = on_press, active
        self.stop_event = threading.Event()
        self._dll = _load()

    def stop(self):
        self.stop_event.set()

    def run(self):
        if self._dll is None:
            return
        state = _State()
        get = lambda i: self._dll.XInputGetState(i, ctypes.byref(state)) == 0  # noqa: E731
        slot, next_scan = None, 0.0
        held: dict[str, float] = {}               # button -> when it fires again
        while not self.stop_event.is_set():
            now = time.monotonic()
            if slot is None:                      # asking empty slots is slow, so only look once a second
                if now >= next_scan:
                    slot = next((i for i in range(4) if get(i)), None)
                    next_scan = now + 1.0
                if slot is None:
                    time.sleep(0.25)
                    continue
            if not get(slot):                     # unplugged / turned off
                slot, held = None, {}
                continue
            pressed = self._pressed(state.Gamepad)
            if not self.active():
                held = dict.fromkeys(pressed, float("inf"))
                time.sleep(0.1)
                continue
            for name in pressed:
                t = held.get(name)
                if t is None or now >= t:
                    self.on_press(name)
                    held[name] = (now + (RATE if t is not None else DELAY)) if name in REPEAT else float("inf")
            for name in [n for n in held if n not in pressed]:
                del held[name]
            time.sleep(1 / 60)

    @staticmethod
    def _pressed(p) -> set:
        out = {name for bit, name in BUTTONS.items() if p.wButtons & bit}
        if p.sThumbLX <= -STICK:
            out.add("left")
        elif p.sThumbLX >= STICK:
            out.add("right")
        if p.sThumbLY >= STICK:
            out.add("up")
        elif p.sThumbLY <= -STICK:
            out.add("down")
        return out
