"""Storage on Google Drive through the Drive API."""
from __future__ import annotations

import io
import json
import os
from datetime import datetime
from pathlib import Path

from .. import CLOUD_ROOT, LEGACY_CLOUD_ROOT
from ..core.scan import FileInfo
from ..core.util import TMP_SUFFIX, safe_name
from ..paths import APP_HOME, app_dir
from . import oauth_client
from .common import (ART_JSON, ART_SUB, CONFIG_NAME, INFO_JSON, LEGACY_ART_DIR, LEGACY_STATS_DIR, PLAYTIME_SUB,
                     _group_playtime, _playtime_entry, _replace)

FOLDER_MIME = "application/vnd.google-apps.folder"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]   # only files this app creates


def find_client_config():
    """The OAuth client: built-in first, else a credentials.json next to the exe/app or in the data folder."""
    if oauth_client.CLIENT_ID and oauth_client.CLIENT_SECRET:
        return {"installed": {
            "client_id": oauth_client.CLIENT_ID, "client_secret": oauth_client.CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]}}
    for p in (APP_HOME / "credentials.json", app_dir() / "credentials.json"):
        if p.is_file():
            return json.loads(p.read_text("utf-8"))
    return None


def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


class DriveBackend:
    """Talks to Google Drive directly.

    Layout in My Drive:
        MareSaveSync/<game>/        one folder per game (appProperty ssRemoved=1 once removed from the library)
            savesync.json           shared game config (exclusions)
            info.json               game info (name, description, …)
            <relative/path.dat>     each save file; its name is its relative path
            art/                    art.json + the cover, banner and logo images
            playtime/<pc id>.json   this game's playtime on one PC (also in its appProperties, so all
                                    playtime is read with a single query)
    """

    kind = "gdrive"

    def __init__(self, client_config, token_path, interactive=True):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as ex:
            raise RuntimeError("Google libraries missing. Run:  pip install -r requirements.txt") from ex

        token_path = Path(token_path)
        creds = None
        if token_path.is_file():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            if not creds or not creds.valid:
                if not interactive:
                    raise PermissionError("Not signed in to Google.")
                if not client_config:
                    raise RuntimeError("This copy of Mare Save Sync has no Google client ID built in. "
                                       "See README → Google sign-in setup.")
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                creds = flow.run_local_server(
                    port=0, prompt="select_account consent",
                    success_message="Signed in to Mare Save Sync. You can close this tab and go back to the app.")
            token_path.write_text(creds.to_json(), "utf-8")

        self.svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.root_id = self._find_root()
        self._games: dict[str, str] = {}          # every game folder, removed ones included
        self._removed: set[str] = set()
        self._files: dict[str, dict[str, str]] = {}
        self._config_ids: dict[str, str | None] = {}
        self._info_ids: dict[str, str | None] = {}
        self._subs: dict[tuple, str] = {}         # (game, "art"/"playtime") -> folder id
        self._art_ids: dict[str, dict[str, str]] = {}
        self._pt_ids: dict[tuple, str] = {}       # (game, device) -> file id
        self._pt_seen: dict[tuple, tuple] = {}    # (game, device) -> (seconds, last_played) in the cloud

    def describe(self) -> str:
        try:
            about = self.svc.about().get(fields="user(emailAddress)").execute()
            return f"Google Drive · {about['user']['emailAddress']}"
        except Exception:
            return "Google Drive"

    # ---------------------------------------------------------- low level
    def _list(self, q, fields="id,name,size,md5Checksum,modifiedTime,appProperties", order=None):
        items, token = [], None
        while True:
            r = self.svc.files().list(q=q, spaces="drive", pageSize=1000, pageToken=token,
                                      orderBy=order, fields=f"nextPageToken, files({fields})").execute()
            items += r.get("files", [])
            token = r.get("nextPageToken")
            if not token:
                return items

    def _find_folder(self, name, parent, create=False, props=None):
        found = self._list(f"name = '{_q(name)}' and mimeType = '{FOLDER_MIME}' and "
                           f"'{parent}' in parents and trashed = false", "id")
        if found:
            return found[0]["id"]
        if not create:
            return None
        body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent]}
        if props:
            body["appProperties"] = props
        return self.svc.files().create(body=body, fields="id").execute()["id"]

    def _find_root(self):
        """My Drive/MareSaveSync, renaming an older version's My Drive/SaveSync to it if that's all there is."""
        fid = self._find_folder(CLOUD_ROOT, "root")
        if fid:
            return fid
        old = self._find_folder(LEGACY_CLOUD_ROOT, "root")
        if old:
            self.svc.files().update(fileId=old, body={"name": CLOUD_ROOT}).execute()
            return old
        return self._find_folder(CLOUD_ROOT, "root", create=True)

    def _get_bytes(self, file_id) -> bytes:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaIoBaseDownload
        buf = io.BytesIO()
        try:
            dl = MediaIoBaseDownload(buf, self.svc.files().get_media(fileId=file_id))
            done = False
            while not done:
                _, done = dl.next_chunk()
        except HttpError as ex:
            if ex.resp.status != 416:      # 416 = empty file
                raise
        return buf.getvalue()

    @staticmethod
    def _json_media(data):
        from googleapiclient.http import MediaIoBaseUpload
        return MediaIoBaseUpload(io.BytesIO(json.dumps(data, indent=2).encode("utf-8")),
                                 mimetype="application/json")

    def _gid(self, game) -> str:
        if game not in self._games:
            self.list_games()
        if game not in self._games:
            raise KeyError(f"Game {game!r} not found on Google Drive")
        return self._games[game]

    def _fid(self, game, rel) -> str:
        if rel not in self._files.get(game, {}):
            self.list_files(game)
        try:
            return self._files[game][rel]
        except KeyError:
            raise KeyError(f"{rel!r} not found in cloud for {game!r}") from None

    def _config_id(self, game):
        if game not in self._config_ids:
            gid = self._gid(game)
            items = self._list(f"'{gid}' in parents and trashed = false and "
                               "appProperties has { key='ssKind' and value='config' }", "id")
            self._config_ids[game] = items[0]["id"] if items else None
        return self._config_ids[game]

    def _sub(self, game, kind, create=False):
        """The game's art/ or playtime/ folder id (None if it doesn't exist and create is False)."""
        if (game, kind) not in self._subs:
            fid = self._find_folder(kind, self._gid(game), create, {"ssKind": f"{kind}-dir"})
            if not fid:
                return None
            self._subs[(game, kind)] = fid
        return self._subs[(game, kind)]

    # --------------------------------------------------------------- games
    def list_games(self):
        items = self._list(f"'{self.root_id}' in parents and mimeType = '{FOLDER_MIME}' "
                           "and trashed = false", "id,name,appProperties")
        items = [it for it in items if not it["name"].startswith(".")]
        self._games = {it["name"]: it["id"] for it in items}
        self._removed = {it["name"] for it in items if (it.get("appProperties") or {}).get("ssRemoved") == "1"}
        return sorted((g for g in self._games if g not in self._removed), key=str.lower)

    def create_game(self, name):
        if name in self.list_games():
            raise ValueError(f"A game called {name!r} already exists.")
        if name in self._removed:                 # added again: bring back its playtime, art and exclusions
            self.svc.files().update(fileId=self._games[name], body={"appProperties": {"ssRemoved": None}}).execute()
            self._removed.discard(name)
            return
        fid = self.svc.files().create(
            body={"name": name, "mimeType": FOLDER_MIME, "parents": [self.root_id]},
            fields="id").execute()["id"]
        self._games[name] = fid
        self._files[name] = {}
        self._config_ids[name] = None
        self.set_game_config(name, {"excludes": []})

    def delete_game(self, name, purge=False):
        """Hides the game from the library, keeping everything. purge: move its whole folder (saves, artwork,
        playtime, exclusions) to the Drive trash instead."""
        gid = self._gid(name)
        if purge:
            self.svc.files().update(fileId=gid, body={"trashed": True}).execute()
            self._games.pop(name, None)
            self._removed.discard(name)
            for cache in (self._files, self._config_ids, self._info_ids, self._art_ids):
                cache.pop(name, None)
            for cache in (self._subs, self._pt_ids, self._pt_seen):     # keyed (game, …)
                for k in [k for k in cache if k[0] == name]:
                    del cache[k]
            return
        self.svc.files().update(fileId=gid, body={"appProperties": {"ssRemoved": "1"}}).execute()
        self._removed.add(name)

    def get_game_config(self, name):
        cid = self._config_id(name)
        cfg = json.loads(self._get_bytes(cid).decode("utf-8") or "{}") if cid else {}
        cfg.setdefault("excludes", [])
        return cfg

    def set_game_config(self, name, cfg):
        media = self._json_media(cfg)
        cid = self._config_id(name)
        if cid:
            self.svc.files().update(fileId=cid, media_body=media).execute()
        else:
            self._config_ids[name] = self.svc.files().create(
                body={"name": CONFIG_NAME, "parents": [self._gid(name)],
                      "appProperties": {"ssKind": "config"}},
                media_body=media, fields="id").execute()["id"]

    # --------------------------------------------------------------- files
    def list_files(self, name):
        gid = self._gid(name)
        items = self._list(f"'{gid}' in parents and trashed = false and mimeType != '{FOLDER_MIME}'",
                           order="modifiedTime desc")
        out, ids = {}, {}
        for it in items:
            ap = it.get("appProperties") or {}
            if ap.get("ssFile") != "1":
                continue
            rel = it["name"]
            if rel in out:               # duplicate (older); newest already kept
                continue
            mtime = float(ap.get("ssMtime") or 0)
            if not mtime and it.get("modifiedTime"):
                mtime = datetime.fromisoformat(it["modifiedTime"].replace("Z", "+00:00")).timestamp()
            out[rel] = FileInfo(rel, int(it.get("size", 0)), it.get("md5Checksum", ""), mtime)
            ids[rel] = it["id"]
        self._files[name] = ids
        return out

    def upload(self, name, rel, src, mtime):
        from googleapiclient.http import MediaIoBaseUpload
        size = os.path.getsize(src)
        props = {"ssFile": "1", "ssMtime": repr(float(mtime))}
        ids = self._files.setdefault(name, {})
        with open(src, "rb") as fh:
            media = MediaIoBaseUpload(fh, mimetype="application/octet-stream",
                                      resumable=size > 5 * 1024 * 1024, chunksize=5 * 1024 * 1024)
            if rel in ids:
                self.svc.files().update(fileId=ids[rel], body={"appProperties": props},
                                        media_body=media, fields="id").execute()
            else:
                ids[rel] = self.svc.files().create(
                    body={"name": rel, "parents": [self._gid(name)], "appProperties": props},
                    media_body=media, fields="id").execute()["id"]

    def download(self, name, rel, dest):
        dest = Path(dest)
        tmp = dest.with_name(dest.name + TMP_SUFFIX)
        tmp.write_bytes(self._get_bytes(self._fid(name, rel)))
        _replace(tmp, dest)

    def delete(self, name, rel):
        fid = self._fid(name, rel)
        self.svc.files().update(fileId=fid, body={"trashed": True}).execute()   # recoverable
        self._files[name].pop(rel, None)

    def read_bytes(self, name, rel):
        return self._get_bytes(self._fid(name, rel))

    def clear_saves(self, name):
        self.list_files(name)
        for fid in list(self._files.get(name, {}).values()):
            self.svc.files().update(fileId=fid, body={"trashed": True}).execute()
        self._files[name] = {}

    # ------------------------------------------------------------ playtime
    def read_all_stats(self):
        self.list_games()
        by_id = {fid: g for g, fid in self._games.items()}
        dirs = {}                                   # playtime folder id -> game
        for it in self._list("mimeType = '" + FOLDER_MIME + "' and trashed = false and "
                             "appProperties has { key='ssKind' and value='playtime-dir' }", "id,parents"):
            game = next((by_id[p] for p in it.get("parents", []) if p in by_id), None)
            if game:
                dirs[it["id"]] = game
                self._subs[(game, PLAYTIME_SUB)] = it["id"]
        entries = []
        for it in self._list("trashed = false and appProperties has { key='ssKind' and value='playtime' }",
                             "id,parents,appProperties"):
            game = next((dirs[p] for p in it.get("parents", []) if p in dirs), None)
            if not game:
                continue
            ap = it.get("appProperties") or {}
            e = {"game": game, "device_id": ap.get("ssDevice"), "device": ap.get("ssDeviceName", ""),
                 "seconds": float(ap.get("ssSeconds") or 0), "last_played": float(ap.get("ssLast") or 0)}
            entries.append(e)
            self._pt_ids[(game, e["device_id"])] = it["id"]
            self._pt_seen[(game, e["device_id"])] = (e["seconds"], e["last_played"])
        legacy = []
        old = self._find_folder(LEGACY_STATS_DIR, self.root_id)
        for it in self._list(f"'{old}' in parents and trashed = false", "id") if old else []:
            try:
                legacy.append(json.loads(self._get_bytes(it["id"]).decode("utf-8")))
            except ValueError:
                pass
        return _group_playtime(entries, legacy)

    def write_stats(self, device_id, doc):
        """Writes this PC's playtime into each game's playtime/ folder (only games that changed)."""
        for game, st in (doc.get("games") or {}).items():
            e = _playtime_entry(game, device_id, doc, st)
            key = (game, device_id)
            if self._pt_seen.get(key) == (e["seconds"], e["last_played"]):
                continue
            try:
                folder = self._sub(game, PLAYTIME_SUB, create=True)
            except KeyError:                       # no folder for it (e.g. removed by an older version)
                continue
            props = {"ssKind": "playtime", "ssDevice": device_id, "ssDeviceName": e["device"].encode()[:96].decode(errors="ignore"),
                     "ssSeconds": repr(float(e["seconds"])), "ssLast": repr(float(e["last_played"]))}
            media = self._json_media(e)
            if key not in self._pt_ids:
                found = self._list(f"'{folder}' in parents and name = '{_q(device_id)}.json' and trashed = false",
                                   "id")
                if found:
                    self._pt_ids[key] = found[0]["id"]
            if key in self._pt_ids:
                self.svc.files().update(fileId=self._pt_ids[key], body={"appProperties": props},
                                        media_body=media).execute()
            else:
                self._pt_ids[key] = self.svc.files().create(
                    body={"name": f"{device_id}.json", "parents": [folder], "appProperties": props},
                    media_body=media, fields="id").execute()["id"]
            self._pt_seen[key] = (e["seconds"], e["last_played"])

    # ------------------------------------------------------------- artwork
    def _art_folder(self, game, create=False):
        fid = self._sub(game, ART_SUB)
        if not fid:                                 # move an older .mss-art/<game>/ in, if there is one
            old_root = self._find_folder(LEGACY_ART_DIR, self.root_id)
            old = self._find_folder(safe_name(game), old_root) if old_root else None
            if old:
                self.svc.files().update(fileId=old, addParents=self._gid(game), removeParents=old_root,
                                        body={"name": ART_SUB, "appProperties": {"ssKind": "art-dir"}}).execute()
                self._subs[(game, ART_SUB)] = fid = old
            elif create:
                fid = self._sub(game, ART_SUB, create=True)
        return fid

    def _art_list(self, game) -> dict[str, str]:
        fid = self._art_folder(game)
        items = self._list(f"'{fid}' in parents and trashed = false", "id,name") if fid else []
        self._art_ids[game] = {it["name"]: it["id"] for it in items}
        return self._art_ids[game]

    def _art_put(self, game, fname, media):
        ids = self._art_ids.get(game)
        if ids is None:
            ids = self._art_list(game)
        if fname in ids:
            self.svc.files().update(fileId=ids[fname], media_body=media).execute()
        else:
            ids[fname] = self.svc.files().create(
                body={"name": fname, "parents": [self._art_folder(game, create=True)]},
                media_body=media, fields="id").execute()["id"]

    def read_art(self, game):
        fid = self._art_list(game).get(ART_JSON)
        if not fid:
            return None
        try:
            return json.loads(self._get_bytes(fid).decode("utf-8")).get("art")
        except ValueError:
            return None

    def write_art(self, game, art):
        self._art_put(game, ART_JSON, self._json_media({"name": game, "art": art}))

    def art_files(self, game):
        return set(self._art_list(game)) - {ART_JSON}

    def upload_art_file(self, game, fname, src):
        from googleapiclient.http import MediaFileUpload
        self._art_put(game, fname, MediaFileUpload(str(src), mimetype="application/octet-stream"))

    def download_art_file(self, game, fname, dest):
        ids = self._art_ids.get(game) or self._art_list(game)
        dest = Path(dest)
        tmp = dest.with_name(dest.name + TMP_SUFFIX)
        tmp.write_bytes(self._get_bytes(ids[fname]))
        _replace(tmp, dest)

    def delete_art_file(self, game, fname):
        ids = self._art_ids.get(game) or self._art_list(game)
        if fname in ids:
            self.svc.files().update(fileId=ids.pop(fname), body={"trashed": True}).execute()

    # ----------------------------------------------------------- game info
    def _info_id(self, game):
        if game not in self._info_ids:
            items = self._list(f"'{self._gid(game)}' in parents and trashed = false and "
                               "appProperties has { key='ssKind' and value='info' }", "id")
            self._info_ids[game] = items[0]["id"] if items else None
        return self._info_ids[game]

    def read_info(self, game):
        fid = self._info_id(game)
        if not fid:
            return None
        try:
            return json.loads(self._get_bytes(fid).decode("utf-8")).get("info")
        except ValueError:
            return None

    def write_info(self, game, info):
        media = self._json_media({"name": game, "info": info})
        fid = self._info_id(game)
        if fid:
            self.svc.files().update(fileId=fid, media_body=media).execute()
        else:
            self._info_ids[game] = self.svc.files().create(
                body={"name": INFO_JSON, "parents": [self._gid(game)], "appProperties": {"ssKind": "info"}},
                media_body=media, fields="id").execute()["id"]
