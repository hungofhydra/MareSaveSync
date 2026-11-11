"""Your own information about a game: a status, tags and notes.

Kept in the game's shared cloud config (savesync.json, under "mine"), so every PC has it, and cached on each PC
(settings "mine_cache") so the library can be filtered at once.
"""
from __future__ import annotations

STATUSES = {"backlog": "Backlog", "playing": "Playing", "on_hold": "On hold", "completed": "Completed",
            "dropped": "Dropped"}
MAX_TAGS, MAX_TAG, MAX_NOTES = 30, 30, 20000


def clean(mine) -> dict:
    """A tidy copy: a known status, distinct short tags, trimmed notes. Empty parts are left out."""
    mine = mine if isinstance(mine, dict) else {}
    out = {}
    if mine.get("status") in STATUSES:
        out["status"] = mine["status"]
    tags, seen = [], set()
    raw = mine.get("tags")
    for t in raw if isinstance(raw, list) else []:
        t = " ".join(str(t).split())[:MAX_TAG]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
    if tags:
        out["tags"] = tags[:MAX_TAGS]
    notes = str(mine.get("notes") or "").strip()[:MAX_NOTES]
    if notes:
        out["notes"] = notes
    return out


def parse_tags(text: str) -> list[str]:
    """“rpg, co-op; Switch” -> ["rpg", "co-op", "Switch"]"""
    return [t for t in text.replace(";", ",").split(",") if t.strip()]


def tags_text(mine: dict) -> str:
    return ", ".join(mine.get("tags") or [])


def status_name(mine: dict) -> str:
    return STATUSES.get(mine.get("status"), "")


def has_tag(mine: dict, query: str) -> bool:
    """True if any tag contains `query` (lower case) - the library search also finds games by their tags."""
    return any(query in t.lower() for t in mine.get("tags") or [])


def passes(mine: dict, key: str) -> bool:
    """Does a game with this `mine` show under the library filter `key` ("" = all, "status:playing", "tag:rpg")?"""
    kind, _, value = key.partition(":")
    if kind == "status":
        return mine.get("status") == value
    if kind == "tag":
        return value in {t.lower() for t in mine.get("tags") or []}
    return True


def filter_choices(mines: list[dict]) -> list[tuple[str, str]]:
    """[(key, shown name)] for the library's Show box: all games, then each status and tag that some game has."""
    statuses: dict[str, int] = {}
    tags: dict[str, list] = {}                      # lower case -> [name as first written, count]
    for m in mines:
        if m.get("status"):
            statuses[m["status"]] = statuses.get(m["status"], 0) + 1
        for t in m.get("tags") or []:
            tags.setdefault(t.lower(), [t, 0])[1] += 1
    out = [("", "All games")]
    out += [(f"status:{k}", f"{v}  ({statuses[k]})") for k, v in STATUSES.items() if k in statuses]
    out += [(f"tag:{k}", f"Tag: {name}  ({n})") for k, (name, n) in sorted(tags.items())]
    return out
