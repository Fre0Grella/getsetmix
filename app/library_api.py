"""The Library API (docs/design/library.md, 3.3), behind the same auth as /api.

This module serves the list, the status, the rescan, and the trash: delete,
restore and purge. The index itself is in app/library.py.

Routes that take an id use the `int` path convertor, so fixed paths such as
`/api/library/trash` or `/api/library/rules` are never read as an id.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from . import library

router = APIRouter(prefix="/api/library")


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


@router.delete("/{fid:int}")
async def delete_file(fid: int):
    """Move one file to the trash."""
    return await _call(library.current().trash, fid)


@router.post("/{fid:int}/restore")
async def restore_file(fid: int):
    """Bring one file back from the trash; 409 if its path is taken."""
    return await _call(library.current().restore, fid)
