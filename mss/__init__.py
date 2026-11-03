"""Mare Save Sync: a small game launcher that keeps saves, playtime and artwork in sync across PCs."""

APP_TITLE = "Mare Save Sync"
VERSION = "3.0"
try:
    from ._build import BUILD           # the release's build number, written by build.py
except ImportError:
    BUILD = 0                           # running from source, or built without a build number
APP_NAME = "SaveSync"      # local data folder in %APPDATA% (kept from before the rename)
CLOUD_ROOT = "MareSaveSync"         # top folder in My Drive / the synced folder
LEGACY_CLOUD_ROOT = "SaveSync"      # older versions' top folder; renamed to CLOUD_ROOT when found
