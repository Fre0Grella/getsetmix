"""GetSetMix — API + UI entrypoint."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import secrets
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import metadata, metrics, rekordbox
from .config import AUTH_TOKEN, BASIC_PASS, BASIC_USER, DATA_DIR, ensure_dirs, settings
from .db import ACTIVE_STATUSES, EDITABLE_STATUSES, db
from .worker import worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("getsetmix")

app = FastAPI(title="GetSetMix", version="1.0.0", docs_url=None, redoc_url=None)
STATIC = Path(__file__).parent / "static"

FETCH_CONCURRENCY = asyncio.Semaphore(2)


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
    if protected and request.url.path != "/api/ping":
        if AUTH_TOKEN:
            supplied = (
                request.headers.get("x-auth-token")
                or request.query_params.get("token")
                or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            )
            if not secrets.compare_digest(supplied or "", AUTH_TOKEN):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        elif BASIC_USER and BASIC_PASS:
            if not _basic_ok(request.headers.get("authorization", "")):
                return Response(status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="GetSetMix"'})
    return await call_next(request)


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
    xml_path: str | None = None
    collection_xml_path: str | None = None
    playlist_name: str | None = None
    output_format: str | None = None
    concurrency: int | None = None
    filename_template: str | None = None
    language: str | None = None


class Purge(BaseModel):
    scope: str  # "history" | "completed" | "inbox"


# ------------------------------------------------------ duplicate flagging
def _dup_sources() -> list[tuple[str, str]]:
    """(xml_path, label) pairs to test a song against: the inbox we write, plus
    the user's full Rekordbox collection export when configured."""
    sources = [(str(settings["xml_path"]), "the inbox")]
    coll = str(settings.get("collection_xml_path") or "").strip()
    if coll:
        sources.append((coll, "your collection"))
    return sources


async def _flag_duplicate(tid: str) -> None:
    """Mark a staged track if it already exists in the inbox/collection XML."""
    track = db.get_track(tid)
    if not track or track["status"] != "staged":
        return
    reason = await asyncio.to_thread(rekordbox.find_duplicate, track, _dup_sources())
    db.update_track(tid, duplicate=1 if reason else 0, duplicate_reason=reason)


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
            msg = str(exc).splitlines()[0][:300]
            db.update_track(tid, status="fetch_error", error=msg)


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
    asyncio.create_task(_resolve_new(tid, url))
    return {"ids": [tid], "duplicate": duplicate}


async def _resolve_new(tid: str, url: str) -> None:
    """Resolve a freshly pasted URL: replace the placeholder row with the
    real single track, or fan out into playlist entries."""
    try:
        probed = await asyncio.to_thread(metadata.probe, url)
    except Exception as exc:
        db.update_track(tid, status="fetch_error", error=str(exc).splitlines()[0][:300])
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
        asyncio.create_task(_fetch_track_meta(new_id, eurl))


@app.get("/api/tracks")
async def list_tracks():
    return {
        "tracks": db.list_tracks(),
        "active_downloads": worker.active_downloads,
        "busy": worker.busy,
    }


@app.patch("/api/tracks/{tid}")
async def edit_track(tid: str, body: TrackEdit):
    track = db.get_track(tid)
    if not track:
        raise HTTPException(404, "Track not found")
    # Metadata edits allowed only before download starts.
    if track["status"] not in EDITABLE_STATUSES:
        raise HTTPException(409, "Track is locked while downloading")
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
    return db.get_track(tid)


@app.delete("/api/tracks/{tid}", status_code=204)
async def remove_track(tid: str):
    track = db.get_track(tid)
    if not track:
        return Response(status_code=204)
    if track["status"] in ACTIVE_STATUSES:
        raise HTTPException(409, "Cannot remove a track while it downloads")
    db.delete_track(tid)
    return Response(status_code=204)


@app.post("/api/tracks/{tid}/cover")
async def upload_cover(tid: str, file: UploadFile):
    track = db.get_track(tid)
    if not track:
        raise HTTPException(404, "Track not found")
    if track["status"] not in EDITABLE_STATUSES:
        raise HTTPException(409, "Track is locked while downloading")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Image larger than 10 MB")
    dest = DATA_DIR / "covers" / f"{tid}.img"
    dest.write_bytes(data)
    db.update_track(tid, cover_path=str(dest), cover_url="")
    return db.get_track(tid)


@app.get("/api/tracks/{tid}/cover")
async def get_cover(tid: str):
    track = db.get_track(tid)
    if not track or not track.get("cover_path") or not Path(track["cover_path"]).exists():
        raise HTTPException(404, "No uploaded cover")
    return FileResponse(track["cover_path"])


