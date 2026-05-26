# DJ Ingestion Service

A self-hosted service that discovers, downloads, tags, and ingests tracks into a DJ library, with Rekordbox as the first supported target.

## Language

**Rekordbox Library**:
The target DJ library that receives ingested tracks; currently the only supported library.
_Avoid_: DJ library, target library

**Source Adapter**:
A component that recognizes a URL and extracts audio + metadata from a specific platform (e.g., YouTube, SoundCloud).
_Avoid_: provider, downloader

**Adapter Runtime**:
The Python subservice that hosts **Source Adapters** and executes metadata + asset fetching.
_Avoid_: adapter service, source adapter host

**Source URL**:
The original URL submitted by the user to ingest a track or a **Source Collection**.
_Avoid_: link

**Source Collection**:
A playlist or set URL that expands into multiple tracks.
_Avoid_: batch URL

**Ingestion Batch**:
A set of staged tracks submitted together for download and tagging.
_Avoid_: queue, playlist

**Preview Job**:
An async job that asks the **Adapter Runtime** to fetch a **Metadata Preview** for a **Source URL**.
_Avoid_: metadata fetch job

**Download Orchestrator**:
The module that executes downloads and enforces concurrency for an **Ingestion Batch**.
_Avoid_: scheduler, worker

**Staged Track**:
An entry in the staging list representing a URL + metadata before download starts.
_Avoid_: job, item

**Track Placeholder**:
A temporary entry created immediately after a URL is submitted, before **Metadata Preview** is available.
_Avoid_: draft track, preview placeholder

**Track Metadata**:
Descriptive fields attached to a track (title, artist, album, genre, cover image, etc.).
_Avoid_: tags, info

**Metadata Preview**:
The **Track Metadata** fetched from a **Source Adapter** before download so a user can confirm or edit it.
_Avoid_: detected metadata, staged metadata

**Ingestion Status**:
The lifecycle state of a **Staged Track** (queued, downloading, tagging, ingested, error).
_Avoid_: state

**Duplicate Override**:
An explicit user-confirmed allowance to ingest a **Source URL** or filename seen before.
_Avoid_: duplicate ignore

**Filename Template**:
A tokenized pattern that defines how downloaded files are named (e.g., "{title} - {artist}").
_Avoid_: naming string

**Output Format**:
The audio encoding produced by the service (default MP3 320kbps; optional FLAC).
_Avoid_: codec

**Inbox Playlist**:
The default Rekordbox playlist where newly ingested tracks appear.
_Avoid_: import list

**Rekordbox XML**:
The Rekordbox-importable XML file that the service appends tracks to.
_Avoid_: library file

## Relationships

- A **Source Adapter** handles URLs from one or more source platforms.
- Each **Source URL** is handled by exactly one **Source Adapter** for metadata + cover fetching.
- A **Preview Job** produces a **Metadata Preview**.
- Each **Staged Track** records its **Source URL** for traceability.
- A **Source Collection** expands into multiple **Staged Tracks**.
- An **Ingestion Batch** contains one or more **Staged Tracks**.
- A **Track Placeholder** is promoted to a **Staged Track** once its **Metadata Preview** arrives.
- Each **Staged Track** has **Track Metadata** that can be auto-detected and then confirmed.
- Each **Staged Track** has an **Ingestion Status**.
- A **Staged Track** may carry a **Duplicate Override**.
- The **Inbox Playlist** belongs to the **Rekordbox Library**.
- The **Rekordbox XML** describes tracks in the **Rekordbox Library**.

## Example dialogue

> **Dev:** "When a track finishes ingesting, does it always land in the **Rekordbox Library**?"
> **Domain expert:** "Yes — Rekordbox is the only target right now."
