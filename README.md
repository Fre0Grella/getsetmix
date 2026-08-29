# GetSetMix

[![CI](https://github.com/Fre0Grella/getsetmix/actions/workflows/ci.yml/badge.svg)](https://github.com/Fre0Grella/getsetmix/actions/workflows/ci.yml)
[![Publish image](https://github.com/Fre0Grella/getsetmix/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Fre0Grella/getsetmix/actions/workflows/docker-publish.yml)
[![Deploy site](https://github.com/Fre0Grella/getsetmix/actions/workflows/pages.yml/badge.svg)](https://github.com/Fre0Grella/getsetmix/actions/workflows/pages.yml)


Self-hosted DJ ingestion service for your homelab. Paste a URL (single track or playlist), review and edit the metadata, batch-download to MP3 320 kbps or FLAC, auto-tag with cover art, and ingest straight into your Rekordbox library via XML — all from a fast, MediaHuman-inspired web UI.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="app/static/assets/mark-light.svg">
  <img alt="GetSetMix" src="app/static/assets/mark-dark.svg" width="420">
</picture>

> Use GetSetMix only for content you have the rights to download.

## Features

- **Paste & go** — single videos or whole playlists/sets fan out into individual editable rows
- **Metadata review before download** — title + artist required, genre highlighted with a DJ-genre picker, optional album; cover override via cover search (iTunes) or manual upload
- **Batch downloads** — global parallelism default of 2 with per-batch override, per-track status (queued → downloading → tagging → ingested / error), overall batch progress bar, cancel button
- **Failures don't halt the batch** — failed tracks are flagged with per-track retry
- **Tagging** — ID3v2.4 / FLAC Vorbis comments: title, artist, album, genre, embedded cover, source URL in the comment field
- **Filename templates** — `{title} {artist} {album} {source} {id} {genre}`, sanitized, missing tokens omitted, collision-safe suffixes
- **Rekordbox link that actually resolves** — a track's identity is its path *relative to the library root*, so the XML written for each machine carries paths valid **on that machine**: `/music/x.mp3` on the server becomes `C:\DJ\x.mp3` in the studio PC's XML and `/Users/m/Music/x.mp3` in the laptop's. One XML per machine, no more "imported but the file is missing"
- **Setup wizard** — `/setup` walks the library, delivery method and DJ machine, then verifies the whole path end to end and tells you the fix for anything that fails
- **Continuous verification** — a link-status chip runs the same checks every minute: library writable, XMLs valid, sampled Locations actually resolving, collection export not stale, companion online
- **`gsm-link` companion** *(optional)* — one stdlib-only file on the Rekordbox machine that reads your Nextcloud/Syncthing folder map, so the DJ-side path is derived rather than typed, and confirms from that side that the files really arrived
- **Nextcloud over WebDAV** — the server can push files (and the XML) straight into Nextcloud, so it needs no mount and no sync client of its own
- **Collection-aware inbox** — optionally point GetSetMix at your full Rekordbox collection XML: before each batch, tracks you've already imported are purged from the inbox XML, so it only ever lists new songs
- **Duplicate detection** — right after metadata is fetched, each track is checked against the inbox XML *and* your collection XML by source URL or by normalized/fuzzy title+artist (filename-independent, so changing the naming template still counts). Duplicates get an amber badge, and starting a batch with duplicates prompts you to download anyway or skip them
- **Share to GetSetMix (Android)** — install the web UI as a PWA and it shows up in the Android share sheet, so you can share a link straight from the YouTube or SoundCloud app; the track lands staged and ready to review
- **Persistence** — SQLite for tracks, URL history, and counters; manual purge from the UI
- **Observability** — Prometheus `/metrics`: job counts by status, active downloads, download durations, errors by source, songs in last 30d / 365d / all time, health
- **Private by default** — bind to localhost or your LAN; optional static-token or Basic Auth for public exposure
- **i18n** — English (default) and Italian UI · **dark by default**, with light and match-system themes
- Runs comfortably under 1 GB RAM

## Quickstart — Docker Compose

```yaml
# deploy/docker-compose.yml (edit the music volume path)
services:
  getsetmix:
    build: ..
    ports: ["8765:8765"]
    volumes:
      - getsetmix-data:/data
      - /path/to/your/music/library:/music
    environment:
      GSM_LANGUAGE: en          # or it
      # GSM_AUTH_TOKEN: change-me   # enable token auth if exposed
volumes:
  getsetmix-data:
```

```bash
docker compose -f deploy/docker-compose.yml up -d --build
# open http://localhost:8765
```

## Kubernetes (first-class)

Plain manifests live in `deploy/k8s/getsetmix.yaml` (Namespace, ConfigMap, PVCs for data + music, Deployment with health probes and Prometheus scrape annotations, Service, optional Ingress commented out).

```bash
# 1. build & push the image, then point the Deployment at it
docker build -t ghcr.io/Fre0Grella/getsetmix:latest .
docker push ghcr.io/Fre0Grella/getsetmix:latest

# 2. apply
kubectl apply -f deploy/k8s/getsetmix.yaml
kubectl -n getsetmix get pods
```

Notes:

- `replicas: 1` with `strategy: Recreate` is intentional — state is SQLite on a PVC.
- Mount your real music library into the `music` PVC (or replace it with `hostPath`/NFS as your cluster dictates).
- A Helm chart is not included; the manifests are small enough to kustomize directly.

## Local app mode (Linux / Windows / macOS)

Same UI, not always-on — auto-opens your browser. Grab a prebuilt executable from the [Releases page](https://github.com/Fre0Grella/getsetmix/releases) (no Python needed, data lives in `~/.getsetmix`), or run from source:

```bash
pip install -r requirements.txt
# ffmpeg must be on PATH (apt install ffmpeg / brew install ffmpeg / winget install ffmpeg)
python run_local.py            # opens http://127.0.0.1:8765
python run_local.py --port 9000 --no-browser
```

## Using it

1. Click **Paste link** — the URL on your clipboard is added (playlists fan out into one row per entry).
2. Rows resolve their metadata; fix title/artist, pick a genre, optionally set album and cover (camera button on the thumbnail → search or upload).
3. Press **Download** to start the batch (the ×N selector overrides parallelism for this batch only). Edits lock once a track is queued.
4. Watch per-track progress and the batch bar; cancel anytime (in-flight tracks are stopped and re-staged).
5. When tracks show **Done**, refresh the *rekordbox xml* tree in Rekordbox and find them in the **Inbox** playlist.

## Setting up the Rekordbox link

Run the wizard once — **open `http://<server>:8765/setup` from the machine that
has Rekordbox**. It is served by the server but meant to be read from there, so
the paths it shows you are the ones you need to paste.

It asks four things and then checks its own work:

1. **Where downloads land on the server** — in Docker this is the path *inside*
   the container (usually `/music`), not the path on your NAS.
2. **How the files reach the DJ machine** — same machine · a folder Nextcloud or
   Syncthing already syncs · upload to Nextcloud over WebDAV (no mount needed —
   best under Docker/Kubernetes) · an SMB/NFS share.
3. **The machine running Rekordbox** — either pair the companion, or type the
   library folder *as that machine sees it*. Either way the wizard previews the
   exact `Location` string the XML will contain before you commit to it.
4. **Verify** — library writable, XML valid, sampled paths resolving, collection
   export present and current, companion reachable. Anything red says what to do.

Then in Rekordbox: **Preferences ▸ Advanced ▸ Database ▸ rekordbox xml** → the
path the wizard shows (it defaults inside the library folder so your sync tool
carries it along with the music). Refresh the *rekordbox xml* tree after each
batch — nothing can make Rekordbox reload it automatically.

### Why the XML used to be broken

The old writer stamped the **server's** absolute path into every `Location`.
The server's truth is `/music/…`; Rekordbox's is `C:\Users\you\Nextcloud\Music\…`.
Nothing reconciled them, so tracks imported as missing files and there was no
setting that could fix it. Machine profiles are that reconciliation, and the
health checks mean you find out at setup rather than before a set.

### The companion (optional but recommended)

```bash
# on the machine with Rekordbox — one file, stdlib only, Python 3.9+
curl -fsSLO http://<server>:8765/link/gsm_link.py
python3 gsm_link.py detect                                      # what it sees
python3 gsm_link.py pair --server http://<server>:8765 --code 123456
python3 gsm_link.py doctor                                      # verify now
python3 gsm_link.py run                                         # keep reporting
```

It reads your Nextcloud/Syncthing folder map so you never type the DJ-side path,
and it verifies from that side that the XML's paths open real files. See
[`agent/README.md`](agent/README.md) for service setup and the `--apply` rules
around Rekordbox's preferences file.

### Multiple machines

Add a profile per machine. Each gets its own XML with its own path space, so a
Windows studio PC and a macOS laptop can share one library without either
seeing the other's paths.

## Share to GetSetMix (Android)

GetSetMix ships as an installable PWA with a [Web Share Target](https://developer.mozilla.org/en-US/docs/Web/Manifest/share_target), so you can push a link into it straight from the YouTube or SoundCloud share sheet instead of copy-pasting.

1. **Expose the instance over HTTPS.** Browsers only let a site install (and register a share target) from a secure origin. The simplest route is the Kubernetes deployment behind a TLS Ingress — uncomment and adapt the Ingress block in `deploy/k8s/getsetmix.yaml` (it includes a cert-manager `tls:` example). Any HTTPS reverse proxy works too.
2. **Install it.** Open the HTTPS URL in **Chrome/Edge on your Android phone** → menu → **Install app / Add to Home screen**.
3. **Share.** In the YouTube or SoundCloud app, tap **Share → GetSetMix**. The app opens, the link is fetched, and the track appears staged in the list — edit metadata and hit **Download** as usual.

Notes:

- **Android only.** iOS Safari doesn't implement the Web Share Target API, so GetSetMix can't appear in the iPhone share sheet (paste-link still works).
- If you've enabled `GSM_AUTH_TOKEN` / Basic Auth, open the installed app and authenticate once first — the token is stored in the browser and reused when you share.

## Configuration

Everything is editable in the UI (gear icon) and persisted to `<data>/config.json`. Machine profiles live in the same file and are managed by the wizard rather than by environment variables. Environment variables override on boot:

| Variable | Default | Purpose |
|---|---|---|
| `GSM_DATA_DIR` | `./data` (`/data` in Docker) | SQLite DB, config, covers, default XML location |
| `GSM_LIBRARY_ROOT` | `./music` (`/music` in Docker) | Downloads land directly here (no inbox folder) |
| `GSM_XML_PATH` | `<data>/rekordbox/getsetmix.xml` | Inbox XML path — used only when no machine profile is configured |
| `GSM_COLLECTION_XML_PATH` | *(unset)* | Full Rekordbox collection XML; when set, already-imported tracks are purged from the inbox XML before each batch |
| `GSM_PLAYLIST_NAME` | `Inbox` | Target playlist inside the XML |
| `GSM_OUTPUT_FORMAT` | `mp3` | `mp3` (320 kbps) or `flac` — global only |
| `GSM_CONCURRENCY` | `2` | Global parallel-download default |
| `GSM_FILENAME_TEMPLATE` | `{artist} - {title}` | Tokens: `{title} {artist} {album} {source} {id} {genre}` |
| `GSM_LANGUAGE` | `en` | `en` or `it` |
| `GSM_THEME` | `dark` | `dark`, `light` or `auto` |
| `GSM_DELIVERY_MODE` | `filesystem` | `filesystem` (shared folder/mount) or `webdav` |
| `GSM_WEBDAV_URL` | *(unset)* | e.g. `https://cloud.example.com/remote.php/dav/files/marco` |
| `GSM_WEBDAV_USER` / `GSM_WEBDAV_PASS` | *(unset)* | Nextcloud user + **app password** |
| `GSM_WEBDAV_ROOT` | *(unset)* | Remote folder the library maps onto, e.g. `Music/DJ` |
| `GSM_AUTH_TOKEN` | *(unset)* | Static token auth (`X-Auth-Token`, `Authorization: Bearer`, or `?token=`) |
| `GSM_BASIC_USER` / `GSM_BASIC_PASS` | *(unset)* | HTTP Basic Auth alternative |

With auth enabled the API and `/metrics` return 401 without credentials; the UI prompts for the token once and stores it in the browser.

## Metrics

`GET /metrics` (Prometheus text format):

```
getsetmix_jobs{status="..."}            # job counts by status
getsetmix_active_downloads
getsetmix_download_duration_seconds_sum / _count
getsetmix_errors_total{source="..."}
getsetmix_songs_downloaded{window="30d"|"365d"|"all"}
getsetmix_healthy
```

`GET /healthz` returns `ok` for probes.

## Development, CI/CD & releases

```bash
pip install -r requirements.txt pytest httpx ruff pre-commit
python -m pytest tests/ -v     # unit + API tests (no network needed)
ruff check app agent tests run_local.py
pre-commit install --hook-type commit-msg --hook-type pre-commit   # local guard rails
```

### Conventional Commits are mandatory

Commit messages **must** follow [Conventional Commits](https://www.conventionalcommits.org/) — versioning is fully automated from them, so a non-conforming message fails CI:

| Commit | Example | Version bump |
|---|---|---|
| `fix:` | `fix: stop crash on empty playlist` | patch — `1.0.0 → 1.0.1` |
| `feat:` | `feat: share target for YouTube` | minor — `1.0.0 → 1.1.0` |
| `feat!:` / `BREAKING CHANGE:` footer | `feat!: drop Python 3.10` | major — `1.0.0 → 2.0.0` |

Other types (`chore`, `docs`, `ci`, `refactor`, `test`, …) are valid and release nothing on their own. The local `commit-msg` hook (from `pre-commit install` above) and the `commitlint.yml` workflow both enforce the format; to hard-block bad commits, enable branch protection on `main` and require the **Commit lint** check.

### Icons

The vectors in `app/static/assets/` are the source of truth — `icon.svg` (the
rounded tile), `icon-maskable.svg` (full-bleed, for PWA safe-zone cropping) and
`mark.svg` (the transparent silhouette, `currentColor`). Every raster is
generated:

```bash
pip install cairosvg pillow
python scripts/build_icons.py     # favicon.ico, icon-192/512.png, icon.png, baked mark variants
```

### CI/CD workflows (`.github/workflows/`)

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | push to `main`, every PR | ruff lint, pytest suite (with ffmpeg), and a no-push Docker build as a PR safety net |
| `commitlint.yml` | push to `main`, every PR | validates commit messages against Conventional Commits |
| `docker-publish.yml` | push to `main` | builds the image for **linux/amd64 + linux/arm64** and pushes to **GHCR** as `latest`, `main`, and the commit SHA |
| `release.yml` | push to `main` | **automated semantic versioning**: bumps the version from the commits, tags `vX.Y.Z`, creates the GitHub Release, builds the standalone executables (Windows / macOS / Linux, PyInstaller) and the immutable versioned images (`:1.2.3`, `:1.2`, `:1`) |
| `pages.yml` | push to `main` touching `site/**` | deploys the landing + docs site in `site/` to **GitHub Pages** |

One-time setup after pushing to GitHub:

1. Replace `Fre0Grella` with your GitHub username in `deploy/k8s/getsetmix.yaml`, `site/*.html`, and this README (`grep -rl Fre0Grella .`).
2. **Settings ▸ Pages ▸ Source: GitHub Actions** to enable the site.
3. After the first publish, **Packages ▸ getsetmix ▸ Package settings ▸ Change visibility** if you want the image public (no `imagePullSecrets` needed in K8s).
4. *(optional)* **Settings ▸ Branches** → protect `main` and require the **Commit lint** check so only Conventional Commits can land.
5. **If `main` requires signed commits**, give the release bot a signing key so its version-bump commit is accepted (run once, locally, with `gh` authenticated):

   ```bash
   ssh-keygen -t ed25519 -C "getsetmix-release-bot" -f gsm_release_key -N ""
   gh ssh-key add gsm_release_key.pub --type signing --title "getsetmix release bot"
   gh secret set SSH_SIGNING_PRIVATE_KEY < gsm_release_key
   gh secret set SSH_SIGNING_PUBLIC_KEY  < gsm_release_key.pub
   rm gsm_release_key gsm_release_key.pub   # the keys now live in GitHub
   ```

   Set `git_committer_email` in `release.yml` to a verified email on the account that owns the signing key so the bot's commits show as **Verified**.

Releasing is automatic — just merge Conventional Commits to `main`:

```text
feat: …  →  semantic-release tags v1.1.0, publishes the GitHub Release with
            getsetmix-windows-x64.exe / -macos-arm64 / -linux-x64, and pushes
            ghcr.io/Fre0Grella/getsetmix:1.1.0 (+ :1.1, :1)
```

The website lives in `site/` — a static landing page (`index.html`) and documentation (`docs.html`), no build step. Edit and push; the workflow handles the rest.

## Project layout

```
app/
  main.py        # FastAPI app, API routes, auth middleware
  worker.py      # asyncio download queue (yt-dlp + ffmpeg)
  metadata.py    # server-side metadata fetch, playlist fan-out
  tagger.py      # ID3v2.4 / FLAC tagging + cover embedding
  rekordbox.py   # DJ_PLAYLISTS XML writer (atomic, corruption-safe)
  profiles.py    # machine profiles + library-relative path mapping
  targets.py     # which XML(s) a finished download is written to
  health.py      # link self-diagnosis (the checks behind the status chip)
  link.py        # pairing + sync API for the companion
  delivery.py    # optional Nextcloud/WebDAV upload
  naming.py      # filename templates + sanitization
  db.py          # SQLite persistence (tracks, history, counters)
  metrics.py     # Prometheus exposition
  config.py      # settings + env overrides
  static/        # the UI (vanilla JS, no build step) — common.js · app.js · setup.js
  static/assets/ # SVG sources of truth + generated rasters (scripts/build_icons.py)
agent/
  gsm_link.py    # the companion that runs on the Rekordbox machine
deploy/
  docker-compose.yml
  k8s/getsetmix.yaml
site/            # landing + docs, deployed to GitHub Pages
tests/           # pytest suite run by CI
.github/workflows/   # ci.yml · docker-publish.yml · pages.yml
run_local.py     # local app mode
```

## API sketch

| Method & path | Purpose |
|---|---|
| `POST /api/tracks {url}` | Add URL (playlist fans out); returns ids + duplicate flag |
| `GET /api/tracks` | All rows + active download count |
| `PATCH /api/tracks/{id}` | Edit metadata (only before download / after error) |
| `DELETE /api/tracks/{id}` | Remove row |
| `POST /api/tracks/{id}/cover` / `GET …/cover` | Upload / fetch cover |
| `GET /api/cover-search?q=` | Cover candidates (iTunes) |
| `POST /api/tracks/{id}/retry` | Retry a failed track |
| `POST /api/batch/start {ids?, concurrency?}` | Start batch |
| `POST /api/batch/cancel` | Cancel batch, re-stage in-flight |
| `GET/PUT /api/settings` | Read / update settings (secrets are never echoed back) |
| `GET/POST /api/profiles` · `PUT/DELETE /api/profiles/{id}` | Machine profiles |
| `POST /api/profiles/preview` | Live preview of the `Location` a profile would produce |
| `GET /api/health/link` | Every link check, with the fix for each failure |
| `POST /api/link/code` | Mint a pairing code (wizard) |
| `POST /api/link/pair` · `POST /api/link/sync` | Companion pairing and heartbeat |
| `GET /api/stats` · `GET /api/history` · `POST /api/purge` | Stats, URL history, manual purge |
