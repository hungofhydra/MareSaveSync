"""Playing games: launching, tracking playtime, syncing before and after."""
from __future__ import annotations

import time
from pathlib import Path
from tkinter import filedialog, messagebox

from .. import APP_TITLE, launcher
from ..core.diff import auto_direction, compute_diff
from ..core.playtime import aggregate_stats, fmt_play_long
from ..core.sync import make_plan
from .dialogs.conflict import ConflictDialog


class PlayMixin:
    """Part of App (see ui/app.py)."""

    def _merge_stats(self, files):
        dev = self.settings.data["device_id"]
        mine = self.settings.data.setdefault("my_stats", {})
        cloud_mine = next((f.get("games", {}) for f in files if f.get("device_id") == dev), {})
        changed = False
        for g, st in cloud_mine.items():
            m = mine.setdefault(g, {"seconds": 0, "last_played": 0})
            for k in ("seconds", "last_played"):
                if st.get(k, 0) > m.get(k, 0):
                    m[k] = st[k]
        if mine != cloud_mine:
            changed = True
        others = [f for f in files if f.get("device_id") != dev]
        self.stats_all = aggregate_stats(others + [{"games": mine}])
        self.settings.save()
        if changed:
            self.when_idle(self._push_stats)

    def _stats_doc(self):
        d = self.settings.data
        return {"device_id": d["device_id"], "device": d.get("device_name", ""), "updated": time.time(),
                "games": d.get("my_stats", {})}

    def _push_stats(self):
        if self.backend is None:
            return
        doc = self._stats_doc()
        self.run_bg("Saving playtime", lambda: self.backend.write_stats(doc["device_id"], doc),
                    lambda r: self.log("Playtime saved to the cloud"),
                    failed=lambda ex: self.log(f"Playtime will be uploaded later: {ex}"))

    def _add_playtime(self, g, seconds):
        now = time.time()
        m = self.settings.data.setdefault("my_stats", {}).setdefault(g, {"seconds": 0, "last_played": 0})
        m["seconds"] = m.get("seconds", 0) + seconds
        m["last_played"] = now
        a = self.stats_all.setdefault(g, {"seconds": 0, "last_played": 0})
        a["seconds"] += seconds
        a["last_played"] = now
        self.settings.save()

    def play_current(self):
        if self.game in self.sessions:
            if messagebox.askyesno(APP_TITLE, f"{self.game} is still being tracked.\n\nHas the game closed? "
                                   "Choose Yes to stop tracking now (playtime is saved and saves are uploaded).",
                                   parent=self):
                self.sessions[self.game].stop_tracking()
            return
        self.play(self.game)

    def pick_exe(self, g):
        if not g:
            return None
        cur = self.settings.data["games"].get(g, {}).get("exe")
        p = filedialog.askopenfilename(parent=self, title=f"Executable for {g}",
                                       initialdir=str(Path(cur).parent) if cur else None,
                                       filetypes=[("Programs", "*.exe *.bat *.cmd *.lnk"), ("All files", "*.*")])
        if not p:
            return None
        self.settings.game(g)["exe"] = str(Path(p))
        self.settings.save()
        self.log(f"{g}: executable set to {p}")
        if self.game == g:
            self._render_header()
        self._debounce("grid", 50, self._layout_grid)
        return p

    def play(self, g):
        if not g or self.busy or g in self.sessions:
            return
        gs = self.settings.game(g)
        exe = gs.get("exe")
        if not exe or not Path(exe).exists():
            if exe:
                messagebox.showwarning(APP_TITLE, f"The executable for {g} wasn't found:\n{exe}", parent=self)
            if not self.pick_exe(g):
                return
        if gs.get("local_path") and gs.get("auto_sync", True):
            if self.backend is None:
                if not messagebox.askyesno(APP_TITLE, "Not connected to the cloud, so saves can't be synced.\n\n"
                                           "Play anyway?", parent=self):
                    return
                self._launch(g)
            else:
                self.auto_sync(g, "before", lambda ok: self._launch(g) if ok else None)
        else:
            self._launch(g)

    def _launch(self, g):
        self._start_session(g)
        self.after(400, self.minimize)

    def _start_session(self, g, attach_started=None):
        gs = self.settings.game(g)
        sess = launcher.GameSession(g, gs["exe"], gs.get("args", ""),
                                    lambda game, secs, err: self.q.put(("game_end", game, secs, err)),
                                    attach_started=attach_started)
        self.sessions[g] = sess
        sess.start()
        self.note(f"Playing {g}" if not attach_started else f"{g} was started outside the app — tracking it")
        self.task_game.configure(text=f"▶ {', '.join(self.sessions)}")
        self.task_game.pack(side="left", padx=4, pady=2)
        if self.game == g:
            self._render_header()
            self._draw_hero()
        self._layout_grid()
        self._update_controls()
        self.set_tray_text(f"playing {', '.join(self.sessions)}")

    # ------------------------------------------------- games started elsewhere
    WATCH_EVERY = 5         # seconds between looks at the running processes

    def _watch_games(self):
        """Background: notice library games started outside the app (Steam, a shortcut, …) so their playtime
        is counted and their saves uploaded when they close, just like games started with Play."""
        while True:
            time.sleep(self.WATCH_EVERY)
            try:
                exes = {launcher.norm_exe(gs["exe"]): g
                        for g, gs in list(self.settings.data.get("games", {}).items())
                        if g in self.all_games and g not in self.sessions
                        and str(gs.get("exe", "")).lower().endswith(".exe")}
                for g, started in launcher.find_running(exes).items():
                    self.q.put(("game_detected", g, started))
            except Exception as ex:
                self.log_ts(f"Watching for games failed: {ex}")

    def _on_game_detected(self, g, started):
        if g in self.sessions or g not in self.all_games:
            return              # already tracked (e.g. started with Play a moment ago) or removed meanwhile
        self._start_session(g, attach_started=started)
        self.notify(f"{g} is running — playtime is being counted and saves will be synced when it closes.")

    def _on_game_end(self, g, seconds, err):
        self.sessions.pop(g, None)
        self.set_tray_text(f"playing {', '.join(self.sessions)}" if self.sessions else "")
        if not self.sessions:
            self.task_game.pack_forget()
        else:
            self.task_game.configure(text=f"▶ {', '.join(self.sessions)}")
        if err:
            self.show_window()
            messagebox.showerror(APP_TITLE, f"Couldn't start {g}:\n{err}", parent=self)
        else:
            self._add_playtime(g, seconds)
            self.note(f"{g} closed — played {fmt_play_long(seconds)}")
            self.when_idle(self._push_stats)
            gs = self.settings.game(g)
            if gs.get("local_path") and gs.get("auto_sync", True) and self.backend is not None:
                self.when_idle(lambda: self.auto_sync(g, "after", lambda ok: None))
        if self.game == g:
            self._render_header()
            self._draw_hero()
        self._layout_grid()
        self._update_controls()

    def auto_sync(self, g, moment, then):
        """moment "before": sync before launching (then(False) cancels launch). "after": upload after playing."""
        path = self._local_path(g)
        gs = self.settings.game(g)

        def failed(ex):
            if moment == "before":
                self.show_window()
                then(messagebox.askyesno(APP_TITLE, f"Couldn't check the cloud saves for {g}:\n{ex}\n\n"
                                         "Play anyway?", parent=self))
            else:
                self.show_window()
                messagebox.showwarning(APP_TITLE, f"Couldn't upload the saves for {g}:\n{ex}\n\n"
                                       "Open the game and press Sync up when you're back online.", parent=self)
                then(False)

        def checked(res):
            cfg, local, cloud = res
            diff = compute_diff(local, cloud, cfg.get("excludes", []), gs.get("base", {}))
            direction = auto_direction(diff)
            if self.game == g:
                self._apply_scan(g, res)
            if direction is None:
                self._set_state(g, "synced")
                self.log(f"{g}: saves already in sync")
                then(True)
                return
            if direction == "ask":
                self._set_state(g, "conflict")
                self.show_window()
                choice = ConflictDialog(self, g, diff, moment).result
                if choice == "cancel":
                    then(False)
                    return
                if choice in (None, "skip"):
                    self.log(f"{g}: sync skipped")
                    then(True)
                    return
                direction = choice
            plan = make_plan(diff, direction, self.mirror_var.get())
            if plan.empty:
                then(True)
                return
            self.log(f"{g}: automatic sync {direction} ({len(plan.transfer)} file(s))")
            self.run_bg(f"Sync {direction}: {g}", lambda: self._do_sync(g, path, plan),
                        lambda r: (self._after_sync(g, direction, r, quiet=True), then(True)), failed=failed)

        self.run_bg(f"Checking saves: {g}", lambda: self._scan(g, path), checked, failed=failed)
