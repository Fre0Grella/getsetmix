# DJ Ingestion Service - Design Spec

Self-hosted service that discovers, downloads, tags, and ingests tracks into the Rekordbox Library from a URL. Rekordbox is the first supported target; the design keeps room for other targets later.

## Scope and assumptions

- Single-tenant instance
- Private-by-default access; optional Basic Auth or static token if exposed publicly
- Lightweight target: <= 512 MB RAM for the server

## User flow

1. Open the service from a domain or local app.
2. Paste a URL (single track or playlist/set).
3. Server fetches metadata and validates the source (YouTube or SoundCloud); UI shows the detected source and metadata.
4. Review and edit metadata (title and artist required; genre highlighted; album optional). Cover image can be overridden via source image search, with manual upload as a fallback.
5. Add to the staging list; repeat as needed.
6. Start a batch download. Show per-track status (queued, downloading, tagging, ingested, error) plus overall batch progress.
7. When complete, reload the Rekordbox XML source to see new tracks in the Inbox playlist.

## Core components

- **API + UI**: FastAPI server hosting a lightweight web UI (prefer a small framework; fall back to static HTML/JS if needed).
- **Ingestion worker**: Runs in-process by default, with an optional separate worker process for scale.
- **Source adapters**: YouTube and SoundCloud first. Playlist/set URLs expand into multiple staged tracks.
- **Metadata/tagger**: Writes ID3/FLAC tags and embeds cover art.
- **Rekordbox XML writer**: Appends tracks to the Rekordbox XML and the Inbox playlist.

## Batching, queueing, and status

- Staging list with explicit batches; default batch includes items not already downloaded (URL history + optional title/artist warning).
- Parallel downloads: global default 2, with optional per-batch override.
- Download order is not guaranteed (parallel execution).
- If a batch is running, newly staged items wait for the next batch.
- Metadata edits allowed only before download starts.
- Failed tracks do not halt the batch; they are marked error with per-track retry.

## Metadata and files

- Server-side metadata fetch; client may show a source hint.
- If metadata fetch fails, allow manual entry to continue.
- Tags include title, artist, album (if provided), genre (if provided), cover image, and the source URL in a comment field.
- Output format: MP3 320 kbps by default; optional FLAC. Output format is global only.
- Filename template tokens: {title}, {artist}, {album}, {source}, {id}, optional {genre}.
- Sanitize filenames (strip illegal characters, normalize whitespace). Omit missing token segments.
- If a filename already exists, append a short suffix and log a warning.
- Download directly into the configured library root (no inbox folder).

## Persistence

- Active batches and staging list are in-memory only (persist across page refresh, lost on service restart).
- URL history and counters are persisted on disk (SQLite or a small file); retain indefinitely with a manual purge option.

## Rekordbox integration

- Use Rekordbox XML import format only (no direct DB integration).
- XML path is configurable.
- Default target playlist is "Inbox."
- Manual Rekordbox XML reload is required after ingestion.

## API surface (draft)

- POST /batches - create a new batch (default: only items not already downloaded)
- POST /batches/{id}/items - add URL(s) to a batch (single track or playlist/set)
- POST /batches/{id}/start - start ingestion for the batch
- GET /batches/{id} - batch status and per-track statuses
- GET /health - liveness check
- GET /metrics - Prometheus metrics

Progress updates are provided via polling.

## Observability

- Structured JSON logs to stdout with batch_id and track_id on every log line.
- /metrics includes:
  - Job counts by status
  - Active downloads
  - Download duration
  - Errors by source
  - Songs downloaded in last 30 days, last 365 days, and all time

## Deployment targets

- **Kubernetes first-class**: plain manifests, optional Helm note.
- **Docker recommended**: include a brief Compose example in the deployment guide.
- **Local app mode**: same web UI, not always-on; auto-opens a browser window on start.
- **OS**: Linux primary for server deployments; Windows/macOS supported for local app mode.

## Module architecture (draft)

This section defines initial seams and deep modules using the domain language in CONTEXT.md.

### Ingestion Batch module

**Interface**: create an Ingestion Batch, add Source URLs or a Source Collection, edit Track Metadata until downloading starts, start ingestion, and read Ingestion Status. The module owns duplicate detection (Source URL or filename match) and delegates download execution to the **Download Orchestrator**.

**Implementation**: maintains the Staged Track list in-memory, enforces Ingestion Status transitions, and coordinates per-track retries without leaking those rules to callers. The module calls a separate persistence module for URL history and filename index lookups and invokes the **Download Orchestrator** for concurrency and execution.

**Depth**: callers get a small, stable interface while batch rules, ordering, and error handling stay inside the module. This concentrates locality for changes to batching and status behavior.

**Tests**: the interface is the test surface. Tests should cover status transitions, metadata edit windows, and duplicate detection without reaching into the implementation.

### Download Orchestrator module

**Interface**: accept a set of Staged Tracks to download, enforce global default concurrency with optional per-batch override, and report per-track completion or failure events to the **Ingestion Batch**.

**Implementation**: runs downloads in parallel with bounded concurrency, preserves the caller-defined ordering semantics (no guaranteed order), and emits completion events for status updates. This module is a seam so the **Ingestion Batch** can be tested with an adapter that simulates timing and failures.

**Depth**: callers get leverage by delegating execution and concurrency to one place, improving locality for download behavior and performance tuning.

**Tests**: the interface is the test surface. Tests should cover concurrency limits, per-batch overrides, error propagation, and retry signalling without reaching into the implementation.

### URL history + filename index module

**Interface**: record and query ingested Source URLs and filenames for the Rekordbox Library.

**Implementation**: disk-backed store (SQLite or a small file) with a lightweight in-memory cache. This module is a seam so the Ingestion Batch module can be tested with an adapter.

### Ingestion Status state machine

**Interface**: validate allowed transitions between queued, downloading, tagging, ingested, and error.

**Implementation**: colocated inside the Ingestion Batch module for locality, unless a second adapter makes the seam real.
