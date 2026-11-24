"""Metadata tagger (mutagen): MP3 ID3v2.4 and FLAC Vorbis comments.

Two paths:

- The download path (`tag_file`) tags a fresh download: title, artist,
  album (if provided), genre (if provided), cover image, and the source URL
  in a comment field.
- The edit path (`edit_file`) changes a file already in the library
  (docs/design/library.md, 4.3): only the fields it is given are written, on a
  hidden copy that replaces the original in one rename. The same path can
  replace or remove the embedded cover (`read_cover` reads it).
"""
from __future__ import annotations

import base64
import os
import shutil
import urllib.request
from pathlib import Path

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, COMM, ID3, TALB, TCON, TDRC, TIT2, TPE1
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4Tags

# The six fields an edit can change, and where each one lives per format
# (docs/design/library.md, 3.4).
EDIT_FIELDS = ("title", "artist", "album", "genre", "year", "comment")
ID3_FRAMES = {"title": TIT2, "artist": TPE1, "album": TALB, "genre": TCON, "year": TDRC}
VORBIS_KEYS = {"title": "title", "artist": "artist", "album": "album", "genre": "genre",
               "year": "date", "comment": "comment"}

USER_AGENT = "Mozilla/5.0 (GetSetMix/1.0)"
MAX_COVER = 10 * 1024 * 1024    # the largest image taken as a cover
KEEP = object()                 # edit_file: leave the cover as it is
COVER_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")


def fetch_image(url: str, timeout: int = 20) -> tuple[bytes, str] | None:
    """The image at an http(s) URL, or None: another scheme (file:, ftp:), an
    empty answer, or one over MAX_COVER."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(MAX_COVER + 1)
            mime = resp.headers.get_content_type() or "image/jpeg"
        if not data or len(data) > MAX_COVER:
            return None
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            mime = sniff_mime(data)
        return data, mime
    except Exception:
        return None


def image_type(data: bytes) -> str | None:
    """The mime type of JPEG, PNG and WebP data by its first bytes; None otherwise."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def sniff_mime(data: bytes) -> str:
    return image_type(data) or "image/jpeg"


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


# ------------------------------------------------------------ reading a cover
def _picked(pictures: list[tuple[int, bytes, str]]) -> tuple[bytes, str] | None:
    """The front cover (type 3) if there is one, else the first picture."""
    pictures = [p for p in pictures if p[1]]
    if not pictures:
        return None
    _, data, mime = next((p for p in pictures if p[0] == 3), pictures[0])
    # What a tag claims is not trusted: an SVG served from this origin could run script.
    return data, image_type(data) or (mime if mime in COVER_TYPES else "image/jpeg")


def read_cover(path: str | Path) -> tuple[bytes, str] | None:
    """The embedded cover of a file as (image bytes, mime type); None if it has
    none or the file cannot be read. Any format mutagen reads; the type is taken
    from the picture's bytes, not from what the tag claims."""
    try:
        audio = mutagen.File(path)
        tags = None if audio is None else audio.tags
        if isinstance(tags, ID3):
            return _picked([(int(a.type), a.data, a.mime or "") for a in tags.getall("APIC")])
        if isinstance(tags, MP4Tags):
            mimes = {13: "image/jpeg", 14: "image/png"}
            return _picked([(3, bytes(c), mimes.get(c.imageformat, "")) for c in
                            tags.get("covr") or []])
        pictures = [(int(p.type), p.data, p.mime or "") for p in getattr(audio, "pictures", [])]
        if not pictures and tags is not None and hasattr(tags, "get"):  # Ogg, Opus
            for block in tags.get("metadata_block_picture") or []:
                p = Picture(base64.b64decode(block))
                pictures.append((int(p.type), p.data, p.mime or ""))
        return _picked(pictures)
    except Exception:
        return None


# ------------------------------------------------------------- the edit path
def _set_cover_id3(tags: ID3, cover: tuple[bytes, str] | None) -> None:
    tags.delall("APIC")
    if cover is not None:
        tags.add(APIC(encoding=3, mime=cover[1], type=3, desc="Cover", data=cover[0]))


