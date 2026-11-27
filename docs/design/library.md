# Library module

| | |
|---|---|
| **Status** | **approved** by the maintainer on 2026-11-14. The two proposals left open on approval, 17 (fields with several values) and 18 (a full date when the year is edited), were decided on 2026-11-14 as proposed; see [section 6](#6-decisions-and-open-questions). Section [4.6.1](#461-the-companions-view-of-server-changes-consolidation), added on 2026-11-24, was **approved** on 2026-11-24 with its five open questions decided as recommended |
| **Issues** | design [#19](https://github.com/Fre0Grella/getsetmix/issues/19), feature [#11](https://github.com/Fre0Grella/getsetmix/issues/11), roadmap [#12](https://github.com/Fre0Grella/getsetmix/issues/12) |
| **Date** | 2026-11-13 |

System-level decisions are in the
[decision log](../architecture.md#9-decision-log) and are not repeated here.
This design rests on four of them: a track is identified by a hash of its
audio (decision 4), files are not renamed in this version (decision 5),
features run wherever the app runs (decision 3), and only components that
allow commercial use ship (decision 2). It adds no new dependency: tags are
read and written with mutagen, hashes come from the standard libraries.

The choices this draft proposed were reviewed with the maintainer and are
recorded under [Decisions and open questions](#6-decisions-and-open-questions).
Every proposal of the draft has been decided.

The batch editing module ([`batch-editing.md`](batch-editing.md),
[#20](https://github.com/Fre0Grella/getsetmix/issues/20)) builds on this
one. What it needs from the Library is designed here, where it belongs: a
checked write of several fields, year and comment as editable fields, and
values indexed exactly as the file holds them.

## 1. Goals and non-goals

### Goals

- **A Library view** of every audio file under the library root, on a phone
  and on a desktop: search, sort, filter, play a preview.
- **Fix a track for good**: edit title, artist, album, genre, year,
  comment and cover, and have the edit reach the file, every paired computer
  and Rekordbox.
- **Delete, recoverably**: a delete moves the file to a trash folder, can be
  undone, and is purged after a set number of days.
- **Bulk actions** on a selection: delete, restore, set genre.
- **Computers follow, carefully**: a paired computer learns which tracks
  changed and which were deleted. It never deletes anything from Rekordbox
  on its own.
- **The same in local mode**: with no server, the view and the index work
  over the library on the DJ's computer.
- **A stable identity** per track that later modules (batch editing,
  analysis) can key their data on.

### Non-goals

- **Renaming or moving files.** Not from the template, not in bulk, not per
  track. A rename done *outside* GetSetMix is followed, not caused.
- **Batch rules** (case fixes, "feat." handling, find and replace). That is
  the batch editing module,
  [#20](https://github.com/Fre0Grella/getsetmix/issues/20).
- **Analysis** of any kind: BPM, key, similarity.
- **Online tag lookup and audio duplicates.** Out of the roadmap
  (decision 6).
- **Users and permissions.** The app stays single-user.
- **Two-way sync.** A computer still cannot change the server's library.

## 2. Where things stand

Checked against the code on 2026-11-13.

| Fact | Where |
|---|---|
| The app only knows tracks it downloaded. The `tracks` table is the download queue; *Clear finished rows* deletes ingested rows. | `app/db.py` |
| `/api/link/files` walks the disk on every request and returns `path`, `size`, `mtime` per file. Names starting with `.` or `~`, or ending in `.part` or `.tmp`, are skipped, folders included. | `app/link.py` |
| The worker tags a download in the temp folder and then moves it into the library root (since [#33](https://github.com/Fre0Grella/getsetmix/pull/33)). Nothing records the file in a table that outlives *Clear finished rows*. | `app/worker.py`, `_process` |
| The tagger writes MP3 (ID3v2.4) and FLAC only, always rewrites title, artist and comment, and is only ever called on a fresh download. | `app/tagger.py` |
| The link serves nine extensions: mp3, flac, m4a, aac, aif, aiff, wav, ogg, opus. | `app/link.py` |
| The companion imports seven of them. Ogg and Opus files are downloaded and then ignored, because Rekordbox cannot import them. | `companion/internal/audio/probe.go` |
| `fetched.json` maps a server path to the time it was fetched. A path in it is never fetched again. | `companion/internal/fetch` |
| `state.json` maps a local path key to the time the importer handled it. | `companion/internal/config` |
| The importer only inserts rows. It skips a file whose path is already in the collection. | `companion/internal/library/import.go` |
| The UI polls `/api/tracks` every 1.2 to 4 seconds and gets the whole list each time. Rows are reconciled by id; nothing is virtualised. | `app/static/app.js` |

## 3. Interfaces and data contracts

### 3.1 Track identity

A track's identity, its **audio id**, is a string:

```text
a1_3f9c0d2a7b1e4c5d8a6f0b9e2d7c1a45
```

| Part | Meaning |
|---|---|
| `a` | computed from the audio payload, so it survives tag edits, moves and renames |
| `1` | version of the algorithm; a change to the rules below makes it `a2` |
| 32 hex digits | the first 128 bits of the SHA-256 of the payload, lowercase |

A file whose container cannot be parsed gets a **fallback id**, `f1_` plus
the same 128 bits over the whole file. It is honest about being weaker: it
changes when anything in the file changes. Files with a fallback id are
listed and can be deleted, but their tags cannot be edited in GetSetMix, so
GetSetMix itself never changes their id.

The payload per container is defined in [4.2](#42-the-audio-hash).

### 3.2 The index

Two tables in `getsetmix.db`, next to the existing ones.

```sql
CREATE TABLE library_files (
    id               INTEGER PRIMARY KEY,      -- key used by the Library API
    path             TEXT    NOT NULL,         -- library-relative, "/"-separated; unique among
                                               -- present and missing rows (a partial index):
                                               -- a tombstone keeps its last path
    audio_id         TEXT    NOT NULL,         -- "a1_…" or "f1_…"
    size             INTEGER NOT NULL,         -- bytes, as last seen
    mtime_ns         INTEGER NOT NULL,         -- as last seen
    format           TEXT    NOT NULL,         -- "mp3", "flac", "m4a", …
    title            TEXT    NOT NULL DEFAULT '',
    artist           TEXT    NOT NULL DEFAULT '',
    album            TEXT    NOT NULL DEFAULT '',
    genre            TEXT    NOT NULL DEFAULT '',
    year             INTEGER,
    comment          TEXT    NOT NULL DEFAULT '',
    has_cover        INTEGER NOT NULL DEFAULT 0,
    multi            TEXT    NOT NULL DEFAULT '',  -- fields holding several values, e.g. "artist,genre"
    duration         REAL,                     -- seconds
    bitrate          INTEGER,                  -- kbps
    sample_rate      INTEGER,
    source_url       TEXT    NOT NULL DEFAULT '',  -- from the download, when known
    search           TEXT    NOT NULL,         -- lowercased, accents folded
    added_at         TEXT    NOT NULL,         -- when it was downloaded or first seen; in the
                                               -- first index, the file's own modification time
    rev              INTEGER NOT NULL,         -- change number of the last change
    content_rev      INTEGER NOT NULL,         -- change number of the last change of the
                                               -- file's bytes: the link's files[].rev (3.5)
    state            TEXT    NOT NULL DEFAULT 'present',
                     -- present | missing | trashed | gone
    state_changed_at TEXT,
    trash_path       TEXT                      -- set when trashed; kept after the purge, so a
                                               -- gone tombstone still says "deleted" (3.5)
);
CREATE INDEX library_files_audio ON library_files (audio_id);
CREATE INDEX library_files_state ON library_files (state, rev);

CREATE TABLE library_meta (
    key   TEXT PRIMARY KEY,   -- 'rev', 'last_reconcile', 'indexed', 'unavailable'
    value TEXT
);
```

- `rev` is one counter for the whole library. Every change to a row (new,
  tags changed, moved, trashed, restored, gone) takes the next value.
- `audio_id` is not unique. Two files with the same audio are two rows, and
  the view says so. The link lists only one of them (the oldest row), so a
  computer fetches the audio once.
- A row in state `trashed` or `gone` is a **tombstone**. It keeps the audio
  id, the last path and the time.
- **Tag columns hold the file's values exactly.** `title`, `artist`,
  `album`, `genre` and `comment` are stored as they are in the file: not
  trimmed, not case-folded, nothing normalised. Lowercasing and accent
  folding exist only in `search`. A caller that shows "the old value" of a
  field, as the batch editing preview does, shows what the file holds.
- `year` is the year of the file's date tag (`TDRC` in ID3, `date` in
  Vorbis comments), or empty.
- **Several values in one field** (decision 17). A file can hold several
  values for a field: a multi-value `TPE1`, or several `ARTIST` comments in
  a FLAC. The index stores them joined with `"; "` in file order, and names
  the field in `multi`. Reading never changes the file. An edit of such a
  field writes the one value it was given, as one value: the text is not
  split on `"; "`. A field that is not edited keeps its several values.

### 3.3 Library API

All under `/api/library`, behind the same auth as the rest of `/api`.

| Method and path | Purpose |
|---|---|
| `GET /api/library` | list: search, filter, sort, paging |
| `GET /api/library/facets` | genres and folders with counts |
| `GET /api/library/status` | current `rev`, counts per state, last reconcile, `unavailable` flag |
| `POST /api/library/rescan` | reconcile now |
| `GET /api/library/{id}` | one file, all fields |
| `PATCH /api/library/{id}` | edit tags |
| `POST /api/library/{id}/cover` | replace the embedded cover (upload, or `{"url": …}`) |
| `GET /api/library/{id}/cover` | the embedded cover; `?size=thumb` a small JPEG of it, for the list |
| `GET /api/library/{id}/audio` | the file, with range requests, for the preview |
| `DELETE /api/library/{id}` | move to trash |
| `POST /api/library/{id}/restore` | bring back from trash |
| `POST /api/library/bulk` | delete, restore or set genre on many |
| `DELETE /api/library/trash` | purge the trash now |

**List.** `GET /api/library?q=&genre=&folder=&state=present&sort=added&order=desc&limit=200&cursor=`

| Parameter | Values | Default |
|---|---|---|
| `q` | free text, matched against `search` (title, artist, album, genre, file name); every word has to match | none |
| `genre`, `folder` | exact match; `folder` is a library-relative directory and matches the files directly in it | none |
| `state` | `present`, `trashed` | `present` |
| `sort` | `added`, `artist`, `title`, `genre` | `added` |
| `order` | `asc`, `desc` | `desc` for `added`, else `asc` |
| `limit` | 1 to 500 | 200 |
| `cursor` | opaque, from the previous page's `next` | none |

```json
{
  "rev": 4812,
  "total": 3274,
  "next": "eyJrIjpbIjIwMjYtMTEtMTIiLDMxOV19",
  "items": [
    {
      "id": 319,
      "audio_id": "a1_3f9c0d2a7b1e4c5d8a6f0b9e2d7c1a45",
      "path": "Artist - Title.mp3",
      "format": "mp3",
      "title": "Title", "artist": "Artist", "album": "", "genre": "House",
      "year": null, "duration": 312.4, "has_cover": true,
      "size": 12518400, "added_at": "2026-11-12T21:04:10+00:00",
      "content_rev": 4801,
      "editable": true,
      "multi": [],
      "same_audio": []
    }
  ]
}
```

`editable` is false for formats the tagger cannot write and for fallback
ids. `multi` names the fields that hold several values in the file.
`same_audio` lists the ids of other files with the same audio id. The item
of `GET /api/library/{id}` also carries `comment`, `bitrate`, `sample_rate`
and `source_url`.

The query behind the list is one internal function,
`library.select(filter)`. Besides serving the pages above, it resolves a
filter (`q`, `genre`, `folder`, `state`) to the full set of matching ids,
each with its `editable` flag, without paging. The batch editing module uses
it to turn "everything matching this filter" into a selection.

**Edit.** `PATCH /api/library/{id}` with any of the fields below. Only the
fields sent are written; every other tag in the file stays as it is. All the
fields of one request are written in one step and take one `rev`.

| Field | Value |
|---|---|
| `title`, `artist`, `album`, `genre` | text; `""` clears the tag |
| `year` | an integer from 1000 to 9999, or `null` to clear it |
| `comment` | text; `""` clears the tag |
| `expect` | optional: an object with the values the caller believes some of these fields hold now |

```json
{ "genre": "Tech House", "year": 2019, "expect": { "genre": "tech-house" } }
```

With `expect`, the write happens only if every named field still holds the
given value in the file. If one differs, nothing is written and the answer
says which:

```json
{ "detail": "the file changed", "differs": { "genre": "House" } }
```

| Answer | When |
|---|---|
| `200` with the updated item | written, index updated, `rev` advanced |
| `400` | a value is not valid for its field (a year out of range) |
| `409` | the format is read-only in this version, or the id is a fallback id |
| `410` | the file is in the trash or gone |
| `412` | `expect` did not match; `differs` holds the file's current values |
| `423` | the file is in use (Windows, local mode, a deck has it loaded) |

`PATCH` is a thin caller of the internal write described in
[4.3](#43-editing-tags), which other modules call without HTTP.

**Bulk.** `POST /api/library/bulk`

```json
{ "ids": [319, 320, 512], "action": "set_genre", "genre": "Tech House" }
```

`action` is `delete`, `restore` or `set_genre`. The answer lists the outcome
per id, so one failure does not hide the rest:

```json
{ "done": [319, 512], "failed": [{ "id": 320, "status": 409, "detail": "read-only format" }] }
```

Once the batch editing module exists, `set_genre` creates one of its edits,
so a bulk genre change is previewed, journalled and undoable like every
other change to many tags. The request stays the same. Until then it works
as described here. Bulk delete and restore stay in this module either way.

**Settings.** One new setting, `trash_days` (`GSM_TRASH_DAYS`, default 30;
0 keeps the trash until it is purged by hand).

### 3.4 Tag fields per format

| Format | Listed and searchable | Tags read | Tags editable in this version | Delete |
|---|---|---|---|---|
| MP3 | yes | ID3v2 | **yes** (written as ID3v2.4) | yes |
| FLAC | yes | Vorbis comments | **yes** | yes |
| M4A | yes | MP4 atoms | no, read-only | yes |
| AIFF | yes | ID3 chunk | no, read-only | yes |
| WAV | yes | ID3 chunk, where present | no, read-only | yes |
| AAC (raw) | yes | none | no | yes |
| Ogg, Opus | yes | Vorbis comments | no, read-only | yes |

The worker only produces MP3 and FLAC, so everything GetSetMix downloaded is
editable. The read-only formats are files the DJ put in the library by other
means. mutagen can write M4A and AIFF; adding them is a later slice, once
their audio hash is covered by fixtures.

What an edit writes, per field:

| Field | MP3 (ID3v2.4) | FLAC (Vorbis comment) |
|---|---|---|
| Title | `TIT2` | `title` |
| Artist | `TPE1` | `artist` |
| Album | `TALB` | `album` |
| Genre | `TCON` | `genre` |
| Year | `TDRC` | `date` |
| Comment | `COMM` (language `eng`, empty description) | `comment` |
| Cover | `APIC` (type 3, front cover) | `PICTURE` block (type 3) |

- **Year.** The download path never writes a year, so today no downloaded
  file has one. When a file holds a full date (`2019-06-14`) and the year is
  not edited, the date is not touched. When the year is edited, the tag is
  written as the year alone (decision 18).
- **Comment.** For a downloaded track the comment is
  `Source: <url> | via GetSetMix`, the only record of the track's origin
  inside the file. It is editable, but the detail sheet asks before it
  replaces a comment that holds a source link.
- **Other tags** (BPM, key, label, remixer, track number, anything a DJ app
  wrote) are never changed by an edit.

### 3.5 Link protocol 2

`GET /api/link/files` keeps its shape and gains fields. Old companions
ignore what they don't know.

```json
{
  "version": "1.9.0",
  "protocol": 2,
  "rev": 4812,
  "files": [
    {
      "path": "Artist - Title.mp3",
      "size": 12518400,
      "mtime": 1794517450,
      "id": "a1_3f9c0d2a7b1e4c5d8a6f0b9e2d7c1a45",
      "rev": 4790
    }
  ],
  "removed": [
    {
      "id": "a1_9b2e…",
      "path": "Other - Track.mp3",
      "at": "2026-11-12T22:10:03+00:00",
      "reason": "deleted"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `protocol` | `2`. Absent means protocol 1: the fields below are missing. |
| `rev` (top) | the library's current change number |
| `files[].id` | the audio id |
| `files[].rev` | the change number of the last time this file's bytes changed |
| `removed[]` | tombstones: tracks trashed in GetSetMix (`deleted`) or that vanished from the disk (`missing`) |

`GET /api/link/file?path=` is unchanged.

A companion does not download a file Rekordbox cannot import
(Ogg and Opus today), and its `status` says how many it skipped and why.
The server keeps listing them, so the Library view stays complete
([#31](https://github.com/Fre0Grella/getsetmix/issues/31)).

**Compatibility.**

| Companion | Server | Behaviour |
|---|---|---|
| old | new | Reads `path`, `size`, `mtime`, ignores the rest. Works as today: no changed tracks, no deletes. |
| new | old | No `protocol` field, so it works as today, keyed by path. |
| new | new | Full behaviour. |

Until the first index of an existing library is complete, a new server
answers as protocol 1, from a disk walk as today. A computer never waits for
the index.

### 3.6 The companion's state

`fetched.json` becomes version 2, keyed by audio id:

```json
{
  "version": 2,
  "tracks": {
    "a1_3f9c…": {
      "path": "Artist - Title.mp3",
      "rev": 4790,
      "at": "2026-11-12T21:10:00Z",
      "tags": { "title": "Title", "artist": "Artist", "album": "", "genre": "House",
                "year": 2019, "comment": "Source: https://… | via GetSetMix" }
    }
  },
  "legacy": { "Gone From Server.mp3": "2026-10-01T18:00:00Z" },
  "removed": { "a1_9b2e…": { "path": "Other - Track.mp3", "at": "2026-11-12T22:15:00Z",
                             "reason": "deleted" } }
}
```

| Key | Meaning |
|---|---|
| `tracks` | what this computer has fetched: the server path, the `rev` it holds, the six tag fields it last saw (title, artist, album, genre, year, comment), and `pending` while a newer copy is in place that the Rekordbox row does not have yet ([#37](https://github.com/Fre0Grella/getsetmix/issues/37)) |
| `legacy` | paths from the old file that the server no longer lists; kept so they are never fetched again if they come back |
| `removed` | tombstones already handled, for tracks this computer holds: the server path, when, the reason, and `recycle` / `recycled` for the opt-in local delete. The first draft held the time alone; that form still reads. Built in [#38](https://github.com/Fre0Grella/getsetmix/issues/38): the path is kept because a track known from `legacy` has no `tracks` entry to take it from |
| `skipped` | listed files of the last fetch that Rekordbox cannot import, counted by extension, for `status` |

While the server speaks protocol 1 the file stays version 1, so an older
companion can still read it.

`state.json` (which local files the importer has handled) stays keyed by
local path, since nothing is renamed. Its values grow from a time to
`{at, size, mtime}`, for telling that a handled file has changed where no
fetch says so: synced folders, slice 7. A fetched track is followed by its
`pending` mark ([4.6](#46-what-a-computer-does)). It gains `removed`: the local
paths the importer has listed in the *removed on server* playlist, so none
is listed twice and a restore can take it out again.

## 4. Design

### 4.1 The index and how it stays true

The disk is the truth. The index is a cache of it that can be rebuilt at any
time.

```mermaid
stateDiagram-v2
    [*] --> present: found on disk, or downloaded
    present --> present: tags changed / moved outside
    present --> trashed: delete in GetSetMix
    trashed --> present: restore
    trashed --> gone: purge after trash_days
    present --> missing: not on disk at reconcile
    missing --> present: back on disk
    missing --> gone: still missing after the grace time
    gone --> [*]
```

**Reconcile** is one pass that brings the index in line with the disk:

1. Walk the library root with the same skip rules as the link (`.`, `~`,
   `.part`, `.tmp`), and skip files modified in the last 10 seconds, the
   settle time the companion already uses. A file in its settle time that
   already has a row is left as it is: not read again, not marked missing.
2. A path whose `size` and `mtime_ns` match its row is unchanged. Nothing is
   read. This is the common case and costs one `stat` per file.
3. A path with no row is hashed and its tags are read. If a row with the
   same audio id is `missing`, or its path vanished in this same pass, the
   file was moved or renamed outside GetSetMix: that row takes the new path.
   A move seen in one pass is therefore a move, not a delete and an add, and
   it does not count towards the guard below. Otherwise it is a new row.
4. A path whose size or time changed is hashed again. Same audio id: the
   tags changed outside GetSetMix; they are read again. Different audio id:
   the content was replaced. The old row becomes `gone` at once, with no
   grace time, and a new row is inserted.
5. A `present` row whose path is not on disk becomes `missing`. It becomes
   `gone` only when it is still missing after the grace time, 24 hours.
   Sync clients delete and recreate files while they update them, and a
   folder can be reorganised by hand over an evening; a day leaves room for
   both.
6. Every change takes the next `rev`.

**The guard.** If one pass would mark more than 20% of the library, and more
than 10 files, as missing, it marks none and sets `unavailable`. The size of
the library is the number of `present` rows before the pass. While the guard
is tripped nothing moves from `missing` to `gone` either. An unmounted
volume or a network share that dropped must never look like a mass delete.
The Library view shows a banner, and the next pass that does not trip the
guard clears it.

**The date a track was added.** A downloaded track is dated when the worker
places it. A file the index finds later is dated when it is first seen. The
first index of an existing library is the exception: every file would get
the same date, so each is dated by its own modification time and sorting by
"added" means something from the start.

**When it runs.**

| Trigger | Why |
|---|---|
| App start | catch what changed while it was off |
| Every 5 minutes | files added, changed or removed by Nextcloud, Syncthing or by hand |
| `/api/link/files`, if the last pass is older than 60 seconds | computers see new tracks as fast as today |
| `POST /api/library/rescan`, and opening the Library view | the DJ wants it now |
| The worker, directly | a finished download is inserted without a walk |

Passes never overlap; a trigger during a pass is dropped.

**The worker.** A download is tagged in the temp folder and then moved into
the library, so a computer never sees an untagged track. This design adds
the last step: the worker inserts the row right after the move, so the row
is there the moment the file is.

**First run over an existing library.** Every file is hashed once, in the
background, in batches committed as they go, so a restart resumes. The
Library view shows progress and lists what is indexed so far.

**Cost.** Estimated for 3,000 tracks of about 10 MB, then measured in the
first build slice ([#35](https://github.com/Fre0Grella/getsetmix/issues/35))
on a laptop with a local SSD.

| Operation | Work | Estimate | Measured |
|---|---|---|---|
| First index | read every file once, SHA-256, read tags | minutes; bound by the disk, not the CPU | a real library of 568 tracks, 6.3 GB: 12 s for the hashing (about 500 MB/s). 3,000 small generated files: 2.7 s, or 23 s when the files had just been written. |
| Reconcile, nothing changed | one `stat` per file | well under a second on a local disk, a few seconds on a network share | 45 ms for 3,000 files |
| Reconcile, one file changed | read and hash that file | tens of milliseconds | 29 to 57 ms |
| List with a search, 3,000 rows | one query | | 7 ms |
| Index size | one row per file | about 1 MB | 1.24 MB for 3,000 rows |

At that rate a 30 GB library indexes in about a minute from an SSD, and in a
few minutes from a hard disk or over a network. The first index of files
that were just copied is several times slower per file on Windows, most
likely the virus scanner reading each new file on first open (not
confirmed).

### 4.2 The audio hash

**Function.** SHA-256, truncated to 128 bits, lowercase hex. It is in the
standard library of both Python and Go, so there is no new dependency for
the image, the executables or the companion. It is hardware-accelerated on
amd64 and on most arm64 chips. Collision resistance is not needed for an
identity, but it costs nothing. 128 bits keeps the id short and leaves the
chance of two different tracks sharing one beyond any practical concern.

**Input.** The bytes of the audio payload, in file order, as defined per
container below. Nothing else is mixed in.

| Container | Payload |
|---|---|
| **MP3** | From the first audio frame to the end of the audio. Leading ID3v2 tags and trailing ID3v1, Lyrics3v2 and APEv2 tags are left out. |
| **FLAC** | Everything after the last metadata block: the audio frames. |
| **WAV** | The payload of the `fmt ` chunk, then the payload of the `data` chunk. |
| **AIFF** | The payload of the `COMM` chunk, then the payload of the `SSND` chunk. |
| **MP4 / M4A** | The payload of every top-level `mdat` atom, in file order. |
| **Ogg, Opus** | The packets of the stream, without the comment packet. Specified here, built later. |

The rules, exact enough to implement twice:

**MP3**

1. *Start.* While the bytes at the current position are `ID3`, skip an
   ID3v2 tag: 10 bytes of header, the syncsafe size in bytes 6 to 9, and 10
   more if the footer flag (bit 4 of byte 5) is set. This covers the tag's
   own padding, which is inside its size.
2. From there, scan forward up to 1 MiB for the first **valid frame**: a
   4-byte header with the 11 sync bits set, a version other than reserved,
   Layer III, a bitrate index other than 0 and 15, a sample-rate index other
   than 3, and, at the offset the frame's length gives, either the end of
   the payload or another header with the same version, layer and sample
   rate. Junk between the tag and the audio is thereby left out.
3. *End.* Repeat until none applies: drop a trailing ID3v1 tag (the last 128
   bytes start with `TAG`); drop a Lyrics3v2 block (ends with `LYRICS200`,
   preceded by its 6-digit size); drop an APEv2 tag (the last 32 bytes start
   with `APETAGEX`; its size field, plus 32 when the header flag is set).
4. Hash from the start to the end.

The Xing, Info or LAME header frame is the first audio frame and **is
hashed**. It is part of the stream, and tag editors leave it alone.

**FLAC**

1. Skip a leading ID3v2 tag if a broken tagger put one there.
2. Expect `fLaC`. Walk the metadata blocks by their 4-byte headers until the
   one with the last-block flag.
3. Hash from the end of that block to the end of the file.

Padding, pictures and comments are metadata blocks, so adding a cover or
growing the padding changes nothing.

**WAV.** Walk the RIFF chunks. Hash the `fmt ` payload, then the `data`
payload, without their headers and pad bytes. `LIST` and `id3 ` chunks are
left out. RF64 and Wave64 get the fallback id.

**AIFF.** Walk the FORM chunks (`AIFF` or `AIFC`). Hash the `COMM` payload,
then the `SSND` payload. The `ID3 ` chunk is left out.

**MP4.** Walk the top-level atoms, with 64-bit sizes and size 0 handled as
the companion's probe does today. Hash the payload of each `mdat`. Tags live
under `moov`; a tag edit can move `mdat` in the file and rewrite the chunk
offsets in `moov`, but the bytes inside `mdat` stay the same.

**Ogg and Opus.** Raw pages cannot be hashed: a comment edit renumbers the
pages that follow and changes their checksums. The rule is to rebuild the
packets from the pages of the first stream and hash every packet except the
second, which is the comment packet in both Vorbis and Opus. A chained file
gets the fallback id. This is not built in the first version.
Rekordbox cannot import these files, the worker never produces them, and
they are read-only in the Library view, so the fallback id serves them until
they matter.

**Anything else, and anything damaged.** A file that does not parse by its
rule gets the fallback id, `f1_` over the whole file. Nothing is guessed.

**Details the first implementation settled.** They are written into the
code and into `testdata/audiohash/README.md`, so the Go side matches:

- The container is chosen by the file extension (`.m4a` and `.mp4` are MP4,
  `.aif` and `.aiff` are AIFF).
- An empty payload gets the fallback id.
- An ID3v2 size byte with its top bit set means the file does not parse.
- A chunk or atom that runs past the end of the file means the file does not
  parse; fewer than 8 stray bytes at the end are ignored.
- The frame after the first MP3 frame must have the sync bits and the same
  version, layer and sample rate. Its bitrate is not checked.
- The first `fmt ` and `data` chunk, and the first `COMM` and `SSND` chunk,
  are the ones used.
- A file cut short in the middle of its audio still parses: it gets an `a1_`
  id, different from the whole file's. Only a file cut in its header or tag
  region gets the fallback id. Either way nothing raises.

**When it is computed, and the cache.** A hash is computed when a file is
first seen and whenever its size or modification time differ from the row.
The row *is* the cache: `(path, size, mtime_ns) → audio_id`. An edit made by
GetSetMix does not rehash: the payload is known not to have changed, and the
row is updated with the file's new size and time directly.

**Two implementations, one answer.** Python in `app/audiohash.py`, Go in
`companion/internal/audio/hash.go`. They are kept equal by shared fixtures
([5](#5-testing)).

**Hard cases.**

| Case | What happens | Judgement |
|---|---|---|
| A tag edit grows the tag past its padding, so the whole file is rewritten | The payload bytes are the same; the id holds. | this is the case the design exists for |
| A tool re-encodes the file, or converts MP3 to FLAC | New audio bytes, new id. | correct: it is a different file; analysis must not carry over blindly |
| A tool changes the audio frames without re-encoding (mp3gain's volume field, "fix VBR header") | New id. | accepted; such tools are rare in a DJ library. The track shows up as one removed and one added. |
| A tag appended at the end in a form not listed above | Counted as audio; the id changes if that tag is later edited. | accepted; mutagen does not write such tags |
| Two files with the same audio and different tags | Same id, two rows. | intended: the view flags them, a computer fetches one |
| FLAC whose frames are re-compressed at another level | New id, although the sound is identical. | see the alternative in [7](#7-alternatives-considered) |

### 4.3 Editing tags

The tagger gains an edit path beside the download path. It differs in two
ways:

- **Only the fields sent are written.** The download path rewrites title,
  artist and comment every time; an edit must leave the comment, the cover
  and every tag it was not asked about untouched.
- **The write is atomic.** The file is copied under a hidden name
  (`.<name>.part`, already skipped by the link and by the companion's
  scanner), the copy is tagged, and it replaces the original in one rename.
  A crash leaves the old file intact, and a computer can never fetch half a
  file. It costs one copy of the file per write, however many fields the
  write changes.

**One internal write.** All tag edits go through one function in the
Library module, callable without HTTP:

```python
library.write_tags(file_id, changes, expect=None) -> WriteResult
```

| Argument | Meaning |
|---|---|
| `changes` | any set of the six fields (title, artist, album, genre, year, comment) with their new values |
| `expect` | optional: the values the caller believes some fields hold now |

1. Read the fields named in `expect` from the file itself, not from the
   index. If one differs, stop: nothing is written, and the result names the
   fields that differ with the values the file holds.
2. Copy, tag the copy with every change, rename it over the original.
3. Update the row (tags, size, time) and take **one** `rev` for the whole
   write.

The result holds the new row, or the mismatch. `PATCH /api/library/{id}` is
a thin caller. The batch editing module calls the function directly, once
per track, with the old values its preview showed as `expect`; a batch
therefore copies each file once, not once per field, and only overwrites
what the DJ saw.

The audio id is unchanged by construction. When the tests run, they also
check it by rehashing.

**Details the edit slice settled**
([#37](https://github.com/Fre0Grella/getsetmix/issues/37)):

- `year` must be a JSON integer; `"2019"`, `2019.0` and `true` are refused
  with `400`, as are an unknown field and `null` for a text field. The range
  applies to what is written: `expect` may name any year a file holds.
- A row that is `missing` (not on disk at the last reconcile), or whose file
  is not on disk at the time of the write, answers `410`, like a trashed one.
- A tag write, a delete and a restore run one at a time, so a delete cannot
  move a file while a write holds a copy of it. A reconcile pass that read a
  file before a write does not put the old size and time back.
- A `PermissionError` while copying or renaming is `423`; the hidden copy is
  removed and the original is left as it was.
- MP3 comment: the edit replaces the `COMM` frame with an empty description
  in English. Frames with a description (iTunes' own, a DJ app's) are never
  touched. Clearing the comment removes every empty-description `COMM`, in
  any language, so no other one shows through.
- The routes with a file id are typed `{fid:int}`, so `/api/library/rules`,
  `/status`, `/rescan` and `/trash` are never taken for an id.
- The detail sheet sends, for each field it changed, the value it showed as
  `expect`. A `412` reloads the sheet with what the file holds. It opens from
  the library list, not from the trash.

**The cover** goes the same way, through
`library.write_cover(file_id, image_or_none)`, with the existing cover
search and upload in front of it. The function returns the image it
replaced, or says there was none, so a caller that keeps a journal can undo
a cover change. `POST /api/library/{id}/cover` does not return the old
image.

### 4.4 Deleting, the trash and tombstones

- **Delete** moves the file to
  `<library>/.trash/<UTC time>-<id>/<original relative path>`. The folder
  starts with a dot, so the link, the reconcile walk and the companion's
  scanner already ignore it. It is on the same volume, so the move is a
  rename. The row becomes `trashed`, keeps its path in `path` and the new
  location in `trash_path`, and takes the next `rev`.
- **Restore** moves it back to its original path and makes the row `present`
  again. If another file has taken that path meanwhile, the restore is
  refused with `409` and the DJ decides. Nothing is renamed to make room.
- **Purge** runs once a day and on demand. It deletes trash folders older
  than `trash_days` and turns their rows to `gone`.
- **A tombstone** is a row in state `trashed` or `gone`. It is what
  `removed[]` in the link listing is built from. Tombstones are kept for
  good. A paired computer can be off for months and must still
  learn of a delete when it comes back; the rows are tiny.

A file that vanishes without GetSetMix (deleted in the Nextcloud app, or by
hand) becomes `missing`, then `gone` after the grace time, and is listed in
`removed[]` with reason `missing`. That answers #11's first open question
with its own "probably yes": **a delete made outside GetSetMix counts as a
server delete**, with the grace time and the guard of [4.1](#41-the-index-and-how-it-stays-true)
as the safety. There is no trash to restore from in that case, and the view
says so.

**As built** ([#38](https://github.com/Fre0Grella/getsetmix/issues/38)):

| Request | Answer |
|---|---|
| `DELETE /api/library/{id}` | `200` with `{id, state: "trashed", rev}`; `404` unknown id; `410` already trashed or gone; `409` the row is `missing` (nothing on disk to move) |
| `POST /api/library/{id}/restore` | `200` with `{id, state: "present", rev}`; `404`; `409` not in the trash, or its path is taken by a file on disk or a live row; `410` purged, or the file in the trash has vanished (the row then becomes `gone`) |
| `DELETE /api/library/trash` | `200` with `{purged: n}`: the whole trash, whatever its age |

- The row is updated and the file moved in one database transaction: if the
  move fails, the row rolls back. A restore keeps `content_rev`, and the
  rename keeps the file's time, so a paired computer does not download it
  again. The empty `<UTC time>-<id>` folder is removed after a restore.
- The purge only deletes `<UTC time>-<id>` folders of trashed rows; anything
  else in `.trash/` is left alone. A folder it cannot delete stays, with its
  row `trashed`, and is tried again the next day.
- `trash_days` 0 means no purge by age: the trash keeps everything until
  *Empty trash*. The daily purge runs with the 5-minute pass, at most once
  per 24 hours (`last_purge` in `library_meta`).
- Routes that take an id use the `int` path convertor, so `/api/library/trash`
  and `/api/library/rules` are never read as an id.

### 4.5 The Library view

One more place in the app, beside the download list. A switch in the top
bar moves between **Downloads** and **Library**.

**On a phone**

- A list of rows: cover, title, artist, a genre chip.
- **Search sits at the bottom**, where the link field is in the download
  view, so it is under the thumb. Typing filters as it goes, with a short
  debounce.
- Genre chips above the list filter with one tap. A sort menu holds added,
  artist, title and genre.
- Tapping a row opens a sheet: the fields (title, artist, album, genre,
  year, comment), the same one-tap genre picks as in the download view,
  cover, preview player, delete. The comment is shown with its source link;
  the sheet asks before it replaces one.
- A long press starts a selection. A bar then offers *Delete* and
  *Set genre*, with the count.

**On a desktop**

- The same data as a table, edited in place like the download rows.
- Click, Shift-click and Ctrl-click select; the same bulk bar appears.
- A folder filter sits beside the genre filter.

**Both**

- A **Trash** entry lists trashed tracks with *Restore* and *Empty trash*.
- Read-only rows say why (format, or damaged file).
- Rows that share their audio with another file carry a small marker.
- English and Italian, light and dark, as the rest of the UI.

**Long lists.** The list is **virtualised**: rows have a fixed height, and
only the visible ones plus a margin are in the page. Data comes in pages of
200 from the API as the list is scrolled. The view does not poll the list;
it polls `/api/library/status` and reloads what is on screen when `rev`
moves. That answers #11's fourth open question.

**Delete confirmation.** One track: an *Undo* toast, no dialog. A selection:
a dialog with the count. No confirmation phrase: a delete is recoverable for
`trash_days`.

**As built** ([#40](https://github.com/Fre0Grella/getsetmix/issues/40)):

- **The list.** Rows have one fixed height (64 px on a phone, 52 px from 721
  px up). The list element is as tall as all its rows, so the scroll bar is
  true, and each row that exists is placed by its position. The page holds the
  rows on screen plus 8 above and 8 below, never more (checked on 3,200
  rows). Pages of 200 come with the cursor, which only goes forward: a jump far
  down fetches the pages in between in a row, and the rows not yet there show
  as skeletons. When `rev` moves the view fetches again as many rows as it
  needs to cover what is on screen and swaps them in at once. Its own writes
  take the next `rev` and do not trigger a reload.
- **Sort and filters.** A sort menu (added, artist, title, genre) with a
  button that reverses it; genre chips with their counts (the 16 largest, tap
  again to clear); on a desktop a folder menu beside them. Both read
  `GET /api/library/facets`, which is fetched again when `rev` moves.
- **Covers in rows.** A row with `has_cover` asks for its image a moment after
  it appears (a fast fling asks for none), four at a time, newest request
  first. It asks for the thumbnail (`?size=thumb`, see below), decodes it at
  96 px and keeps only that copy (600 of them, least recently used out). A row
  without a cover, or whose image cannot be read, keeps the placeholder. The
  detail sheet still loads the full cover.
- **Thumbnails.** The embedded picture can be hundreds of kilobytes (on the
  first real library the median was 103 KB and the largest 493 KB), and a row
  shows it in a 44 px box, so scrolling the list once would download tens of
  megabytes. `GET /api/library/{id}/cover?size=thumb` answers with a square
  JPEG of at most 144 px (about 3x the box; centred crop, never enlarged,
  quality 80, a few KB), made with Pillow on first request and kept in
  `DATA_DIR/thumbs/<id>-<content_rev>.jpg` (`app/thumbs.py`). It is written
  to a temporary file and moved into place, the thumbnails of older revisions
  of the file are removed when a new one is made, and a purge from the trash
  removes them all. A JPEG is decoded reduced (`Image.draft`), a picture over
  the 10 MB cover cap or over 25 million pixels is not decoded, and one
  thumbnail is made at a time, so a burst of rows cannot fill the pod's 1 GiB.
  Whatever cannot be thumbnailed (damaged, an unknown format, too large) is
  answered with the full cover as before; no cover is the same `404`. The
  cache headers are the full cover's, with their own `ETag`.
- **Preview.** The detail sheet has a native audio element on
  `GET /api/library/{id}/audio`, which loads nothing before Play. It is stopped
  before any write to the file, because a tag or cover write moves the audio
  inside it.
- **Markers.** A small *Same audio* marker on rows that share their audio with
  another file (the sheet lists the other paths), and a *Read-only* marker
  that names the format, or says the file is damaged; the full reason is in the
  marker's title and in the sheet.

**The new routes, as built.**

| Request | Answer |
|---|---|
| `GET /api/library/facets?state=present` | `{rev, genres: [{name, count}], folders: [{path, count}]}`, genres by count then name, folders by name; a folder counts the files directly in it, like the `folder` filter; files with no genre and files in the root are in no facet |
| `GET /api/library/{id}/cover?v=` | the embedded image with its type read from its bytes (front cover first, else the first picture); `ETag` from `content_rev`; `?v=` equal to the current `content_rev` is cached for a year, anything else revalidates, so a new cover has a new address; `304` on a matching `If-None-Match`; `404` no cover |
| `GET /api/library/{id}/cover?size=thumb&v=` | the same, as a JPEG thumbnail of at most 144 px (the full cover when it cannot be made); its own `ETag`; `400` for any other `size` |
| `GET /api/library/{id}/audio` | the file, `206` for a `Range` of one range (`first-last`, `first-`, `-last`), `416` with `Content-Range: bytes */size` past the end, `200` whole for anything else; the file is opened once per 256 KB so a write is never blocked on Windows |
| `POST /api/library/{id}/cover` | multipart `file`, or JSON `{"url": "https://..."}`; the updated item; `400` not a JPEG, PNG or WebP image, or an address that is not http(s); `413` over 10 MB; `502` the address did not give an image; then as `PATCH` |

- Both reads serve a present row from its path and a trashed row from the
  trash, and never anything outside the library root: a row path with `..`,
  an absolute one, a link that leaves the root, or a trash path that is not a
  `.trash/<time>-<id>/` one is a `404`. A purged (`gone`) track, a `missing`
  one and a file that is not on disk are `410`; an unknown id is `404`.
- The list item gains `content_rev`, the `rev` of the last change of the
  file's bytes. A tag or cover write sets it to the write's `rev`.
- `library.write_cover(file_id, image)` takes `(bytes, mime)` or `None` (remove)
  and returns `CoverResult(item, previous)`; `previous` is the image the file
  had, as `(bytes, mime)`, or `None`. The mime type is replaced by what the bytes
  are. It uses the tag write's atomic copy and rename, its owner-keeping, its
  lock and its errors; the picture written is the only one in the file, as a
  front cover. `edit_file(path, changes, cover=...)` takes `KEEP`, `None` or the
  image, so a tag change never touches the cover.
- The download of a cover address only takes `http` and `https`, and at most
  10 MB; this also closes `file:` addresses for the download path.

### 4.6 What a computer does

The rule that a computer never changes the server stays. So does the rule
that a delete on the computer sticks.

```mermaid
sequenceDiagram
    participant App as App (server)
    participant Fetch as Companion: fetch
    participant Imp as Companion: importer
    participant RB as Rekordbox master.db

    Note over App: the DJ edits a genre in the Library view
    Fetch->>App: GET /api/link/files
    App-->>Fetch: files[] with id and rev, removed[]
    Fetch->>Fetch: rev is newer than the one held for this id
    Fetch->>App: GET /api/link/file
    Fetch->>Fetch: replace the local file, keep the old tags in state
    Imp->>Imp: scan: a handled file has a new size or time
    Imp->>RB: backup, one transaction: update the row's tags
    Imp->>RB: integrity check, restore on failure
```

**A changed track** (the listing's `rev` for an id is newer than the one in
`fetched.json`):

1. If the local file is no longer there, the DJ removed it. Record the new
   `rev` and do nothing else. Deleting on the computer still sticks.
2. Otherwise download to `.part` and rename over the local file, as a new
   track is downloaded today. The audio hash of the download is checked
   against the id.
3. The importer's next sync sees that a file it has handled changed size or
   time. It reads the tags from the file and compares them with the tags
   remembered in `fetched.json`.
4. For the row with that path, under the importer's safety (Rekordbox
   closed, backup, one transaction, integrity check, restore on failure):

| Column | Change |
|---|---|
| `Title` | new value, if the title changed on the server |
| `ArtistID`, `AlbumID`, `GenreID` | the id of the row with that exact name, created when missing, as an import does |
| `ReleaseYear` | new value, if the year changed on the server; empty when it was cleared |
| `Commnt` | new value, if the comment changed on the server |
| `FileSize` | the file's new size |
| `rb_file_id` | the file's new filesystem id, since the file was replaced |
| `updated_at`, `rb_local_usn` | now, and the next change number |
| `agentRegistry.localUpdateCount` | the last change number used |

   Nothing else in the row is touched. Cues, the beat grid, the analysis
   path, ratings, play counts and playlist entries hang off the row's `ID`,
   which does not change.

5. **Only fields that changed on the server are written.** If the DJ changed
   the artist in Rekordbox and the server changed the genre, the artist in
   Rekordbox is kept. If both changed the same field, the server's value
   wins.
6. If no row has that path, the DJ removed the track from Rekordbox. It is
   not imported again.

**A deleted track** (an id in `removed[]` not yet in the state's `removed`):

1. The row is added to a root playlist, **GetSetMix: removed on server**,
   created when missing, with the same playlist code and the same
   `masterPlaylists6.xml` mirror as the import playlist. A track is never
   added twice.
2. Nothing is removed from the collection. Removing a track would also lose
   its cues, grid and playlist entries; that decision is the DJ's.
3. With the option *Delete the local file too* (off by default) the local
   file goes to the system's recycle bin, so even that is
   recoverable. Without the option the file stays.
4. If the id is listed again later (a restore), the track is taken out of
   that playlist.

Both need a write to `master.db`, so both wait while Rekordbox is open, as
imports do.

**As built** for deleted tracks ([#38](https://github.com/Fre0Grella/getsetmix/issues/38)):

- *Fetch* owns `fetched.json`. It records a tombstone only for a track this
  computer holds (in `tracks`, or by path in `legacy`), drops it when the id
  is listed again, and does the opt-in local delete. It never opens
  `master.db`.
- *The importer* compares the tombstones in `fetched.json` with the paths it
  has listed (`state.json`, `removed`), without writing them. The
  difference is written in the same sync as the imports, under the same
  backup, after the imports, so a track fetched and removed while Rekordbox
  was open has its row by then. Nothing to list means `master.db` is not
  opened. A path with no row in the collection (the DJ removed it) is
  recorded as handled and not looked for again.
- Taking a track out of the playlist deletes its `djmdSongPlaylist` row in
  that playlist only and renumbers the rest, each moved entry with the next
  change number, as pyrekordbox does.
- *Delete the local file too* is `"delete_removed_files": true` in the
  `server` entry of `companion.json`; Setup does not offer it yet. It acts
  on tombstones handled while it is on, never on older ones, and only on
  tracks deleted in GetSetMix: a file that vanished from the server's disk
  (reason `missing`) leaves the local copy alone, since it may be the last.
  A path the server lists again under another id was replaced, so it is not
  a removal. Windows: the
  Recycle Bin through `SHFileOperationW` with undo, only on a fixed drive
  (a network share or a USB stick has no bin and Windows would delete for
  good), and asking rather than deleting if the bin is turned off. macOS:
  the Finder moves it to the Trash, which asks once for permission to
  control the Finder. A failed move leaves the file and is tried again on
  the next fetch. If the track is restored on the server and its file went
  to the bin, it is downloaded again.
- The "handled file is gone" rule for local mode and synced folders is slice
  7; without a paired server nothing is listed.

**Details the edit slice settled**
([#37](https://github.com/Fre0Grella/getsetmix/issues/37)):

- *Where the old tags come from.* `fetch` reads the six fields from a file
  when it first downloads it and keeps them in `fetched.json`. A track
  fetched before this version has none; its local copy, read just before the
  newer copy replaces it, gives them. A file with no tags at all has none,
  and then all six fields are written.
- *Who writes `fetched.json`.* `fetch`, and the importer for one thing: once
  a row is updated it stores the file's tags and clears `pending`. Both take
  the same lock file (`fetch.lock`). While a fetch runs, changed tracks wait
  for the next sync; new tracks are still imported.
- *Which files.* Step 3 above is narrowed: the importer acts on a track that
  `fetch` marked `pending` when it put a newer copy in place, not on any
  change of size or time. So a tag edit made on this computer with another
  program is not taken for a server change, and a newer copy that arrives
  before `state.json` is widened is not lost. A change in a folder a sync
  client fills is left alone until slice 7; decision 11 applies there.
- *Tombstones win.* A track with a tombstone is not fetched and its row is
  not updated, even if a newer copy was already waiting. When a server path
  is listed again under another id (a replaced file, not a removal), the
  newest id speaks for that local file. The replaced audio does not update
  the old row: its cues would belong to other audio.
- *Where the newer copy lands.* At the path this computer fetched the track
  under, even if the server has moved it since.
- *The audio check* runs on a newer copy only. A copy whose audio id differs
  replaces nothing, and its `rev` is not recorded, so it is tried again.
- *The comment* is read as the server reads it: the ID3 frame with no
  description, in English if there are several. Frames written in another
  order, or a frame like `iTunNORM`, no longer look like a changed comment.
  This also applies to what a new import writes to `Commnt`.
- An emptied title is written as the file name, as an import does. A cleared
  year or comment empties `ReleaseYear` or `Commnt`. `rb_file_id` is written
  only when the file's id could be read.

**Folders filled by a sync client.** When Setup was told *My server's music
folder is already synced here*, there is no fetch. Nextcloud or Syncthing
replaces a changed file itself, and the importer's scan picks the change up
by size and time, as in step 3. Without a paired server the importer has no
remembered tags to compare with, so it writes all six fields (title,
artist, album, genre, year, comment).
Deletes arrive as files that vanish; see local mode below.

**Migration of `fetched.json`**, on the first fetch against a protocol 2
server:

1. For each listed file whose path is in the old map: record its id. If the
   local file has the listed size, record the listed `rev`. If not, record
   `rev` 0, so it counts as changed and is fetched again.
2. Old paths the server no longer lists go to `legacy`.
3. The old file is kept as `fetched.v1.json`.

`state.json` values are widened in place on the first sync: each handled
path gets the size and time the file has at that moment, and nothing is
acted on.

#### 4.6.1 The companion's view of server changes (consolidation)

**Status: approved** on 2026-11-24 (see the decisions below); slices 1 to 3
of the build plan are built, and the first half of slice 4. It changes how the companion's code is arranged,
not what it does.
It is numbered under 4.6 so that 4.7 and 4.8 keep their numbers: the code
cites "4.7" for local mode.

##### What the walk found

A read-only walk of the companion on 2026-11-24 traced how it knows what
changed on the server. Each finding below was checked against the code.
Where the walk was wrong or incomplete, the row says so.

| # | Finding | Where |
|---|---|---|
| 1 | "Removed on server" crosses five packages. `fetch` records tombstones by audio id. `importer` compares them with the paths it has already listed. `config` holds that list. `library` writes the playlist. `main` logs it. | `fetch.Client.tombstones`, `fetch.State.Removed`; `importer.removals`; `config.State.Removed` (type `config.Listed`); `library.MarkRemoved`; `main.logRemoved` |
| 2 | Two maps are both called `Removed` and use different keys: `fetch.State.Removed` is keyed by audio id, `config.State.Removed` by `library.PathKey`. `fetch` alone also has a type `Removed` (a listing entry) and a field `Report.Removed` (server paths). | `fetch/state.go`, `fetch/fetch.go`, `config/config.go` |
| 3 | "Changed on server" is decided across four packages: `fetch` (`refresh`, `State.Stale`, `State.Remember`, `Track.Pending`, `Track.Tags`), `importer` (`loadFetched`, `prepare`), `library` (`Changed`, `Update`) and `audio` (`ReadTags`, `TagsOf`). **Correction:** `config.Handled.Widen` runs in the same sync but decides nothing. The size and time it stores are written and never read; they wait for slice 7. | `importer/importer.go` |
| 4 | "Has this file been handled" is three different facts in three stores: handled by the importer (`state.json` `seen`, by path key), fetched from the server (`fetched.json`, by audio id or by path), and in the collection (`library.KnownPaths`). The mapping between a path key and an audio id is built in two places, `fetch.State.Stale` and `importer.removals`, both through `fetch.Local`. **Correction:** `importer.Sync` does not rebuild it; it uses the map from `Stale` and turns report paths back into keys with `PathKey` to find it again. | `fetch/state.go`, `importer/removed.go`, `importer/importer.go` |
| 5 | `fetched.json` is read at five call sites and written at four. Reads: `main.runFetch` (locked), `importer.loadFetched` (an unlocked first look, then again under the lock), `importer.removals` (unlocked), `setup` step `first` (unlocked). Writes: `main.runFetch` (locked), `importer.Sync` (locked), `setup` step `first` (unlocked), `setup.seedFetchState` (unlocked). | `cmd/gsm-companion/main.go`, `importer`, `setup/pc.go` |
| 6 | **Correction:** step `first` re-implements `runFetch` only in the `DryRunOS` test run. A real Setup starts `gsm-companion fetch`, which takes the lock. **Missed by the walk:** `seedFetchState` writes a whole new `fetched.json` without the lock. An unlocked read is never torn, because `Save` writes a temporary file and renames it. But one sync reads two versions of the file: one in `removals`, one in `loadFetched`. | `setup/pc.go` |
| 7 | **New:** `state.json` has no lock at all, and nothing stops two syncs at once. The launcher, the scheduled fetch and `watch` can each run `importer.Sync`. Two syncs both rewrite `state.json`, and both copy `master.db` into the same `backup` folder. A sync that fails could restore a copy the other sync took while it was writing. | `importer/importer.go` (`snapshot`, `restore`) |
| 8 | `config.State` is shallow: its interface is as large as its data. Only the importer writes it (`Sync`, `Baseline`). Only `cmdStatus` also reads it. `config` imports `fetch` only for the `fetch.Server` type. **Addition:** it also imports `scan`, for `scan.File` in `Mark` and `Widen`. | `config/config.go` |
| 9 | The domain types `Track` and `Tags`, the function `PathKey` and the file type codes live in `library`, the SQLCipher package. So `audio`, `scan` and `fetch` import the database package, and every test of theirs builds the cgo driver. **Correction:** `config` does not import `library` itself; it reaches it through `fetch` and `scan`. | `library/import.go`, `library/update.go`, `library/db.go` |
| 10 | The query `SELECT … FolderPath FROM djmdContent WHERE rb_local_deleted = 0 …` is written five times: `KnownPaths`, `DominantFolder`, inline in `Import`, `contentIDs`, inline in `Update`. **Correction:** only two of them pick a row for a path. `Update` keeps the oldest row (`ORDER BY created_at`). `contentIDs`, used by `MarkRemoved`, keeps the last row read, with no `ORDER BY`, so the winner is not defined. `KnownPaths` and `Import` build a set of paths, and `DominantFolder` counts folders. So when a path has two rows, `Update` and `MarkRemoved` can act on different rows, and a later restore can take out a different row than the one listed. | `library/db.go`, `library/import.go`, `library/removed.go`, `library/update.go` |

The behaviour is right and well tested. The problem is **locality**. Each
of the questions "what is new", "what changed" and "what was removed" is
answered by code spread over several packages. The next rules (slice 7:
synced folders, local mode, "handled file is gone") would add a third key
mapping and touch every one of them again.

##### Goals and non-goals

Goals:

- **One module owns what the companion knows about server tracks.** It
  answers "what changed", "what was removed" and "what is new since the
  last sync". Its answers name each server track by audio id. The local path
  comes with each answer as a derived view.
- **One owner for `fetched.json` and `state.json`.** No other package reads
  or writes them. Every write happens under the file's lock.
- **Domain types in a pure package.** `audio`, `scan`, `fetch`, `config` and
  the new module build and test without SQLCipher.
- **One path-to-row lookup in `library`**, with a defined winner when a path
  has several rows.
- **Same behaviour.** Every existing importer and fetch test passes, with
  the same assertions.

Non-goals:

- No change to what is written to `master.db`, or to when it is written.
  The one exception is a path with two live rows: the row chosen becomes
  defined (slice 2 of the build plan).
- No change to the formats of `fetched.json`, `state.json` or
  `companion.json`, unless a step below needs it. None does.
- Any later migration stays backwards compatible: a new companion reads
  every file an old one wrote, and an old one keeps working on what a new
  one wrote.
- The Rekordbox safety rules of
  [architecture 8.1](../architecture.md#81-writing-to-rekordbox) stay as
  they are.
- No new feature. Local mode and synced folders stay slice 7.
- No change to the link protocol or to the server.

##### The proposed shape

**A pure package, `track`.** It holds what every other package means by a
track:

- `Track` (the import candidate), `Tags`, the field names, `Changed`;
- `PathKey`, and `Local` (a server path mapped safely into a folder);
- the Rekordbox file type codes that `audio.Probe` fills in;
- the link listing types (`File`, `Listing`, the listing's removed entry),
  since they name tracks by audio id.

It imports nothing from the companion and no database driver. `library`
keeps type aliases (`type Track = track.Track`) while callers move.
`FolderPath` stays in `library`: it is a Rekordbox storage rule.

**A deep module, `ledger`, owns the two state files.** Its interface is
small: three questions, and one record call for each outcome. Behind that
interface it holds:

- the two file formats and their migrations;
- the mapping between path keys and audio ids;
- the newest-id-per-path rule;
- the rule that a tombstone wins;
- the two `removed` records joined into one answer;
- the locks.

| Call | Caller | What it answers or records | Key | File | Lock |
|---|---|---|---|---|---|
| `Plan(listing)` | fetch | which listed tracks are new, which have a newer copy, which were deleted here, which tombstones to record or drop, which local files go to the recycle bin | audio id (path for protocol 1) | `fetched.json` | `fetch.lock`, held by the fetch run |
| `Fetched`, `Refreshed`, `Kept`, `Tombstoned`, `Restored`, `Recycled` | fetch | what the run did, one call per outcome | audio id | `fetched.json` | `fetch.lock` |
| `Seed(listing, all)` | Setup, through fetch | the first state: everything to fetch, or only what arrives from now on | audio id | `fetched.json` | `fetch.lock` |
| `Unhandled(files)` | importer, `status` | the scanned local files no sync has handled yet | path key | `state.json` | none: a snapshot |
| `Work()` | importer | `Changed` (a newer copy is in place and the row is behind), `Removed` (a tombstone not yet listed), `Restored` (listed, but the server has it again) | audio id, with the local path | both | none for `Removed` and `Restored`; `Changed` is read again under `fetch.lock` |
| `Handled(files)`, `Baseline(files)` | importer | local files dealt with | path key | `state.json` | `sync.lock` |
| `Applied(changed, tags)` | importer | the row now holds these tags; `pending` is cleared | audio id | `fetched.json` | `fetch.lock`, taken before the write as today |
| `Listed(item)`, `Unlisted(item)` | importer | the playlist now has, or no longer has, the track | audio id outside; path key inside the file | `state.json` | `sync.lock` |

The importer hands the items of `Work()` back to the record calls. It never
builds a key itself. `library` names the input items in its results, so the
importer does not turn paths back into keys at the end of a sync.

The vocabulary changes with it:

- a **tombstone** is the server saying a track is removed;
- **listed** means the track is in the *removed on server* playlist;
- the name `Removed` is used once, for the item `Work()` returns.

**The seam moves.** Today `fetch` and `importer` meet in two JSON files
that each one reads and interprets. After the change they meet at the
ledger's interface. Tests can sit at that seam without a server and without
a `master.db`.

**Who touches the files.**

- Only `ledger` reads or writes `fetched.json`, `fetched.v1.json` and
  `state.json`. No other package knows the file names.
- A read that leads to a write of the same file happens under that file's
  lock, after the lock is taken.
- A read for a question only may be a snapshot without the lock: `status`,
  or the check whether a sync has anything to do. Files are replaced by a
  rename, so a snapshot is always whole.
- `fetch.lock` keeps its meaning: a fetch is running, or `fetched.json` is
  being changed. A fetch run holds it, as today. Setup's seed and its
  dry-run fetch now take it too, through `fetch`.
- `sync.lock` is new. It means an import into Rekordbox is running, and it
  covers `state.json` and the backup folder. One sync at a time closes
  finding 7.
- Lock order: `sync.lock` first, then `fetch.lock`. The importer only
  *tries* `fetch.lock`. If a fetch holds it, changed tracks wait for the
  next sync, as today. A fetch never waits for `sync.lock` while it holds
  `fetch.lock`. So the two locks cannot deadlock.
- One lock for both files was considered. It would block every import for
  as long as a fetch runs, up to 30 minutes for the scheduled one. That is
  worse than today.

**`config` becomes settings only.** `fetch.Server` moves to `config.Server`.
`fetch` keeps a type alias for one release. `config.State` moves into
`ledger`. After that `config` imports nothing from the companion.

**`fetch` becomes the network half.** It lists, downloads, checks the audio
id and moves files. It asks `ledger.Plan` what to do and records what it
did. `main.runFetch` moves into `fetch` as one function, so the launcher,
the scheduled task and Setup's dry run run the same code under the same
lock.

**One path-to-row lookup in `library`.** One function reads `ID`,
`FolderPath` and `created_at` of the live rows, once per transaction. It
returns, for each path key, the row that wins. The winner is the **oldest
live row** (`created_at`, then `ID`): the row Rekordbox has had longest,
most likely the one with the cues. This is `Update`'s rule today.
`KnownPaths`, `Import`, `MarkRemoved` and `Update` all use the function.
`DominantFolder` counts folders, not rows; it stays its own query.

**Dependencies before** (code outside tests; `install`, `notices`,
`serverscript` left out):

```mermaid
flowchart TB
    cmd["cmd/gsm-companion"]
    setup --> config & fetch & importer & library & rekordbox
    cmd --> config & fetch & importer & library & rekordbox & scan & setup & watch
    watch --> importer & scan & audio
    importer --> config & fetch & library & scan & audio & rekordbox
    config --> fetch & scan
    fetch --> library & audio & recycle
    scan --> library & audio
    audio --> library
    library --> cgo[("go-sqlcipher (cgo)")]
    fetch -.->|reads, writes| fj[("fetched.json")]
    importer -.->|reads, writes| fj
    setup -.->|reads, writes| fj
    cmd -.->|reads, writes| fj
    importer -.->|reads, writes| sj[("state.json")]
    cmd -.->|reads| sj
```

**Dependencies after:**

```mermaid
flowchart TB
    cmd["cmd/gsm-companion"]
    setup --> config & fetch & importer & library & rekordbox
    cmd --> config & fetch & importer & ledger & library & rekordbox & scan & setup & watch
    watch --> importer & scan & audio
    importer --> config & ledger & library & scan & audio & rekordbox
    fetch --> config & ledger & audio & recycle & track
    ledger --> track & scan
    scan --> audio & track
    audio --> track
    library --> track
    library --> cgo[("go-sqlcipher (cgo)")]
    ledger -.->|only owner| fj[("fetched.json")]
    ledger -.->|only owner| sj[("state.json")]
```

After the change only `importer`, `setup` and `cmd` import `library`. Only
they link SQLCipher.

##### Data contracts

No format changes. The table says who owns each file after the change.

| File | Version | Owner | Writes under | Old companions |
|---|---|---|---|---|
| `companion.json` | none | `config` | Setup only | unchanged |
| `fetched.json` | 1 while the server speaks protocol 1, 2 after | `ledger` | `fetch.lock` | read it as today |
| `fetched.v1.json` | the version 1 file, kept once | `ledger` | `fetch.lock` | unchanged |
| `state.json` | none; `seen` values are a time or `{at, size, mtime}` | `ledger` | `sync.lock` | read it as today |
| `fetch.lock` | — | `fetch` run and `ledger` writes | — | same meaning |
| `sync.lock` | new | importer | — | ignored; they behave as today |

The migrations that exist move into `ledger` unchanged, with their tests:

- `fetched.json` version 1 to version 2, on the first protocol 2 listing;
- a tombstone written as a time alone;
- a `seen` value written as a time alone, widened on the first sync.

An old companion reads everything a new one writes, because nothing new is
written. The only new thing on disk is `sync.lock`, which an old companion
does not know. During the minutes Setup takes to replace the program, an
old and a new process can still run two syncs at once, as any two do today.

A later format change becomes possible without touching any caller.
Example: keep "listed" on the tombstone itself, keyed by audio id, instead
of in `state.json` by path. It is not proposed here; see the open
questions.

##### Alternatives considered

| Alternative | For | Against |
|---|---|---|
| **Leave the code as is, add tests only** | No risk to working code. The importer's tests already cover most behaviour through `Sync`. | The unlocked writers (finding 6) and the concurrent syncs (finding 7) stay. Slice 7 adds another key mapping in four packages. Tests that sit on two JSON files break with every internal change. |
| **Targeted fixes only**: lock the two Setup writers, add `sync.lock`, one row lookup | Small, and it closes the real risks. | Locality does not improve. It is slices 2 and 3 of the plan below without the ledger. It is a good fallback if the ledger is not approved. |
| **Merge `config.State` into `fetch.State`**, one file owned by `fetch` | One file, one lock, one owner. | `state.json` also serves folders with no server (synced folders), where `fetch` has no business. `fetch` would become the importer's memory too. Losing `state.json` is dangerous: an old companion that finds no `state.json` treats every file as new and re-imports tracks the DJ removed from Rekordbox. The format change cannot be read by old companions. |
| **Make `fetch` the deep module**, owning both files | One package fewer. | `fetch` would hold the network, the download policy and the importer's memory. The importer would depend on the network package for its own state. |
| **One SQLite file (`state.db`) instead of JSON** | Transactions and locks come with SQLite. Queries instead of maps. | The state module would depend on a cgo driver, against the goal of a pure core. The data is small: thousands of entries load and save in milliseconds. JSON can be read and fixed by hand. The move is one-way: old companions cannot read it. Worth looking at again if per-track data grows, for example analysis results. |

##### Testing

What is protected, and how:

- **The ledger, through its interface.** These are pure Go tests: no
  server, no `master.db`, no cgo. Each case writes the two files, calls a
  question, and checks the answer and the files after the record calls:
  - new, newer, deleted here, tombstoned;
  - the newest id wins when a server path was replaced;
  - a tombstone wins over a waiting newer copy;
  - a restore takes out a listed track only;
  - `Applied` stores the tags and clears `pending`;
  - `Unhandled` after `Handled`.
- **The locks.** Two ledgers on one folder lose no write. A second sync gets
  `sync.lock` only after the first ends. The importer skips changed tracks,
  and only those, while `fetch.lock` is held. A lock older than its limit is
  taken over.
- **Migration.** Golden files in `testdata/ledger/` record each form the
  files have had:
  - `fetched.json` version 1;
  - version 2 with time-only tombstones;
  - `state.json` with time-only `seen` values;
  - `state.json` with `removed`.

  Each is opened, asked the three questions, and saved. The answers must
  equal what today's code gives for the same files. Opening twice changes
  nothing. A copy of today's decoder, kept in the test, must read every
  saved file the same way. That is the old-companion check.
- **The importer, with the `librarytest` fixture.** Today's tests in
  `importer_test.go`, `removed_test.go` and `update_test.go` stay as the net
  for every slice. Only their set-up changes: they prepare state through
  ledger test helpers, not by writing `fetch.State` by hand. They assert the
  same columns, playlist rows and backups.
- **The row lookup, with `librarytest`.** Two live rows share one path.
  `Update` changes the oldest only. `MarkRemoved` lists the oldest and a
  restore takes the same row out. `KnownPaths` is unchanged.
- **The import rules.** A Go test runs `go list -deps`. It fails if `track`,
  `audio`, `scan`, `fetch`, `ledger` or `config` depend on `library` or on
  go-sqlcipher. It also fails if a package other than `ledger` names
  `fetched.json` or `state.json`.

##### Decisions (2026-11-24)

The five questions of the draft, decided by the maintainer as recommended:

1. **`sync.lock` is added**: one sync at a time. A sync that finds it held
   waits up to 30 seconds, then skips and logs; the launcher starts
   Rekordbox either way. A launch right after the scheduled sync still
   imports its tracks.
2. **Duplicate paths**: only the oldest live row is updated and listed
   (built in [#77](https://github.com/Fre0Grella/getsetmix/pull/77)), and
   the lookup is limited to this computer's `DeviceID`: a duplicate row is
   usually a leftover, and writing to it could touch a row Rekordbox does
   not use. **Refined while building slice 2** (maintainer, 2026-11-27):
   this computer's oldest row is *preferred*; when it has no row for a
   file, the oldest row of any device is still written, as before, so a
   library whose rows carry another device's ID keeps its updates. "Is the
   file already in Rekordbox?" looks at every device's rows, or such a
   library would be imported a second time.
3. **Names**: `track` and `ledger`.
4. **The two `removed` records** stay as they are, joined inside the
   ledger. No format change; revisit only if the join causes trouble.
5. **Architecture**: the companion's layering goes into
   [architecture 8.8](../architecture.md#88-code-structure-and-its-checks)
   with an import-rule test in CI, and decision 10 records it.

##### Build plan

Each slice is one pull request. The companion stays releasable after each,
and the existing tests pass unchanged in what they assert.

1. **Pure `track` package.** Move `Track`, `Tags`, `Changed`, `PathKey`,
   `Local`, the file type codes and the link listing types. Keep aliases in
   `library` and `fetch`. Add the import-rule test. No behaviour change.
   **Built:** the listing's removed entry is `track.Tombstone`; the MP3
   builder for tests moved from `librarytest` to a pure `track/tracktest`,
   so `fetch` tests without SQLCipher too. The test is
   `internal/layers`; the ledger and the state-file rule join it in slice 3.
2. **One row lookup in `library`.** Use it in `KnownPaths`, `Import`,
   `MarkRemoved` and `Update`. Add the duplicate-path test. Behaviour
   changes only for a path with two live rows.
   **Built:** `rowsByPath` in `library/rows.go`, with `localDevice` (the
   device detection `Import` had) and `knownPaths`. Since #77 `Update` and
   `MarkRemoved` already took the oldest row; what changes is the device
   preference of decision 2.
3. **`ledger` with today's formats.** Move `fetch.State`, `config.State`,
   their load, save and lock, and the migrations into it. Move
   `fetch.Server` to `config.Server`. Every reader and writer goes through
   the ledger. Setup's seed and dry-run fetch go through `fetch`'s single
   run. Add `sync.lock`, if open question 1 is approved. This closes
   findings 5 to 7.
   **Built:** `internal/ledger` holds `Fetched` (`fetched.json`) and
   `Synced` (`state.json`). Either file can be saved only through its held
   lock (`FetchLock`, `SyncLock`); `ReadFetched` and `ReadSynced` are the
   snapshots for questions. `fetch.lock` behaves as before: refused at
   once, taken over after two hours, since an older companion may hold it.
   `sync.lock` is waited for up to 30 seconds; its holder refreshes it
   every minute, so a sync that died blocks the next one for at most five
   minutes, not hours. A skipped sync returns `ErrSyncRunning`: the
   launcher still starts Rekordbox, a fetch logs it, the watcher tries
   again. A dry run takes no lock. One sync reads `fetched.json` once (and
   again only under `fetch.lock`), so it no longer sees two versions.
   `Baseline` writes under `sync.lock`; Setup's seed is `fetch.Seed`.
   `config` is `companion.json` alone, with `config.Server`. Tests write
   state through `ledger/ledgertest`. The layers test now also checks the
   ledger and `config`, and that no code outside the ledger names its
   files.
4. **The ledger's questions.** Add `Plan`, `Unhandled`, `Work` and the
   record calls. Remove `importer.removals`, `fetch.State.Stale`, the key
   handling in `loadFetched` and the re-keying at the end of `Sync`. The
   golden migration tests come in this slice.
   **Built in two parts.** *4a, the importer's side:* `ledger.WorkFor`
   answers `Changed`, `Removed` and `Restored` as `Item`s (audio id, local
   path, key, and the tags last seen for a changed one); `Unhandled`,
   `Handled`, `Listed`, `Unlisted` and `Applied` are the record calls, and
   `NewSynced` is Baseline's fresh state. `importer.removals`,
   `Fetched.Stale` and the re-keying are gone: the importer maps the
   library's results back by the paths it gave. The golden files are in
   `internal/ledger/testdata`, checked with a frozen copy of the decoder.
   They pin one old answer: a tombstone in its first form (the time alone)
   names no path, so it lists nothing, and a track listed for it counts as
   restored. *4b, the fetch side:* `Plan` and its record calls.
5. **Clean-up.** Remove the aliases. Bring the `fetch` and `config` package
   comments, and 4.6 above, in line with the code.

Slice 7 of the library plan (local mode and synced folders) is then built
on the ledger. "A handled file is gone" becomes one more kind of item that
`Work()` returns.

### 4.7 Local mode

With no server the app runs on the DJ's computer and the library root is a
folder the companion watches. The same index, the same API and the same view
work over it. There is no link and no fetch; the file system carries the
news.

| In the Library view | On the same machine |
|---|---|
| Edit tags | The file is replaced in place. The importer's next sync, right before Rekordbox starts, sees the change and updates the row. |
| Delete | The file moves to `.trash/`. The importer sees that a file it handled is gone while its row is still in the collection, and adds the row to the *removed* playlist. Rekordbox shows the track as missing until the DJ removes it or the file is restored. |
| Restore | The file is back at its path. The row works again, and the track leaves the *removed* playlist. |

An edit can fail with `423` when Rekordbox has the file loaded on a deck.
The view says to unload it and try again.

The "handled file is gone" rule is used in local mode and for synced
folders only. With a paired server a missing local file means the DJ
deleted it on purpose, and the tombstone from the server is what counts.

### 4.8 Who may delete

Anyone who can open the UI can edit and delete, as they can change every
setting today. That fits one DJ on a home server, and a delete is
recoverable. Link tokens open `/api/link` only, so a paired computer cannot
delete. A hosted offering for several people needs real users and
permissions; that is a
[risk in the architecture document](../architecture.md#10-risks-and-technical-debt),
not something this module solves.

## 5. Testing

| Layer | What is tested |
|---|---|
| **Hash fixtures, both languages** | `testdata/audiohash/` holds small audio files of a few kilobytes and `expected.json`. For each file it gives the expected id; for each group it lists files that must share an id (the same audio with no tags, ID3v2.3, ID3v2.4, ID3v1, APEv2, a cover, grown padding, `moov` before and after `mdat`, extra RIFF chunks) and files that must differ. `tests/test_audiohash.py` and `companion/internal/audio/hash_test.go` read the same folder, so the two implementations cannot drift. A script next to the fixtures records how they were made. |
| **Hash properties** | Edit every tag field with the tagger and with the edit path: the id holds. Truncate or corrupt a file: fallback id, no exception. |
| **Index and reconcile** (pytest, `tmp_path`) | New, changed, moved, missing and back, gone after the grace time, the 20% guard, the settle time, resume after an interrupted first index. |
| **Edit path** (pytest, on fixture files) | A write changes only the fields it was given: every other tag, the cover and the audio id are the same before and after. Several fields in one call make one copy and take one `rev`. Year and comment are written to the right frame per format; a full date is left alone when the year is not edited. With `expect`, a mismatch writes nothing and names the fields that differ. `write_cover` returns the image it replaced. A field with several values is indexed joined, listed in `multi`, and kept when another field is edited. Index columns hold the file's values unfolded. |
| **Library API** (pytest, as `tests/test_api.py`) | List with search, filters, sorts and paging; `library.select` returns every matching id with its `editable` flag; edit per format, including year and comment; the `400`, `409`, `410`, `412` and `423` answers; delete, restore, purge; bulk with a partial failure. |
| **Link protocol** (pytest and Go) | The listing's new fields; an old companion's reading of a new listing; a new companion against an old listing; trashed files are neither listed nor served. |
| **Companion** (Go, with the `librarytest` fixture) | State migration; a changed track updates exactly the columns in [4.6](#46-what-a-computer-does) and leaves cues and playlist rows alone; a deleted track lands in the playlist once; a restore removes it; a locally deleted file is not fetched again; everything is refused while Rekordbox runs; the backup is restored when the check fails. |
| **UI** | The virtualised list with a few thousand rows on a phone-sized viewport; selection and bulk bar; both languages. |

**Manual checklist against a real Rekordbox**, on a copy of a library,
before the companion slices ship. Only the maintainer can run it; the
automated tests stop at the `librarytest` fixture.

*Set up, so the real library is never at risk.*

1. Do it in a second Windows user account (or on another computer) whose
   Rekordbox has its own small library: a few tracks, not the DJ library.
   Only if that is not possible: quit Rekordbox, copy the whole
   `%APPDATA%\Pioneer\rekordbox` folder somewhere safe first, and put it
   back when done. Never use this fallback in the weeks before a gig.
2. Pair that account's companion with a GetSetMix server whose library
   holds a few test tracks (not the real music), and let it fetch and
   import them. In Rekordbox, analyse one of them, set two hot cues and a
   memory cue, adjust the grid, give it a rating, and put it in a second
   playlist besides *GetSetMix*. Quit Rekordbox.

*Edit one track (slice 3,
[#37](https://github.com/Fre0Grella/getsetmix/issues/37)).*

3. In the Library view, open that track and change title, artist, album,
   genre (with a chip), year and comment (answer *Replace it*). Save.
4. On the computer run `gsm-companion fetch` (or wait for the scheduled
   task), then open Rekordbox with the GetSetMix launcher.

- [ ] The row shows the six new values.
- [ ] The track keeps its hot cues, memory cue, beat grid, rating and its
      place in both playlists.
- [ ] Rekordbox does not flag the file as missing and does not ask to
      analyse it again, with the file replaced and `rb_file_id` and
      `FileSize` updated. *(Open question below.)*
- [ ] What Rekordbox shows for the cover, before and after *Reload Tag*.
      *(Open question below.)*
- [ ] Change only the genre in Rekordbox, quit, then change only the year on
      the server and fetch again: Rekordbox keeps its genre and shows the
      new year.
- [ ] Remove a test track from the Rekordbox collection, edit it on the
      server, fetch: it is not imported again.
- [ ] Delete a fetched test track's file on the computer, edit it on the
      server, fetch: it is not downloaded again.
- [ ] A USB export of the edited track works and carries the new tags.
- [ ] Note the answers to the two open questions in
      [section 6](#6-decisions-and-open-questions).

*Later slices.*

- [ ] What Rekordbox shows for the cover after a cover edit, with and
      without *Reload Tag* (slice 6).
- [ ] The same with Cloud Library Sync on, if available.

**Delete and restore** ([#38](https://github.com/Fre0Grella/getsetmix/issues/38)),
by the maintainer, on a **copy** of a Rekordbox library (never the one for a
gig), with Rekordbox closed while the companion syncs:

- [ ] Delete two fetched tracks in the Library view, run
      `gsm-companion fetch`, open Rekordbox: a root playlist
      *GetSetMix: removed on server* holds exactly those two tracks.
- [ ] Both tracks are still in the collection with their hot cues, memory
      cues, beat grid and their place in every other playlist.
- [ ] Quit and reopen Rekordbox: the playlist is still there, with the same
      tracks (the `masterPlaylists6.xml` mirror agrees with `master.db`).
- [ ] Fetch again: neither track is listed twice.
- [ ] Restore one in the Trash view, fetch, open Rekordbox: it has left the
      playlist and plays as before; the other is still listed.
- [ ] With Rekordbox open, delete a track and fetch: nothing changes until
      Rekordbox is closed and the launcher or the next fetch runs.
- [ ] With `"delete_removed_files": true` (on a test folder): a deleted
      track's local file is in the Recycle Bin (Windows) or the Trash
      (macOS, after allowing control of the Finder), and Rekordbox shows it
      as missing, still in the playlist.

## 6. Decisions and open questions

Decided with the maintainer on 2026-11-14. The first four were discussed one
by one; the rest were accepted as proposed.

| # | Question | Decision |
|---|---|---|
| 1 | Grace time before a file that vanished outside GetSetMix counts as deleted | **24 hours** (the draft proposed 15 minutes; the maintainer asked for longer) |
| 2 | The guard against mass deletes | no tombstones when more than 20% and more than 10 files go missing in one pass |
| 3 | Server and Rekordbox both changed the same field | the server's value wins |
| 4 | Where the trash lives | inside the library root, `<library>/.trash/`. A library synced by Nextcloud or Syncthing carries it along when hidden files are synced. |
| 5 | Exact duplicates (same audio, two files) | two rows, flagged in the view; a computer fetches one |
| 6 | Id format | `a1_` plus 128 bits of SHA-256 in hex; `f1_` for the fallback |
| 7 | Ogg and Opus hashing | specified, not built in the first version; fallback id until then |
| 8 | FLAC: hash the frame bytes, or use the MD5 in STREAMINFO | the frame bytes |
| 9 | How often to reconcile | every 5 minutes, plus the triggers in 4.1 |
| 10 | How long tombstones are kept | for good |
| 11 | Synced-folder mode with no paired server | every tag field the companion handles is written on a change (six, with year and comment) |
| 12 | "Handled file is gone" as a delete signal | local mode and synced folders only |
| 13 | Search | a folded `search` column matched with `LIKE`; SQLite full-text search if it proves too slow |
| 14 | Editing M4A and AIFF | a later slice |
| 15 | *Delete the local file too*: where the local file goes | the system's recycle bin, not a hard delete |
| 16 | Files Rekordbox cannot import (Ogg, Opus) | the companion skips them and says so; the server keeps listing them ([3.5](#35-link-protocol-2), [#31](https://github.com/Fre0Grella/getsetmix/issues/31)). Decided after approval, on 2026-11-14. |

Added on approval, from what the batch editing module needs
([its section 3.7](batch-editing.md#37-what-this-module-needs-from-the-library-module)):

| Addition | Where |
|---|---|
| One internal write of several fields, atomic, one `rev`, with an optional check of the old values | [3.3](#33-library-api), [4.3](#43-editing-tags) |
| Year and comment are editable and reach Rekordbox (`ReleaseYear`, `Commnt`) | [3.3](#33-library-api), [3.4](#34-tag-fields-per-format), [3.6](#36-the-companions-state), [4.6](#46-what-a-computer-does) |
| The cover write returns the image it replaced | [4.3](#43-editing-tags) |
| A filter resolves to ids with their `editable` flag | [3.3](#33-library-api) |
| Tag values are indexed exactly as the file holds them | [3.2](#32-the-index) |
| A rule for fields with several values | [3.2](#32-the-index), decision 17 |
| Bulk *set genre* goes through batch editing once it exists | [3.3](#33-library-api) |

Decided on 2026-11-14, before the slice that edits tags
([#37](https://github.com/Fre0Grella/getsetmix/issues/37)), as proposed:

| # | Question | Decision |
|---|---|---|
| 17 | A field that holds several values in the file | the index shows them joined with `"; "` and names the field in `multi`; an edit of that field writes the one value given, not split on `"; "`; a field that is not edited keeps its values ([3.2](#32-the-index)). The maintainer's reason: Rekordbox shows several artists badly, so his library keeps one main artist per track (on a remix, the known remixer), with Rekordbox's *Remixer* and *Original Artist* fields for the rest; that cleanup belongs to batch editing, not to this module. |
| 18 | A full date in the file when the year is edited | the date is left alone unless the year is edited; then the tag is written as the year alone ([3.4](#34-tag-fields-per-format)) |

Still open, with no proposal:

- **Does Rekordbox accept a changed `rb_file_id` and `FileSize` silently?**
  The manual checklist ([5](#5-testing)) answers it; still open after the
  edit slice was built, waiting for the maintainer's run. If not, the
  alternative is to write the download into the existing file instead of
  replacing it, which keeps the filesystem id and gives up the atomic
  rename.
- **What does Rekordbox do with the cover** of a track whose file changed?
  Its artwork is cached in its own files. This version does not touch them.
  Still open, answered by the same run.
- **Changing the library root in Settings.** Every row vanishes at once, so
  the guard trips and stays tripped, while the files under the new root are
  indexed as new rows. It needs a rule: most likely, a changed root starts a
  fresh index. Found while building the first slice.

#11's open questions, for the record:

| #11 asks | Answer |
|---|---|
| Does a delete made outside GetSetMix count? | Yes, after a grace time and behind the guard ([4.4](#44-deleting-the-trash-and-tombstones)). |
| Identity across renames | The audio hash ([decision 4](../architecture.md#9-decision-log), [4.2](#42-the-audio-hash)). |
| Who may delete | Anyone who can open the UI; no phrase, since deletes are recoverable ([4.8](#48-who-may-delete)). |
| Long lists on a phone | A virtualised list, paged data, search under the thumb ([4.5](#45-the-library-view)). |

## 7. Alternatives considered

| Alternative | Why not |
|---|---|
| **An id written into a tag** | Every existing file has to be rewritten once, a copied file carries the same id as its source, another tagger can strip it, and formats without tags have nowhere to put it. Rejected in [decision 4](../architecture.md#9-decision-log). |
| **The path as identity** | What exists today. A rename outside GetSetMix looks like a delete plus a new track, and a result computed on the computer cannot be tied to the server's copy with certainty. |
| **A hash of the whole file** | Changes with every tag edit, which is the main thing this module does. Kept only as the fallback for files that do not parse. |
| **FLAC's own MD5 in STREAMINFO** | Free to read, and it survives re-compression. But some encoders leave it zero, it is trusted without checking, and it would make FLAC the one format whose id is not a hash of bytes read. It stays an option for an `a2`. |
| **An audio fingerprint (Chromaprint) as identity** | It is fuzzy by design: two masters of one track can match. An identity has to be exact. Also out of the roadmap. |
| **A filesystem watcher instead of a periodic reconcile** | Events are not delivered reliably through Docker bind mounts, network shares and every platform the app runs on. A walk that only calls `stat` is cheap and always right. A watcher can be added later as a hint that triggers a pass sooner. |
| **Hard delete** | One wrong tap on a phone would destroy the backup copy. |
| **Removing deleted tracks from Rekordbox automatically** | Loses cues, grids and playlist entries without asking. |
| **Sending tag changes to the computer as data, without the file** | The local file would keep the old tags, and Rekordbox's *Reload Tag* would bring them back. The companion would also need a tag writer in Go. |
| **Loading the whole list in the page** | Works at a few hundred tracks, not at a few thousand on a phone. |

## 8. Build slices

Thin slices, each working end to end, in the order they would be built.
Each slice is an issue under
[#11](https://github.com/Fre0Grella/getsetmix/issues/11).

1. **Index and a read-only Library list.** The tables, the Python audio hash
   with its fixtures, reconcile with the guard, the worker inserting the row
   after it places a file, `GET /api/library` and a plain list in the UI
   with search. Measures the costs estimated in 4.1.
2. **Link protocol 2.** `id`, `rev` and `removed[]` in the listing, served
   from the index. The Go audio hash against the shared fixtures. The
   companion reads protocol 2 and migrates `fetched.json`; its behaviour
   does not change yet, except that it stops downloading files Rekordbox
   cannot import.
3. **Edit one track, all the way.** The tagger's edit path and the
   internal write with its check of old values, `PATCH` for the six fields,
   the detail sheet, and on the computer: re-download, the importer's change
   detection, the update of the Rekordbox row. Ends with the manual
   checklist.
4. **Delete and restore, all the way.** Trash, restore, purge, tombstones,
   the Trash view, and on the computer the *removed on server* playlist and
   the opt-in local delete.
5. **Selection and bulk actions.** Bulk delete, restore and set genre, with
   the selection UI on phone and desktop.
6. **The full view.** Virtualised list, facets and filters, sorts, preview
   player, cover edit, duplicate markers.
7. **Local mode and synced folders.** The "handled file is gone" rule, the
   `423` path, Setup's wording.
8. **More formats.** M4A and AIFF editing; the Ogg and Opus hash, if
   wanted.
