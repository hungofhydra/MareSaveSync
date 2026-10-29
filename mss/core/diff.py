"""Comparing this PC with the cloud, file by file."""
from __future__ import annotations

from dataclasses import dataclass

from .excludes import is_excluded, matching_patterns
from .scan import FileInfo

SAME, LOCAL_ONLY, CLOUD_ONLY, CHANGED, EXCLUDED = (
    "same", "local_only", "cloud_only", "changed", "excluded")


@dataclass
class DiffEntry:
    path: str
    status: str
    local: FileInfo | None = None
    cloud: FileInfo | None = None
    hint: str = ""
    changed_side: str | None = None   # "local" | "cloud" | "both" | None (unknown)


def compute_diff(local, cloud, excludes, base=None, unset=None) -> list[DiffEntry]:
    """Compare this PC with the cloud.

    `base` is {path: md5} of the state both sides shared after this PC's last
    sync. It lets us tell *which* side changed (and spot conflicts).
    `unset` is {cloud prefix: name} of save folders not set on this PC; their files are left alone.
    """
    base = base or {}
    unset = unset or {}
    out = []
    for rel in sorted(set(local) | set(cloud), key=str.lower):
        l, c = local.get(rel), cloud.get(rel)
        e = DiffEntry(rel, SAME, l, c)
        hits = matching_patterns(rel, excludes)
        skip = next((n for p, n in unset.items() if rel.startswith(p)), None)
        if skip is not None:
            e.status, e.hint = EXCLUDED, f"Folder “{skip}” not set on this PC"
        elif hits:
            e.status, e.hint = EXCLUDED, f"Matches {hits[0]}"
        elif l and c:
            if l.md5 != c.md5:
                e.status = CHANGED
                b = base.get(rel)
                if b == c.md5:
                    e.changed_side, e.hint = "local", "Changed on this PC"
                elif b == l.md5:
                    e.changed_side, e.hint = "cloud", "Changed in cloud"
                elif b:
                    e.changed_side, e.hint = "both", "Changed on both sides"
                else:
                    e.hint = "This PC is newer" if l.mtime >= c.mtime else "Cloud is newer"
        elif l:
            e.status = LOCAL_ONLY
            if rel in base:
                e.changed_side, e.hint = "cloud", "Deleted from cloud"
            else:
                e.changed_side, e.hint = "local", "New on this PC"
        else:
            e.status = CLOUD_ONLY
            if rel in base:
                e.changed_side, e.hint = "local", "Deleted on this PC"
            else:
                e.changed_side, e.hint = "cloud", "New in cloud"
        out.append(e)
    return out


def baseline(local, cloud, excludes) -> dict[str, str]:
    return {r: l.md5 for r, l in local.items()
            if r in cloud and cloud[r].md5 == l.md5 and not is_excluded(r, excludes)}


def auto_direction(diff):
    """Decide an automatic sync direction: None (in sync), "up", "down" or "ask" (conflict/unknown)."""
    pending = [e for e in diff if e.status not in (SAME, EXCLUDED)]
    if not pending:
        return None
    sides = {e.changed_side for e in pending}
    if sides <= {"local"}:
        return "up"
    if sides <= {"cloud"}:
        return "down"
    return "ask"
