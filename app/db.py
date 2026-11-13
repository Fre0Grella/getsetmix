"""SQLite persistence: staged/processed tracks, URL history, counters."""
from __future__ import annotations

import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .config import DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    source TEXT DEFAULT '',
    video_id TEXT DEFAULT '',
    title TEXT DEFAULT '',
    artist TEXT DEFAULT '',
    album TEXT DEFAULT '',
    genre TEXT DEFAULT '',
    duration REAL DEFAULT 0,
    thumbnail TEXT DEFAULT '',
    cover_url TEXT DEFAULT '',
    cover_path TEXT DEFAULT '',
    status TEXT NOT NULL,
    progress REAL DEFAULT 0,
    error TEXT DEFAULT '',
    duplicate INTEGER DEFAULT 0,
    duplicate_reason TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    download_seconds REAL DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    downloaded_at TEXT
);
CREATE TABLE IF NOT EXISTS url_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counters (
    key TEXT PRIMARY KEY,
    value REAL DEFAULT 0
);
-- The library index (docs/design/library.md, 3.2); written by app/library.py.
CREATE TABLE IF NOT EXISTS library_files (
    id               INTEGER PRIMARY KEY,
    path             TEXT    NOT NULL,
    audio_id         TEXT    NOT NULL,
    size             INTEGER NOT NULL,
    mtime_ns         INTEGER NOT NULL,
    format           TEXT    NOT NULL,
    title            TEXT    NOT NULL DEFAULT '',
    artist           TEXT    NOT NULL DEFAULT '',
    album            TEXT    NOT NULL DEFAULT '',
    genre            TEXT    NOT NULL DEFAULT '',
    year             INTEGER,
    comment          TEXT    NOT NULL DEFAULT '',
    has_cover        INTEGER NOT NULL DEFAULT 0,
    multi            TEXT    NOT NULL DEFAULT '',
    duration         REAL,
    bitrate          INTEGER,
    sample_rate      INTEGER,
    source_url       TEXT    NOT NULL DEFAULT '',
    search           TEXT    NOT NULL,
    added_at         TEXT    NOT NULL,
    rev              INTEGER NOT NULL,
    state            TEXT    NOT NULL DEFAULT 'present',
    state_changed_at TEXT,
    trash_path       TEXT
);
-- One live row per path. Tombstones (trashed, gone) keep their last path,
-- which a new file may take, so the design's UNIQUE is partial here.
CREATE UNIQUE INDEX IF NOT EXISTS library_files_path
    ON library_files (path) WHERE state IN ('present', 'missing');
