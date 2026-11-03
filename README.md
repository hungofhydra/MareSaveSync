# Mare Save Sync

A small game launcher that keeps your saves and playtime in sync across PCs through Google Drive.

## Cover art (SteamGridDB)

1. Make a free account at steamgriddb.com, then Preferences → API → generate a key.
2. Settings → Artwork → paste the key → Save key.
3. **Add game** opens a picker after you type the name: choose which game it is (its official name and
   description are previewed, and you can use the official name in the library) and click a cover. **Skip**
   adds it with the first search result picked automatically. Games added before you set a key get that too.
   The description comes from the game's Steam store page; games that aren't on Steam (Epic exclusives,
   console games you run in an emulator, …) get the one from their Wikipedia article.
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
- **View → Playtime stats…** shows your playtime on all PCs together: this week, the last 30 days and all
  time, hours per week for the last 12 weeks (a chart, or the same as a table; hover a week to see its games),
  and every game's hours on each PC with where and when it was last played. A game's Game tab also shows its
  hours on each PC. In fullscreen mode it's ☰ → **Playtime stats** (◀ ▶ pick a week to see its games), and a
  game's page shows its hours on each PC. Weekly numbers start with the first session played on this version: older playtime only
  has totals, not dates.

## Emulators

- **Set up an emulator once per PC:** Settings → Emulators… → **Add emulator…** and pick its program. The arguments
  that start a ROM are filled in for common emulators (RetroArch, Dolphin, PCSX2, DuckStation, PPSSPP, RPCS3, Cemu,
  Ryujinx, xemu, mGBA, melonDS, Azahar, Flycast, Snes9x, Mesen); `{rom}` is replaced by the game's ROM. RetroArch
  needs its core: change `CORE` in its arguments, or add one RetroArch profile per core.
