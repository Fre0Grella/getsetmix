"""Ingestion worker.

Runs batch downloads with bounded parallelism (global default 2, optional
per-batch override). Each track: download (yt-dlp + ffmpeg) -> tag (mutagen)
-> move into the library root -> append to the Rekordbox XML. Failed tracks
don't halt the batch; they are marked `error` and can be retried per-track.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import threading
import time
from pathlib import Path

import yt_dlp

from . import rekordbox, tagger
from .config import DATA_DIR, settings
from .db import db, now_iso
from .naming import render_filename, unique_path

log = logging.getLogger("getsetmix.worker")


class BatchCancelled(Exception):
    pass


class Worker:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._cancel = threading.Event()
        self._runners: list[asyncio.Task] = []
        self._target_runners = 0
        self.active_downloads = 0
        self._loop: asyncio.AbstractEventLoop | None = None

    # ----------------------------------------------------------- lifecycle
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def busy(self) -> bool:
        return self.active_downloads > 0 or not self._queue.empty()

    # --------------------------------------------------------------- batch
    async def start_batch(self, ids: list[str], concurrency: int | None = None) -> list[str]:
        """Queue staged tracks; spin up runners. Returns the queued ids."""
        self._cancel.clear()
        queued: list[str] = []
        for tid in ids:
            track = db.get_track(tid)
            if not track or track["status"] not in ("staged", "error", "fetch_error"):
                continue
            if not (track.get("title") and track.get("artist")):
                db.update_track(tid, status="fetch_error",
                                error="Title and artist are required")
                continue
            db.update_track(tid, status="queued", progress=0, error="")
            self._queue.put_nowait(tid)
            queued.append(tid)

        n = max(1, min(8, concurrency or settings["concurrency"]))
        self._target_runners = n
        self._runners = [r for r in self._runners if not r.done()]
        while len(self._runners) < n:
            self._runners.append(asyncio.create_task(self._runner()))
        return queued

    async def cancel_batch(self) -> int:
        """Stop active downloads, return queued tracks to `staged`."""
        self._cancel.set()
        drained = 0
        while not self._queue.empty():
            try:
                tid = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            db.update_track(tid, status="staged", progress=0)
            self._queue.task_done()
            drained += 1
        return drained

    # -------------------------------------------------------------- runner
    async def _runner(self) -> None:
        while True:
            try:
                tid = await asyncio.wait_for(self._queue.get(), timeout=30)
            except asyncio.TimeoutError:
                return  # idle runner exits; recreated on next batch
            try:
                if self._cancel.is_set():
                    db.update_track(tid, status="staged", progress=0)
                else:
                    self.active_downloads += 1
                    try:
                        await asyncio.to_thread(self._process, tid)
                    finally:
                        self.active_downloads -= 1
            except Exception:
                log.exception("runner crashed on %s", tid)
            finally:
                self._queue.task_done()

    # ----------------------------------------------------- per-track logic
    def _process(self, tid: str) -> None:
        track = db.get_track(tid)
        if not track:
            return
        started = time.monotonic()
        tmpdir = DATA_DIR / "tmp" / tid
        try:
            db.update_track(tid, status="downloading", progress=0, error="")
            tmpdir.mkdir(parents=True, exist_ok=True)

            audio = self._download(track, tmpdir)

            db.update_track(tid, status="tagging", progress=100)
            final = self._place_in_library(track, audio)
            tagger.tag_file(str(final), {**track, "file_path": str(final)})
            rekordbox.add_track(
                settings["xml_path"], track, str(final), settings["playlist_name"]
            )

            elapsed = time.monotonic() - started
            db.update_track(
                tid, status="ingested", progress=100, file_path=str(final),
                downloaded_at=now_iso(), download_seconds=elapsed,
            )
            db.bump("total_ingested")
            db.bump("download_seconds_sum", elapsed)
            db.bump("download_seconds_count")
            log.info("ingested %s -> %s (%.1fs)", tid, final.name, elapsed)
        except BatchCancelled:
            db.update_track(tid, status="staged", progress=0)
        except Exception as exc:  # per-track error, batch continues
            msg = str(exc).splitlines()[0][:300]
            db.update_track(tid, status="error", error=msg)
            db.bump(f"errors_source:{track.get('source') or 'unknown'}")
            log.warning("track %s failed: %s", tid, msg)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _download(self, track: dict, tmpdir: Path) -> Path:
        fmt = settings["output_format"]
        cancel = self._cancel
        tid = track["id"]
        last = {"pct": -5.0}

        def hook(d: dict) -> None:
            if cancel.is_set():
                raise BatchCancelled()
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                if total:
                    pct = done * 100.0 / total
                    if pct - last["pct"] >= 2:  # throttle DB writes
                        last["pct"] = pct
                        db.update_track(tid, progress=round(pct, 1))
            elif d.get("status") == "finished":
                db.update_track(tid, status="tagging", progress=100)

        postprocessor = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3" if fmt == "mp3" else "flac",
        }
        if fmt == "mp3":
            postprocessor["preferredquality"] = "320"

        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(tmpdir / "%(id)s.%(ext)s"),
            "postprocessors": [postprocessor],
            "progress_hooks": [hook],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 30,
            "retries": 3,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(track["url"], download=True)

        ext = ".mp3" if fmt == "mp3" else ".flac"
        produced = sorted(tmpdir.glob(f"*{ext}"))
        if not produced:
            produced = sorted(p for p in tmpdir.iterdir() if p.is_file())
        if not produced:
            raise RuntimeError("Download produced no audio file")
        return produced[0]

    def _place_in_library(self, track: dict, audio: Path) -> Path:
        # Download directly into the configured library root (no inbox folder).
        library = Path(settings["library_root"])
        library.mkdir(parents=True, exist_ok=True)
        stem = render_filename(settings["filename_template"], track)
        final, collided = unique_path(library, stem, audio.suffix.lower())
        if collided:
            log.warning("filename collision for %r, saved as %s", stem, final.name)
        shutil.move(str(audio), final)
        return final


worker = Worker()
