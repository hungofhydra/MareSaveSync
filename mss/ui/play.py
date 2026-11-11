"""Playing games: launching, tracking playtime, syncing before and after."""
from __future__ import annotations

import datetime as dt
import threading
import time
from pathlib import Path
from tkinter import filedialog

from .. import APP_TITLE, launcher
from ..core import commands, emulators
from ..core.diff import auto_direction
from ..core.playtime import add_session, aggregate_stats, fmt_play_long
from ..core.sync import make_plan


class PlayMixin:
    """Part of App (see ui/app.py)."""

    other_pcs: list = []                        # the other PCs' playtime docs ({"device_id", "device", "games"})

    def recent_games(self, n) -> list[str]:
        """The n most recently played games (then the rest by name), for the Start and tray menus."""
        return sorted(self.all_games, key=lambda g: (-(self.stats_all.get(g, {}).get("last_played") or 0),
                                                     g.lower()))[:n]

    def pc_stats(self) -> list[dict]:
        """Every PC's playtime, this one last: [{"device_id", "device", "games": {game: {seconds, last_played,
        days?}}, "me": bool}]."""
        d = self.settings.data
        mine = {"device_id": d["device_id"], "device": d.get("device_name") or "This PC",
                "games": d.get("my_stats", {}), "me": True}
        return [dict(f, me=False) for f in self.other_pcs] + [mine]

    def load_play_history(self, weeks, done):
        """Every PC's per-day playtime for the last `weeks` weeks, loaded in the background (the other PCs' is in
        their playtime files). done([(game, {date: seconds}), …], error or None) is called on the Tk thread."""
        first = dt.datetime.combine(dt.date.today() - dt.timedelta(weeks=weeks), dt.time()).timestamp()
        mine = [(g, st.get("days")) for g, st in self.settings.data.get("my_stats", {}).items() if st.get("days")]
        b, dev, result = self.backend, self.settings.data["device_id"], {}

        def work():
            try:
                others = b.read_play_history(first, dev) if b is not None else []
                result["h"] = mine + [(e["game"], e["days"]) for e in others]
            except Exception as ex:
                result.update(h=mine, error=ex)
                self.log_ts(f"Couldn't load the other PCs' playtime history: {ex}")
        threading.Thread(target=work, daemon=True).start()

        def check():
            if "h" in result:
                done(result["h"], result.get("error"))
            else:
                self.after(150, check)
        check()

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
        self.other_pcs = others                 # each PC's totals, for the stats window
        self.stats_all = aggregate_stats(others + [{"games": mine}])
        self.settings.save()
        self.resort()
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
        add_session(m.setdefault("days", {}), now, seconds)
        a = self.stats_all.setdefault(g, {"seconds": 0, "last_played": 0})
        a["seconds"] += seconds
        a["last_played"] = now
        self.settings.save()
        self.resort()

    def play_current(self):
        if self.game in self.sessions:
            if self.confirm(APP_TITLE, f"{self.game} is still being tracked.\n\nHas the game closed? "
                            "Choose Yes to stop tracking now (playtime is saved and saves are uploaded)."):
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

    def launch_command(self, g):
        """(program, arguments) that start the game on this PC, or None if what's needed isn't set or found.
        A game set to run with an emulator starts the emulator with its ROM (see core/emulators.py)."""
        gs = self.settings.data["games"].get(g, {})
        if gs.get("emulator"):
            prof = self.settings.data.get("emulators", {}).get(gs["emulator"])
            if not prof or not Path(prof.get("exe") or "").is_file() or not Path(gs.get("rom") or "").is_file():
                return None
            return prof["exe"], emulators.launch_args(prof, gs["rom"], gs.get("args", ""))
        exe = gs.get("exe")
        return (exe, gs.get("args", "")) if exe and Path(exe).exists() else None

    def _emulator_problem(self, g):
        """What's missing to start a game that runs with an emulator (None if it doesn't use one)."""
        gs = self.settings.data["games"].get(g, {})
        name = gs.get("emulator")
        if not name:
            return None
        prof = self.settings.data.get("emulators", {}).get(name)
        if not prof:
            return f"{g} is set to run with the emulator “{name}”, which isn't set up on this PC."
        if not Path(prof.get("exe") or "").is_file():
            return f"The emulator “{name}” wasn't found:\n{prof.get('exe') or '(no program set)'}"
        if not Path(gs.get("rom") or "").is_file():
            return (f"{g}'s ROM wasn't found:\n{gs['rom']}" if gs.get("rom")
                    else f"Choose {g}'s ROM first (its Game tab → ROM).")
        return None

    def play(self, g):
        if not g or self.busy or g in self.sessions:
            return
        gs = self.settings.game(g)
        problem = self._emulator_problem(g)
        if problem:
            self.tell(APP_TITLE, problem + "\n\nSet it on the game's Game tab (emulators: Settings → Emulators…).",
                      "warning")
            return
        exe = gs.get("exe")
        if not gs.get("emulator") and (not exe or not Path(exe).exists()):
            if exe:
                self.tell(APP_TITLE, f"The executable for {g} wasn't found:\n{exe}", "warning")
            if not self.pick_exe(g):
                return
        if not gs.get("local_path") and gs.get("auto_sync", True) and self.backend is not None \
                and not gs.get("find_declined") and not gs.get("emulator"):
            # no save folder here yet: find it first, so this PC starts from the saves in the cloud
            # (not for emulated games: Ludusavi's list is of PC games, and a PC port's saves aren't these)
            self.find_saves(g, lambda found: self.play(g) if found else self._launch(g))
            return
        if gs.get("local_path") and gs.get("auto_sync", True):
            if self.backend is None:
                if not self.confirm(APP_TITLE, "Not connected to the cloud, so saves can't be synced.\n\n"
                                    "Play anyway?"):
                    return
                self._launch(g)
            else:
                self.auto_sync(g, "before", lambda ok: self._launch(g) if ok else None)
        else:
            self._launch(g)

    def _launch(self, g):
        """Start the game, after its "before launching" command (if it has one) has run."""
        before = self.settings.data["games"].get(g, {}).get("before_cmd", "").strip()
        if not before:
            self._begin(g)
            return
        program, _ = self.launch_command(g) or (None, "")
        env, folder = commands.game_env(g, program), commands.start_folder(program)
        self.log(f"{g}: running its command before launching: {before}")
        self.when_idle(lambda: self.run_bg(f"Before launching {g}", lambda: commands.run(before, folder, env),
                                           lambda res: self._before_done(g, res)))

    def _before_done(self, g, res):
        if res.ok:
            self.log(f"{g}: the command before launching finished")
        else:
            self.log(f"{g}: the command before launching {res.problem()}")
            self.show_window()
            if not self.confirm(APP_TITLE, f"The command to run before {g} starts {res.problem()}\n\n"
                                           f"Command: {res.command}\n\nPlay anyway?"):
                return
        if g in self.all_games and g not in self.sessions:
            self._begin(g)

    def _begin(self, g):
        self._start_session(g)
        if not self.fs_on:          # fullscreen mode stays up behind the game, like a console's home screen
            self.after(400, self.minimize)

    def _run_after_command(self, g, seconds, program):
        """The game's "after it closes" command: in the background, so saving and syncing don't wait for it."""
        after = self.settings.data["games"].get(g, {}).get("after_cmd", "").strip()
        if not after:
            return
        env, folder = commands.game_env(g, program, seconds), commands.start_folder(program)
        self.log(f"{g}: running its command after the game: {after}")

        def work():
            res = commands.run(after, folder, env)
            self.log_ts(f"{g}: the command after the game finished" if res.ok
                        else f"{g}: the command after the game {res.problem()}")
        threading.Thread(target=work, daemon=True).start()

    def _start_session(self, g, attach_started=None):
        exe, args = self.launch_command(g)
        sess = launcher.GameSession(g, exe, args,
                                    lambda game, secs, err: self.q.put(("game_end", game, secs, err)),
                                    attach_started=attach_started)
        self.sessions[g] = sess
        self.refresh_tray_menu()
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
                # not games run by an emulator: its program running doesn't say which game it is
                exes = {launcher.norm_exe(gs["exe"]): g
                        for g, gs in list(self.settings.data.get("games", {}).items())
                        if g in self.all_games and g not in self.sessions and not gs.get("emulator")
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
        sess = self.sessions.pop(g, None)
        if sess is not None and not sess.attach_started and g in self.all_games:     # only games Play started
            self._run_after_command(g, seconds, (self.launch_command(g) or (None,))[0])
        self.refresh_tray_menu()
        self.set_tray_text(f"playing {', '.join(self.sessions)}" if self.sessions else "")
        if not self.sessions:
            self.task_game.pack_forget()
        else:
            self.task_game.configure(text=f"▶ {', '.join(self.sessions)}")
        if self.fs_on and not self.sessions:
            self.show_window()      # back to fullscreen mode when the game closes
        if err:
            self.show_window()
            self.tell(APP_TITLE, f"Couldn't start {g}:\n{err}", "error")
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
        def failed(ex):
            if moment == "before":
                self.show_window()
                then(self.confirm(APP_TITLE, f"Couldn't check the cloud saves for {g}:\n{ex}\n\nPlay anyway?"))
            else:
                self.show_window()
                self.tell(APP_TITLE, f"Couldn't upload the saves for {g}:\n{ex}\n\n"
                          "Open the game and press Sync up when you're back online.", "warning")
                then(False)

        def checked(res):
            cfg, local, cloud = res
            diff = self._diff(g, cfg, local, cloud)
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
                choice = self.ask_conflict(g, diff, moment)
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
            roots = self._roots(g, cfg)
            self.run_bg(f"Sync {direction}: {g}", lambda: self._do_sync(g, roots, plan),
                        lambda r: (self._after_sync(g, direction, r, quiet=True), then(True)), failed=failed)

        self.run_bg(f"Checking saves: {g}", lambda: self._scan(g), checked, failed=failed)
