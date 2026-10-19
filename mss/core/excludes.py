"""Exclusion patterns: which save files are never synced."""
from __future__ import annotations

import fnmatch

from .util import norm_rel


def matching_patterns(rel: str, patterns) -> list[str]:
    """Patterns that exclude `rel`.

    * "/Player.log", "/Screenshots"  -> anchored to the save folder root
    * "Logs/*.txt"                   -> contains a slash, so also anchored
    * "*.log", "Cache"               -> matches a file or folder name anywhere
    A pattern that matches a folder excludes everything inside it.
    Matching is case-insensitive (Windows-friendly).
    """
    rel = norm_rel(rel).lower()
    parts = rel.split("/")
    prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    hits = []
    for raw in patterns:
        pat = raw.strip().replace("\\", "/")
        if not pat or pat.startswith("#"):
            continue
        anchored = pat.startswith("/")
        p = pat.strip("/").lower()
        if not p:
            continue
        pool = prefixes if (anchored or "/" in p) else parts
        if any(fnmatch.fnmatchcase(x, p) for x in pool):
            hits.append(raw)
    return hits


def is_excluded(rel: str, patterns) -> bool:
    return bool(matching_patterns(rel, patterns))
