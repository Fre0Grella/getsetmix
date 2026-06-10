"""Metadata tagger (mutagen): MP3 ID3v2.4 and FLAC Vorbis comments.

Tags written: title, artist, album (if provided), genre (if provided),
cover image, and the source URL in a comment field.
"""
from __future__ import annotations

import urllib.request

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, COMM, ID3, TALB, TCON, TIT2, TPE1
from mutagen.mp3 import MP3

USER_AGENT = "Mozilla/5.0 (GetSetMix/1.0)"


def fetch_image(url: str, timeout: int = 20) -> tuple[bytes, str] | None:
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            mime = resp.headers.get_content_type() or "image/jpeg"
        if not data:
            return None
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            mime = sniff_mime(data)
        return data, mime
    except Exception:
        return None


def sniff_mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def load_cover(meta: dict) -> tuple[bytes, str] | None:
    """Priority: manually uploaded file -> overridden cover URL -> thumbnail."""
    if meta.get("cover_path"):
        try:
            with open(meta["cover_path"], "rb") as fh:
                data = fh.read()
            return data, sniff_mime(data)
        except OSError:
            pass
    return fetch_image(meta.get("cover_url") or "") or fetch_image(meta.get("thumbnail") or "")


def comment_text(meta: dict) -> str:
    return f"Source: {meta.get('url', '')} | via GetSetMix"


def tag_file(path: str, meta: dict) -> None:
    if path.lower().endswith(".flac"):
        _tag_flac(path, meta)
    else:
        _tag_mp3(path, meta)


def _tag_mp3(path: str, meta: dict) -> None:
    audio = MP3(path)
    if audio.tags is None:
        audio.add_tags()
    tags: ID3 = audio.tags  # type: ignore[assignment]
    tags.delall("TIT2")
    tags.add(TIT2(encoding=3, text=meta.get("title") or ""))
    tags.delall("TPE1")
    tags.add(TPE1(encoding=3, text=meta.get("artist") or ""))
    if meta.get("album"):
        tags.delall("TALB")
        tags.add(TALB(encoding=3, text=meta["album"]))
    if meta.get("genre"):
        tags.delall("TCON")
        tags.add(TCON(encoding=3, text=meta["genre"]))
    tags.delall("COMM")
    tags.add(COMM(encoding=3, lang="eng", desc="", text=comment_text(meta)))
    cover = load_cover(meta)
    if cover:
        data, mime = cover
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
    audio.save(v2_version=4)


def _tag_flac(path: str, meta: dict) -> None:
    audio = FLAC(path)
    audio["title"] = meta.get("title") or ""
    audio["artist"] = meta.get("artist") or ""
    if meta.get("album"):
        audio["album"] = meta["album"]
    if meta.get("genre"):
        audio["genre"] = meta["genre"]
    audio["comment"] = comment_text(meta)
    cover = load_cover(meta)
    if cover:
        data, mime = cover
        pic = Picture()
        pic.type = 3
        pic.mime = mime
        pic.desc = "Cover"
        pic.data = data
        audio.clear_pictures()
        audio.add_picture(pic)
    audio.save()
