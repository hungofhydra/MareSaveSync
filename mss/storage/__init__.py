"""Storage backends for Mare Save Sync (top folder MareSaveSync/ in My Drive or the synced folder).

Both expose the same methods:
    describe() list_games() create_game(name) delete_game(name, purge=False)
    get_game_config(name) set_game_config(name, cfg)
    list_files(name) -> {rel: FileInfo}
    upload(name, rel, src_path, mtime) download(name, rel, dest_path)
    delete(name, rel) read_bytes(name, rel)
    read_all_stats() write_stats(device_id, doc)
    read_art(name) write_art(name, art)
    art_files(name) upload_art_file(name, fname, src) download_art_file(name, fname, dest)
    delete_art_file(name, fname)
    read_info(name) write_info(name, info)

Everything about a game lives in its own folder: the saves, savesync.json, an art/ folder (art.json + images)
and a playtime/ folder (one file per PC). Removing a game just hides the folder, so everything comes back if
the game is added again; removing with purge deletes the folder.
"""
from .common import Locked
from .folder import FolderBackend
from .gdrive import DriveBackend, find_client_config

__all__ = ["DriveBackend", "FolderBackend", "Locked", "find_client_config"]
