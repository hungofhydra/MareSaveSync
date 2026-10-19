"""Mare Save Sync — keeps your game saves, playtime and artwork in sync between PCs.

Run:  python app.py        (the code lives in the mss/ package)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mss.ui.app import main  # noqa: E402

if __name__ == "__main__":
    main()
