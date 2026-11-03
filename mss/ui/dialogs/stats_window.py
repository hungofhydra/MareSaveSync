"""Playtime stats: totals, hours per week (a chart, or the same as a table) and every game's hours on each PC.

The totals per PC come with the library. The per-day history behind the weekly numbers is in each PC's playtime
files, so it's loaded (in the background) when this window opens.
"""
from __future__ import annotations

import datetime as dt
import threading
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ...core.playtime import fmt_ago, fmt_play_long, history_start, weekly
from ..theme import UI, UIB, T
from ..widgets import Btn, label, window

if TYPE_CHECKING:
    from ..app import App

WEEKS = 12
BAR = "#3a6fd8"                     # one series: the theme's title-bar blue (passes the dataviz palette checks)
BAR_HOVER = "#0a0a80"
GRID, AXIS, SURFACE = "#e6e6e6", "#a0a0a0", "#ffffff"


def hours(sec) -> str:
    h = (sec or 0) / 3600
    return "0 h" if h == 0 else f"{h:.1f} h".replace(".0 h", " h") if h < 10 else f"{h:.0f} h"


class StatsWindow(tk.Toplevel):
    def __init__(self, app: App):
        super().__init__(app)
        self.app = app
        self.title("Playtime — Mare Save Sync")
        self.geometry("1080x760")
        self.configure(bg=T["desk"])
        self.weeks: list[dict] | None = None        # None until the history has loaded
        self.since: dt.date | None = None
        self.hover: int | None = None
        outer, _bar, body = window(self, "Playtime", app.icon16)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        tiles = tk.Frame(body, bg=T["face"])
        tiles.pack(fill="x", pady=(2, 8))
        self.tile_vals = {}
        for key, name in (("week", "This week"), ("month", "Last 30 days"), ("all", "All time")):
            f = tk.Frame(tiles, bg=T["field"], relief="sunken", bd=2, padx=14, pady=8)
            f.pack(side="left", padx=(0, 8))
            tk.Label(f, text=name, bg=T["field"], fg=T["muted"], font=UI).pack(anchor="w")
            v = tk.Label(f, text="…", bg=T["field"], fg=T["ink"], font=(UI[0], UI[1] + 10, "bold"))
            v.pack(anchor="w")
            self.tile_vals[key] = v
        label(tiles, "All PCs together.", muted=True).pack(side="left", padx=6, anchor="s")

        head = tk.Frame(body, bg=T["face"])
        head.pack(fill="x")
        label(head, f"Hours played per week, last {WEEKS} weeks", bold=True).pack(side="left")
        self.view = tk.StringVar(value="chart")
        for text, v in (("Table", "table"), ("Chart", "chart")):
            tk.Radiobutton(head, text=text, value=v, variable=self.view, command=self._show_view, bg=T["face"],
                           activebackground=T["face"], selectcolor=T["field"], font=UI).pack(side="right")
        self.caption = label(body, "", muted=True, anchor="w", justify="left")
        self.caption.pack(fill="x")

        self.chart_box = tk.Frame(body, bg=T["face"], relief="sunken", bd=2)
        self.chart = tk.Canvas(self.chart_box, bg=SURFACE, height=250, highlightthickness=0, bd=0)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda e: self._draw_chart())
        self.week_table = self._tree(body, [("week", "Week of", 140, "w"), ("hours", "Played", 90, "e"),
                                            ("top", "Most played that week", 420, "w")], height=8)
        self._show_view()

        label(body, "Games", bold=True).pack(anchor="w", pady=(10, 2))
        self.pcs = app.pc_stats()
        cols = [("game", "Game", 260, "w"), ("total", "Total", 80, "e")]
        cols += [(f"pc{i}", pc.get("device") or "PC", 110, "e") for i, pc in enumerate(self.pcs)]
        cols += [("last", "Last played", 140, "w"), ("where", "On", 120, "w")]
        self.games = self._tree(body, cols, height=10)
        self.games.master.pack(fill="both", expand=True)
        self._fill_games()

        bot = tk.Frame(body, bg=T["face"])
        bot.pack(fill="x", pady=(8, 0))
        Btn(bot, "Close", self.destroy, kind="default", padx=18).pack(side="right")
        self.tile_vals["all"].configure(text=hours(sum(st.get("seconds", 0) for st in app.stats_all.values())))
        self._load()

    # ------------------------------------------------------------ data
    def _load(self):
        app = self.app
        first = dt.datetime.combine(dt.date.today() - dt.timedelta(weeks=WEEKS), dt.time()).timestamp()
        mine = [(g, st.get("days")) for g, st in app.settings.data.get("my_stats", {}).items() if st.get("days")]
        result: dict = {}

        def work():
            try:
                b = app.backend
                others = b.read_play_history(first, app.settings.data["device_id"]) if b is not None else []
                result["h"] = mine + [(e["game"], e["days"]) for e in others]
            except Exception as ex:
                result["error"] = ex
                result["h"] = mine
        threading.Thread(target=work, daemon=True).start()

        def check():
            if not self.winfo_exists():
                return
            if "h" not in result:
                self.after(150, check)
                return
            if "error" in result:
                app.log(f"Couldn't load the other PCs' playtime history: {result['error']}")
            self._loaded(result["h"], result.get("error"))
        check()

    def _loaded(self, histories, error=None):
        self.weeks = weekly(histories, WEEKS)
        self.since = history_start(histories)
        today = dt.date.today()
        month = sum(s for _g, days in histories for k, s in (days or {}).items()
                    if (today - dt.date.fromisoformat(k)).days < 30)
        self.tile_vals["week"].configure(text=hours(self.weeks[-1]["seconds"]))
        self.tile_vals["month"].configure(text=hours(month))
        cap = ("Weekly numbers start on " + self.since.strftime("%d %b %Y") +
               ": playtime from before then has no dates, so it's only in the totals.") if self.since else \
            "Weekly numbers start from your next game session: playtime from before has no dates."
        if error:
            cap += "  (Only this PC's: the other PCs' history couldn't be loaded.)"
        self.caption.configure(text=cap)
        self._draw_chart()
        t = self.week_table
        t.delete(*t.get_children())
        for w in reversed(self.weeks):
            top = sorted(w["games"].items(), key=lambda kv: -kv[1])[:3]
            t.insert("", "end", values=(w["start"].strftime("%d %b %Y"), hours(w["seconds"]),
                                        ",  ".join(f"{g} {hours(s)}" for g, s in top)))

    def _fill_games(self):
        app, t = self.app, self.games
        rows = []
        for g in app.all_games:
            per = [pc["games"].get(g, {}) for pc in self.pcs]
            last_i = max(range(len(per)), key=lambda i: per[i].get("last_played", 0), default=None)
            last = per[last_i].get("last_played", 0) if last_i is not None else 0
            rows.append((g, sum(p.get("seconds", 0) for p in per), [p.get("seconds", 0) for p in per], last,
                         self.pcs[last_i].get("device") if last else ""))
        for g, total, per, last, where in sorted(rows, key=lambda r: (-r[1], r[0].lower())):
            t.insert("", "end", values=(g, hours(total), *[hours(s) if s else "—" for s in per],
                                        fmt_ago(last) if last else "never", where))

    # ------------------------------------------------------------ chart
    def _show_view(self):
        if self.view.get() == "chart":
            self.week_table.master.pack_forget()
            self.chart_box.pack(fill="x", pady=(4, 0), after=self.caption)
        else:
            self.chart_box.pack_forget()
            self.week_table.master.pack(fill="x", pady=(4, 0), after=self.caption)

    def _draw_chart(self):
        c = self.chart
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        if W < 50:
            return
        if self.weeks is None:
            c.create_text(W // 2, H // 2, text="Loading…", fill=T["muted"], font=UI)
            return
        left, right, top, bottom = 52, 20, 22, 30
        pw, ph = W - left - right, H - top - bottom
        peak = max(w["seconds"] for w in self.weeks) / 3600
        step = next((s for s in (0.5, 1, 2, 5, 10, 20, 50, 100) if peak / s <= 5), 200)
        ymax = max(step, step * -(-peak // step))
        y = lambda h: top + ph - ph * h / ymax  # noqa: E731
        k = 0.0
        while k <= ymax + 1e-9:                                 # hairline grid, clean hour ticks
            c.create_line(left, y(k), W - right, y(k), fill=GRID if k else AXIS)
            c.create_text(left - 8, y(k), text=f"{k:g} h", anchor="e", fill=T["muted"], font=UI)
            k += step
        slot = pw / len(self.weeks)
        bw = min(24, slot * 0.6)
        best = max(range(len(self.weeks)), key=lambda i: self.weeks[i]["seconds"])
        for i, w in enumerate(self.weeks):
            cx = left + slot * (i + 0.5)
            h = w["seconds"] / 3600
            tag = f"wk{i}"
            # the whole column is the hover target, not just the bar
            c.create_rectangle(cx - slot / 2, top, cx + slot / 2, top + ph, fill=SURFACE, outline="", tags=tag)
            if h > 0:
                self._bar(cx - bw / 2, y(h), cx + bw / 2, y(0), BAR_HOVER if i == self.hover else BAR, tag)
            if i == best and h > 0:                             # label only the peak; the rest is in the tooltip
                c.create_text(cx, y(h) - 4, text=hours(w["seconds"]), anchor="s", fill=T["ink"], font=UIB, tags=tag)
            if slot >= 56 or i % 2 == (len(self.weeks) - 1) % 2:
                c.create_text(cx, top + ph + 8, text=w["start"].strftime("%d %b"), anchor="n", fill=T["muted"],
                              font=UI, tags=tag)
            c.tag_bind(tag, "<Enter>", lambda e, i=i: self._hover(i))
            c.tag_bind(tag, "<Leave>", lambda e, i=i: self._hover(None) if self.hover == i else None)
        if self.hover is not None:
            self._tooltip(self.hover, left + slot * (self.hover + 0.5), W)

    def _bar(self, x1, y1, x2, y2, color, tag):
        """4px rounded at the top, square at the baseline."""
        r = min(4, (x2 - x1) / 2, max(0, y2 - y1))
        pts = [x1, y2, x1, y1 + r, x1, y1, x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2]
        self.chart.create_polygon(pts, smooth=True, fill=color, outline="", tags=tag)
        if y2 - y1 > r:                                         # keep the bottom corners square
            self.chart.create_rectangle(x1, y1 + r, x2, y2, fill=color, outline="", tags=tag)

    def _hover(self, i):
        if self.hover != i:
            self.hover = i
            self._draw_chart()

    def _tooltip(self, i, cx, W):
        c, w = self.chart, self.weeks[i]
        end = w["start"] + dt.timedelta(days=6)
        lines = [f"{w['start'].strftime('%d %b')} – {end.strftime('%d %b %Y')}",
                 fmt_play_long(w["seconds"]) if w["seconds"] else "Not played"]
        top = sorted(w["games"].items(), key=lambda kv: -kv[1])
        lines += [f"{g}  {fmt_play_long(s)}" for g, s in top[:4]]
        if len(top) > 4:
            lines.append(f"…and {len(top) - 4} more")
        t = c.create_text(0, 0, text="\n".join(lines), anchor="nw", fill=T["ink"], font=UI)
        x1, y1, x2, y2 = c.bbox(t)
        tw, th = x2 - x1 + 16, y2 - y1 + 12
        x = cx + 16 if cx + 16 + tw < W - 4 else cx - 16 - tw
        c.move(t, x + 8, 10 + 6)
        r = c.create_rectangle(x, 10, x + tw, 10 + th, fill="#ffffe1", outline=T["shadow"])
        c.tag_lower(r, t)

    # ------------------------------------------------------------ helpers
    def _tree(self, parent, cols, height):
        f = tk.Frame(parent, bg=T["face"], relief="sunken", bd=2)
        t = ttk.Treeview(f, columns=[k for k, *_ in cols], show="headings", height=height, selectmode="browse")
        for key, title, width, anchor in cols:
            t.heading(key, text=title, anchor=anchor,
                      command=lambda key=key: self._sort(t, key))
            t.column(key, width=width, minwidth=50, anchor=anchor, stretch=key in ("game", "top"))
        vs = ttk.Scrollbar(f, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=vs.set)
        t.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        return t

    @staticmethod
    def _sort(t, key):
        """Click a heading: sort by it (numbers by value, the rest by text); click again to reverse."""
        def val(v):
            v = str(v)
            if v.endswith(" h") and v[:-2].replace(".", "", 1).isdigit():
                return (0, -float(v[:-2]), "")
            return (1, 0, v.lower())
        rows = [(val(t.set(i, key)), i) for i in t.get_children("")]
        rev = getattr(t, "_sorted", None) == key
        rows.sort(reverse=rev)
        for n, (_v, i) in enumerate(rows):
            t.move(i, "", n)
        t._sorted = None if rev else key
