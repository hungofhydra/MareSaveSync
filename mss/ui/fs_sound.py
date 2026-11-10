"""Fullscreen mode's sounds: short, quiet tones made here (no sound files to ship) and played with Windows'
PlaySound. They're written once to data/sounds as .wav files, because PlaySound can only play a file without
waiting for it to finish. Elsewhere than Windows, or with no sound device, nothing is played.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from ..paths import app_dir

try:
    import winsound
except ImportError:
    winsound = None

RATE = 22050
VOLUME = 0.2
SET = "1"                   # change it when SOUNDS changes: the files are made again
# name -> [(frequency in Hz, 0 for a pause; milliseconds)]
SOUNDS = {
    "move": [(1050, 26)],                                   # the focus moved / a key was typed
    "select": [(700, 38), (1050, 62)],                      # A
    "back": [(700, 38), (470, 62)],                         # B
    "prompt": [(590, 80), (880, 130)],                      # a question appears
    "alert": [(880, 90), (0, 40), (880, 90), (0, 40), (660, 170)],     # a save conflict, a warning
    "error": [(196, 120), (0, 50), (165, 200)],             # something failed
}
_files: dict[str, Path] = {}


def _samples(notes) -> bytes:
    out = bytearray()
    for freq, ms in notes:
        n = int(RATE * ms / 1000)
        for i in range(n):
            # a few ms of fade-in and a fade-out over the whole note: no clicks
            env = min(1.0, i / (RATE * 0.004)) * (1 - i / n) ** 1.5
            v = math.sin(2 * math.pi * freq * i / RATE) * env * VOLUME if freq else 0.0
            out += struct.pack("<h", int(v * 32767))
    return bytes(out)


def sound_file(name: str) -> Path:
    """The sound's .wav, made the first time it's needed."""
    if name not in _files:
        d = app_dir() / "sounds"
        p = d / f"{name}-{SET}.wav"
        if not p.is_file():
            d.mkdir(exist_ok=True)
            for old in d.glob(f"{name}-*.wav"):
                old.unlink(missing_ok=True)
            with wave.open(str(p), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(_samples(SOUNDS[name]))
        _files[name] = p
    return _files[name]


def play(name: str) -> None:
    """Start playing a sound and return at once (a sound still playing is cut off)."""
    if winsound is None:
        return
    try:
        winsound.PlaySound(str(sound_file(name)),
                           winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:           # no sound device, the data folder can't be written, …
        pass
