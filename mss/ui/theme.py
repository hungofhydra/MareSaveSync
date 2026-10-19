"""Look and feel: colours, fonts and sizes.

Classic silver window chrome on a teal desktop, navy→blue title bars, a starry night banner.
"""
from __future__ import annotations

import sys

WIN = sys.platform == "win32"

T = dict(desk="#2b8383", face="#c0c0c0", hi="#ffffff", shadow="#808080", dark="#000000",
         t1="#0b0b86", t2="#3a6fd8", t1i="#7b7b7b", t2i="#b4b4b4", navy="#0a0a80", ink="#000000",
         field="#ffffff", muted="#4a4a4a", danger="#8b1a2b", moon="#fff4c4")
C = dict(panel2=T["face"], fg=T["ink"], sel=T["navy"])          # used by context menus
UI = ("Tahoma", 9) if WIN else ("Helvetica", 10)
UIB = (UI[0], UI[1], "bold")
SMALL = (UI[0], UI[1] - 1)
MONO = ("Lucida Console", 9) if WIN else ("Courier", 10)
GRID_BG = "#14124e"
TILE_W, TILE_H = 150, 225
HERO_H, HERO_BAR = 236, 62
