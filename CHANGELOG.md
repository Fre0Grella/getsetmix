# CHANGELOG


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
