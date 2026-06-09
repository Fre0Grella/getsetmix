"""Server-side metadata fetch (yt-dlp) and artist/title heuristics."""
from __future__ import annotations

import re
from typing import Any

import yt_dlp

_SPLIT_SEPS = (" - ", " \u2013 ", " \u2014 ", " | ", " \uff0d ")
_NOISE = re.compile(
    r"\s*[\(\[](official\s*(video|audio|music\s*video)|lyric\s*video|lyrics|"
    r"visualizer|hd|hq|4k|audio|video\s*ufficiale|testo)[\)\]]\s*",
    re.IGNORECASE,
)


def clean_title(raw: str) -> str:
    return _NOISE.sub(" ", raw or "").strip()


def clean_uploader(raw: str) -> str:
    raw = re.sub(r"\s*-\s*Topic$", "", raw or "").strip()
    raw = re.sub(r"VEVO$", "", raw, flags=re.IGNORECASE).strip()
    return raw


def split_artist_title(raw_title: str, uploader: str) -> tuple[str, str]:
    title = clean_title(raw_title)
    for sep in _SPLIT_SEPS:
        if sep in title:
            artist, rest = title.split(sep, 1)
            return artist.strip(), rest.strip()
    return clean_uploader(uploader), title


def best_thumbnail(info: dict) -> str:
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = info.get("thumbnails") or []
    if thumbs:
        thumbs = sorted(thumbs, key=lambda t: (t.get("width") or 0), reverse=True)
        return thumbs[0].get("url", "")
    return ""


def _ydl(extra: dict | None = None) -> yt_dlp.YoutubeDL:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "socket_timeout": 20,
    }
    if extra:
        opts.update(extra)
    return yt_dlp.YoutubeDL(opts)


def probe(url: str) -> dict:
    """Resolve a URL. Returns either:
    {"kind": "single", "meta": {...}}  or
    {"kind": "playlist", "title": str, "entries": [{"url", "title", "uploader",
                                                    "duration", "thumbnail"}]}
    Raises on unreachable/invalid sources.
    """
    with _ydl({"extract_flat": "in_playlist", "playlist_items": "1-500"}) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("_type") == "playlist" or "entries" in info:
        entries = []
        for e in info.get("entries") or []:
            if not e:
                continue
            entries.append({
                "url": e.get("webpage_url") or e.get("url") or "",
                "title": e.get("title") or "",
                "uploader": e.get("uploader") or e.get("channel") or "",
                "duration": float(e.get("duration") or 0),
                "thumbnail": best_thumbnail(e),
                "id": e.get("id") or "",
                "extractor": e.get("ie_key") or info.get("extractor_key") or "",
            })
        return {"kind": "playlist", "title": info.get("title") or "", "entries": entries}

    return {"kind": "single", "meta": full_meta_from_info(info)}


def fetch_single(url: str) -> dict:
    with _ydl({"noplaylist": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("entries"):
        info = next((e for e in info["entries"] if e), info)
    return full_meta_from_info(info)


def full_meta_from_info(info: dict) -> dict:
    raw_title = info.get("track") or info.get("title") or ""
    uploader = info.get("artist") or info.get("uploader") or info.get("channel") or ""
    if info.get("track") and info.get("artist"):
        artist, title = info["artist"], info["track"]
    else:
        artist, title = split_artist_title(raw_title, uploader)
    return {
        "title": title,
        "artist": artist,
        "album": info.get("album") or "",
        "genre": (info.get("genre") or "") if isinstance(info.get("genre"), str) else "",
        "duration": float(info.get("duration") or 0),
        "thumbnail": best_thumbnail(info),
        "video_id": info.get("id") or "",
        "source": info.get("extractor_key") or info.get("extractor") or "",
        "url": info.get("webpage_url") or "",
    }
