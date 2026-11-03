"""Emulator profiles: a game can be started by an emulator with its ROM instead of an .exe of its own.

A profile is set up once per PC: {"exe": the emulator, "args": an argument template with {rom} where the ROM's
path goes}. Each game that uses it has, on this PC, "emulator" (the profile's name) and "rom" (its file).
Common emulators' arguments are filled in from the program's name (PRESETS).
"""
from __future__ import annotations

from pathlib import Path

ROM = "{rom}"

# program name (lower case, no .exe) -> (shown name, arguments). RetroArch needs its core: change "CORE".
PRESETS = {
    "retroarch": ("RetroArch", '-L "cores\\CORE_libretro.dll" "{rom}"'),
    "dolphin": ("Dolphin", '-b -e "{rom}"'),
    "pcsx2-qt": ("PCSX2", '-batch -fullscreen -- "{rom}"'),
    "pcsx2": ("PCSX2", '-batch -fullscreen -- "{rom}"'),
    "duckstation-qt-x64-releaseltcg": ("DuckStation", '-batch -fullscreen "{rom}"'),
    "duckstation": ("DuckStation", '-batch -fullscreen "{rom}"'),
    "ppssppwindows64": ("PPSSPP", '--fullscreen "{rom}"'),
    "ppssppwindows": ("PPSSPP", '--fullscreen "{rom}"'),
    "rpcs3": ("RPCS3", '--no-gui "{rom}"'),
    "cemu": ("Cemu", '-f -g "{rom}"'),
    "ryujinx": ("Ryujinx", '--fullscreen "{rom}"'),
    "xemu": ("xemu", '-full-screen -dvd_path "{rom}"'),
    "mgba": ("mGBA", '-f "{rom}"'),
    "melonds": ("melonDS", '-f "{rom}"'),
    "azahar": ("Azahar", '-f "{rom}"'),
    "lime3ds": ("Lime3DS", '-f "{rom}"'),
    "flycast": ("Flycast", '"{rom}"'),
    "snes9x-x64": ("Snes9x", '-fullscreen "{rom}"'),
    "mesen": ("Mesen", '--fullscreen "{rom}"'),
}
DEFAULT_ARGS = '"{rom}"'


def preset_for(exe) -> tuple[str, str]:
    """(a name for the profile, its arguments) guessed from the emulator's program."""
    stem = Path(exe).stem.lower()
    if stem in PRESETS:
        return PRESETS[stem]
    for key, preset in PRESETS.items():        # e.g. "duckstation-qt-x64-releaseltcg-avx2"
        if stem.startswith(key):
            return preset
    return Path(exe).stem, DEFAULT_ARGS


def launch_args(profile: dict, rom: str, extra: str = "") -> str:
    """The emulator's command-line arguments for this ROM (plus the game's own launch options)."""
    args = profile.get("args") or DEFAULT_ARGS
    args = args.replace(ROM, rom) if ROM in args else f'{args} "{rom}"'
    return f"{args} {extra}".strip()
