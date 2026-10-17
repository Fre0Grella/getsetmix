# CHANGELOG


## v1.5.0 (2026-10-17)

### Features

- **ui**: Mobile-first layout and theme switch
  ([`19e0985`](https://github.com/Fre0Grella/getsetmix/commit/19e0985dc595fda86816bc958ac207013d65e8e7))

The UI is now designed for the phone first, since that is where links arrive (share sheet or
  clipboard) and where most edits happen:

- Adding and downloading live in a bottom deck within thumb reach, with the batch progress on top of
  it. On wide screens it becomes a transport bar. - Rows are compact on a phone (cover, title,
  artist, genre, state and the one action that moves the track on). Tapping a row opens it with
  full-size fields, labels, every action, and one-tap genre picks (genres already used in the list
  first). Fields in a compact row don't take taps, so opening a row never throws up the keyboard. -
  Inputs are 16px or more, so iOS no longer zooms in on focus. Tap targets are 44px. The deck steps
  aside while a row field is being edited, and interactive-widget=resizes-content keeps it above the
  Android keyboard. - Settings is a full-screen sheet on a phone and stays a side panel on a
  computer. From 721px the Rekordbox-style columns are unchanged.

Theme: Auto, Light or Dark in Settings > Interface. It applies at once and is stored per device in
  localStorage, so a phone can be dark while the desktop follows the system. An inline script
  applies it before first paint, and the theme-color meta (Android status bar) follows the choice.

Logo: the header and app icons were raster cut-outs with chewed edges and a halo around the speed
  dashes. They are replaced by the vector redraw from the wizard branch (icon.svg,
  icon-maskable.svg, mark.svg), recoloured from teal to the master logo's blue to match the UI
  accent. The header mark is inline, so its figure follows the theme. Rasters come from
  scripts/build_icons.py (Playwright), which replaces fix_icon.py; the Pages site uses the same
  assets.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV


## v1.4.0 (2026-10-17)

### Continuous Integration

- **companion**: Test and release Windows and macOS
  ([`6acb179`](https://github.com/Fre0Grella/getsetmix/commit/6acb179ffec467eb0932597194d87fa02714dcf9))

Tests run on Windows (cgo through MSYS2 UCRT64 gcc), macOS and Linux. Releases are automated from
  companion/VERSION: a push to main whose VERSION has no companion-vX.Y.Z tag yet builds a static
  Windows pair (gsm-companion.exe + the windowless gsm-companionw.exe) and a universal macOS binary,
  then publishes the release with SHA256SUMS. Pushing a companion-v* tag releases that commit, as a
  pre-release when the version has a suffix. The prefix keeps these tags apart from the server's
  semantic-release vX.Y.Z tags, and make_latest stays false so the server remains the repo's latest
  release.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

### Documentation

- Point to the companion from the README
  ([`99ff140`](https://github.com/Fre0Grella/getsetmix/commit/99ff1407f0a7a51d343917ffab14ce1de58b6109))

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

- **deploy**: Plan auto-update with Keel
  ([`58c2d29`](https://github.com/Fre0Grella/getsetmix/commit/58c2d29f28956923869570dc3cc6d12774097d79))

Handoff for the session that sets up self-updating on the home server: Keel polls GHCR and rolls the
  deployment whenever the digest behind :latest changes, so pushes to main and the weekly yt-dlp
  refresh both reach the server without a manual rollout. Covers the checks to run against the live
  deployment first (it lives in namespace nextcloud, not the repo manifest's getsetmix), install,
  verification, rollback, and the release-only variant.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

### Features

- **companion**: Import deliveries into Rekordbox
  ([`20a69ba`](https://github.com/Fre0Grella/getsetmix/commit/20a69babc404b087972bd274c006797de7e5bd4d))

gsm-companion runs on the DJ's computer and adds the tracks a sync client delivers straight into
  Rekordbox's collection (master.db), into a "GetSetMix" playlist. No XML source to refresh, no drag
  and drop.

Rekordbox must be closed while its database is written, so nothing has to stay resident: the default
  "Rekordbox (GetSetMix)" launcher imports (about 1 s, 0.1 s when nothing is new) and then starts
  Rekordbox. Unattended imports are opt-in: on Windows a watcher that sleeps on
  ReadDirectoryChangesW and on the Rekordbox process handle (about 10 MB, 0% CPU idle); on macOS a
  launchd agent with WatchPaths, so nothing of ours runs between changes.

Safety: - never writes while Rekordbox runs (checked before reading and again before writing); opens
  nothing unless a file is new; - backs up master.db and masterPlaylists6.xml, writes in one
  transaction, runs quick_check, and restores the backup on failure; - remembers handled files, so a
  track deleted in Rekordbox stays deleted; files still syncing (temp names, conflicts, modified in
  the last 10 s) are left alone.

Rows mirror Rekordbox's own, checked against a real 7.2 library rather than copied from pyrekordbox:
  the local device from djmdProperty (not the first djmdDevice), ContentLink from the latest local
  import, rb_file_id = NTFS file ID / inode, UTC "…mmm +00:00" timestamps, localUpdateCount and
  per-row rb_local_usn, and the playlist mirrored into masterPlaylists6.xml without reformatting it.
  Stream facts are parsed from MP3/FLAC/WAV/AIFF/MP4 headers; on 514 real tracks they match what
  Rekordbox stored (file ID, rate, depth, type 514/514, length 513, bitrate 510). An end-to-end run
  on a copy of that library reads back cleanly with pyrekordbox and passes integrity_check.

Go with SQLCipher compiled in (go-sqlcipher, no OpenSSL): one ~5 MB static binary per platform.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

### Testing

- **companion**: Build test paths natively per OS
  ([`a4fe23f`](https://github.com/Fre0Grella/getsetmix/commit/a4fe23fa7d996cc5b35264fe32caf799681881c2))

Two library tests spelled Windows paths with backslashes, which are ordinary filename characters on
  macOS and Linux, so CI failed there. Build them with filepath.FromSlash instead.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV


## v1.3.0 (2026-10-17)

### Bug Fixes

- **ytdlp**: Bundle Deno and keep yt-dlp fresh
  ([`4d1e743`](https://github.com/Fre0Grella/getsetmix/commit/4d1e74369ee4442926b845edf28a271beacee13a))

YouTube now serves media only to clients that solve its JavaScript challenges. yt-dlp does that with
  an external JS runtime plus the yt-dlp-ejs scripts; the image had neither and a months-old yt-dlp,
  so metadata resolved through a fallback client while every download died with "HTTP Error 403:
  Forbidden".

- Dockerfile: copy a pinned Deno (bin-2.9.3, amd64 + arm64) and install yt-dlp[default], which
  brings yt-dlp-ejs; the build fails fast if either is missing. - Weekly scheduled image rebuild. CI
  resolves the newest yt-dlp from PyPI and passes it as YTDLP_VERSION, which busts the cached pip
  layer (a plain rebuild would reuse the stale install from the GHA cache). - app/ytdl.py: one place
  that builds YoutubeDL options, enabling whichever supported runtime is installed (deno, node,
  quickjs, bun), so local mode works with Node too. - 403s now carry the fix ("install Deno…")
  instead of a bare error, GET /api/status reports yt-dlp age and runtime, and the UI shows a banner
  when downloads are bound to fail. - PyInstaller builds collect yt_dlp_ejs; k8s pulls :latest
  always. - CI pins ruff to the pre-commit version (newer releases widen the default rule set and
  would fail lint with no code change) and runs node --check on the UI scripts, which have no build
  step to catch a syntax error.

Verified with a real YouTube download inside the built image: yt-dlp reports "JS runtimes:
  deno-2.9.3" and writes the MP3, no 403.

Closes #9

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

### Features

- **ui**: Redesign as a track browser
  ([`8a70ae4`](https://github.com/Fre0Grella/getsetmix/commit/8a70ae468ac12630cc8da8499bda85eb53d21ffc))

The list is now laid out like Rekordbox's own browser instead of a stack of floating cards: dense
  rows under column headers (track, album, genre, time, status), artwork kept 16:9, and fields that
  read as plain text until hovered or focused, so editing metadata is in place.

- A real link field in the top bar: Enter adds, pasting a link adds it at once, and Ctrl+V anywhere
  on the page works too. With the field empty, Add reads the clipboard; no more prompt() fallback. -
  Status is one cell per row (dot + label: ready, queued, %, writing tags, in your library, error)
  with only the actions that apply; yt-dlp's "ERROR:" prefix is trimmed, the full text is the
  tooltip. - Settings is a grouped side panel (downloads, library and Rekordbox, interface,
  housekeeping) that leaves the list in view. It opens at once and stays inert until its values
  load, so neither Escape nor a fast Save can race the fetch (a Save could have written an empty
  library folder). - Follows the system theme, both designed: OKLCH neutrals tinted toward the
  logo's navy, the logo's "mix" blue as the only accent. - Phones: the Download action moves to a
  bottom dock within thumb reach, rows wrap album and genre onto a second line. - Copy rewritten in
  both languages (EN/IT keys kept in parity), without em dashes; picker emoji replaced with the UI's
  icons.

Every DOM id app.js binds to is kept; the share-target flow is unchanged. Checked in Chrome at 1280
  and 390 px, dark and light, with every row state, and by driving the real flows (add by Enter,
  paste anywhere, inline edit persisted, settings save + language switch, Escape, cover search).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV


## v1.2.1 (2026-07-05)

### Bug Fixes

- **ui**: Fix genre textbox flickering
  ([`1a4a8ac`](https://github.com/Fre0Grella/getsetmix/commit/1a4a8ac3ff0aabe26fc1086a99c018c18d141073))

### Continuous Integration

- Scope release asset download to executables
  ([`7f02307`](https://github.com/Fre0Grella/getsetmix/commit/7f023076a6e8c47652c252f19f84e10f834c27ab))

The attach job downloaded all run artifacts, which now includes the buildx .dockerbuild artifact
  from the image job, causing the download to fail. Filter to getsetmix-* so only the executables
  are pulled and attached.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

- Use .mjs commitlint config required by commitlint-github-action
  ([`d6c663c`](https://github.com/Fre0Grella/getsetmix/commit/d6c663c8b06bb99f4df6f77153c9dee9ae2f7ab3))

wagoid/commitlint-github-action v6 rejects a .js configFile with ".js extension is not allowed for
  the configFile, please use .mjs instead", which made the Commit lint job red on every push.
  Convert the config to an ESM commitlint.config.mjs and point the workflow at it.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>


## v1.2.0 (2026-06-16)

### Chores

- Trigger release pipeline
  ([`06f9ad1`](https://github.com/Fre0Grella/getsetmix/commit/06f9ad19aba4252cb12e35704334bbdb6bac3309))

### Continuous Integration

- Automate semantic versioning and enforce Conventional Commits
  ([`345c1de`](https://github.com/Fre0Grella/getsetmix/commit/345c1de230fc86621f07e0e2e4740ce4b1069c3e))

Releases are now driven by Conventional Commits on main instead of manual tags.
  python-semantic-release reads the commit history and bumps the version (fix -> patch, feat ->
  minor, breaking -> major), tags vX.Y.Z, creates the GitHub Release, and builds the executables +
  versioned images in one run.

- pyproject.toml: python-semantic-release config; single version source in app/__init__.py
  (__version__), wired into FastAPI - release.yml: consolidated version -> executables -> versioned
  images, no PAT needed (self-contained run; release commit carries [skip ci]) - docker-publish.yml:
  now main-only (latest/main/sha); versioned tags moved to release.yml - commitlint.yml +
  commitlint.config.js + .pre-commit-config.yaml: make Conventional Commits mandatory in CI and
  locally (commit-msg hook) - docs + test for the version wiring

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

- Sign semantic-release commits to satisfy signed-commit protection
  ([`281a846`](https://github.com/Fre0Grella/getsetmix/commit/281a8463975eee28ff0cf1e3ee2f67d6098f7562))

main has branch protection requiring verified signatures, which rejected the release bot's unsigned
  version-bump push. Configure python-semantic-release to SSH-sign its commit using a signing key on
  the owner account, supplied via the SSH_SIGNING_PRIVATE_KEY / SSH_SIGNING_PUBLIC_KEY repo secrets.
  Setup steps added to the README.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

### Features

- Share to GetSetMix from YouTube/SoundCloud via PWA share target
  ([`1496657`](https://github.com/Fre0Grella/getsetmix/commit/1496657ac357e48623378ac93484b864fa180b53))

Make GetSetMix installable as a PWA with a Web Share Target so a track can be shared straight from
  the YouTube/SoundCloud Android share sheet: the link is fetched and lands staged in the existing
  review/download UI.

- main.py: serve /manifest.webmanifest, /sw.js, and the /share landing - manifest + minimal
  (no-cache) service worker; 192/512 maskable icons generated by scripts/fix_icon.py - app.js:
  register SW, consumeShare() extracts the first URL from the shared text and reuses the paste flow;
  new row scrolls into view and flashes - k8s: TLS Ingress example (HTTPS is required for PWA
  install) - docs + tests for the new routes

Android only -- iOS Safari has no Web Share Target API.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>


## v1.1.1 (2026-06-10)

### Bug Fixes

- Upgrade mobile ui
  ([`51d7aa9`](https://github.com/Fre0Grella/getsetmix/commit/51d7aa98a73605b7ce66401a88c9d8a4e0e1d810))


## v1.1.0 (2026-06-10)

### Features

- Duplicate now are showed in the main view by a warning badge,
  ([`cddd4c6`](https://github.com/Fre0Grella/getsetmix/commit/cddd4c6880c26409bf9960263be55eb1b10121eb))


## v1.0.0 (2026-06-10)

### Bug Fixes

- Add proper .gitignore
  ([`7aec5c3`](https://github.com/Fre0Grella/getsetmix/commit/7aec5c3b51fd77e73bb580d52926ff59d55c2115))

- Fix deployment name for container
  ([`e7754d0`](https://github.com/Fre0Grella/getsetmix/commit/e7754d03ca18d0486ebcd73406b851b2219a7d8c))

- Remove placeholders
  ([`35789bb`](https://github.com/Fre0Grella/getsetmix/commit/35789bb0423fd9f7b8a45a28ece5775c732b578e))

### Chores

- Add a development mode
  ([`b79a012`](https://github.com/Fre0Grella/getsetmix/commit/b79a0125d4caf5bf6d72606c8adbd18817373e7b))

- Add deployement manifest for k8s
  ([`6f5e647`](https://github.com/Fre0Grella/getsetmix/commit/6f5e6477babf277a595953ddc73b6db8bb74f4fe))

### Continuous Integration

- Add gh pages and some ci/cd
  ([`4b6d220`](https://github.com/Fre0Grella/getsetmix/commit/4b6d2204d67d0b1a23c9ede79d48cde6240ccceb))

- Setup ci/cd and add a build system
  ([`65fe4d9`](https://github.com/Fre0Grella/getsetmix/commit/65fe4d9c0833e3e13febe2002c4df8c6c0426895))

### Documentation

- Add a product documentation
  ([`bacd534`](https://github.com/Fre0Grella/getsetmix/commit/bacd534978a75aa6487197a744b97f8e5808e6f4))

- Add concept ui
  ([`8b8a0db`](https://github.com/Fre0Grella/getsetmix/commit/8b8a0db27d1b4fca8b2118935ac650a7e015e240))

- Adding design concept
  ([`d1b7033`](https://github.com/Fre0Grella/getsetmix/commit/d1b7033ce12ac6b2d65ad878dc7cc365d4e6d6cd))

- Improve architecture design
  ([`58a4548`](https://github.com/Fre0Grella/getsetmix/commit/58a45485803e81c5d50bbe1ce048c5d0146a13fa))

- Initialize context
  ([`a17918c`](https://github.com/Fre0Grella/getsetmix/commit/a17918cdb1a55311e770f8b21eb99efcc1914b81))

- Updated architectural design choices
  ([`a3898e8`](https://github.com/Fre0Grella/getsetmix/commit/a3898e80e3705fe1d5f8cd13f8a2d56aad7975a1))

### Features

- Add service orchestration for api and state
  ([`88dd11d`](https://github.com/Fre0Grella/getsetmix/commit/88dd11dbd6e84b4597eebb6a9c531612ddc4fced))

- Add staging ui
  ([`a7a3cab`](https://github.com/Fre0Grella/getsetmix/commit/a7a3cab0da70df7a3abf0908364c82338b621727))

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>

- Add the python adapter runtime
  ([`1ce7815`](https://github.com/Fre0Grella/getsetmix/commit/1ce7815fa26bff1d36f883fe07f8da8d28a070fc))

- All done, good job fable
  ([`8575d53`](https://github.com/Fre0Grella/getsetmix/commit/8575d533839464b85f42dee0d9111ca4f286d707))

- Collection-aware inbox, path picker, EN default, exe releases, UI fixes
  ([`c50582b`](https://github.com/Fre0Grella/getsetmix/commit/c50582ba519d001eec244490455ae65de1d9a419))

- brand icon: black square removed (transparent bg), new light variant for dark surfaces, favicons
  regenerated (scripts/fix_icon.py) - GH pages mock translated to English; English is now the
  default UI language and the GSM_LANGUAGE default everywhere - new optional "Rekordbox collection
  XML" setting (GSM_COLLECTION_XML_PATH): before each batch, tracks already imported into the full
  collection are purged from the inbox XML (matched by file location, title+artist fallback) -
  server-side path picker (GET /api/fs/list) with Browse buttons for the library folder and both XML
  paths - track rows no longer squash when many links/playlists are added (flex: none) - improved
  mobile layout: touch targets, bottom-sheet modals, 16px inputs, always-visible cover button on
  touch screens - release.yml builds standalone executables (Windows/macOS/Linux, PyInstaller) on
  v*.*.* tags; frozen builds keep their data in ~/.getsetmix

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

### Refactoring

- Cleaning up for fable
  ([`77a222f`](https://github.com/Fre0Grella/getsetmix/commit/77a222f890ff2df74ce9d4ab2e3c8e91fe166373))
