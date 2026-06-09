"""Filename templating and sanitization.

Tokens: {title} {artist} {album} {source} {id} and optional {genre}.
Missing token segments are omitted and separators are collapsed.
"""
from __future__ import annotations

import re
from pathlib import Path

TOKENS = ("title", "artist", "album", "source", "id", "genre")
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_component(value: str) -> str:
    value = _ILLEGAL.sub("", value or "")
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value


def render_filename(template: str, meta: dict) -> str:
    out = template
    for token in TOKENS:
        out = out.replace("{%s}" % token, sanitize_component(str(meta.get(token) or "")))
    # collapse separators left behind by empty tokens
    out = re.sub(r"\s*[-–—_]\s*(?=[-–—_])", "", out)          # "- -" -> "-"
    out = re.sub(r"(\(\s*\)|\[\s*\]|\{\s*\})", "", out)        # empty brackets
    out = re.sub(r"\s{2,}", " ", out)
    out = out.strip(" -–—_.,")
    return out or "untitled"


def unique_path(directory: Path, stem: str, ext: str) -> tuple[Path, bool]:
    """Return a non-colliding path; bool flags that a suffix was appended."""
    candidate = directory / f"{stem}{ext}"
    if not candidate.exists():
        return candidate, False
    n = 2
    while True:
        candidate = directory / f"{stem} ({n}){ext}"
        if not candidate.exists():
            return candidate, True
        n += 1
