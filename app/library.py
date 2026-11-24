"""The library index: one row per audio file under the library root.

The disk is the truth; the index is a cache of it that a reconcile pass
brings back in line (docs/design/library.md, 4.1). A pass walks the root with
the link's skip rules, leaves files changed in the last 10 seconds alone,
reads nothing for a file whose size and mtime match its row, hashes the rest
in batches committed as they go (so a first index resumes after a restart),
follows files moved outside GetSetMix by their audio id, marks vanished
files missing and, after 24 hours, gone. If a pass would mark more than 20%
of the library, and more than 10 files, as missing, it marks none and sets
`unavailable` instead.

A delete moves the file to `<root>/.trash/<UTC time>-<id>/<path>` and makes
its row a `trashed` tombstone; a restore moves it back; a daily purge deletes
trash older than `trash_days` and turns those rows `gone` (design 4.4).

Time comes from an injectable clock, so the settle and grace times are
testable without waiting.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import time
import unicodedata
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import mutagen
from mutagen.id3 import ID3
from mutagen.mp4 import MP4Tags

from . import audiohash, config
from . import db as dbmod
from .link import AUDIO_EXTS, served
from .link import _skip as skipped  # the link's skip rules, shared on purpose

log = logging.getLogger("getsetmix.library")

SETTLE_SECONDS = 10
GRACE_SECONDS = 24 * 3600
GUARD_SHARE = 0.20
GUARD_MIN = 10
BATCH = 50                  # files hashed per committed batch
INTERVAL_SECONDS = 5 * 60   # the periodic pass
LINK_MAX_AGE = 60           # /api/link/files reconciles when the last pass is older
LINK_WAIT = 10              # ...and waits this long for it, once the library is indexed
EDITABLE_FORMATS = ("mp3", "flac")
LIVE = ("present", "missing")
SORTS = {"added": "added_at", "artist": "artist COLLATE NOCASE",
         "title": "title COLLATE NOCASE", "genre": "genre COLLATE NOCASE"}
SORT_COLUMNS = {"added": "added_at", "artist": "artist", "title": "title", "genre": "genre"}
STATES = ("present", "trashed")
TAG_FIELDS = ("title", "artist", "album", "genre", "comment")
TRASH_DIR = ".trash"        # inside the root; the dot keeps it out of the walk and the link
DAY = 24 * 3600


class LibraryError(Exception):
    """A request the library refuses, with the HTTP status that says why."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _trash_folder(root: Path, trash_rel: str | None) -> Path | None:
    """The `<UTC time>-<id>` folder a trash path lives in, or None if it is not one."""
    parts = (trash_rel or "").split("/")
    if len(parts) < 3 or parts[0] != TRASH_DIR or parts[1] in ("", ".", ".."):
        return None
    return root / TRASH_DIR / parts[1]


