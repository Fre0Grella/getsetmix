"""GetSetMix — API + UI entrypoint."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import mimetypes
import os
import secrets
import string
import sys
import urllib.parse
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (
    __version__,
    genres,
    library,
    library_api,
    link,
    matching,
    metadata,
    metrics,
    outbound,
    rules,
    tagger,
    ytdl,
)
from .auth import bearer_token
from .config import (
    AUTH_TOKEN,
    BASIC_PASS,
    BASIC_USER,
    DATA_DIR,
    ensure_dirs,
    patch_problem,
    settings,
)
from .db import ACTIVE_STATUSES, EDITABLE_STATUSES, db
from .worker import worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("getsetmix")

app = FastAPI(title="GetSetMix", version=__version__, docs_url=None, redoc_url=None)
app.include_router(library_api.router)
STATIC = Path(__file__).parent / "static"

FETCH_CONCURRENCY = asyncio.Semaphore(2)

# The event loop keeps only a weak reference to a task: one nothing else holds
# can be garbage-collected before it finishes. Background work is kept here
# until it is done.
_background: set[asyncio.Task] = set()


def _spawn(work: Coroutine[Any, Any, None]) -> asyncio.Task:
    """Run `work` in the background, held until it finishes."""
    task = asyncio.create_task(work)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


# --------------------------------------------------------------------- auth
def _basic_ok(header: str) -> bool:
    try:
        scheme, _, payload = header.partition(" ")
        if scheme.lower() != "basic":
            return False
        user, _, pwd = base64.b64decode(payload).decode().partition(":")
        return secrets.compare_digest(user, BASIC_USER) and secrets.compare_digest(pwd, BASIC_PASS)
    except Exception:
        return False


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Private-by-default; optional static token or Basic Auth when exposed.
    protected = request.url.path.startswith("/api") or request.url.path == "/metrics"
    # /api/link/* answers to the paired computers' own tokens instead.
    if request.url.path.startswith("/api/link/"):
        if not link.authorized(request.headers.get("authorization", "")):
            return JSONResponse({"detail": "unknown computer: pair it again from GetSetMix Setup"},
                                status_code=401)
        return await call_next(request)
    if protected and request.url.path != "/api/ping":
        if AUTH_TOKEN:
            supplied = (
                request.headers.get("x-auth-token")
                or request.query_params.get("token")
                or bearer_token(request.headers.get("authorization", ""))
            )
            if not secrets.compare_digest(supplied or "", AUTH_TOKEN):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        elif BASIC_USER and BASIC_PASS and not _basic_ok(request.headers.get("authorization", "")):
            return Response(status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="GetSetMix"'})
    return await call_next(request)


# The page and its scripts are checked again on every load (a cheap 304 when
# nothing changed), so an update shows at once instead of whenever the
# browser's own guess at freshness runs out. Covers keep their own caching.
UI_PATHS = ("/", "/share", "/sw.js", "/manifest.webmanifest")


@app.middleware("http")
async def revalidate_ui(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if (path in UI_PATHS or path.startswith("/static/")) and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache"
    return response


# ------------------------------------------------------------------ models
class AddUrl(BaseModel):
    url: str


class TrackEdit(BaseModel):
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    cover_url: str | None = None


class BatchStart(BaseModel):
    ids: list[str] | None = None
    concurrency: int | None = None  # optional per-batch override
    force: bool = False             # download even tracks flagged as duplicates


class SettingsPatch(BaseModel):
    library_root: str | None = None
    output_format: str | None = None
    concurrency: int | None = None
    filename_template: str | None = None
    language: str | None = None
    trash_days: int | None = None


class Purge(BaseModel):
    scope: str  # "history" | "completed"


# ------------------------------------------- downloads and the Library index
def _label(row: dict) -> str:
    """How the UI names a Library file: "Artist – Title", else its file name."""
    label = f'{row["artist"]} – {row["title"]}'.strip(" –")
    return label or row["path"].rsplit("/", 1)[-1]


async def _flag_duplicate(tid: str) -> None:
    """Mark a staged track the Library already has (issue #71). The reason is
    the matching file's label, which the UI words in the user's language."""
    track = db.get_track(tid)
    if not track or track["status"] != "staged":
        return
    match = await asyncio.to_thread(library.current().same_song, track)
    flag = {"duplicate": 1 if match else 0,
            "duplicate_reason": _label(match) if match else "",
            "duplicate_of": match["id"] if match else None}
    if any(track.get(k) != v for k, v in flag.items()):  # no write, no new updated_at
        db.update_track(tid, **flag)


_checked_rev: int | None = None  # the Library rev the staged flags were last checked at


async def _recheck_duplicates() -> None:
    """Check every staged track again when the Library has changed since the
    last check: a delete, a restore, a reconcile or a finished download can
    each make a track owned, or no longer owned. One cheap read otherwise."""
    global _checked_rev
    rev = await asyncio.to_thread(library.current().rev)
    if rev == _checked_rev:
        return
    for track in db.tracks_by_status("staged"):
        await _flag_duplicate(track["id"])
    _checked_rev = rev  # a change during the loop gets the next call


def _with_library_state(tracks: list[dict]) -> list[dict]:
    """Say where each finished download is in the Library now (issue #71):
    `library_state` present, trashed or absent, and `library_id`. Both stay
    None until the first index is complete, when "absent" would be a guess."""
    for t in tracks:
        t["library_state"] = t["library_id"] = None
    done = [t for t in tracks if t["status"] == "ingested"]
    lib = library.current()
    if not done or not lib.indexed():
        return tracks
    found = lib.locate([(t.get("audio_id") or "", t.get("file_path") or "") for t in done])
    for t, row in zip(done, found, strict=True):
        if row is not None and row["state"] in ("present", "trashed"):
            t["library_state"], t["library_id"] = row["state"], row["id"]
        else:
            t["library_state"], t["library_id"] = "absent", None
    return tracks


# --------------------------------------------------- background meta fetch
async def _fetch_track_meta(tid: str, url: str) -> None:
    async with FETCH_CONCURRENCY:
        try:
            meta = await asyncio.to_thread(metadata.fetch_single, url)
            db.update_track(
                tid,
                status="staged",
                title=meta["title"], artist=meta["artist"], album=meta["album"],
                genre=meta["genre"] or "", duration=meta["duration"],
                thumbnail=meta["thumbnail"], video_id=meta["video_id"],
                source=meta["source"], url=meta["url"] or url, error="",
            )
            await _flag_duplicate(tid)
        except Exception as exc:
            # Metadata fetch failed -> manual entry allowed to continue.
            db.update_track(tid, status="fetch_error", error=ytdl.explain(exc))


# -------------------------------------------------------------------- API
@app.get("/api/ping")
async def ping():
    return {"app": "GetSetMix", "auth": bool(AUTH_TOKEN or (BASIC_USER and BASIC_PASS))}


@app.post("/api/tracks", status_code=201)
async def add_tracks(body: AddUrl):
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "Not a valid URL")
    duplicate = db.url_seen(url)
    tid = db.create_track(url, status="fetching")
    _spawn(_resolve_new(tid, url))
    return {"ids": [tid], "duplicate": duplicate}


async def _resolve_new(tid: str, url: str) -> None:
    """Resolve a freshly pasted URL: replace the placeholder row with the
    real single track, or fan out into playlist entries."""
    try:
        probed = await asyncio.to_thread(metadata.probe, url)
    except Exception as exc:
        db.update_track(tid, status="fetch_error", error=ytdl.explain(exc))
        db.add_history(url)
        return

    db.add_history(url)
    if probed["kind"] == "single":
        m = probed["meta"]
        db.update_track(
            tid, status="staged",
            url=m["url"] or url, title=m["title"], artist=m["artist"],
            album=m["album"], genre=m["genre"] or "", duration=m["duration"],
            thumbnail=m["thumbnail"], video_id=m["video_id"], source=m["source"],
        )
        await _flag_duplicate(tid)
        return

    db.delete_track(tid)  # placeholder replaced by one row per entry
    for entry in probed["entries"]:
        eurl = entry["url"]
        if not eurl:
            continue
        artist, title = metadata.split_artist_title(entry["title"], entry["uploader"])
        new_id = db.create_track(
            eurl, status="fetching",
            title=title, artist=artist, duration=entry["duration"],
            thumbnail=entry["thumbnail"], video_id=entry["id"],
            source=entry["extractor"],
        )
        _spawn(_fetch_track_meta(new_id, eurl))


@app.get("/api/tracks")
async def list_tracks():
    await _recheck_duplicates()
    tracks = await asyncio.to_thread(_with_library_state, db.list_tracks())
    for t in tracks:  # the UI reads these instead of keeping its own status lists
        t["editable"] = t["status"] in EDITABLE_STATUSES
        t["active"] = t["status"] in ACTIVE_STATUSES
    return {
        "tracks": tracks,
        "active_downloads": worker.active_downloads,
        "busy": worker.busy,
    }


def _track_or_404(tid: str) -> dict:
    track = db.get_track(tid)
    if not track:
        raise HTTPException(404, "Track not found")
    return track


def _editable_track(tid: str) -> dict:
    """A track whose metadata and cover may change: only before its download starts."""
    track = _track_or_404(tid)
    if track["status"] not in EDITABLE_STATUSES:
        raise HTTPException(409, "Track is locked while downloading")
    return track


@app.patch("/api/tracks/{tid}")
async def edit_track(tid: str, body: TrackEdit):
    track = _editable_track(tid)
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch:
        if track["status"] == "fetch_error" and (
            (patch.get("title") or track["title"]) and (patch.get("artist") or track["artist"])
        ):
            patch["status"] = "staged"
            patch["error"] = ""
        db.update_track(tid, **patch)
        # Editing title/artist changes a track's identity -> re-check duplicates.
        if "title" in patch or "artist" in patch:
            await _flag_duplicate(tid)
    return _track_or_404(tid)


@app.delete("/api/tracks/{tid}", status_code=204)
async def remove_track(tid: str):
    track = db.get_track(tid)
    if not track:
        return Response(status_code=204)  # already gone: deleting is idempotent
    if track["status"] in ACTIVE_STATUSES:
        raise HTTPException(409, "Cannot remove a track while it downloads")
    db.delete_track(tid)
    return Response(status_code=204)


@app.post("/api/tracks/{tid}/cover")
async def upload_cover(tid: str, file: UploadFile):
    """A cover for a staged track, used when it is downloaded. Checked as the
    Library's covers are: 413 over 10 MB, 400 not a JPEG, PNG or WebP image."""
    _editable_track(tid)
    try:
        data, _ = library.check_image(await file.read(tagger.MAX_COVER + 1))
    except library.LibraryError as exc:
        raise HTTPException(exc.status, exc.detail) from None
    dest = DATA_DIR / "covers" / f"{tid}.img"
    dest.write_bytes(data)
    db.update_track(tid, cover_path=str(dest), cover_url="")
    return _track_or_404(tid)


@app.get("/api/tracks/{tid}/cover")
async def get_cover(tid: str):
    """The uploaded cover, with the type its bytes say (never what a client
    claimed: an SVG served from this origin could run script)."""
    track = _track_or_404(tid)
    data = b""
    if track.get("cover_path"):
        with contextlib.suppress(OSError):
            data = await asyncio.to_thread(Path(track["cover_path"]).read_bytes)
    mime = tagger.image_type(data)
    if mime is None:
        raise HTTPException(404, "No uploaded cover")
    return Response(data, media_type=mime, headers={"X-Content-Type-Options": "nosniff"})


@app.post("/api/tracks/{tid}/retry")
async def retry_track(tid: str):
    track = _track_or_404(tid)
    if track["status"] != "error":
        raise HTTPException(409, "Only failed tracks can be retried")
    queued = await worker.start_batch([tid])
    return {"queued": queued}


@app.post("/api/batch/start")
async def start_batch(body: BatchStart):
    ids = body.ids or [t["id"] for t in db.tracks_by_status("staged")]
    if not body.force:
        await _recheck_duplicates()  # the gate reads the flags: bring them up to date
        # Gate on duplicates: if any selected track already exists, ask the
        # user before downloading instead of silently making a numbered copy.
        dupes = [
            {"id": t["id"], "title": t["title"], "artist": t["artist"],
             "reason": t["duplicate_reason"]}
            for t in (db.get_track(i) for i in ids)
            if t and t["status"] == "staged" and t.get("duplicate")
        ]
        if dupes:
            return {"needs_confirm": True, "duplicates": dupes, "queued": [], "count": 0}
    queued = await worker.start_batch(ids, body.concurrency)
    return {"queued": queued, "count": len(queued)}


@app.post("/api/batch/cancel")
async def cancel_batch():
    drained = await worker.cancel_batch()
    return {"requeued_to_staged": drained}


@app.get("/api/cover-search")
async def cover_search(q: str):
    """Source image search for cover override (iTunes Search API, no key)."""
    if not q.strip():
        return {"results": []}
    qs = urllib.parse.urlencode({"term": q, "media": "music", "limit": 12})
    url = f"https://itunes.apple.com/search?{qs}"

    def _get() -> list[dict]:
        with outbound.open_url(url) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
        out = []
        for item in payload.get("results", []):
            art = (item.get("artworkUrl100") or "").replace("100x100", "600x600")
            if art:
                out.append({
                    "thumb": item.get("artworkUrl100"),
                    "full": art,
                    "label": f"{item.get('artistName', '')} – "
                             f"{item.get('trackName') or item.get('collectionName', '')}",
                })
        return out

    try:
        return {"results": await asyncio.to_thread(_get)}
    except Exception as exc:
        raise HTTPException(502, f"Cover search failed: {exc}") from exc


def _drives() -> dict:
    """The drive letters of a Windows machine, as the top of the folder picker."""
    drives = [{"name": f"{d}:", "path": f"{d}:\\"}
              for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    return {"path": "", "parent": None, "dirs": drives}


def _subfolders(base: Path) -> list[dict]:
    """The folders directly in `base`, by name; hidden and unreadable ones left out.
    Raises OSError when `base` itself cannot be listed."""
    dirs = []
    for p in sorted(base.iterdir(), key=lambda p: p.name.lower()):
        if p.name.startswith("."):
            continue
        try:
            if p.is_dir():
                dirs.append({"name": p.name, "path": str(p)})
        except OSError:
            continue  # broken symlinks, unreadable entries
    return dirs


def _folder_listing(path: str) -> dict:
    if not path.strip():
        if os.name == "nt":
            return _drives()
        base = Path("/")
    else:
        base = Path(path).expanduser()
    try:
        base = base.resolve()
        if not base.is_dir():
            base = base.parent  # tolerate file paths pasted in the inputs
        if not base.is_dir():
            raise HTTPException(404, "Not a directory")
        dirs = _subfolders(base)
    except PermissionError:
        raise HTTPException(403, "Permission denied") from None
    except OSError as exc:
        raise HTTPException(400, str(exc).splitlines()[0]) from exc
    parent = str(base.parent) if base.parent != base else None
    if parent is None and os.name == "nt":
        parent = ""  # drive root -> drive list
    return {"path": str(base), "parent": parent, "dirs": dirs}


@app.get("/api/fs/list")
async def fs_list(path: str = ""):
    """Server-side directory listing for the folder picker (the library root).

    Empty path lists drives on Windows and / on POSIX. Only folders are listed.
    """
    return await asyncio.to_thread(_folder_listing, path)


@app.get("/api/settings")
async def get_settings():
    return settings.data


@app.put("/api/settings")
async def put_settings(body: SettingsPatch):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    problem = patch_problem(patch)
    if problem:
        raise HTTPException(400, problem)
    settings.update(patch)
    ensure_dirs()
    return settings.data


@app.get("/api/status")
async def status():
    """Download-engine health: yt-dlp version/age and the JS runtime YouTube needs."""
    return {"version": __version__, "ytdlp": await asyncio.to_thread(ytdl.status)}


@app.get("/api/stats")
async def stats():
    return db.stats()


@app.get("/api/history")
async def history():
    return {"history": db.history()}


@app.post("/api/purge")
async def purge(body: Purge):
    if body.scope == "history":
        return {"purged": db.purge_history(), "scope": "history"}
    if body.scope == "completed":
        return {"purged": db.purge_completed(), "scope": "completed"}
    raise HTTPException(400, "scope must be 'history' or 'completed'")


# ------------------------------------------------------------ cleanup rules
@app.get("/api/library/rules")
async def library_rules():
    """The cleanup-rule catalogue, plus the genre list the UI's picker reads.
    The UI reads only the genres today; the catalogue is for batch editing (#47)."""
    return {**rules.catalogue(), "genres": list(genres.GENRES),
            "genre_picks": list(genres.GENRE_PICKS),
            # rules the UI applies as you type; the server checks them again
            "year_range": list(library.YEAR_RANGE), "source_pattern": matching.SOURCE_PATTERN}


# ------------------------------------------------------------------- link
@app.get("/api/link/files")
async def link_files():
    """Link protocol 2 from the index; protocol 1, from a disk walk, until it is built."""
    listing = await asyncio.to_thread(library.current().link_listing, refresh=True)
    if listing is not None:
        return {"version": __version__, **listing}
    root = Path(settings["library_root"])
    files = await asyncio.to_thread(link.list_files, root)
    return {"version": __version__, "files": files}


@app.get("/api/link/file")
async def link_file(path: str):
    found = link.resolve(Path(settings["library_root"]), path)
    if found is None:
        raise HTTPException(404, "no such track")
    return FileResponse(found, media_type="application/octet-stream")


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint():
    return metrics.render(worker.active_downloads)


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


# ----------------------------------------------------------------- licenses
def _notice_file(name: str) -> Path | None:
    """LICENSE and THIRD-PARTY-NOTICES.md, wherever this build keeps them: the
    source tree, the Docker image, or the PyInstaller bundle."""
    roots = [Path(__file__).parent.parent, Path("/usr/share/doc/getsetmix")]
    bundle = getattr(sys, "_MEIPASS", None)  # set by PyInstaller only
    if bundle:
        roots.insert(0, Path(bundle))
    for root in roots:
        if (root / name).is_file():
            return root / name
    return None


# Public on purpose, like /healthz: the notices hold no secrets and the footer
# link must work in a plain browser tab, where no token header is sent.
@app.get("/licenses", response_class=PlainTextResponse)
async def licenses():
    found = _notice_file("THIRD-PARTY-NOTICES.md")
    if found is None:
        raise HTTPException(404, "notices not found in this build")
    return (found.read_text(encoding="utf-8")
            + "\n\n---\n\nGetSetMix itself is AGPL-3.0-only. Full text: /licenses/agpl\n")


@app.get("/licenses/agpl", response_class=PlainTextResponse)
async def licenses_agpl():
    found = _notice_file("LICENSE")
    if found is None:
        raise HTTPException(404, "license not found in this build")
    return found.read_text(encoding="utf-8")


# --------------------------------------------------------------------- UI
# The UI is ES modules, which a browser runs only when served as JavaScript.
# Python takes types from the system, and a Windows registry can say
# text/plain for .js: pin it, or the local app would show a blank page.
mimetypes.add_type("text/javascript", ".js")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/share")
async def share():
    # Web Share Target landing (Android PWA). The shared link arrives in the
    # query string; the SPA reads it on boot and stages the track. Same
    # document as "/" so all the existing UI/edit/download flow applies.
    return FileResponse(STATIC / "index.html")


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(STATIC / "manifest.webmanifest",
                        media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    # Served from the root so its scope covers the whole app.
    return FileResponse(STATIC / "sw.js", media_type="application/javascript")


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(STATIC / "assets" / "favicon.ico")


@app.on_event("startup")
async def on_startup():
    ensure_dirs()
    # Recover tracks stuck mid-download from a previous run.
    for t in db.tracks_by_status(*ACTIVE_STATUSES):
        db.update_track(t["id"], status="staged", progress=0)
    log.info("GetSetMix ready — library=%s", settings["library_root"])
    for problem in await asyncio.to_thread(ytdl.problems):
        log.warning("%s", problem)
    library.start()  # index the library now, in the background, then every 5 minutes


@app.on_event("shutdown")
async def on_shutdown():
    library.stop()
