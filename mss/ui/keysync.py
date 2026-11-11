"""Settings → Sync up / Sync down for the SteamGridDB and IGDB keys: they go to the cloud, and come back on another PC,
only when one of those buttons is pressed. The rules are in core/keys.py."""
from __future__ import annotations

from .. import APP_TITLE
from ..core import keys


class KeySyncMixin:
    """Part of App (see ui/app.py)."""

    def keys_up(self):
        """Put this PC's keys in the cloud (keys the cloud has that this PC lacks stay there)."""
        if self.backend is None:
            self.tell(APP_TITLE, "Connect to your storage first (Settings).")
            return
        mine = keys.set_keys(self.settings.data)
        if not mine:
            self.tell(APP_TITLE, "This PC has no SteamGridDB or IGDB key to put in the cloud yet.")
            return
        b = self.backend

        def work():
            b.write_shared(keys.merged_doc(b.read_shared(), mine))
            return mine

        self.run_bg("Sync up API keys", work, lambda sent: self.note(f"API keys in the cloud now: {keys.names(sent)}"))

    def keys_down(self, then=None):
        """Take the keys the cloud has (this PC's other keys stay). then() runs once they are saved."""
        if self.backend is None:
            self.tell(APP_TITLE, "Connect to your storage first (Settings).")
            return
        b = self.backend

        def done(found):
            if not found:
                self.tell(APP_TITLE, "The cloud has no API keys yet.\n\nOn a PC that has them, open Settings and "
                                     "press Sync up.")
                return
            d = self.settings.data
            changed = [k for k, v in found.items() if d.get(k, "") != v]
            d.update(found)
            self.settings.save()
            if not changed:
                self.note("This PC already has the keys that are in the cloud")
            else:
                self.note(f"Took the {keys.names(changed)} key{'s' if len(changed) > 1 else ''} from the cloud — "
                          "fetching artwork and game info")
                for g in self.all_games:
                    self.fetch_meta(g)
            if then:
                then()

        self.run_bg("Sync down API keys", lambda: keys.from_cloud(b.read_shared()), done)
