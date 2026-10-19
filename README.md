# Mare Save Sync

A small game launcher that keeps your saves and playtime in sync across PCs through Google Drive.

## Cover art (SteamGridDB)

1. Make a free account at steamgriddb.com, then Preferences → API → generate a key.
2. Settings → Artwork → paste the key → Save key.
3. **Add game** opens a picker after you type the name: choose which game it is (its official name and
   description are previewed, and you can use the official name in the library) and click a cover. **Skip**
   adds it with the first search result picked automatically. Games added before you set a key get that too.
4. To change it later: right-click a cover → **Game info & artwork…** — or click **Use image from file…**
   there to use your own picture as the cover.
5. The artwork and its images are saved in the cloud in the game's `art/` folder, so every PC shows the
   same art (other PCs don't even need a SteamGridDB key). Like playtime, it's kept apart from the saves:
   deleting cloud saves or removing the game doesn't erase it (only _Purge all data_ does).

## Playing

- Set the game's .exe once per PC (you're asked on first Play, or Game tab → Browse).
  Launch options go in the Game tab.
- The app treats the game as running while its process — or any program inside the game's folder — is
  running, so launchers that start the real game and exit are handled. If it ever keeps saying
  “Playing” after you quit, press **Playing…** (or Options → Game has closed) to stop tracking.
- Turn off “Sync automatically” in the Game tab for games you want to sync by hand.
- Achievements are not synced

## Install (each PC)

**Easiest:** copy the `MareSaveSync` folder to each PC — a USB stick works too — and double-click
`MareSaveSync.exe` inside it. No Python needed, nothing is installed. Windows SmartScreen may
say “Windows protected your PC” because the exe isn't code-signed — click _More info → Run anyway_.

The app is fully portable — everything stays in its folder:

```
MareSaveSync\
  MareSaveSync.exe
  _internal\        the program's runtime (Python, libraries, artwork) — nothing is unpacked to %TEMP%
  data\             created on first start: settings, Google sign-in, cached covers, backups
```

Move or copy the folder anywhere you can write to (not Program Files): if it can't write its `data` folder, it
says so and closes rather than keeping settings somewhere else. If you used an older version, its
`%APPDATA%\SaveSync` is copied into `data` on first start (the original is left as it was). The only thing
outside the folder is the optional **Start with Windows** entry; it follows the folder if you move it (it's
updated the next time you start the app). Running from source uses `%APPDATA%\SaveSync` instead.

**From source:**

1. Install Python 3.10+ from python.org (on Windows, tick “Add python.exe to PATH”; tkinter is included).
2. In this folder run:
   ```
   pip install -r requirements.txt
   python app.py
   ```
   (Use `pythonw app.py` on Windows to run without a console window.)

To build the exe yourself, double-click `build_exe.bat` (Windows, Python 3.12 installed). Both it and the
release workflow run `build.py`.

### Releases

Every push to `main`/`master` builds the app on GitHub Actions (`.github/workflows/release.yml`) and publishes a
release `v<version>.<run number>` with `MareSaveSync-…-windows.zip` — unzip it anywhere and run
`MareSaveSync\MareSaveSync.exe`. The version comes from `VERSION` in `mss/__init__.py`. Google sign-in is built
in from the repository secrets `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (Settings → Secrets and variables →
Actions); without them the release still builds, just without built-in sign-in.

### Project layout

```
app.py                  entry point (python app.py)
mss/
  paths.py              assets, exe/source folder, local data folder
  launcher.py           start a game and wait for it to close; start with Windows
  core/                 no GUI: scan.py, excludes.py, diff.py, sync.py, compare.py, playtime.py, settings.py
  storage/              cloud backends: folder.py, gdrive.py (+ oauth_client.py reading .env), common.py
  providers/            online services: sgdb.py (SteamGridDB API), steam.py (Steam store details)
  art/                  cover art: sources.py (registry), images.py (local cache)
  info/                 game info: sources.py (registry; SteamGridDB + Steam store)
  ui/
    app.py              main window, built from mixins:
    library.py  details.py  play.py  sync.py  artwork.py  info.py (About tab)
    theme.py  widgets.py  theme_art.py (banner/icon drawing)
    dialogs/            settings, metadata (game info & artwork picker), conflict, remove, diff_window
```

## Storage options

- **Google Drive** — Sign in with Google. Saves go to `My Drive/MareSaveSync/`. The app uses the `drive.file`
  permission, so it can only see files it created, not the rest of your Drive.
- **A synced folder** — e.g. your Google Drive for desktop folder `G:\My Drive`. No sign-in setup needed;
  wait for the Drive client to finish syncing before you Sync down on another PC.

## Using it

- **Add game** → name it → choose the save folder and the .exe on this PC. _Choose folder → Type or paste a path_ accepts
  things like `%USERPROFILE%\AppData\LocalLow\AcrobaticChirimenjako\SchrodingersCallAdv`
  (AppData is hidden in the normal folder picker).
- **Diff** tab shows every file: _Same_, _Different_, _Only on this PC_, _Only in cloud_, _Excluded_,
  with sizes and dates on both sides. The **Note** column says which side changed since this PC last
  synced; _⚠ Changed on both sides_ means a conflict. Double-click a file to compare its contents
  (text/JSON line diff, or a hex diff for binary saves).
- **Exclusions** tab: add a file, a folder or a pattern. Or right-click any file in the diff →
  _Exclude this file / folder / all \*.ext files_. Rules are stored with the game in the cloud, so every
  PC uses the same list. Excluded files are never uploaded, downloaded or deleted. Good first rules:
  `*.log`, `Player.log`, crash dumps, shader caches.
- **Sync up / Sync down** always rescan first and show a confirmation with what will be uploaded,
  downloaded or deleted, and warn if you're about to overwrite progress made elsewhere.
- **Mirror deletions** (on by default): makes the target exactly match the source. Turn it off to only
  add/overwrite files.

## Safety nets

- Before every Sync down, local files that will be replaced or deleted are zipped to
  `data\backups\<game>\` next to the exe (last 20 kept).
- On Google Drive, files deleted by Sync up go to the Drive trash, and Drive keeps older versions of
  overwritten files (right-click → Manage versions).
- Close the game before syncing; files the game has locked are reported in the log.

## Where things are stored

Local files are in the `data` folder next to `MareSaveSync.exe` (or `%APPDATA%\SaveSync` when running from
source — that folder keeps the original “SaveSync” name so existing settings carry over after the rename).

- This PC's settings (which folder each game uses here, sync baseline): `data\config.json`
- Google sign-in: `data\token.json` (Settings → Sign out removes it)
- Cached cover art: `data\art\`; backups: `data\backups\`
- The only thing outside the folder: **Start with Windows** adds a registry entry pointing at the exe. It's
  updated when you start the moved app; turn it off before deleting the folder.
- In the cloud, everything about a game is in its own folder `My Drive/MareSaveSync/<game>/`:
  the save files, `savesync.json` (exclusions), `info.json` (name, description, …), `art/` (artwork choice +
  images) and `playtime/` (one file per PC).
  **Remove from library** only hides the folder; add the game again with the same name and its saves,
  playtime, artwork and exclusions come back. Tick **Purge all data** in that dialog to delete the whole
  folder instead (on Google Drive it goes to the trash, so it can still be restored from there).
- Older versions used a top folder called `SaveSync`. The first time this version connects it renames that
  folder to `MareSaveSync` (nothing is copied or lost), and picks up the old `.mss-stats/` and `.mss-art/`
  data inside it. Update the app on every PC: older versions keep looking for `SaveSync`, and still show
  removed games.
