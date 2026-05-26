# DJ Ingestion Service

A self-hosted service that discovers, downloads, tags, and ingests tracks into a DJ library, with Rekordbox as the first supported target.

## Language

**Rekordbox Library**:
The target DJ library that receives ingested tracks; currently the only supported library.
_Avoid_: DJ library, target library

**Source Adapter**:
A component that recognizes a URL and extracts audio + metadata from a specific platform (e.g., YouTube, SoundCloud).
_Avoid_: provider, downloader

**Source URL**:
The original URL submitted by the user to ingest a track or a **Source Collection**.
_Avoid_: link

**Source Collection**:
A playlist or set URL that expands into multiple tracks.
_Avoid_: batch URL

**Ingestion Batch**:
A set of staged tracks submitted together for download and tagging.
_Avoid_: queue, playlist

**Download Orchestrator**:
The module that executes downloads and enforces concurrency for an **Ingestion Batch**.
_Avoid_: scheduler, worker

**Staged Track**:
An entry in the staging list representing a URL + metadata before download starts.
_Avoid_: job, item

**Track Metadata**:
Descriptive fields attached to a track (title, artist, album, genre, cover image, etc.).
_Avoid_: tags, info

**Ingestion Status**:
The lifecycle state of a **Staged Track** (queued, downloading, tagging, ingested, error).
_Avoid_: state

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
- Each **Staged Track** records its **Source URL** for traceability.
- A **Source Collection** expands into multiple **Staged Tracks**.
- An **Ingestion Batch** contains one or more **Staged Tracks**.
- Each **Staged Track** has **Track Metadata** that can be auto-detected and then confirmed.
- Each **Staged Track** has an **Ingestion Status**.
- The **Inbox Playlist** belongs to the **Rekordbox Library**.
- The **Rekordbox XML** describes tracks in the **Rekordbox Library**.

## Example dialogue

> **Dev:** "When a track finishes ingesting, does it always land in the **Rekordbox Library**?"
> **Domain expert:** "Yes — Rekordbox is the only target right now."