CREATE INDEX IF NOT EXISTS library_files_audio ON library_files (audio_id);
CREATE INDEX IF NOT EXISTS library_files_state ON library_files (state, rev);
CREATE TABLE IF NOT EXISTS library_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# Track lifecycle:
#   fetching -> staged | fetch_error           (metadata phase)
#   staged   -> queued -> downloading -> tagging -> ingested
#   any download phase -> error (per-track retry allowed)
EDITABLE_STATUSES = ("staged", "fetch_error", "error")
ACTIVE_STATUSES = ("queued", "downloading", "tagging")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path = DATA_DIR / "getsetmix.db"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a DB was first created."""
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(tracks)")}
        for col, ddl in (
            ("duplicate", "duplicate INTEGER DEFAULT 0"),
            ("duplicate_reason", "duplicate_reason TEXT DEFAULT ''"),
        ):
            if col not in have:
                self._conn.execute(f"ALTER TABLE tracks ADD COLUMN {ddl}")

    # ------------------------------------------------------------- helpers
    def _exec(self, sql: str, params: tuple = ()):  # write
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """The connection, held for several statements committed as one."""
        with self._lock:
            try:
                yield self._conn
            except BaseException:
                self._conn.rollback()
                raise
            self._conn.commit()

    # -------------------------------------------------------------- tracks
    def create_track(self, url: str, **fields) -> str:
        tid = uuid.uuid4().hex[:12]
        base = {
            "id": tid, "url": url, "status": "fetching",
            "created_at": now_iso(), "updated_at": now_iso(),
        }
        base.update(fields)
        cols = ", ".join(base.keys())
        marks = ", ".join("?" for _ in base)
        self._exec(f"INSERT INTO tracks ({cols}) VALUES ({marks})", tuple(base.values()))
        return tid

    def update_track(self, tid: str, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = now_iso()
        sets = ", ".join(f"{k} = ?" for k in fields)
        self._exec(f"UPDATE tracks SET {sets} WHERE id = ?", (*fields.values(), tid))

    def get_track(self, tid: str) -> dict | None:
        rows = self._query("SELECT * FROM tracks WHERE id = ?", (tid,))
        return rows[0] if rows else None

    def list_tracks(self) -> list[dict]:
        return self._query("SELECT * FROM tracks ORDER BY created_at DESC, id DESC")

    def delete_track(self, tid: str) -> None:
        self._exec("DELETE FROM tracks WHERE id = ?", (tid,))

    def tracks_by_status(self, *statuses: str) -> list[dict]:
        marks = ", ".join("?" for _ in statuses)
        return self._query(
            f"SELECT * FROM tracks WHERE status IN ({marks}) ORDER BY created_at ASC",
            statuses,
        )

    def purge_completed(self) -> int:
        cur = self._exec(
            "DELETE FROM tracks WHERE status IN ('ingested', 'error', 'fetch_error')"
        )
        return cur.rowcount

    # ------------------------------------------------------------- history
    def add_history(self, url: str) -> None:
        self._exec("INSERT INTO url_history (url, added_at) VALUES (?, ?)", (url, now_iso()))

    def history(self, limit: int = 200) -> list[dict]:
        return self._query(
            "SELECT * FROM url_history ORDER BY id DESC LIMIT ?", (limit,)
        )

    def purge_history(self) -> int:
        return self._exec("DELETE FROM url_history").rowcount

    def url_seen(self, url: str) -> bool:
        return bool(self._query("SELECT 1 FROM url_history WHERE url = ? LIMIT 1", (url,)))

    # ------------------------------------------------------------ counters
    def bump(self, key: str, amount: float = 1) -> None:
        self._exec(
            "INSERT INTO counters (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = value + ?",
            (key, amount, amount),
        )

    def counter(self, key: str) -> float:
        rows = self._query("SELECT value FROM counters WHERE key = ?", (key,))
        return rows[0]["value"] if rows else 0

    def counters_prefix(self, prefix: str) -> dict[str, float]:
        rows = self._query(
            "SELECT key, value FROM counters WHERE key LIKE ?", (prefix + "%",)
        )
        return {r["key"][len(prefix):]: r["value"] for r in rows}

    # --------------------------------------------------------------- stats
    def downloaded_since(self, days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        rows = self._query(
            "SELECT COUNT(*) AS n FROM tracks WHERE status = 'ingested' AND downloaded_at >= ?",
            (cutoff,),
        )
        return rows[0]["n"]

    def status_counts(self) -> dict[str, int]:
        rows = self._query("SELECT status, COUNT(*) AS n FROM tracks GROUP BY status")
        return {r["status"]: r["n"] for r in rows}

    def stats(self) -> dict:
        return {
            "songs_30d": self.downloaded_since(30),
            "songs_365d": self.downloaded_since(365),
            "songs_all_time": int(self.counter("total_ingested")),
            "status_counts": self.status_counts(),
            "download_seconds_sum": self.counter("download_seconds_sum"),
            "download_seconds_count": self.counter("download_seconds_count"),
            "errors_by_source": self.counters_prefix("errors_source:"),
            "history_count": self._query("SELECT COUNT(*) AS n FROM url_history")[0]["n"],
        }


db = Database()
