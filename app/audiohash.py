"""The audio id: a hash of a file's audio payload, so it survives tag edits.

    a1_<32 hex>   SHA-256 of the audio payload, first 128 bits
    f1_<32 hex>   the same over the whole file, for anything that does not parse

The payload per container, and the exact rules, are in
docs/design/library.md, section 4.2. The Go companion implements the same
rules; both are checked against testdata/audiohash. Only hashlib and plain
parsing: mutagen is never used to find the payload.
"""
from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path

ALGORITHM = "a1"
FALLBACK = "f1"
SCAN_LIMIT = 1 << 20   # how far past the ID3v2 tags an MP3's first frame may start
_READ = 1 << 20


class _NotParsed(Exception):
    """The file does not follow its container's rule: use the fallback id."""


def audio_id(path: str | os.PathLike) -> str:
    """The audio id of the file at `path`.

    Never raises for a damaged file (that gets the fallback id); raises
    OSError only when the file cannot be read at all.
    """
    path = Path(path)
    with open(path, "rb") as fh:
        size = os.fstat(fh.fileno()).st_size
        parse = _PARSERS.get(path.suffix.lower())
        if parse is not None:
            try:
                ranges = parse(_File(fh, size))
            except (_NotParsed, struct.error, ValueError):
                ranges = None
            if ranges and any(end > start for start, end in ranges):
                return f"{ALGORITHM}_{_digest(fh, ranges)}"
        return f"{FALLBACK}_{_digest(fh, [(0, size)])}"


def is_fallback(aid: str) -> bool:
    return aid.startswith(FALLBACK + "_")


def _digest(fh, ranges: list[tuple[int, int]]) -> str:
    h = hashlib.sha256()
    for start, end in ranges:
        fh.seek(start)
        left = end - start
        while left > 0:
            block = fh.read(min(_READ, left))
            if not block:
                raise OSError("file shrank while it was hashed")
            h.update(block)
            left -= len(block)
    return h.hexdigest()[:32]


class _File:
    def __init__(self, fh, size: int) -> None:
        self.fh = fh
        self.size = size

    def read(self, pos: int, n: int) -> bytes:
        """Exactly n bytes at pos, or _NotParsed."""
        if pos < 0 or n < 0 or pos + n > self.size:
            raise _NotParsed
        self.fh.seek(pos)
        data = self.fh.read(n)
        if len(data) != n:
            raise _NotParsed
        return data


