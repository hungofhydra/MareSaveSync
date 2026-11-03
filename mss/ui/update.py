"""Updates: checking GitHub for a newer release now and then, and installing it (see updater.py)."""
from __future__ import annotations

import threading

from .. import APP_TITLE, updater
from ..core.util import human_size

CHECK_EVERY_MS = 12 * 3600 * 1000      # the app can stay in the tray for days


class UpdateMixin:
    """Part of App (see ui/app.py)."""

    update_info: dict | None = None

    def _auto_check_updates(self):
        """Check in the background; an update found shows the Update button (nothing is installed by itself)."""
        if updater.can_update() and self.settings.data.get("check_updates", True):
            def work():
                try:
                    self.q.put(("update", updater.check()))
                except Exception as ex:
                    self.log_ts(f"Couldn't check for updates: {ex}")
            threading.Thread(target=work, daemon=True).start()
        self.after(CHECK_EVERY_MS, self._auto_check_updates)

    def _on_update_info(self, info):
        if not info or (self.update_info and self.update_info["tag"] == info["tag"]):
            return
        self.update_info = info
        self.update_btn.configure(text=f"Update to {info['tag']}")
        self.update_btn.pack(side="right", padx=(4, 0), before=self.settings_btn)
        self.note(f"{APP_TITLE} {info['tag']} is available")
        s = self.settings.data
        if s.get("update_notified") != info["tag"]:     # once per version, e.g. while it waits in the tray
            self.notify(f"{APP_TITLE} {info['tag']} is available. Open the app to update.")
            s["update_notified"] = info["tag"]
            self.settings.save()

    def check_updates_now(self):
        """Help → Check for updates…"""
        if not updater.can_update():
            self.tell("Check for updates", f"This is {APP_TITLE} {updater.current_text()}, "
                      + ("run from source: update it with git pull." if not updater.FROZEN
                         else "built on this PC, so it doesn't know which release it is. Download the latest "
                              f"release from github.com/{updater.REPO}/releases."))
            return

        def done(info):
            if info:
                self._on_update_info(info)
                self.install_update()
            else:
                self.tell("Check for updates", f"You have the latest version ({updater.current_text()}).")
        self.run_bg("Checking for updates", updater.check, done)

    def install_update(self):
        info = self.update_info
        if not info:
            return
        if self.sessions:
            self.tell("Update", f"Close {', '.join(self.sessions)} first: the app has to restart to update.")
            return
        if self.busy:
            self.tell("Update", "Please wait for the current task to finish.")
            return
        size = f" ({human_size(info['size'])})" if info.get("size") else ""
        if not self.confirm("Update", f"Update {APP_TITLE} from {updater.current_text()} to {info['tag']}?\n\n"
                            f"The update{size} is downloaded, then the app closes, updates itself and starts "
                            "again. Your settings, saves and artwork aren't touched."):
            return
        last = [-1]

        def progress(done, total):
            pct = done * 100 // total if total else 0
            if pct // 5 != last[0]:           # every 5 %
                last[0] = pct // 5
                self.q.put(("status", f"Downloading update… {pct}%"))

        def finish(new):
            self.log(f"Installing {info['tag']} — restarting")
            try:
                updater.start_finish(new, ["--fullscreen"] if self.fs_on else [])
            except OSError as ex:
                self.tell("Update failed", f"Couldn't start the update:\n{ex}", "error")
                return
            self.destroy()
        self.run_bg("Downloading update", lambda: updater.download(info, progress), finish)
