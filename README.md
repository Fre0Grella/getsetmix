# GetSetMix

[![CI](https://github.com/YOUR_USER/getsetmix/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USER/getsetmix/actions/workflows/ci.yml)
[![Publish image](https://github.com/YOUR_USER/getsetmix/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/YOUR_USER/getsetmix/actions/workflows/docker-publish.yml)
[![Deploy site](https://github.com/YOUR_USER/getsetmix/actions/workflows/pages.yml/badge.svg)](https://github.com/YOUR_USER/getsetmix/actions/workflows/pages.yml)


Self-hosted DJ ingestion service for your homelab. Paste a URL (single track or playlist), review and edit the metadata, batch-download to MP3 320 kbps or FLAC, auto-tag with cover art, and ingest straight into your Rekordbox library via XML — all from a fast, MediaHuman-inspired web UI.

![GetSetMix](app/static/assets/logo.png)

> Use GetSetMix only for content you have the rights to download.

## Features

- **Paste & go** — single videos or whole playlists/sets fan out into individual editable rows
- **Metadata review before download** — title + artist required, genre highlighted with a DJ-genre picker, optional album; cover override via cover search (iTunes) or manual upload
- **Batch downloads** — global parallelism default of 2 with per-batch override, per-track status (queued → downloading → tagging → ingested / error), overall batch progress bar, cancel button
- **Failures don't halt the batch** — failed tracks are flagged with per-track retry
- **Tagging** — ID3v2.4 / FLAC Vorbis comments: title, artist, album, genre, embedded cover, source URL in the comment field
- **Filename templates** — `{title} {artist} {album} {source} {id} {genre}`, sanitized, missing tokens omitted, collision-safe suffixes
- **Rekordbox XML** — tracks appended to a configurable XML and an "Inbox" playlist (name configurable); reload the XML source in Rekordbox to see new tracks
- **Persistence** — SQLite for tracks, URL history, and counters; manual purge from the UI
- **Observability** — Prometheus `/metrics`: job counts by status, active downloads, download durations, errors by source, songs in last 30d / 365d / all time, health
- **Private by default** — bind to localhost or your LAN; optional static-token or Basic Auth for public exposure
- **i18n** — Italian (default) and English UI
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
      GSM_LANGUAGE: it          # or en
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
docker build -t ghcr.io/YOUR_USER/getsetmix:latest .
docker push ghcr.io/YOUR_USER/getsetmix:latest

# 2. apply
kubectl apply -f deploy/k8s/getsetmix.yaml
kubectl -n getsetmix get pods
```

Notes:

- `replicas: 1` with `strategy: Recreate` is intentional — state is SQLite on a PVC.
- Mount your real music library into the `music` PVC (or replace it with `hostPath`/NFS as your cluster dictates).
- A Helm chart is not included; the manifests are small enough to kustomize directly.

## Local app mode (Linux / Windows / macOS)

Same UI, not always-on — auto-opens your browser:

```bash
pip install -r requirements.txt
# ffmpeg must be on PATH (apt install ffmpeg / brew install ffmpeg / winget install ffmpeg)
python run_local.py            # opens http://127.0.0.1:8765
python run_local.py --port 9000 --no-browser
```

## Using it

1. Click **Incolla link** — the URL on your clipboard is added (playlists fan out into one row per entry).
2. Rows resolve their metadata; fix title/artist, pick a genre, optionally set album and cover (camera button on the thumbnail → search or upload).
3. Press **Scarica** to start the batch (the ×N selector overrides parallelism for this batch only). Edits lock once a track is queued.
4. Watch per-track progress and the batch bar; cancel anytime (in-flight tracks are stopped and re-staged).
5. When tracks show **Finito**, open Rekordbox → **File ▸ Import collection / reload the rekordbox.xml source** and find them in the **Inbox** playlist.

In Rekordbox, point *Preferences ▸ Advanced ▸ Database ▸ rekordbox xml* at the XML path shown in Settings (default `<data>/rekordbox/getsetmix.xml`), then refresh the *rekordbox xml* tree in the sidebar after each batch.

## Configuration

Everything is editable in the UI (gear icon) and persisted to `<data>/config.json`. Environment variables override on boot:

| Variable | Default | Purpose |
|---|---|---|
| `GSM_DATA_DIR` | `./data` (`/data` in Docker) | SQLite DB, config, covers, default XML location |
| `GSM_LIBRARY_ROOT` | `./music` (`/music` in Docker) | Downloads land directly here (no inbox folder) |
| `GSM_XML_PATH` | `<data>/rekordbox/getsetmix.xml` | Rekordbox XML path |
| `GSM_PLAYLIST_NAME` | `Inbox` | Target playlist inside the XML |
| `GSM_OUTPUT_FORMAT` | `mp3` | `mp3` (320 kbps) or `flac` — global only |
| `GSM_CONCURRENCY` | `2` | Global parallel-download default |
| `GSM_FILENAME_TEMPLATE` | `{artist} - {title}` | Tokens: `{title} {artist} {album} {source} {id} {genre}` |
| `GSM_LANGUAGE` | `it` | `it` or `en` |
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
pip install -r requirements.txt pytest httpx ruff
python -m pytest tests/ -v     # unit + API tests (no network needed)
ruff check app tests run_local.py
```

Three GitHub Actions workflows ship with the repo (`.github/workflows/`):

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | push to `main`, every PR | ruff lint, pytest suite (with ffmpeg), and a no-push Docker build as a PR safety net |
| `docker-publish.yml` | push to `main`, tags `v*.*.*` | builds the image for **linux/amd64 + linux/arm64** and pushes to **GHCR** with smart tags: `latest` + `main` on main; `1.2.3`, `1.2`, `1` and the commit SHA on a `v1.2.3` tag |
| `pages.yml` | push to `main` touching `site/**` | deploys the landing + docs site in `site/` to **GitHub Pages** |

One-time setup after pushing to GitHub:

1. Replace `YOUR_USER` with your GitHub username in `deploy/k8s/getsetmix.yaml`, `site/*.html`, and this README (`grep -rl YOUR_USER .`).
2. **Settings ▸ Pages ▸ Source: GitHub Actions** to enable the site.
3. After the first publish, **Packages ▸ getsetmix ▸ Package settings ▸ Change visibility** if you want the image public (no `imagePullSecrets` needed in K8s).

Releasing is just a tag:

```bash
git tag v1.0.0 && git push origin v1.0.0
# → ghcr.io/YOUR_USER/getsetmix:1.0.0 (+ :1.0, :1, :latest)
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
  naming.py      # filename templates + sanitization
  db.py          # SQLite persistence (tracks, history, counters)
  metrics.py     # Prometheus exposition
  config.py      # settings + env overrides
  static/        # the UI (vanilla JS, no build step)
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
| `GET/PUT /api/settings` | Read / update settings |
| `GET /api/stats` · `GET /api/history` · `POST /api/purge` | Stats, URL history, manual purge |
