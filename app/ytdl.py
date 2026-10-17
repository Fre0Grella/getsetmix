"""yt-dlp wiring shared by metadata fetch and downloads.

YouTube gates its media URLs behind JavaScript challenges (signature / "n"
parameter / PO tokens). yt-dlp solves them with an *external* JS runtime plus
the `yt-dlp-ejs` scripts; without one, metadata still resolves through a
fallback client but the media bytes come back `HTTP Error 403: Forbidden`.

So every YoutubeDL instance gets its options from `base_opts()`, which enables
whichever supported runtime is installed, and every user-facing error goes
through `explain()`, which turns a bare 403 into the actual fix.
"""
from __future__ import annotations

import functools
import importlib.util
import shutil
from datetime import date
from typing import Any

import yt_dlp
from yt_dlp.version import __version__ as YTDLP_VERSION

# yt-dlp's own preference order (bun is deprecated upstream, so it goes last).
RUNTIME_PREFERENCE = ("deno", "node", "quickjs", "bun")
# Same threshold at which yt-dlp itself starts warning that it is outdated.
STALE_AFTER_DAYS = 90

DENO_HINT = "install Deno (https://deno.com — `winget install DenoLand.Deno`, " \
            "`brew install deno`) and restart GetSetMix"


@functools.lru_cache(maxsize=1)
def js_runtime() -> dict | None:
    """The first installed JS runtime yt-dlp can use, or None."""
    try:
        from yt_dlp.globals import supported_js_runtimes
        classes = supported_js_runtimes.value
    except (ImportError, AttributeError):  # internal API moved: fall back to PATH
        classes = {}
    for name in RUNTIME_PREFERENCE:
        cls = classes.get(name)
        if cls is None:
            exe = shutil.which("qjs" if name == "quickjs" else name)
            if exe:
                return {"name": name, "path": exe, "version": "unknown"}
            continue
        info = cls().info
        if info and info.supported:
            return {"name": name, "path": info.path, "version": info.version}
    return None


def ejs_installed() -> bool:
    return importlib.util.find_spec("yt_dlp_ejs") is not None


def ytdlp_age_days(today: date | None = None) -> int:
    try:
        y, m, d = (int(p) for p in YTDLP_VERSION.split(".")[:3])
        return ((today or date.today()) - date(y, m, d)).days
    except ValueError:
        return 0


def base_opts(extra: dict | None = None) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    runtime = js_runtime()
    if runtime:
        opts["js_runtimes"] = {runtime["name"]: {"path": runtime["path"]}}
    if extra:
        opts.update(extra)
    return opts


def ydl(extra: dict | None = None) -> yt_dlp.YoutubeDL:
    return yt_dlp.YoutubeDL(base_opts(extra))


def problems() -> list[str]:
    """Human-readable reasons YouTube downloads are likely to fail."""
    out = []
    if not js_runtime():
        out.append(f"No JavaScript runtime found, so YouTube will refuse downloads: {DENO_HINT}.")
    if not ejs_installed():
        out.append("The yt-dlp-ejs package is missing: `pip install -U \"yt-dlp[default]\"`.")
    age = ytdlp_age_days()
    if age > STALE_AFTER_DAYS:
        out.append(f"yt-dlp {YTDLP_VERSION} is {age} days old and YouTube changes often: "
                   "pull a newer image or `pip install -U \"yt-dlp[default]\"`.")
    return out


def status() -> dict:
    return {
        "version": YTDLP_VERSION,
        "age_days": ytdlp_age_days(),
        "js_runtime": js_runtime(),
        "ejs": ejs_installed(),
        "problems": problems(),
    }


def explain(exc: BaseException) -> str:
    """One-line error for the UI, with the likely fix appended for 403s."""
    lines = str(exc).splitlines()
    msg = (lines[0] if lines else type(exc).__name__)[:300]
    blocked = "403" in msg or "Sign in to confirm" in msg or "challenge" in msg.lower()
    if blocked:
        fixes = problems()
        if fixes:
            return f"{msg} — {fixes[0]}"
    return msg