# ----------------------------------------------------------------- ID3v2
def _skip_id3v2(f: _File, pos: int) -> int:
    """Past every ID3v2 tag that starts at pos (header, size, optional footer)."""
    while pos + 10 <= f.size and f.read(pos, 3) == b"ID3":
        head = f.read(pos, 10)
        if any(b & 0x80 for b in head[6:10]):
            raise _NotParsed  # not a syncsafe size
        tag = (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
        pos += 10 + tag + (10 if head[5] & 0x10 else 0)
        if pos > f.size:
            raise _NotParsed
    return pos


# ------------------------------------------------------------------- MP3
_MPEG1_L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
_MPEG2_L3 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def _frame_length(h: bytes) -> int | None:
    """The length of the Layer III frame whose header is h, or None if h is not one."""
    if h[0] != 0xFF or h[1] & 0xE0 != 0xE0:
        return None
    version = (h[1] >> 3) & 3
    layer = (h[1] >> 1) & 3
    bitrate = h[2] >> 4
    rate = (h[2] >> 2) & 3
    if version == 1 or layer != 1 or bitrate in (0, 15) or rate == 3:
        return None
    padding = (h[2] >> 1) & 1
    if version == 3:
        return 144000 * _MPEG1_L3[bitrate] // _RATES[3][rate] + padding
    return 72000 * _MPEG2_L3[bitrate] // _RATES[version][rate] + padding


def _same_stream(a: bytes, b: bytes) -> bool:
    """b has the sync bits and a's version, layer and sample rate."""
    return (b[0] == 0xFF and b[1] & 0xE0 == 0xE0
            and (a[1] & 0x1E) == (b[1] & 0x1E)            # version and layer
            and (a[2] & 0x0C) == (b[2] & 0x0C))           # sample rate


def _mp3_end(f: _File, start: int) -> int:
    end = f.size
    while True:
        if end - 128 >= start and f.read(end - 128, 3) == b"TAG":
            end -= 128
            continue
        if end - 15 >= start and f.read(end - 9, 9) == b"LYRICS200":
            digits = f.read(end - 15, 6)
            if digits.isdigit():
                drop = int(digits) + 15
                if end - drop < start:
                    raise _NotParsed
                end -= drop
                continue
        if end - 32 >= start and f.read(end - 32, 8) == b"APETAGEX":
            footer = f.read(end - 32, 32)
            tag, flags = struct.unpack("<I4xI", footer[12:24])
            drop = tag + (32 if flags & 0x80000000 else 0)
            if drop < 32 or end - drop < start:
                raise _NotParsed
            end -= drop
            continue
        return end


def _mp3(f: _File) -> list[tuple[int, int]]:
    start = _skip_id3v2(f, 0)
    end = _mp3_end(f, start)
    limit = min(end, start + SCAN_LIMIT)
    window = f.read(start, limit - start)
    i = window.find(b"\xff")
    while i != -1:
        pos = start + i
        if pos + 4 <= end:
            head = f.read(pos, 4)
            length = _frame_length(head)
            if length:
                nxt = pos + length
                if nxt == end or (nxt + 4 <= end and _same_stream(head, f.read(nxt, 4))):
                    return [(pos, end)]
        i = window.find(b"\xff", i + 1)
    raise _NotParsed


# ------------------------------------------------------------------ FLAC
def _flac(f: _File) -> list[tuple[int, int]]:
    pos = _skip_id3v2(f, 0)
    if f.read(pos, 4) != b"fLaC":
        raise _NotParsed
    pos += 4
    while True:
        head = f.read(pos, 4)
        pos += 4 + int.from_bytes(head[1:4], "big")
        if pos > f.size:
            raise _NotParsed
        if head[0] & 0x80:
            return [(pos, f.size)]


# ------------------------------------------------------ RIFF and IFF chunks
def _chunks(f: _File, magic: bytes, forms: tuple[bytes, ...], order: str,
            wanted: tuple[bytes, bytes]) -> list[tuple[int, int]]:
    head = f.read(0, 12)
    if head[:4] != magic or head[8:12] not in forms:
        raise _NotParsed
    found: dict[bytes, tuple[int, int]] = {}
    pos = 12
    while pos + 8 <= f.size:
        kind, size = struct.unpack(order + "4sI", f.read(pos, 8))
        start, end = pos + 8, pos + 8 + size
        if end > f.size:
            raise _NotParsed
        if kind in wanted and kind not in found:
            found[kind] = (start, end)
        pos = end + (size & 1)
    if len(found) != 2:
        raise _NotParsed
    return [found[wanted[0]], found[wanted[1]]]


def _wav(f: _File) -> list[tuple[int, int]]:
    return _chunks(f, b"RIFF", (b"WAVE",), "<", (b"fmt ", b"data"))


def _aiff(f: _File) -> list[tuple[int, int]]:
    return _chunks(f, b"FORM", (b"AIFF", b"AIFC"), ">", (b"COMM", b"SSND"))


# ------------------------------------------------------------------- MP4
def _mp4(f: _File) -> list[tuple[int, int]]:
    mdats = []
    pos = 0
    while pos + 8 <= f.size:
        size, kind = struct.unpack(">I4s", f.read(pos, 8))
        head = 8
        if size == 1:
            size, head = struct.unpack(">Q", f.read(pos + 8, 8))[0], 16
        elif size == 0:
            size = f.size - pos
        if size < head or pos + size > f.size:
            raise _NotParsed
        if kind == b"mdat":
            mdats.append((pos + head, pos + size))
        pos += size
    if not mdats:
        raise _NotParsed
    return mdats


_PARSERS = {
    ".mp3": _mp3,
    ".flac": _flac,
    ".wav": _wav,
    ".aif": _aiff,
    ".aiff": _aiff,
    ".m4a": _mp4,
    ".mp4": _mp4,
}
