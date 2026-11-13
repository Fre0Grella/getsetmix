"""The Library API (docs/design/library.md, 3.3), behind the same auth as /api.

This slice serves the read-only list, the status and the rescan. The index
itself is in app/library.py.
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
