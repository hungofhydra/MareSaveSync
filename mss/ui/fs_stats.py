"""Playtime stats in fullscreen mode (☰ → Playtime stats): the same numbers as the desktop window
(dialogs/stats_window.py), drawn for a TV-sized screen. Left / right pick a week, which lists its games (the
controller's version of hovering a bar); B goes back.
"""
from __future__ import annotations

import datetime as dt

from ..core.playtime import fmt_ago, fmt_play_long, history_start, weekly
from .dialogs.stats_window import WEEKS, game_rows, history_caption, hours, last_days
from .fullscreen import FS

BAR = FS["blue"]                    # passes the dataviz palette checks on the card surface
TOP_GAMES = 5


class FsStatsMixin:
    """Part of App (see ui/app.py)."""

    _fs_stats: dict | None = None   # {"weeks", "since", "month", "error"} once loaded

    def fs_open_stats(self):
        self._fs_view, self._fs_stats, self._fs_week = "stats", None, WEEKS - 1
        self._fs_render()

        def done(histories, error):
            self._fs_stats = {"weeks": weekly(histories, WEEKS), "since": history_start(histories),
                              "month": last_days(histories, 30), "error": error}
            self._fs_refresh()
        self.load_play_history(WEEKS, done)

    def _fs_stats_input(self, b):
        if b == "b":
            self._fs_view = "home"
        elif b in ("left", "right", "lb", "rb"):
            step = {"left": -1, "right": 1, "lb": -4, "rb": 4}[b]
            self._fs_week = max(0, min(WEEKS - 1, self._fs_week + step))
        self._fs_render()

    def _fs_stats_page(self, W, H):
        c, p = self._fs_c, self._fs_px
        scrim = self._fs_scrim(W, H)
        if scrim is not None:
            c.create_image(0, 0, image=scrim, anchor="nw")
        x0, y = p(96), p(118)
        c.create_text(x0, y, text="Playtime", anchor="nw", fill=FS["ink"], font=self._fs_font(44, bold=True))
        c.create_text(x0 + p(250), y + p(26), text="All PCs together", anchor="w", fill=FS["sub"],
                      font=self._fs_font(19))
        st = self._fs_stats
        y += p(84)
        total = sum(s.get("seconds", 0) for s in self.stats_all.values())
        tiles = [("This week", hours(st["weeks"][-1]["seconds"]) if st else "…"),
                 ("Last 30 days", hours(st["month"]) if st else "…"), ("All time", hours(total))]
        tx = x0
        for name, value in tiles:
            self._fs_rrect(tx, y, tx + p(250), y + p(112), p(14), fill=FS["card"], outline=FS["line"])
            c.create_text(tx + p(24), y + p(22), text=name, anchor="nw", fill=FS["sub"], font=self._fs_font(17))
            c.create_text(tx + p(24), y + p(50), text=value, anchor="nw", fill=FS["ink"],
                          font=self._fs_font(40, bold=True))
            tx += p(274)

        # weekly chart, left; the chosen week's games, right
        y += p(140)
        bottom = H - p(84) - p(30)
        chart_w = int((W - 2 * x0) * 0.62)
        self._fs_rrect(x0, y, x0 + chart_w, bottom, p(16), fill=FS["card"], outline=FS["line"])
        c.create_text(x0 + p(28), y + p(22), text=f"Hours per week, last {WEEKS} weeks", anchor="nw",
                      fill=FS["ink"], font=self._fs_font(20, semi=True))
        c.create_text(x0 + p(28), y + p(54), text=history_caption(st["since"]) if st else "Loading…", anchor="nw",
                      fill=FS["dim"], font=self._fs_font(15), width=chart_w - p(56))
        if st:
            self._fs_week_bars(st["weeks"], x0 + p(28), y + p(100), x0 + chart_w - p(28), bottom - p(24))
        px = x0 + chart_w + p(28)
        self._fs_rrect(px, y, W - x0, bottom, p(16), fill=FS["card"], outline=FS["line"])
        if st:
            self._fs_week_detail(st["weeks"][self._fs_week], px + p(28), y + p(22), W - x0 - px - p(56), bottom)
        else:
            self._fs_top_games(px + p(28), y + p(22), W - x0 - px - p(56), bottom)

    def _fs_week_bars(self, weeks, x1, y1, x2, y2):
        c, p = self._fs_c, self._fs_px
        axis_w, label_h = p(56), p(34)
        left, base = x1 + axis_w, y2 - label_h
        peak = max(w["seconds"] for w in weeks) / 3600
        step = next((s for s in (0.5, 1, 2, 5, 10, 20, 50, 100) if peak / s <= 4), 200)
        ymax = max(step, step * -(-peak // step))
        y = lambda h: base - (base - y1) * h / ymax  # noqa: E731
        k = 0.0
        while k <= ymax + 1e-9:                     # hairline grid, clean hour ticks
            c.create_line(left, y(k), x2, y(k), fill=FS["line"])
            c.create_text(left - p(10), y(k), text=f"{k:g} h", anchor="e", fill=FS["dim"], font=self._fs_font(14))
            k += step
        slot = (x2 - left) / len(weeks)
        bw = min(p(30), slot * 0.55)
        for i, w in enumerate(weeks):
            cx = left + slot * (i + 0.5)
            h = w["seconds"] / 3600
            focused = i == self._fs_week
            tag = f"week{i}"
            c.create_rectangle(cx - slot / 2, y1, cx + slot / 2, y2, fill="", outline="", tags=tag)
            if focused:                              # the chosen week, like the focused cover
                self._fs_rrect(cx - slot / 2 + p(3), y1 - p(8), cx + slot / 2 - p(3), y2, p(10), fill="",
                               outline=FS["glow"], width=p(2), tags=tag)
            if h > 0:                                # rounded at the top, square at the baseline
                a, b2, top = cx - bw / 2, cx + bw / 2, y(h)
                r = min(p(5), bw / 2, base - top)
                color = FS["focus"] if focused else BAR
                c.create_polygon([a, base, a, top + r, a, top, a + r, top, b2 - r, top, b2, top, b2, top + r, b2, base],
                                 smooth=True, fill=color, outline="", tags=tag)
                if base - top > r:
                    c.create_rectangle(a, top + r, b2, base, fill=color, outline="", tags=tag)
            if slot >= p(70) or i % 2 == (len(weeks) - 1) % 2 or focused:
                c.create_text(cx, base + p(10), text=w["start"].strftime("%d %b"), anchor="n", tags=tag,
                              fill=FS["ink"] if focused else FS["dim"], font=self._fs_font(14, semi=focused))
            c.tag_bind(tag, "<Button-1>", lambda e, i=i: self._fs_pick_week(i))

    def _fs_pick_week(self, i):
        if not self._fs_prompts and self._fs_menu is None:
            self._fs_week = i
            self._fs_render()

    def _fs_week_detail(self, w, x, y, width, bottom):
        c, p = self._fs_c, self._fs_px
        end = w["start"] + dt.timedelta(days=6)
        this = w["start"] == weekly([], 1)[0]["start"]
        c.create_text(x, y, text="This week" if this else f"{w['start'].strftime('%d %b')} – {end.strftime('%d %b')}",
                      anchor="nw", fill=FS["sub"], font=self._fs_font(18, semi=True))
        c.create_text(x, y + p(32), text=fmt_play_long(w["seconds"]) if w["seconds"] else "Not played",
                      anchor="nw", fill=FS["ink"], font=self._fs_font(32, bold=True))
        y += p(100)
        top = sorted(w["games"].items(), key=lambda kv: -kv[1])
        for g, secs in top:
            if y > bottom - p(70):
                c.create_text(x, y, text=f"…and {len(top) - top.index((g, secs))} more", anchor="nw",
                              fill=FS["dim"], font=self._fs_font(17))
                break
            self._fs_game_line(x, y, width, g, hours(secs), secs / max(1, w["seconds"]))
            y += p(54)

    def _fs_top_games(self, x, y, width, bottom):
        """Before the weeks have loaded: the most played games (from the totals every PC shares)."""
        c, p = self._fs_c, self._fs_px
        c.create_text(x, y, text="Most played", anchor="nw", fill=FS["sub"], font=self._fs_font(18, semi=True))
        y += p(48)
        rows = game_rows(self, self.pc_stats())[:TOP_GAMES]
        most = max((r[1] for r in rows), default=1) or 1
        for g, total, _per, last, where in rows:
            if total <= 0 or y > bottom - p(60):
                break
            self._fs_game_line(x, y, width, g, hours(total), total / most,
                               f"Last played {fmt_ago(last)}" + (f" on {where}" if where else ""))
            y += p(64)

    def _fs_game_line(self, x, y, width, name, value, share, sub=""):
        """A game's name and hours, with a thin bar showing its share."""
        c, p = self._fs_c, self._fs_px
        v = c.create_text(x + width, y, text=value, anchor="ne", fill=FS["ink"], font=self._fs_font(18, semi=True))
        c.create_text(x, y, text=name, anchor="nw", fill=FS["ink"], font=self._fs_font(18),
                      width=max(p(80), c.bbox(v)[0] - x - p(16)))
        by = y + p(30)
        c.create_line(x, by, x + width, by, fill=FS["line"], width=p(4), capstyle="round")
        if share > 0:
            c.create_line(x, by, x + max(p(4), width * min(1, share)), by, fill=BAR, width=p(4), capstyle="round")
        if sub:
            c.create_text(x, by + p(8), text=sub, anchor="nw", fill=FS["dim"], font=self._fs_font(14))
