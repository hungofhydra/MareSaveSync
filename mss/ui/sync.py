"""Manual Sync up / Sync down, and checking in the background whether each game is in sync."""
from __future__ import annotations

import time

from ..core import folders
from ..core.diff import EXCLUDED, baseline
from ..core.sync import execute_plan, make_plan
from ..core.util import human_size

CHECK_EVERY_MS = 30 * 60 * 1000         # another PC may upload newer saves while this one waits in the tray


class SyncMixin:
    """Part of App (see ui/app.py)."""

    # ------------------------------------------------- is each game in sync? (library badges)
    def check_states(self):
        """Check every game in the background: in sync, newer in the cloud, not uploaded or a conflict.
        Games whose save folder isn't set here yet pick up the place another PC shared (see savefind.py)."""
        if self.backend is not None and self.all_games:
            self.state_q.put(list(self.all_games))

    def _periodic_state_check(self):
        self.check_states()
        self.after(CHECK_EVERY_MS, self._periodic_state_check)

    def _state_worker(self):
        while True:
            games = self.state_q.get()
            newer = []
            for g in games:
                if self.backend is None or g in self.sessions:
                    continue                # a game being played is checked when it closes
                started = time.time()
                try:
                    cfg, local, cloud = self._scan(g)
                except Exception as ex:
                    self.log_ts(f"Checking the saves of {g} failed: {ex}")
                    continue
                if not (self._local_path(g) or folders.MAIN in self._shared_folders(g, cfg)):
                    continue                # no save folder on this PC: nothing to compare
                state = self._state_from(self._diff(g, cfg, local, cloud))
                if state == "cloud_newer" and self.settings.data["games"].get(g, {}).get("state") != state:
                    newer.append(g)
                self.q.put(("state", g, state, started))
            if newer:
                self.q.put(("cloud_newer", newer))

    def _announce_cloud_newer(self, games):
        games = [g for g in games if self.settings.data["games"].get(g, {}).get("state") == "cloud_newer"]
        if len(games) == 1:
            self.note(f"{games[0]}: newer saves in the cloud — Play or Sync down gets them")
        elif games:
            self.note(f"{len(games)} games have newer saves in the cloud: {', '.join(games)}")

    def sync(self, direction):
        game = self.game
        if not self._local_path():
            return

        def after_scan(res):
            self._apply_scan(game, res)
            roots = self._roots(game, res[0])
            missing = [p for p in roots.values() if p and not folders.root_exists(p)]
            if direction == "up" and missing:
                self.tell("Sync up", "This save folder or file does not exist:\n" + "\n".join(missing), "error")
                return
            plan = make_plan(self.diff, direction, self.mirror_var.get())
            if plan.empty:
                self.tell("SaveSync", "Already in sync — nothing to do.")
                return
            if not self.confirm(f"Sync {direction}", self._plan_text(game, plan), warn=bool(plan.at_risk)):
                return
            self.run_bg(f"Syncing {direction}", lambda: self._do_sync(game, roots, plan),
                        lambda r: self._after_sync(game, direction, r))
        self.run_bg(f"Comparing {game}", lambda: self._scan(game), after_scan)

    def _plan_text(self, game, plan):
        up = plan.direction == "up"
        n = lambda k: f"{k} file" + ("" if k == 1 else "s")  # noqa: E731
        size = sum((e.local if up else e.cloud).size for e in plan.transfer)
        lines = [f"{game}:  {'this PC  →  cloud' if up else 'cloud  →  this PC'}", ""]
        if plan.transfer:
            lines.append(f"• {'Upload' if up else 'Download'} {n(len(plan.transfer))} ({human_size(size)})")
        if plan.delete:
            lines.append(f"• Delete {n(len(plan.delete))} {'from the cloud' if up else 'on this PC'}")
        src_count = sum(1 for e in self.diff if e.status != EXCLUDED and (e.local if up else e.cloud))
        if src_count == 0 and plan.delete:
            lines += ["", f"⚠ The {'save folder on this PC' if up else 'cloud'} is EMPTY. "
                      f"This will delete every file on the {'cloud' if up else 'PC'} side."]
        if plan.at_risk:
            where = "in the cloud (probably from another PC)" if up else "on this PC"
            lines += ["", f"⚠ These were changed {where} since this PC last synced, and will be overwritten:"]
            lines += [f"     {e.path}" for e in plan.at_risk[:8]]
            if len(plan.at_risk) > 8:
                lines.append(f"     …and {len(plan.at_risk) - 8} more")
        if not up and (plan.delete or any(e.local for e in plan.transfer)):
            lines += ["", "Local files that get replaced or deleted are zipped to a backup first."]
        if up and plan.delete and self.backend.kind == "gdrive":
            lines += ["", "Deleted cloud files go to the Google Drive trash."]
        lines += ["", "Make sure the game is closed. Continue?"]
        return "\n".join(lines)

    def _do_sync(self, game, roots, plan):
        backup = execute_plan(plan, self.backend, game, roots, log=self.log_ts)
        res = self._scan(game)
        return backup, res

    def _after_sync(self, game, direction, r, quiet=False):
        backup, res = r
        cfg, local, cloud = res
        g = self.settings.game(game)
        g["base"] = baseline(local, cloud, cfg.get("excludes", []))
        g["last_sync"] = {"direction": direction, "time": time.time()}
        self.settings.save()
        self._set_state(game, self._state_from(self._diff(game, cfg, local, cloud)))
        if game == self.game:
            self._render_header()
            self._apply_scan(game, res)
        if quiet:
            self.note(f"{game}: saves synced {'up' if direction == 'up' else 'down'}"
                      + (" (backup made)" if backup else ""))
            return
        self.log(f"{game}: sync {direction} finished")
        msg = f"Sync {direction} finished."
        if backup:
            msg += f"\n\nBackup of replaced local files:\n{backup}"
        self.tell("SaveSync", msg)
