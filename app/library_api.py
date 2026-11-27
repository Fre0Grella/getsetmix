"""The Library API (docs/design/library.md, 3.3), behind the same auth as /api.

This module serves the list, the facets, the status, the rescan, bulk actions,
batch edits (app/edits.py), one file and its tag edit, its cover (read and replace) and audio (with range
requests, for the preview), and the trash: delete, restore and purge. The index and the
writes are in app/library.py; the routes here are thin callers.

Routes that take an id use the `int` path convertor, so fixed paths such as
`/api/library/trash` or `/api/library/rules` are never read as an id.
"""
from __future__ import annotations

import asyncio
import mimetypes
import re
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.datastructures import UploadFile

from . import edits, library, tagger, thumbs

router = APIRouter(prefix="/api/library")

CHUNK = 256 * 1024
AUDIO_TYPES = {".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4",
               ".aac": "audio/aac", ".wav": "audio/wav", ".aif": "audio/aiff",
               ".aiff": "audio/aiff", ".ogg": "audio/ogg", ".opus": "audio/ogg"}
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


@router.get("")
async def list_library(q: str = "", genre: str = "", folder: str = "", state: str = "present",
                       sort: str = "added", order: str | None = None, limit: int = 200,
                       cursor: str | None = None):
    try:
        return await asyncio.to_thread(
            library.current().list, q=q, genre=genre, folder=folder, state=state, sort=sort,
            order=order, limit=limit, cursor=cursor)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/facets")
async def library_facets(state: str = "present"):
    """Genres and folders with their counts, for the filters."""
    try:
        return await asyncio.to_thread(library.current().facets, state)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/status")
async def library_status():
    return await asyncio.to_thread(library.current().status)


@router.post("/rescan", status_code=202)
async def library_rescan():
    """Reconcile now, in the background; `started` is false while a pass already runs."""
    return {"started": library.current().trigger()}


@router.delete("/trash")
async def empty_trash():
    """Purge the whole trash now, whatever its age."""
    purged = await asyncio.to_thread(library.current().purge, everything=True)
    return {"purged": purged}