- **Each game:** its Game tab → **Run with:** the emulator, then choose its **ROM**. Play starts the emulator with
  it. The emulator and ROM are set on each PC, like a game's .exe. Games run by an emulator aren't noticed when
  the emulator is started outside the app (it can't tell which game is running): start them with Play.
- **Saves in one file:** emulators often keep every game's saves in one folder (RetroArch's `saves\` has one
  `.srm` per game). Saves tab → Choose… → **Choose a single file…** syncs just that game's file. It keeps the
  name it had when first chosen in the cloud, so on another PC the file can be called something else (choose it
  there the same way, or let Sync down create it). Extra save locations (Add folder…) can be single files too.

## Fullscreen mode (handheld PCs)

A full-screen view made for an Xbox controller, like Steam Big Picture — for the ROG Ally, Legion Go and
other Windows handhelds (their built-in controls count as an Xbox controller).

- Open it with **View → Fullscreen mode**, **F11**, or Settings → Fullscreen mode → **Open Fullscreen mode**.
  Tick **Start in Fullscreen mode** (off by default) to always start in it, or start the app with `--fullscreen`.
- The selected game's art fills the screen and the library is a row of covers below it, most recently played
  first (☰ → **Sort** changes the order). **A** opens a game (Play, Sync up, Sync down, Check saves), **X** plays
  it, **Y** searches the library, **LB / RB** page through the covers, **☰** opens the menu (Add game, Desktop
  mode, Exit, …), **B** goes back or clears the search. The keyboard works too (arrows, Enter, Esc, Tab for the
  menu), and so do touch and the mouse.
- **Add game** (☰) works with the controller: type the name on the on-screen keyboard (**A** types, **X**
  deletes, **Y** is a space, **LB** is Shift, **☰** is Done), pick which game it is (needs a SteamGridDB key, see
  Cover art), pick its program from where Steam, the Epic Games Launcher or GOG installed it, and confirm the
  save folder that was found. Anything you skip can be done later. A game with no .exe set offers the same
  programs when you press Play, and one with no save folder has **Find save folder** on its page.
- Save conflicts and sync questions appear inside fullscreen mode, so you answer them with the controller.
- Fullscreen mode stays open behind the game while you play and comes back to the front when it closes.
- **☰ → Settings:** start in fullscreen mode, start with Windows, mirror deletions, update checks, the SteamGridDB
  key and this PC's name (typed on the on-screen keyboard). **A** changes the selected one.
- A game's page → **⋯ More:** **Show save files** lists the comparison with the cloud (differences first; **A** on a
  file shows both sides and can exclude it or its folder, **X** compares again), plus Sync automatically, Launch
  options and Look for the save folder again.
- Extra save folders, writing exclusion patterns, emulators, storage and appearance are set up in desktop mode
  (☰ → Desktop mode), as is choosing a game's .exe or save folder by hand.

**AnyFSE** (use it as the home app of the Xbox full screen experience): in AnyFSE's settings choose a
**Custom** launcher, pick `MareSaveSync.exe`, and give it the argument `--fullscreen`. Settings →
Fullscreen mode shows the exact path and has a Copy button. AnyFSE finds the app by its window, and its
_exit full screen experience when the launcher closes_ option works when you choose ☰ → Exit.

Only one copy of the app runs at a time. Starting it again (from AnyFSE, a shortcut, …) brings the copy that is
already running — for example the one waiting in the tray after **Start with Windows** — to the front;
with `--fullscreen` it switches to fullscreen mode.

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

**Updates:** the app checks GitHub for a newer release when it starts and every 12 hours, and shows an
**Update to v…** button in the status bar (also in the Start menu and fullscreen mode's ☰ menu, plus a Windows
notification once per version). Nothing is installed until you click it and say yes. The update is downloaded
into `data\update\`, checked against the checksum GitHub publishes, and then the app closes, swaps in the new
`MareSaveSync.exe` and `_internal`, and starts again. The `data` folder is left alone, and if the swap fails the
old version is put back. Help → **Check for updates…** checks right away; Settings → Updates turns the
automatic check off. Close any game you're playing first. Only release builds update themselves: a copy run
from source or built on your own PC doesn't know which release it is.

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
`MareSaveSync\MareSaveSync.exe`. The version comes from `VERSION` in `mss/__init__.py`; the workflow passes its run
number to `build.py` (`MSS_BUILD`), which builds it into the exe so the app knows which release it is and can
update itself (`mss/updater.py`). Google sign-in is built
in from the repository secrets `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (Settings → Secrets and variables →
Actions); without them the release still builds, just without built-in sign-in.

### Project layout

```
app.py                  entry point (python app.py)
mss/
  paths.py              assets, exe/source folder, local data folder
  launcher.py           start a game and wait for it to close; start with Windows
  applog.py             the log file (data\logs), tracebacks of errors, the bug report text
  updater.py            check GitHub releases, download an update and swap it in (--finish-update)
  instance.py           one copy at a time: a second start hands over to the running one
  core/                 no GUI: scan.py, excludes.py, diff.py, sync.py, compare.py, playtime.py, settings.py,
                        folders.py, savepaths.py (paths that work on every PC), detect.py (finding save folders),
                        installs.py (where Steam / Epic / GOG installed a game, and its .exe),
                        emulators.py (emulator presets and launch arguments)
  storage/              cloud backends: folder.py, gdrive.py (+ oauth_client.py reading .env), common.py
  providers/            online services: sgdb.py (SteamGridDB API), steam.py (Steam store details),
                        wikipedia.py, ludusavi.py (Ludusavi's list of save locations)
  art/                  cover art: sources.py (registry), images.py (local cache)
  info/                 game info: sources.py (registry; SteamGridDB + Steam store)
  ui/
    app.py              main window, built from mixins:
    library.py  details.py  play.py  sync.py  artwork.py  info.py (About tab)  savefind.py (finding save folders)
    update.py           the Update button, Help → Check for updates…
    fullscreen.py       fullscreen mode (controller UI); gamepad.py reads the Xbox controller (XInput)
    fs_keyboard.py      the on-screen keyboard;  fs_add.py  Add game in fullscreen mode
    fs_settings.py      settings, a game's options and its save files in fullscreen mode;  fs_stats.py  playtime
    theme.py  widgets.py  theme_art.py (banner/icon drawing)
    dialogs/            settings, metadata (game info & artwork picker), conflict, remove, diff_window
```

## Storage options

- **Google Drive** — Sign in with Google. Saves go to `My Drive/MareSaveSync/`. The app uses the `drive.file`
  permission, so it can only see files it created, not the rest of your Drive.
- **A synced folder** — e.g. your Google Drive for desktop folder `G:\My Drive`. No sign-in setup needed;
  wait for the Drive client to finish syncing before you Sync down on another PC.

## Using it

- **Sort** the library by name, last played, most played or recently added (the box next to Refresh). The order
  is remembered, and updates when a game closes. Games you've never played go last when sorting by playtime.
  For games added by older versions, "added" is when their cloud folder was created.
- **Add game** → name it → choose the .exe on this PC. The save folder is then found automatically and you're asked
  whether to use it. If it isn't found, choose it yourself: _Choose… → Type or paste a path_ accepts things like
  `%USERPROFILE%\AppData\LocalLow\AcrobaticChirimenjako\SchrodingersCallAdv` (AppData is hidden in the normal
  folder picker).
- **Finding save folders automatically** uses [Ludusavi's list of save locations](https://github.com/mtkennerly/ludusavi-manifest)
  (over 20,000 PC games, from PCGamingWiki). It's downloaded the first time it's needed (about 18 MB, once) and checked
  for updates once a week. The game is matched by its Steam id, else its name; games kept in the install folder
  are found through the game's .exe or your Steam libraries. Saves in the Windows registry, Steam Cloud's own
  folder and Xbox app containers aren't synced. To look again later: Saves tab → _Choose… → Find automatically_.
- **Every other PC finds the folder by itself.** When a save folder is under your user folder, AppData, Documents
  or ProgramData, where it is gets stored with the game in the cloud (e.g.
  `<home>/AppData/LocalLow/Team Cherry/Hollow Knight`), and other PCs use the same place in their own user folder:
  opening the game or pressing Play there is enough. Folders elsewhere (like `D:\Games\…`) are chosen on each PC.
  Press **Play** on a PC where the save folder isn't set yet and it's looked for first, so you start from the
  saves in the cloud.
- Game keeps saves in more than one place? **Saves** tab → **Add folder…** as many times as needed. Each
  extra folder is named once and every PC sees it; choose where it is on each PC. Until it's chosen on a
  PC, its files are left alone there. In the cloud each extra folder is stored under `@2/`, `@3/`, …;
  **Remove** stops syncing it and deletes its cloud copy (files on the PCs are kept).
- **Diff** tab shows every file: _Same_, _Different_, _Only on this PC_, _Only in cloud_, _Excluded_,
  with sizes and dates on both sides. The **Note** column says which side changed since this PC last
  synced; _⚠ Changed on both sides_ means a conflict. Double-click a file to compare its contents
  (text/JSON line diff, or a hex diff for binary saves).
- **Exclusions** tab: add a file, a folder or a pattern. Or right-click any file in the diff →
  _Exclude this file / folder / all \*.ext files_. Rules are stored with the game in the cloud, so every
  PC uses the same list. Excluded files are never uploaded, downloaded or deleted. Good first rules:
  `*.log`, `Player.log`, crash dumps, shader caches.
- **Library badges** show where each game stands: _✓ Synced_, _☁ Cloud is newer_ (another PC uploaded newer saves:
  Play or Sync down gets them), _▲ Not uploaded_ (this PC has saves the cloud doesn't) and _⚠ Conflict_ (both changed).
  Every game is checked in the background after connecting, on Refresh, and every 30 minutes; a note says when
  games have newer saves in the cloud. Save files that haven't changed aren't read again.
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
- Cached cover art: `data\art\`; backups: `data\backups\`; the list of save locations: `data\ludusavi.json`
- The log: `data\logs\MareSaveSync.log` (about the last 3 MB). **Help → Log…** shows it, with **Errors only**
  and **Copy for bug report**, which copies the app and Windows versions, the storage type and the end of the
  log with your user name taken out of paths. Paste that into a GitHub issue (**Report a problem on GitHub…**).
- The only thing outside the folder: **Start with Windows** adds a registry entry pointing at the exe. It's
  updated when you start the moved app; turn it off before deleting the folder.
- In the cloud, everything about a game is in its own folder `My Drive/MareSaveSync/<game>/`:
  the save files, `savesync.json` (exclusions, extra save folders, where the save folders are), `info.json` (name, description, …), `art/` (artwork choice +
  images) and `playtime/` (one file per PC, with its total and its seconds per day for the last 400 days).
  **Remove from library** only hides the folder; add the game again with the same name and its saves,
  playtime, artwork and exclusions come back. Tick **Purge all data** in that dialog to delete the whole
  folder instead (on Google Drive it goes to the trash, so it can still be restored from there).
- Older versions used a top folder called `SaveSync`. The first time this version connects it renames that
  folder to `MareSaveSync` (nothing is copied or lost), and picks up the old `.mss-stats/` and `.mss-art/`
  data inside it. Update the app on every PC: older versions keep looking for `SaveSync`, and still show
  removed games.