@app.post("/api/tracks/{tid}/retry")
async def retry_track(tid: str):
    track = db.get_track(tid)
    if not track:
        raise HTTPException(404, "Track not found")
    if track["status"] != "error":
        raise HTTPException(409, "Only failed tracks can be retried")
    queued = await worker.start_batch([tid])
    return {"queued": queued}


@app.post("/api/batch/start")
async def start_batch(body: BatchStart):
    ids = body.ids or [t["id"] for t in db.tracks_by_status("staged")]
    if not body.force:
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
        req = urllib.request.Request(url, headers={"User-Agent": "GetSetMix/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
        out = []
        for item in payload.get("results", []):
            art = (item.get("artworkUrl100") or "").replace("100x100", "600x600")
            if art:
                out.append({
                    "thumb": item.get("artworkUrl100"),
                    "full": art,
                    "label": f"{item.get('artistName', '')} – {item.get('trackName') or item.get('collectionName', '')}",
                })
        return out

    try:
        return {"results": await asyncio.to_thread(_get)}
    except Exception as exc:
        raise HTTPException(502, f"Cover search failed: {exc}")


@app.get("/api/fs/list")
async def fs_list(path: str = "", ext: str = ""):
    """Server-side directory listing for the path-picker UI.

    Empty path lists drives on Windows and / on POSIX. `ext` (e.g. ".xml")
    filters the files returned; directories are always included.
    """
    import os
    import string

    def _list() -> dict:
        if not path.strip():
            if os.name == "nt":
                drives = [
                    {"name": f"{d}:", "path": f"{d}:\\"}
                    for d in string.ascii_uppercase if Path(f"{d}:\\").exists()
                ]
                return {"path": "", "parent": None, "dirs": drives, "files": []}
            base = Path("/")
        else:
            base = Path(path).expanduser()
        try:
            base = base.resolve()
            if not base.is_dir():
                base = base.parent  # tolerate file paths pasted in the inputs
            if not base.is_dir():
                raise HTTPException(404, "Not a directory")
            entries = sorted(base.iterdir(), key=lambda p: p.name.lower())
        except HTTPException:
            raise
        except PermissionError:
            raise HTTPException(403, "Permission denied")
        except OSError as exc:
            raise HTTPException(400, str(exc).splitlines()[0])
        dirs, files = [], []
        for p in entries:
            if p.name.startswith("."):
                continue
            try:
                if p.is_dir():
                    dirs.append({"name": p.name, "path": str(p)})
                elif not ext or p.suffix.lower() == ext.lower():
                    files.append({"name": p.name, "path": str(p)})
            except OSError:
                continue  # broken symlinks, unreadable entries
        if base.parent != base:
            parent = str(base.parent)
        else:
            parent = "" if os.name == "nt" else None  # drive root -> drive list
        return {"path": str(base), "parent": parent, "dirs": dirs, "files": files}

    return await asyncio.to_thread(_list)


@app.get("/api/settings")
async def get_settings():
    return settings.data


@app.put("/api/settings")
async def put_settings(body: SettingsPatch):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "output_format" in patch and patch["output_format"] not in ("mp3", "flac"):
        raise HTTPException(400, "output_format must be 'mp3' or 'flac'")
    if "language" in patch and patch["language"] not in ("it", "en"):
        raise HTTPException(400, "language must be 'it' or 'en'")
    if "concurrency" in patch and not 1 <= int(patch["concurrency"]) <= 8:
        raise HTTPException(400, "concurrency must be between 1 and 8")
    if "filename_template" in patch and not patch["filename_template"].strip():
        raise HTTPException(400, "filename_template cannot be empty")
    settings.update(patch)
    ensure_dirs()
    return settings.data


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
    if body.scope == "inbox":
        # Manual run of the same purge that fires automatically at batch start:
        # drop inbox tracks already present in the full Rekordbox collection.
        collection = str(settings.get("collection_xml_path") or "").strip()
        if not collection:
            raise HTTPException(400, "Set a Rekordbox collection XML path first")
        removed = await asyncio.to_thread(
            rekordbox.purge_imported, settings["xml_path"], collection
        )
        return {"purged": removed, "scope": "inbox"}
    raise HTTPException(400, "scope must be 'history', 'completed' or 'inbox'")


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint():
    return metrics.render(worker.active_downloads)


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


# --------------------------------------------------------------------- UI
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
    worker.bind_loop(asyncio.get_running_loop())
    # Recover tracks stuck mid-download from a previous run.
    for t in db.tracks_by_status(*ACTIVE_STATUSES):
        db.update_track(t["id"], status="staged", progress=0)
    log.info("GetSetMix ready — library=%s xml=%s",
             settings["library_root"], settings["xml_path"])