async def _call(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except library.LibraryError as exc:
        raise HTTPException(exc.status, exc.detail) from None


@router.post("/bulk")
async def library_bulk(body: Annotated[dict, Body()]):
    """Delete, restore or set the genre of many tracks; the outcome per id.
    A genre goes through a batch edit, so it shows in the history and can be undone."""
    if body.get("action") == "set_genre":
        steps = [{"op": "set", "field": "genre", "value": body.get("genre")}]
        return await _call(edits.current().at_once, body.get("ids"), steps)
    return await _call(library.current().bulk, body.get("ids"), body.get("action"))


# ------------------------------------------------- batch editing (edits)
@router.post("/edits", status_code=201)
async def make_edit(body: Annotated[dict, Body()]):
    """Preview an edit: a selection and steps; the changes are stored, not written."""
    return await _call(edits.current().preview, body)


@router.get("/edits")
async def edit_history(limit: int = 50, cursor: str | None = None):
    """The edits that were applied, newest first."""
    return await _call(edits.current().history, limit, cursor)


@router.get("/edits/{eid:int}")
async def get_edit(eid: int):
    """One edit: state, counts and the progress of its apply."""
    item = await asyncio.to_thread(edits.current().get, eid)
    if item is None:
        raise HTTPException(404, "no such edit")
    return item


@router.get("/edits/{eid:int}/changes")
async def edit_changes(eid: int, field: str = "", state: str = "", warning: str = "",
                       limit: int = 200, cursor: str | None = None):
    """The changes of an edit, per track and field, paged."""
    return await _call(edits.current().changes, eid, field, state, warning, limit, cursor)


@router.post("/edits/covers", status_code=201)
async def upload_cover(request: Request):
    """An image for a `set_cover` step, as an upload or `{"url": ...}`; answers
    `{"source": "upload:<token>"}`, kept a day unless an edit uses it."""
    return await _call(edits.current().keep_image, await _image(request))


@router.patch("/edits/{eid:int}")
async def leave_out(eid: int, body: Annotated[dict, Body()]):
    """Leave tracks or changes out of a preview, or put them back."""
    return await _call(edits.current().leave_out, eid, body)


@router.get("/rulesets")
async def rulesets():
    """The saved rule sets, the built-in ones first."""
    return await _call(edits.current().rulesets)


@router.post("/rulesets", status_code=201)
async def new_ruleset(body: Annotated[dict, Body()]):
    return await _call(edits.current().save_ruleset, body)


@router.put("/rulesets/{rid:int}")
async def change_ruleset(rid: int, body: Annotated[dict, Body()]):
    """Rename, reorder or change a saved rule set; a built-in one is refused."""
    return await _call(edits.current().save_ruleset, body, rid)


@router.delete("/rulesets/{rid:int}", status_code=204)
async def delete_ruleset(rid: int):
    await _call(edits.current().delete_ruleset, rid)


@router.post("/edits/{eid:int}/apply", status_code=202)
async def apply_edit(eid: int):
    """Write a previewed edit, one file at a time; also retries what failed."""
    return await _call(edits.current().apply, eid)


@router.post("/edits/{eid:int}/undo", status_code=202)
async def undo_edit(eid: int, body: Annotated[dict | None, Body()] = None):
    """Revert an edit, whole or for `{"files": [ids]}`, as a new edit applying now."""
    return await _call(edits.current().undo, eid, (body or {}).get("files"))


@router.get("/{fid:int}")
async def library_file(fid: int):
    item = await asyncio.to_thread(library.current().item, fid)
    if item is None:
        raise HTTPException(404, "no such track")
    return item


@router.patch("/{fid:int}")
async def edit_library_file(fid: int, body: Annotated[dict, Body()]):
    """Edit tags: any of title, artist, album, genre, year and comment, plus an
    optional `expect` with the values the caller believes the file holds."""
    changes = dict(body)
    expect = changes.pop("expect", None)
    result = await _call(library.current().write_tags, fid, changes, expect)
    if not result.written:
        return JSONResponse({"detail": "the file changed", "differs": result.differs},
                            status_code=412)
    return result.item


@router.delete("/{fid:int}")
async def delete_file(fid: int):
    """Move one file to the trash."""
    return await _call(library.current().trash, fid)


@router.post("/{fid:int}/restore")
async def restore_file(fid: int):
    """Bring one file back from the trash; 409 if its path is taken."""
    return await _call(library.current().restore, fid)


# ------------------------------------------------------------------- cover
def _etag_matches(request: Request, etag: str) -> bool:
    given = request.headers.get("if-none-match", "")
    return any(tag.strip().removeprefix("W/") == etag.removeprefix("W/")
               for tag in given.split(","))


@router.get("/{fid:int}/cover")
async def get_cover(fid: int, request: Request, v: int | None = None,
                    size: str | None = None):
    """The embedded cover, as stored; with `?size=thumb` a small JPEG of it, for
    the list (made once per `content_rev` and kept on disk, app/thumbs.py; the
    full cover if it cannot be decoded). Cached by its `content_rev`: a request
    that names the current one with `?v=` may keep the image for a year, any
    other revalidates, so an edited cover refreshes."""
    if size not in (None, "thumb"):
        raise HTTPException(400, "size can only be thumb")
    row, path = await _call(library.current().media, fid)
    etag = f'W/"cover-{"thumb-" if size else ""}{row["id"]}-{row["content_rev"]}"'
    fresh = v is not None and v == row["content_rev"]
    headers = {"ETag": etag, "X-Content-Type-Options": "nosniff",
               "Cache-Control": ("private, max-age=31536000, immutable" if fresh
                                 else "private, no-cache")}
    if _etag_matches(request, etag):
        return Response(status_code=304, headers=headers)
    if size:
        thumb = await asyncio.to_thread(thumbs.get, row["id"], row["content_rev"], path)
        if thumb is not None:
            return Response(thumb, media_type="image/jpeg", headers=headers)
    cover = await asyncio.to_thread(tagger.read_cover, path)
    if cover is None:
        raise HTTPException(404, "this track has no cover")
    return Response(cover[0], media_type=cover[1], headers=headers)


@router.post("/{fid:int}/cover")
async def set_cover(fid: int, request: Request):
    """Replace the embedded cover: an uploaded image (multipart, field `file`)
    or `{"url": "https://..."}` to download one. Answers with the updated item."""
    result = await _call(library.current().write_cover, fid, (await _image(request), ""))
    return result.item


async def _image(request: Request) -> bytes:
    """The image of a cover request: an upload (multipart, field `file`) or
    `{"url": "https://..."}` to download. Its bytes are checked by the caller."""
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            url = (await request.json()).get("url")
        except Exception:
            url = None
        if not isinstance(url, str):
            raise HTTPException(400, 'send {"url": "https://..."} or upload an image')
        if not url.lower().startswith(("http://", "https://")):
            raise HTTPException(400, "the address must start with http:// or https://")
        fetched = await asyncio.to_thread(tagger.fetch_image, url)
        if fetched is None:
            raise HTTPException(502, "could not download an image from that address")
        data = fetched[0]
    else:
        try:
            upload = (await request.form()).get("file")
        except Exception:
            upload = None
        if not isinstance(upload, UploadFile):
            raise HTTPException(400, 'send {"url": "https://..."} or upload an image')
        data = await upload.read(tagger.MAX_COVER + 1)
    return data


# ------------------------------------------------------------------- audio
def _byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """The (first, last) byte a Range header asks for; None to send it all.
    Raises ValueError when the range cannot be satisfied. A header that is not
    one simple `bytes=` range is ignored, as the standard allows."""
    m = RANGE.match((header or "").strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return None
    if m.group(1) == "":  # the last n bytes
        n = int(m.group(2))
        if n == 0:
            raise ValueError
        return max(size - n, 0), size - 1
    first = int(m.group(1))
    last = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
    if first >= size or first > last:
        raise ValueError
    return first, last


def _chunks(path, first: int, last: int):
    # The file is opened for each chunk and not held between them: a tag edit
    # replaces the file, and on Windows a held handle would make that fail.
    pos = first
    while pos <= last:
        with open(path, "rb") as fh:
            fh.seek(pos)
            data = fh.read(min(CHUNK, last - pos + 1))
        if not data:
            return
        pos += len(data)
        yield data


@router.get("/{fid:int}/audio")
async def get_audio(fid: int, request: Request):
    """The audio file, with range requests, for the preview player."""
    _, path = await _call(library.current().media, fid)
    try:
        st = await asyncio.to_thread(path.stat)
    except OSError:
        raise HTTPException(410, "the file is not on disk") from None
    size = st.st_size
    headers = {"Accept-Ranges": "bytes", "ETag": f'W/"{size}-{st.st_mtime_ns}"',
               "Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"}
    media = (AUDIO_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
             or "application/octet-stream")
    try:
        span = _byte_range(request.headers.get("range"), size)
    except ValueError:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
    if span is None:
        span, status = (0, size - 1), 200
    else:
        status = 206
        headers["Content-Range"] = f"bytes {span[0]}-{span[1]}/{size}"
    headers["Content-Length"] = str(max(span[1] - span[0] + 1, 0))
    return StreamingResponse(_chunks(path, *span), status_code=status, media_type=media,
                             headers=headers)
