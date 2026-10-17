# gsm-companion — straight into Rekordbox

GetSetMix puts tracks in a folder; your sync client (Nextcloud, Syncthing, …)
brings that folder to the computer that runs Rekordbox. **gsm-companion** is
the last step: it adds those tracks to the Rekordbox **collection** itself,
into a `GetSetMix` playlist — no XML to refresh, no drag and drop.

One file, ~5 MB, no runtime to install. Windows and macOS (the platforms
Rekordbox runs on).

## How it stays out of your way

Rekordbox keeps its collection in `master.db` and must be **closed** while
anyone else writes to it. So the companion doesn't need to run all the time —
it needs to run *right before Rekordbox starts*:

| Mode | What runs in the background | When tracks appear |
|---|---|---|
| **Launcher** (default) — open Rekordbox with the *Rekordbox (GetSetMix)* shortcut | **nothing** — it imports (≈1 s, 0.1 s when nothing is new), starts Rekordbox, exits | every time you open Rekordbox |
| **Autostart**, Windows — `install --autostart` | one ~10 MB process asleep on folder notifications (0 % CPU, no polling) | as soon as they arrive; if Rekordbox is open, the moment you close it |
| **Autostart**, macOS — `install --autostart` | **nothing** — launchd watches the folder and starts a one-shot sync | same |

## Install

1. Download the build for your OS from the
   [Releases page](https://github.com/Fre0Grella/getsetmix/releases?q=companion)
   (`gsm-companion-windows-x64.zip` or `gsm-companion-macos.tar.gz`) and unpack
   it somewhere permanent, e.g. `%LOCALAPPDATA%\GetSetMix` or `~/Applications`.
2. Close Rekordbox, then in a terminal in that folder:

   ```sh
   gsm-companion setup      # finds your Rekordbox library and the folder to watch
   gsm-companion install    # creates the "Rekordbox (GetSetMix)" launcher
   ```

3. Open Rekordbox with **Rekordbox (GetSetMix)** from now on (Start menu /
   Desktop on Windows, `~/Applications` on macOS — it has Rekordbox's icon).

`setup` proposes the folder that holds most of your collection; pass
`--folder DIR` (repeatable) to choose. Tracks already in that folder count as
handled, so nothing you deliberately left out of Rekordbox gets pulled in —
add `--import-existing` if you *do* want them. Delete a track from Rekordbox
later and it stays deleted: the companion remembers what it has handled.

New tracks are not analysed yet: select the `GetSetMix` playlist and choose
**Analyze Track**, or let Rekordbox analyse them when you load them.

### macOS: first run

The binaries are not notarised. The first time, right-click → Open, or run
`xattr -d com.apple.quarantine gsm-companion`.

## Commands

```text
gsm-companion setup [--folder DIR]... [--playlist NAME] [--import-existing]
gsm-companion install [--autostart]     launcher (+ unattended imports)
gsm-companion launch                    import new tracks, then start Rekordbox
gsm-companion sync [--dry-run] [--wait] one import; --wait outlasts an open Rekordbox
gsm-companion watch                     stay running and import as tracks arrive
gsm-companion status                    what it watches, what is pending
gsm-companion uninstall                 remove launcher and autostart
```

On Windows the release also has `gsm-companionw.exe`: the same program without
a console window, used by the launcher and autostart so nothing flashes up.

Config, state, log and the last backup live in `%APPDATA%\GetSetMix`
(Windows) or `~/Library/Application Support/GetSetMix` (macOS).

## Safety

Writing to another program's database deserves suspicion, so:

- **Never while Rekordbox runs.** Checked before reading and again right
  before writing.
- **Nothing is opened unless something is new.** The usual run is a folder
  scan and an exit.
- **Backup first, one transaction, integrity check after.** `master.db` and
  `masterPlaylists6.xml` are copied to `backup/` before every write; if the
  write or SQLite's `quick_check` fails, the backup is put back.
- **Rows match Rekordbox's own.** Every column mirrors what Rekordbox stores
  for an imported track — device, `ContentLink`, `rb_file_id` (the NTFS file
  ID / inode), timestamps, the change counter (`localUpdateCount` and each
  row's `rb_local_usn`) and the playlist mirror in `masterPlaylists6.xml` —
  checked field by field against a real Rekordbox 7.2 library, and read back
  with [pyrekordbox](https://github.com/dylanljones/pyrekordbox) as an
  independent reader.
- **Files still syncing are left alone**: hidden/temp names (Nextcloud's
  `.name.~xxxx`), partial downloads, conflict copies, and anything modified in
  the last 10 seconds.

If something ever looks wrong, close Rekordbox and copy the files from
`backup/` back into Rekordbox's folder (`%APPDATA%\Pioneer\rekordbox` /
`~/Library/Pioneer/rekordbox`). Rekordbox also keeps its own dated
`master.backup.*.db` copies there.

## How it works

`master.db` is a SQLCipher 4 database. Its key is the same on every install
and has been public since pyrekordbox extracted it, which is what makes this
possible without hooking into Rekordbox at all. The companion adds one
`djmdContent` row per track (plus `djmdArtist`/`djmdAlbum`/`djmdGenre` rows by
exact name, reusing existing ones), appends them to the playlist through
`djmdSongPlaylist`, and bumps the change counters Rekordbox uses to notice
local edits (and to sync them, if you use Cloud Library Sync).

Built with Go and [go-sqlcipher](https://github.com/mutecomm/go-sqlcipher)
(SQLCipher compiled in, no OpenSSL), [fsnotify](https://github.com/fsnotify/fsnotify)
and [tag](https://github.com/dhowden/tag).

## Releasing

`companion/VERSION` is the version. A push to `main` that changes it builds
both platforms and publishes the `companion-vX.Y.Z` release (see
`.github/workflows/companion.yml`); pushing a `companion-v*` tag does the same
for that commit, as a pre-release when the version has a suffix (`-rc.1`).
