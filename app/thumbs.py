"""Small cover thumbnails for the Library list (docs/design/library.md, 4.5).

A row of the list shows its cover in a 44 px box, and the embedded picture can
be hundreds of kilobytes. `get` makes a 144 px square JPEG of it (about 3x the
box, for a dense screen), keeps it on disk under DATA_DIR/thumbs as
`<file id>-<content_rev>.jpg`, and serves it again from there. An edited cover
has a new `content_rev`, so it gets a new file and the old one is removed.

Decoding is bounded for a 1 GiB pod: a picture over the cover size cap, or over
MAX_PIXELS once decoded, is refused (None), a JPEG is decoded already reduced
(`Image.draft`), and one thumbnail is made at a time.
"""
from __future__ import annotations

import io
import logging
import os
import threading
from pathlib import Path

from PIL import Image, ImageOps

from . import config, tagger

log = logging.getLogger("getsetmix.thumbs")

THUMB_PX = 144          # the side of the square thumbnail, at most
QUALITY = 80
MAX_PIXELS = 25_000_000  # a picture larger than this (5000 x 5000) is not decoded
FORMATS = ("JPEG", "PNG", "WEBP", "GIF")  # the only decoders a cover may reach

_make = threading.Lock()  # one thumbnail at a time: a decode is the heavy part
_FLIP = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
         4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
         6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
         8: Image.Transpose.ROTATE_90}  # EXIF orientation -> the turn that fixes it


def make_thumb(data: bytes) -> bytes | None:
    """A JPEG thumbnail of image bytes (a centred square, THUMB_PX at most, never
    enlarged), or None when the picture is over the size caps or cannot be
    decoded: the caller then serves the picture as it is."""
    if not data or len(data) > tagger.MAX_COVER:
        return None
    try:
        # only the cover types (tagger.COVER_TYPES): no EPS, PSD or other
        # decoders that are rarely needed and have a history of flaws
        with Image.open(io.BytesIO(data), formats=FORMATS) as im:
            width, height = im.size
            if width * height > min(MAX_PIXELS, Image.MAX_IMAGE_PIXELS or MAX_PIXELS):
                return None
            side = min(THUMB_PX, width, height)
            turn = _FLIP.get(im.getexif().get(0x0112))
            if im.format == "JPEG":
                im.draft("RGB", (side, side))  # decode at 1/2, 1/4 or 1/8 where it fits
            im.load()
            if im.mode in ("RGBA", "LA") or "transparency" in im.info:
                rgba = im.convert("RGBA")  # transparency goes onto white, as on a printed cover
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                im = flat
            elif im.mode != "RGB":
                im = im.convert("RGB")
            small = ImageOps.fit(im, (side, side), Image.Resampling.LANCZOS)
            if turn is not None:
                small = small.transpose(turn)
            out = io.BytesIO()
            small.save(out, "JPEG", quality=QUALITY, optimize=True)
            return out.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None
    except Exception:  # truncated, damaged or an unknown format: not worth a traceback
        log.info("thumbs: could not decode a cover", exc_info=True)
        return None


def _folder() -> Path:
    return config.DATA_DIR / "thumbs"


def _file(fid: int, rev: int) -> Path:
    return _folder() / f"{fid}-{rev}.jpg"


def _read(target: Path) -> bytes | None:
    try:
        return target.read_bytes()
    except OSError:
        return None


def get(fid: int, rev: int, path: str | Path) -> bytes | None:
    """The thumbnail of the cover embedded in `path`, for file `fid` at
    `content_rev` `rev`: from disk if it was made, else made now and kept.
    None if the file has no cover or the cover cannot be thumbnailed."""
    target = _file(fid, rev)
    hit = _read(target)
    if hit is not None:
        return hit
    with _make:
        hit = _read(target)  # another request may have made it while this one waited
        if hit is not None:
            return hit
        cover = tagger.read_cover(path)
        thumb = make_thumb(cover[0]) if cover else None
        if thumb is None:
            return None
        _keep(target, thumb, fid)
        return thumb


def _keep(target: Path, thumb: bytes, fid: int) -> None:
    """Write the thumbnail atomically and remove the older ones of the file. A
    disk that cannot be written to only costs the cache, not the answer."""
    part = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.part")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        part.write_bytes(thumb)
        os.replace(part, target)
    except OSError:
        log.warning("thumbs: could not keep %s", target.name, exc_info=True)
        part.unlink(missing_ok=True)
        return
    drop(fid, keep=target)


def drop(fid: int, keep: Path | None = None) -> None:
    """Remove the thumbnails of file `fid` (all, or all but `keep`)."""
    try:
        stale = list(_folder().glob(f"{fid}-*.jpg"))
    except OSError:
        return
    for old in stale:
        if keep is None or old != keep:
            try:
                old.unlink(missing_ok=True)
            except OSError:
                log.warning("thumbs: could not remove %s", old.name, exc_info=True)
