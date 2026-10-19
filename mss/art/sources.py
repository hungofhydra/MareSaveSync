"""Cover-art sources the artwork dialog can search. To add one, give it a class with the same
search / images / art_for methods as sgdb.SGDB and register it in SOURCES."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..providers import sgdb


@dataclass(frozen=True)
class Source:
    name: str
    key_setting: str            # settings key holding this source's API key
    make: Callable[[str], object]


SOURCES: dict[str, Source] = {s.name: s for s in (
    Source("SteamGridDB", "sgdb_key", sgdb.SGDB),
)}
DEFAULT = "SteamGridDB"