def _set_cover_flac(audio: FLAC, cover: tuple[bytes, str] | None) -> None:
    audio.clear_pictures()
    if cover is not None:
        pic = Picture()
        pic.type = 3
        pic.mime = cover[1]
        pic.desc = "Cover"
        pic.data = cover[0]
        audio.add_picture(pic)


def _edit_mp3(path: str, changes: dict, cover=KEEP) -> None:
    audio = MP3(path)
    if audio.tags is None:
        audio.add_tags()
    tags: ID3 = audio.tags  # type: ignore[assignment]
    for field, value in changes.items():
        if field == "comment":
            # The comment is the COMM frame with an empty description, in
            # English; comments with a description (iTunes' own, a DJ app's)
            # are left alone. Clearing also drops empty-description comments in
            # other languages, which would otherwise show through.
            for frame in list(tags.getall("COMM")):
                if frame.desc == "" and (frame.lang == "eng" or value == ""):
                    del tags[frame.HashKey]
            if value != "":
                tags.add(COMM(encoding=3, lang="eng", desc="", text=value))
            continue
        frame = ID3_FRAMES[field]
        tags.delall(frame.__name__)
        if field == "year":
            if value is not None:
                tags.add(TDRC(encoding=3, text=str(value)))
        elif value != "":
            tags.add(frame(encoding=3, text=value))
    if cover is not KEEP:
        _set_cover_id3(tags, cover)
    audio.save(v2_version=4)


def _edit_flac(path: str, changes: dict, cover=KEEP) -> None:
    audio = FLAC(path)
    if audio.tags is None:
        audio.add_tags()
    for field, value in changes.items():
        key = VORBIS_KEYS[field]
        if value is None or value == "":
            if key in audio:
                del audio[key]
        else:
            audio[key] = str(value)  # one value, replacing every old one
    if cover is not KEEP:
        _set_cover_flac(audio, cover)
    audio.save()


EDITORS = {".mp3": _edit_mp3, ".flac": _edit_flac}


def _keep_owner(source: Path, copy: Path) -> None:
    """Give the copy the original's owner, which `copy2` does not.

    On a server the library is often shared with another program (a Nextcloud
    volume, say) that must keep access to the file after the rename. Best
    effort: without the right to change it, the file keeps the app's owner.
    """
    if not hasattr(os, "chown"):
        return
    st = source.stat()
    try:
        os.chown(copy, st.st_uid, st.st_gid)
    except OSError:
        pass


def edit_file(path: str | Path, changes: dict, cover=KEEP) -> None:
    """Write `changes` (any of EDIT_FIELDS) into the file at path, atomically.

    `cover` is KEEP (the default: the cover is not touched), None (every
    embedded picture is removed) or (image bytes, mime type), which replaces
    every embedded picture with that one, as the front cover. It goes in the
    same copy and the same rename as the fields.

    The file is copied under a hidden name (".<name>.part", which the link,
    the reconcile walk and the companion's scanner all skip), the copy is
    tagged, and it replaces the original in one rename: a crash leaves the old
    file intact, and a reader never sees half a file. Fields not in `changes`
    are not touched. Text is written as one value, never split; "" (or None
    for the year) clears the tag. Raises OSError when the file cannot be
    copied or replaced (PermissionError on Windows while another program
    holds it open).
    """
    path = Path(path)
    editor = EDITORS.get(path.suffix.lower())
    if editor is None:
        raise ValueError(f"{path.suffix or 'this format'} is read-only")
    unknown = set(changes) - set(EDIT_FIELDS)
    if unknown:
        raise ValueError(f"not an editable field: {', '.join(sorted(unknown))}")
    part = path.with_name(f".{path.name}.part")
    try:
        shutil.copy2(path, part)
        _keep_owner(path, part)
        editor(str(part), changes, cover)
        os.replace(part, path)
    except BaseException:
        try:
            part.unlink()
        except OSError:
            pass
        raise
