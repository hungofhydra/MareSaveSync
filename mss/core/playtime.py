"""Playtime formatting, merging the per-PC numbers, and the per-day history behind the weekly chart.

Each PC keeps, per game, its total seconds, when it was last played, and "days": {"YYYY-MM-DD": seconds} (local
dates, the last DAYS_KEPT days). Days are only known from when this was added; earlier playtime has no date.
"""
from __future__ import annotations

import datetime as dt
import time

DAYS_KEPT = 400


def fmt_play_short(sec) -> str:
    m = int((sec or 0) // 60)
    if m < 60:
        return f"{m}m"
    h = m / 60
    return (f"{h:.1f}".rstrip("0").rstrip(".") if h < 10 else str(int(h))) + "h"


def fmt_play_long(sec) -> str:
    m = int((sec or 0) // 60)
    if m < 120:
        return f"{m} minute{'s' if m != 1 else ''}"
    return f"{m // 60} h {m % 60} min"


def fmt_ago(ts) -> str:
    if not ts or ts < 1e9:
        return "never"
    d = time.time() - ts
    if d < 90:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)} minutes ago"
    if d < 7200:
        return "about 1 hour ago"
    if d < 86400:
        return f"about {int(d // 3600)} hours ago"
    if d < 172800:
        return "yesterday"
    if d < 30 * 86400:
        return f"{int(d // 86400)} days ago"
    return time.strftime("%d %b %Y", time.localtime(ts))


def add_session(days: dict, end: float, seconds: float) -> dict:
    """Add a session that ended at `end` to {date: seconds}, split at midnight. Drops days older than DAYS_KEPT."""
    t1 = dt.datetime.fromtimestamp(end)
    t = t1 - dt.timedelta(seconds=max(0.0, float(seconds)))
    while t < t1:
        midnight = dt.datetime.combine(t.date() + dt.timedelta(days=1), dt.time())
        part_end = min(midnight, t1)
        key = t.date().isoformat()
        days[key] = round(days.get(key, 0) + (part_end - t).total_seconds(), 1)
        t = part_end
    oldest = (t1.date() - dt.timedelta(days=DAYS_KEPT)).isoformat()
    for k in [k for k in days if k < oldest]:
        del days[k]
    return days


def week_start(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())        # Monday


def weekly(histories, weeks: int, today: dt.date | None = None) -> list[dict]:
    """The last `weeks` weeks, oldest first: [{"start": date, "seconds": total, "games": {game: seconds}}].
    histories: [(game, {date: seconds}), …] from every PC."""
    today = today or dt.date.today()
    first = week_start(today) - dt.timedelta(weeks=weeks - 1)
    out = [{"start": first + dt.timedelta(weeks=i), "seconds": 0.0, "games": {}} for i in range(weeks)]
    for game, days in histories:
        for key, secs in (days or {}).items():
            try:
                i = (dt.date.fromisoformat(key) - first).days // 7
            except ValueError:
                continue
            if 0 <= i < weeks:
                w = out[i]
                w["seconds"] += secs
                w["games"][game] = w["games"].get(game, 0) + secs
    return out


def history_start(histories) -> dt.date | None:
    """The first day any playtime has a date."""
    keys = [k for _g, days in histories for k in (days or {})]
    return dt.date.fromisoformat(min(keys)) if keys else None


def aggregate_stats(files: list) -> dict:
    """Merge every device's stats file: {game: {"seconds": total, "last_played": newest}}."""
    out: dict = {}
    for f in files:
        for game, st in (f.get("games") or {}).items():
            o = out.setdefault(game, {"seconds": 0, "last_played": 0})
            o["seconds"] += float(st.get("seconds", 0))
            o["last_played"] = max(o["last_played"], float(st.get("last_played", 0)))
    return out