def fold(text: str) -> str:
    """Lowercase, accents removed: what `search` holds and what a query is matched as."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


# ------------------------------------------------------------------ tags
def _joined(values) -> tuple[str, bool]:
    values = [str(v) for v in (values or [])]
    return "; ".join(values), len(values) > 1


def _year(text: str) -> int | None:
    m = re.match(r"\s*(\d{4})", text or "")
    return int(m.group(1)) if m else None


def read_tags(path: Path) -> dict:
    """Tags and stream info as the file holds them. Never raises.

    Several values in one field are joined with "; " in file order and the
    field is named in `multi` (design 3.2, proposal 17).
    """
    out = {f: "" for f in TAG_FIELDS}
    out.update(year=None, has_cover=0, multi="", duration=None, bitrate=None, sample_rate=None)
    try:
        audio = mutagen.File(path)
    except Exception:
        return out
    if audio is None:
        return out
    info = getattr(audio, "info", None)
    if info is not None:
        length = getattr(info, "length", None)
        out["duration"] = round(float(length), 3) if length else None
        bitrate = getattr(info, "bitrate", None)
        out["bitrate"] = int(bitrate) // 1000 if bitrate else None
        out["sample_rate"] = getattr(info, "sample_rate", None) or None
    tags = audio.tags
    values: dict[str, list] = {}
    year_text = ""
    try:
        if isinstance(tags, ID3):
            for field, frame in (("title", "TIT2"), ("artist", "TPE1"),
                                 ("album", "TALB"), ("genre", "TCON")):
                if frame in tags:
                    values[field] = list(tags[frame].text)
            comments = [c for c in tags.getall("COMM") if c.desc == ""]
            comments.sort(key=lambda c: c.lang != "eng")
            if comments:
                values["comment"] = list(comments[0].text)
            if "TDRC" in tags and tags["TDRC"].text:
                year_text = str(tags["TDRC"].text[0])
            out["has_cover"] = int(bool(tags.getall("APIC")))
        elif isinstance(tags, MP4Tags):
            for field, atom in (("title", "\xa9nam"), ("artist", "\xa9ART"), ("album", "\xa9alb"),
                                ("genre", "\xa9gen"), ("comment", "\xa9cmt")):
                if atom in tags:
                    values[field] = list(tags[atom])
            year_text = str((tags.get("\xa9day") or [""])[0])
            out["has_cover"] = int(bool(tags.get("covr")))
        elif tags is not None and hasattr(tags, "get"):  # Vorbis comments
            for field in TAG_FIELDS:
                found = tags.get(field)
                if found:
                    values[field] = list(found)
            year_text = str((tags.get("date") or [""])[0])
            pictures = getattr(audio, "pictures", None)
            out["has_cover"] = int(bool(pictures) or bool(tags.get("metadata_block_picture")))
    except Exception:
        log.warning("could not read the tags of %s", path, exc_info=True)
    multi = []
    for field, found in values.items():
        out[field], several = _joined(found)
        if several:
            multi.append(field)
    out["multi"] = ",".join(f for f in ("title", "artist", "album", "genre", "comment") if f in multi)
    out["year"] = _year(year_text)
    return out


def _search(rel: str, tags: dict) -> str:
    name = rel.rsplit("/", 1)[-1]
    return fold(" ".join([tags["title"], tags["artist"], tags["album"], tags["genre"], name]))


# ------------------------------------------------------------------ walk
def _walk(root: Path) -> list[tuple[str, int, int]]:
    """(relative path, size, mtime_ns) of every audio file the link would serve."""
    found: list[tuple[str, int, int]] = []
    stack = [(root, "")]
    while stack:
        folder, prefix = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            if skipped(entry.name):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append((Path(entry.path), prefix + entry.name + "/"))
                    continue
                if os.path.splitext(entry.name)[1].lower() not in AUDIO_EXTS:
                    continue
                st = entry.stat()
            except OSError:
                continue
            if st.st_size:
                found.append((prefix + entry.name, st.st_size, st.st_mtime_ns))
    return found


# --------------------------------------------------------------- the index
class Library:
    def __init__(self, database, root: Callable[[], Path] | None = None,
                 clock: Callable[[], float] = time.time,
                 trash_days: Callable[[], int] | None = None) -> None:
        self.db = database
        self.root = root or (lambda: Path(config.settings["library_root"]))
        self.clock = clock
        self.trash_days = trash_days or (lambda: int(config.settings.get("trash_days", 30)))
        self._pass = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()
        self.progress = {"running": False, "done": 0, "total": 0}

    # -------------------------------------------------------------- meta
    def _meta(self, conn: sqlite3.Connection, key: str) -> str | None:
        row = conn.execute("SELECT value FROM library_meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute("INSERT INTO library_meta (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def _next_rev(self, conn: sqlite3.Connection) -> int:
        rev = int(self._meta(conn, "rev") or 0) + 1
        self._set_meta(conn, "rev", str(rev))
        return rev

    # ------------------------------------------------------------ passes
    def trigger(self) -> bool:
        """Start a pass in the background; False if one is running (dropped)."""
        if not self._pass.acquire(blocking=False):
            return False
        self._idle.clear()

        def run() -> None:
            try:
                self._reconcile()
            except Exception:
                log.exception("library reconcile failed")
            finally:
                self._idle.set()
                self._pass.release()

        threading.Thread(target=run, name="library-reconcile", daemon=True).start()
        return True

    def wait(self, timeout: float | None = None) -> bool:
        """Until no background pass runs; False on timeout."""
        return self._idle.wait(timeout)

    def reconcile(self) -> dict | None:
        """One pass, now, in this thread; None if another pass is running."""
        if not self._pass.acquire(blocking=False):
            return None
        try:
            return self._reconcile()
        finally:
            self._pass.release()

    def _reconcile(self) -> dict:
        root = self.root()
        now = self.clock()
        settle_ns = int((now - SETTLE_SECONDS) * 1e9)
        on_disk: dict[str, tuple[int, int]] = {}
        settling: set[str] = set()
        for rel, size, mtime_ns in _walk(root):
            if mtime_ns > settle_ns:
                settling.add(rel)
            else:
                on_disk[rel] = (size, mtime_ns)

        with self.db.transaction() as conn:
            rows = {r["path"]: dict(r) for r in conn.execute(
                "SELECT * FROM library_files WHERE state IN ('present', 'missing')")}
            # The first index of an existing library: a file is dated by its own
            # time, so sorting by "added" means something. Later, by when it is seen.
            first = self._meta(conn, "indexed") is None
        library_size = sum(1 for r in rows.values() if r["state"] == "present")

        work: list[tuple[str, int, int]] = []
        back: list[dict] = []
        for rel, (size, mtime_ns) in on_disk.items():
            row = rows.get(rel)
            if row and row["size"] == size and row["mtime_ns"] == mtime_ns:
                if row["state"] == "missing":
                    back.append(row)
                continue
            work.append((rel, size, mtime_ns))
        work.sort()

        # Rows whose file is not where it was: what a new file may have moved from.
        away = [r for path, r in rows.items() if path not in on_disk and path not in settling]
        candidates: dict[str, list[dict]] = {}
        for row in sorted(away, key=lambda r: r["id"]):
            candidates.setdefault(row["audio_id"], []).append(row)
        moved: set[int] = set()
        summary = {"new": 0, "changed": 0, "replaced": 0, "moved": 0, "back": 0, "missing": 0,
                   "gone": 0}

        self.progress = {"running": True, "done": 0, "total": len(work)}
        try:
            for start in range(0, len(work), BATCH):
                batch = []
                for rel, size, mtime_ns in work[start:start + BATCH]:
                    read = self._read(root, rel)
                    self.progress["done"] += 1
                    if read is not None:
                        batch.append((rel, size, mtime_ns, *read))
                with self.db.transaction() as conn:
                    for rel, size, mtime_ns, aid, tags in batch:
                        kind = self._apply(conn, rel, size, mtime_ns, aid, tags, now,
                                           candidates, moved,
                                           added=min(mtime_ns / 1e9, now) if first else now)
                        summary[kind] += 1
        finally:
            self.progress = {"running": False, "done": 0, "total": 0}

        with self.db.transaction() as conn:
            for row in back:
                conn.execute(
                    "UPDATE library_files SET state = 'present', state_changed_at = ?, rev = ? "
                    "WHERE id = ? AND state = 'missing'",
                    (_iso(now), self._next_rev(conn), row["id"]))
                summary["back"] += 1

            vanished = [r for r in away if r["state"] == "present" and r["id"] not in moved
                        and not (root / r["path"]).exists()]
            too_many = (len(vanished) > GUARD_SHARE * library_size and len(vanished) > GUARD_MIN)
            if too_many:
                log.warning("library: %d of %d files vanished at once; marking none missing "
                            "until the library is available again", len(vanished), library_size)
            else:
                for row in vanished:
                    conn.execute(
                        "UPDATE library_files SET state = 'missing', state_changed_at = ?, rev = ? "
                        "WHERE id = ? AND state = 'present'",
                        (_iso(now), self._next_rev(conn), row["id"]))
                    summary["missing"] += 1
                for row in conn.execute(
                        "SELECT id, state_changed_at FROM library_files WHERE state = 'missing'"
                ).fetchall():
                    if row[0] in moved or not row[1] or now - _ts(row[1]) < GRACE_SECONDS:
                        continue
                    conn.execute(
                        "UPDATE library_files SET state = 'gone', state_changed_at = ?, rev = ? "
                        "WHERE id = ?", (_iso(now), self._next_rev(conn), row[0]))
                    summary["gone"] += 1
            self._set_meta(conn, "unavailable", "1" if too_many else "0")
            self._set_meta(conn, "last_reconcile", _iso(now))
            self._set_meta(conn, "indexed", "1")
        if any(summary.values()):
            log.info("library reconcile: %s", summary)
        return summary

    def _read(self, root: Path, rel: str) -> tuple[str, dict] | None:
        """The audio id and tags of a file, outside any lock; None if it vanished."""
        path = root / rel
        try:
            aid = audiohash.audio_id(path)
        except OSError:
            return None
        return aid, read_tags(path)

    def _apply(self, conn: sqlite3.Connection, rel: str, size: int, mtime_ns: int, aid: str,
               tags: dict, now: float, candidates: dict[str, list[dict]], moved: set[int],
               added: float) -> str:
        """Bring one row in line with a file that is new or changed. Returns what it was."""
        current = conn.execute(
            "SELECT * FROM library_files WHERE path = ? AND state IN ('present', 'missing')",
            (rel,)).fetchone()
        if current is not None:
            if current["audio_id"] == aid:
                self._update(conn, current["id"], rel, size, mtime_ns, aid, tags, now,
                             back=current["state"] != "present")
                return "changed"
            # Same path, other audio: the old track is gone and this is a new one.
            conn.execute("UPDATE library_files SET state = 'gone', state_changed_at = ?, rev = ? "
                         "WHERE id = ?", (_iso(now), self._next_rev(conn), current["id"]))
            self._insert(conn, rel, size, mtime_ns, aid, tags, _iso(added), "")
            return "replaced"
        # A row whose file is not where it was, with this audio: moved outside GetSetMix.
        for row in candidates.get(aid, []):
            if row["id"] in moved:
                continue
            still = conn.execute("SELECT state, path FROM library_files WHERE id = ?",
                                 (row["id"],)).fetchone()
            if still and still["state"] in LIVE and still["path"] == row["path"]:
                moved.add(row["id"])
                self._update(conn, row["id"], rel, size, mtime_ns, aid, tags, now, back=True)
                return "moved"
        self._insert(conn, rel, size, mtime_ns, aid, tags, _iso(added), "")
        return "new"

    def _update(self, conn: sqlite3.Connection, fid: int, rel: str, size: int, mtime_ns: int,
                aid: str, tags: dict, now: float, back: bool) -> None:
        was = conn.execute("SELECT size, mtime_ns FROM library_files WHERE id = ?",
                           (fid,)).fetchone()
        rev = self._next_rev(conn)
        fields = {**self._columns(rel, size, mtime_ns, aid, tags), "state": "present",
                  "rev": rev}
        # The bytes changed (a tag edit) when the size or time did; a move or a
        # file coming back as it was keeps its content_rev, so a paired computer
        # does not download it again (link protocol 2, files[].rev).
        if was is None or (was["size"], was["mtime_ns"]) != (size, mtime_ns):
            fields["content_rev"] = rev
        if back:
            fields["state_changed_at"] = _iso(now)
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE library_files SET {sets} WHERE id = ?", (*fields.values(), fid))

    def _insert(self, conn: sqlite3.Connection, rel: str, size: int, mtime_ns: int, aid: str,
                tags: dict, added_at: str, source_url: str) -> int:
        rev = self._next_rev(conn)
        fields = {**self._columns(rel, size, mtime_ns, aid, tags), "source_url": source_url,
                  "added_at": added_at, "state": "present", "state_changed_at": added_at,
                  "rev": rev, "content_rev": rev}
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        cur = conn.execute(f"INSERT INTO library_files ({cols}) VALUES ({marks})",
                           tuple(fields.values()))
        return int(cur.lastrowid)

    @staticmethod
    def _columns(rel: str, size: int, mtime_ns: int, aid: str, tags: dict) -> dict:
        return {
            "path": rel, "audio_id": aid, "size": size, "mtime_ns": mtime_ns,
            "format": os.path.splitext(rel)[1].lower().lstrip("."),
            **{k: tags[k] for k in (*TAG_FIELDS, "year", "has_cover", "multi", "duration",
                                    "bitrate", "sample_rate")},
            "search": _search(rel, tags),
        }

    # --------------------------------------------------------- the worker
    def add_file(self, path: Path, source_url: str = "") -> int:
        """Index a file the worker just placed, without a walk. Returns its row id."""
        root = self.root()
        rel = Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
        st = Path(path).stat()
        aid, tags = audiohash.audio_id(path), read_tags(Path(path))
        now = self.clock()
        with self.db.transaction() as conn:
            current = conn.execute(
                "SELECT id, audio_id FROM library_files "
                "WHERE path = ? AND state IN ('present', 'missing')", (rel,)).fetchone()
            if current is not None and current["audio_id"] == aid:
                self._update(conn, current["id"], rel, st.st_size, st.st_mtime_ns, aid, tags,
                             now, back=True)
                if source_url:
                    conn.execute("UPDATE library_files SET source_url = ? WHERE id = ?",
                                 (source_url, current["id"]))
                return int(current["id"])
            if current is not None:
                conn.execute("UPDATE library_files SET state = 'gone', state_changed_at = ?, "
                             "rev = ? WHERE id = ?",
                             (_iso(now), self._next_rev(conn), current["id"]))
            return self._insert(conn, rel, st.st_size, st.st_mtime_ns, aid, tags, _iso(now),
                                source_url)

    # ------------------------------------------------------------ the trash
    def trash(self, fid: int) -> dict:
        """Move a file to `<root>/.trash/<UTC time>-<id>/<path>` (design 4.4).

        The row becomes `trashed`, keeps its path and takes the next rev. Raises
        LibraryError: 404 unknown id, 410 already in the trash or gone, 409 the
        file is not on disk (missing).
        """
        root = Path(self.root())
        now = self.clock()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM library_files WHERE id = ?", (fid,)).fetchone()
            if row is None:
                raise LibraryError(404, "no such track")
            if row["state"] in ("trashed", "gone"):
                raise LibraryError(410, "the track is already deleted")
            src = root / row["path"]
            if row["state"] != "present" or not src.is_file():
                raise LibraryError(409, "the file is not on disk")
            stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            trash_rel = f"{TRASH_DIR}/{stamp}-{fid}/{row['path']}"
            rev = self._next_rev(conn)
            conn.execute(
                "UPDATE library_files SET state = 'trashed', state_changed_at = ?, "
                "trash_path = ?, rev = ? WHERE id = ?", (_iso(now), trash_rel, rev, fid))
            # Moved inside the transaction: if the move fails, the row rolls back.
            dest = root / trash_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        log.info("library: moved %s to the trash", row["path"])
        return {"id": fid, "state": "trashed", "rev": rev}

    def restore(self, fid: int) -> dict:
        """Move a trashed file back to its path; the row is `present` again.

        Raises LibraryError: 404 unknown id, 409 not in the trash or its path is
        taken (nothing is renamed to make room), 410 purged, or the trashed file
        itself has vanished (the row is then `gone`).
        """
        root = Path(self.root())
        now = self.clock()
        vanished = False
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM library_files WHERE id = ?", (fid,)).fetchone()
            if row is None:
                raise LibraryError(404, "no such track")
            if row["state"] == "gone":
                raise LibraryError(410, "the track was purged from the trash")
            if row["state"] != "trashed" or not row["trash_path"]:
                raise LibraryError(409, "the track is not in the trash")
            src = root / row["trash_path"]
            dest = root / row["path"]
            if not src.is_file():
                conn.execute("UPDATE library_files SET state = 'gone', state_changed_at = ?, "
                             "rev = ? WHERE id = ?", (_iso(now), self._next_rev(conn), fid))
                vanished = True
            else:
                taken = conn.execute(
                    "SELECT 1 FROM library_files WHERE path = ? AND state IN ('present', 'missing')",
                    (row["path"],)).fetchone()
                if taken or dest.exists():
                    raise LibraryError(409, "another file has taken this track's place: "
                                            + row["path"])
                rev = self._next_rev(conn)
                conn.execute("UPDATE library_files SET state = 'present', state_changed_at = ?, "
                             "trash_path = NULL, rev = ? WHERE id = ?", (_iso(now), rev, fid))
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
        if vanished:
            raise LibraryError(410, "the file is no longer in the trash")
        self._tidy_trash(root, row["trash_path"])
        log.info("library: restored %s", row["path"])
        return {"id": fid, "state": "present", "rev": rev}

    def purge(self, everything: bool = False) -> int:
        """Delete trash older than `trash_days` (all of it with `everything`).

        Each purged row becomes `gone` and keeps its trash path, so its
        tombstone still says it was deleted in GetSetMix. `trash_days` 0 keeps
        the trash until it is emptied by hand. Returns how many were purged.
        """
        days = self.trash_days()
        if not everything and days <= 0:
            return 0
        root = Path(self.root())
        now = self.clock()
        with self.db.transaction() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT id, path, trash_path, state_changed_at FROM library_files "
                "WHERE state = 'trashed' ORDER BY id")]
        purged = 0
        for row in rows:
            if not everything and (not row["state_changed_at"]
                                   or now - _ts(row["state_changed_at"]) < days * DAY):
                continue
            folder = _trash_folder(root, row["trash_path"])
            try:
                if folder is not None and folder.exists():
                    shutil.rmtree(folder)
            except OSError:
                log.warning("library: could not purge %s from the trash", row["path"],
                            exc_info=True)
                continue
            with self.db.transaction() as conn:
                conn.execute("UPDATE library_files SET state = 'gone', state_changed_at = ?, "
                             "rev = ? WHERE id = ? AND state = 'trashed'",
                             (_iso(now), self._next_rev(conn), row["id"]))
            purged += 1
        if purged:
            log.info("library: purged %d file(s) from the trash", purged)
        return purged

    def purge_due(self) -> int:
        """The daily purge: runs when the last one is a day old or more."""
        with self.db.transaction() as conn:
            last = self._meta(conn, "last_purge")
        now = self.clock()
        if last is not None and now - _ts(last) < DAY:
            return 0
        purged = self.purge()
        with self.db.transaction() as conn:
            self._set_meta(conn, "last_purge", _iso(now))
        return purged

    @staticmethod
    def _tidy_trash(root: Path, trash_rel: str) -> None:
        """Remove the empty folders a restore leaves in the trash."""
        folder = _trash_folder(root, trash_rel)
        if folder is None:
            return
        for path in sorted((p for p in folder.rglob("*") if p.is_dir()), reverse=True):
            with contextlib.suppress(OSError):
                path.rmdir()
        with contextlib.suppress(OSError):
            folder.rmdir()

    # ------------------------------------------------------------- reads
    def status(self) -> dict:
        with self.db.transaction() as conn:
            counts = {r[0]: r[1] for r in conn.execute(
                "SELECT state, COUNT(*) FROM library_files GROUP BY state")}
            meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM library_meta")}
        return {
            "rev": int(meta.get("rev") or 0),
            "counts": counts,
            "last_reconcile": meta.get("last_reconcile"),
            "unavailable": meta.get("unavailable") == "1",
            "indexed": meta.get("indexed") == "1",
            "indexing": dict(self.progress),
        }

    # -------------------------------------------------------------- link
    def link_listing(self, refresh: bool = False) -> dict | None:
        """What paired computers read, as link protocol 2 (design 3.5).

        None until the first index is complete: the link then answers as
        protocol 1, from a disk walk. With `refresh`, a pass is started when the
        last one is older than LINK_MAX_AGE, and waited for (up to LINK_WAIT)
        only once the library is indexed, so a computer never waits for a first
        index.

        Each audio id is listed once, from its oldest row (decision 5). A
        file's `rev` is the last change of its bytes, not of its row, so a move
        outside GetSetMix is not downloaded again. `removed` holds one entry per
        tombstoned audio id that no listed file has.
        """
        if refresh:
            with self.db.transaction() as conn:
                last = self._meta(conn, "last_reconcile")
                indexed = self._meta(conn, "indexed") is not None
            if last is None or self.clock() - _ts(last) > LINK_MAX_AGE:
                self.trigger()
            if indexed:
                self.wait(LINK_WAIT)
        with self.db.transaction() as conn:
            if self._meta(conn, "indexed") is None:
                return None
            rev = int(self._meta(conn, "rev") or 0)
            rows = conn.execute(
                "SELECT path, size, mtime_ns, audio_id, content_rev FROM library_files "
                "WHERE state = 'present' ORDER BY id").fetchall()
            tombstones = conn.execute(
                "SELECT path, audio_id, state, state_changed_at, trash_path FROM library_files "
                "WHERE state IN ('trashed', 'gone') ORDER BY rev, id").fetchall()
        files: dict[str, dict] = {}
        for r in rows:
            if r["audio_id"] in files or r["size"] <= 0 or not served(r["path"]):
                continue
            files[r["audio_id"]] = {"path": r["path"], "size": r["size"],
                                    "mtime": r["mtime_ns"] // 1_000_000_000,
                                    "id": r["audio_id"], "rev": r["content_rev"]}
        removed: dict[str, dict] = {}
        for r in tombstones:
            if r["audio_id"] in files or not served(r["path"]):
                continue
            removed.pop(r["audio_id"], None)  # the latest tombstone of an id counts
            deleted = r["state"] == "trashed" or r["trash_path"]
            removed[r["audio_id"]] = {"id": r["audio_id"], "path": r["path"],
                                      "at": r["state_changed_at"],
                                      "reason": "deleted" if deleted else "missing"}
        return {"protocol": 2, "rev": rev,
                "files": sorted(files.values(), key=lambda f: f["path"]),
                "removed": list(removed.values())}

    def file(self, fid: int) -> dict | None:
        """One row, all fields."""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM library_files WHERE id = ?", (fid,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _where(q: str | None, genre: str | None, folder: str | None,
               state: str) -> tuple[list[str], list]:
        if state not in STATES:
            raise ValueError(f"state must be one of {', '.join(STATES)}")
        where, params = ["state = ?"], [state]
        for word in fold(q or "").split():
            escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("search LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")
        if genre:
            where.append("genre = ?")
            params.append(genre)
        if folder:
            prefix = folder.strip("/") + "/"
            where.append("substr(path, 1, ?) = ? AND instr(substr(path, ?), '/') = 0")
            params += [len(prefix), prefix, len(prefix) + 1]
        return where, params

    @staticmethod
    def _editable(fmt: str, aid: str) -> bool:
        return fmt in EDITABLE_FORMATS and not audiohash.is_fallback(aid)

    def select(self, q: str | None = None, genre: str | None = None, folder: str | None = None,
               state: str = "present") -> list[dict]:
        """Every id matching a filter, with its editable flag, without paging."""
        where, params = self._where(q, genre, folder, state)
        with self.db.transaction() as conn:
            rows = conn.execute(
                f"SELECT id, format, audio_id FROM library_files WHERE {' AND '.join(where)} "
                "ORDER BY id", params).fetchall()
        return [{"id": r["id"], "editable": self._editable(r["format"], r["audio_id"])}
                for r in rows]

    def list(self, q: str | None = None, genre: str | None = None, folder: str | None = None,
             state: str = "present", sort: str = "added", order: str | None = None,
             limit: int = 200, cursor: str | None = None) -> dict:
        """One page of the list (design 3.3). Raises ValueError for a bad argument."""
        if sort not in SORTS:
            raise ValueError(f"sort must be one of {', '.join(SORTS)}")
        order = order or ("desc" if sort == "added" else "asc")
        if order not in ("asc", "desc"):
            raise ValueError("order must be asc or desc")
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        where, params = self._where(q, genre, folder, state)
        expr = SORTS[sort]
        page_where, page_params = list(where), list(params)
        if cursor:
            try:
                key = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
                value, last_id = key["k"]
                if key.get("s") != f"{sort}:{order}":
                    raise ValueError
            except Exception:
                raise ValueError("cursor does not belong to this list") from None
            op = "<" if order == "desc" else ">"
            page_where.append(f"({expr} {op} ? OR ({expr} = ? AND id {op} ?))")
            page_params += [value, value, last_id]
        direction = order.upper()
        with self.db.transaction() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM library_files WHERE {' AND '.join(where)}",
                                 params).fetchone()[0]
            rows = [dict(r) for r in conn.execute(
                f"SELECT * FROM library_files WHERE {' AND '.join(page_where)} "
                f"ORDER BY {expr} {direction}, id {direction} LIMIT ?",
                (*page_params, limit + 1))]
            more = len(rows) > limit
            rows = rows[:limit]
            same = self._same_audio(conn, rows)
            rev = int(self._meta(conn, "rev") or 0)
        nxt = None
        if more:
            last = rows[-1]
            raw = json.dumps({"k": [last[SORT_COLUMNS[sort]], last["id"]], "s": f"{sort}:{order}"},
                             separators=(",", ":"), ensure_ascii=False)
            nxt = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        return {"rev": rev, "total": total, "next": nxt,
                "items": [self._item(r, same) for r in rows]}

    @staticmethod
    def _same_audio(conn: sqlite3.Connection, rows: list[dict]) -> dict[str, list[int]]:
        ids = sorted({r["audio_id"] for r in rows})
        out: dict[str, list[int]] = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ", ".join("?" for _ in chunk)
            for r in conn.execute(
                    f"SELECT id, audio_id FROM library_files WHERE state = 'present' "
                    f"AND audio_id IN ({marks}) ORDER BY id", chunk):
                out.setdefault(r["audio_id"], []).append(r["id"])
        return out

    def _item(self, row: dict, same: dict[str, list[int]]) -> dict:
        return {
            "id": row["id"], "audio_id": row["audio_id"], "path": row["path"],
            "format": row["format"], "title": row["title"], "artist": row["artist"],
            "album": row["album"], "genre": row["genre"], "year": row["year"],
            "duration": row["duration"], "has_cover": bool(row["has_cover"]),
            "size": row["size"], "added_at": row["added_at"],
            "editable": self._editable(row["format"], row["audio_id"]),
            "multi": [f for f in row["multi"].split(",") if f],
            "same_audio": [i for i in same.get(row["audio_id"], []) if i != row["id"]],
        }


# ------------------------------------------------------------ the app's one
_current: Library | None = None
_current_lock = threading.Lock()
_periodic: asyncio.Task | None = None


def current() -> Library:
    """The Library over the app's database (rebuilt if the database is)."""
    global _current
    with _current_lock:
        if _current is None or _current.db is not dbmod.db:
            _current = Library(dbmod.db)
        return _current


async def _every_interval() -> None:
    while True:
        current().trigger()
        try:
            await asyncio.to_thread(current().purge_due)
        except Exception:
            log.exception("library: the daily purge of the trash failed")
        await asyncio.sleep(INTERVAL_SECONDS)


def start() -> None:
    """At app start: a pass now (the first index, in the background), then every 5
    minutes; the trash is purged of what is older than `trash_days` once a day."""
    global _periodic
    _periodic = asyncio.get_running_loop().create_task(_every_interval())


def stop() -> None:
    if _periodic is not None:
        _periodic.cancel()
