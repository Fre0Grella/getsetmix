"""Build the audio hash fixtures in this folder and write expected.json.

Run from anywhere, with ffmpeg on PATH and mutagen installed:

    python testdata/audiohash/make_fixtures.py

ffmpeg is needed only here, never at test time: the files it makes are
committed. Its output can differ between ffmpeg versions, so running the
script again may change the bytes and the ids; that is fine as long as the
new files are committed together with the new expected.json.

The expected ids are NOT computed with app/audiohash.py. Each one comes from
how the file was built: the script knows which bytes it put in as audio (the
PCM it generated, an untagged MP3 that is all frames, the frames after the
metadata ffmpeg wrote, the payload of the mdat atom), hashes those, and then
adds tags, covers, padding and chunks around them with mutagen or by hand.
That way the fixtures check the implementation instead of repeating it.

The id rules are in docs/design/library.md, section 4.2.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

from mutagen.aiff import AIFF
from mutagen.apev2 import APEv2
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, COMM, ID3, TALB, TCON, TDRC, TIT2, TPE1
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE

HERE = Path(__file__).resolve().parent


def audio_id(payload: bytes) -> str:
    return "a1_" + hashlib.sha256(payload).hexdigest()[:32]


def fallback_id(data: bytes) -> str:
    return "f1_" + hashlib.sha256(data).hexdigest()[:32]


def ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True
    )


def sine(freq: int, rate: int, seconds: float) -> list[str]:
    return ["-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate={rate}:duration={seconds}"]


BITEXACT = ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact", "-ac", "1"]


def tiny_png() -> bytes:
    """A valid 2x2 red PNG, so a cover costs a few dozen bytes."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 2 for _ in range(2))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


COVER = tiny_png()


def id3_frames(tags: ID3, title: str = "Night Drive") -> None:
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=["Some Artist", "Other Artist"]))
    tags.add(TALB(encoding=3, text="An Album"))
    tags.add(TCON(encoding=3, text="House"))
    tags.add(TDRC(encoding=3, text="2019-06-14"))
    tags.add(COMM(encoding=3, lang="eng", desc="", text="Source: https://example.test | via GetSetMix"))


def syncsafe(n: int) -> bytes:
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def id3v1(title: str) -> bytes:
    def field(s: str, n: int) -> bytes:
        return s.encode("latin-1")[:n].ljust(n, b"\x00")
    return (b"TAG" + field(title, 30) + field("Some Artist", 30) + field("An Album", 30)
            + b"2019" + field("comment", 30) + b"\x00")


def lyrics3v2() -> bytes:
    body = b"LYRICSBEGIN" + b"IND00002" + b"10" + b"LYR00011" + b"la la la la"
    return body + f"{len(body):06d}".encode() + b"LYRICS200"


def id3v24_with_footer() -> bytes:
    """An ID3v2.4 tag with the footer flag set, built by hand (mutagen never writes one)."""
    text = b"\x03Footer Title"
    frame = b"TIT2" + syncsafe(len(text)) + b"\x00\x00" + text
    header = b"ID3\x04\x00\x10" + syncsafe(len(frame))
    footer = b"3DI\x04\x00\x10" + syncsafe(len(frame))
    return header + frame + footer


# ------------------------------------------------------------------ parsers
# Kept deliberately small and separate from app/audiohash.py: they only read
# what ffmpeg wrote, to know which bytes are the audio.

def flac_frames(data: bytes) -> bytes:
    assert data[:4] == b"fLaC", "ffmpeg did not write a bare FLAC stream"
    pos = 4
    while True:
        last = data[pos] & 0x80
        size = int.from_bytes(data[pos + 1:pos + 4], "big")
        pos += 4 + size
        if last:
            return data[pos:]


def flac_streaminfo(data: bytes) -> bytes:
    assert data[4] & 0x7F == 0, "first block must be STREAMINFO"
    size = int.from_bytes(data[5:8], "big")
    return data[8:8 + size]


def mp4_atoms(data: bytes) -> list[tuple[bytes, int, int]]:
    """(type, payload start, payload end) of every top-level atom."""
    out, pos = [], 0
    while pos < len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        head = 8
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            head = 16
        elif size == 0:
            size = len(data) - pos
        out.append((kind, pos + head, pos + size))
        pos += size
    return out


def mdat_payload(data: bytes) -> bytes:
    return b"".join(data[s:e] for kind, s, e in mp4_atoms(data) if kind == b"mdat")


# ---------------------------------------------------------------- builders
def pcm16(freq: int, rate: int, seconds: float, big_endian: bool) -> bytes:
    fmt = ">h" if big_endian else "<h"
    n = int(rate * seconds)
    return b"".join(
        struct.pack(fmt, int(12000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n)
    )


def riff_chunk(kind: bytes, body: bytes) -> bytes:
    return kind + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) % 2 else b"")


def wav(chunks: list[bytes]) -> bytes:
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def iff_chunk(kind: bytes, body: bytes) -> bytes:
    return kind + struct.pack(">I", len(body)) + body + (b"\x00" if len(body) % 2 else b"")


def ieee_extended(value: float) -> bytes:
    """An 80-bit IEEE 754 extended float, as AIFF stores the sample rate."""
    exponent = int(math.floor(math.log2(value)))
    mantissa = int(value * (1 << (63 - exponent)))
    return struct.pack(">HQ", exponent + 16383, mantissa)


def aiff(chunks: list[bytes]) -> bytes:
    body = b"AIFF" + b"".join(chunks)
    return b"FORM" + struct.pack(">I", len(body)) + body


class Fixtures:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.same: dict[str, list[str]] = {}
        self.different: list[list[str]] = []

    def put(self, rel: str, data: bytes, expected: str, group: str | None) -> Path:
        path = HERE / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.files[rel] = expected
        if group:
            self.same.setdefault(group, []).append(rel)
        return path

    def tagged(self, rel: str, base: bytes, expected: str, group: str, tag) -> None:
        """Write `base`, let `tag(path)` change it, and record the result."""
        path = self.put(rel, base, expected, group)
        tag(path)
        assert path.read_bytes() != base, f"{rel}: tagging changed nothing"


def build(work: Path) -> Fixtures:
    fx = Fixtures()

    # ------------------------------------------------------------------ MP3
    # ffmpeg writes the LAME "Info" frame first and no tag at all, so the
    # untagged file is the payload.
    def mp3(freq: int, rate: int, seconds: float, kbps: int) -> bytes:
        out = work / f"sine{freq}-{rate}.mp3"
        ffmpeg(*sine(freq, rate, seconds), *BITEXACT, "-c:a", "libmp3lame", "-b:a", f"{kbps}k",
               "-id3v2_version", "0", "-write_id3v1", "0", str(out))
        data = out.read_bytes()
        assert data[0] == 0xFF and data[1] & 0xE0 == 0xE0, "ffmpeg wrote a tag"
        return data

    plain = mp3(440, 22050, 0.3, 32)
    want = audio_id(plain)
    fx.put("mp3/plain.mp3", plain, want, "mp3")

    def v23(p: Path) -> None:
        t = ID3()
        id3_frames(t)
        t.save(p, v2_version=3)

    def v24(p: Path) -> None:
        t = ID3()
        id3_frames(t)
        t.save(p, v2_version=4)

    def cover(p: Path) -> None:
        t = ID3()
        id3_frames(t)
        t.add(APIC(encoding=3, mime="image/png", type=3, desc="Cover", data=COVER))
        t.save(p, v2_version=4)

    def padded(p: Path) -> None:
        t = ID3()
        id3_frames(t)
        t.save(p, v2_version=4, padding=lambda info: 3000)

    def ape(p: Path) -> None:
        t = APEv2()
        t["Title"] = "Night Drive"
        t["Artist"] = "Some Artist"
        t.save(p)

    fx.tagged("mp3/id3v23.mp3", plain, want, "mp3", v23)
    fx.tagged("mp3/id3v24.mp3", plain, want, "mp3", v24)
    fx.tagged("mp3/cover.mp3", plain, want, "mp3", cover)
    fx.tagged("mp3/padding.mp3", plain, want, "mp3", padded)
    fx.tagged("mp3/apev2.mp3", plain, want, "mp3", ape)
    fx.put("mp3/id3v1.mp3", plain + id3v1("Night Drive"), want, "mp3")
    fx.put("mp3/lyrics3.mp3", plain + lyrics3v2() + id3v1("Night Drive"), want, "mp3")
    fx.put("mp3/footer.mp3", id3v24_with_footer() + plain, want, "mp3")
    # Junk between the tag and the first frame is skipped by the frame scan.
    fx.put("mp3/junk.mp3", id3v24_with_footer() + b"\x00" * 300 + plain, want, "mp3")

    def everything(p: Path) -> None:
        cover(p)
        ape(p)
        with open(p, "ab") as fh:
            fh.write(lyrics3v2())
        with open(p, "ab") as fh:
            fh.write(id3v1("Night Drive"))

    fx.tagged("mp3/all-tags.mp3", plain, want, "mp3", everything)

    other = mp3(880, 22050, 0.3, 32)
    fx.put("mp3/other-audio.mp3", other, audio_id(other), None)
    mpeg1 = mp3(440, 44100, 0.1, 64)
    fx.put("mp3/mpeg1.mp3", mpeg1, audio_id(mpeg1), None)

    # ----------------------------------------------------------------- FLAC
    def flac(freq: int) -> bytes:
        out = work / f"sine{freq}.flac"
        ffmpeg(*sine(freq, 8000, 0.25), *BITEXACT, "-c:a", "flac", "-sample_fmt", "s16", str(out))
        return out.read_bytes()

    produced = flac(440)
    frames = flac_frames(produced)
    want = audio_id(frames)
    bare = b"fLaC" + b"\x80" + struct.pack(">I", 34)[1:] + flac_streaminfo(produced) + frames
    fx.put("flac/ffmpeg.flac", produced, want, "flac")
    fx.put("flac/plain.flac", bare, want, "flac")

    def vorbis(p: Path) -> None:
        f = FLAC(p)
        f["title"] = "Night Drive"
        f["artist"] = ["Some Artist", "Other Artist"]
        f["genre"] = "House"
        f["date"] = "2019"
        f.save()

    def flac_cover(p: Path) -> None:
        vorbis(p)
        f = FLAC(p)
        pic = Picture()
        pic.type, pic.mime, pic.desc, pic.data = 3, "image/png", "Cover", COVER
        f.add_picture(pic)
        f.save()

    def flac_padding(p: Path) -> None:
        f = FLAC(p)
        f["title"] = "Night Drive"
        f.save(padding=lambda info: 5000)

    fx.tagged("flac/tags.flac", bare, want, "flac", vorbis)
    fx.tagged("flac/cover.flac", bare, want, "flac", flac_cover)
    fx.tagged("flac/padding.flac", bare, want, "flac", flac_padding)
    # A broken tagger put an ID3v2 tag in front of fLaC.
    junk_tag = work / "tag.id3"
    junk_tag.write_bytes(b"")
    t = ID3()
    t.add(TIT2(encoding=3, text="Night Drive"))
    t.save(junk_tag, v2_version=3, padding=lambda info: 0)
    fx.put("flac/id3-in-front.flac", junk_tag.read_bytes() + bare, want, "flac")

    other = flac(880)
    fx.put("flac/other-audio.flac", other, audio_id(flac_frames(other)), None)

    # ------------------------------------------------------------------ WAV
    fmt = struct.pack("<HHIIHH", 1, 1, 8000, 16000, 2, 16)
    data = pcm16(440, 8000, 0.15, big_endian=False)
    want = audio_id(fmt + data)
    plain_wav = wav([riff_chunk(b"fmt ", fmt), riff_chunk(b"data", data)])
    fx.put("wav/plain.wav", plain_wav, want, "wav")
    info = b"INFO" + riff_chunk(b"INAM", b"Night Drive\x00") + riff_chunk(b"IART", b"Artist\x00")
    fx.put("wav/list-info.wav",
           wav([riff_chunk(b"fmt ", fmt), riff_chunk(b"data", data), riff_chunk(b"LIST", info)]),
           want, "wav")
    # Odd-sized chunks (each with its pad byte) before fmt and between fmt and data.
    fx.put("wav/extra-chunks.wav",
           wav([riff_chunk(b"JUNK", b"\x00" * 27), riff_chunk(b"fmt ", fmt),
                riff_chunk(b"bext", b"x" * 13), riff_chunk(b"data", data)]),
           want, "wav")

    def wave_id3(p: Path) -> None:
        w = WAVE(p)
        w.add_tags()
        id3_frames(w.tags)
        w.save()

    fx.tagged("wav/id3.wav", plain_wav, want, "wav", wave_id3)
    other_data = pcm16(880, 8000, 0.15, big_endian=False)
    fx.put("wav/other-audio.wav", wav([riff_chunk(b"fmt ", fmt), riff_chunk(b"data", other_data)]),
           audio_id(fmt + other_data), None)

    # ----------------------------------------------------------------- AIFF
    def comm(frames_count: int) -> bytes:
        return struct.pack(">hIh", 1, frames_count, 16) + ieee_extended(8000.0)

    be = pcm16(440, 8000, 0.15, big_endian=True)
    comm_body = comm(len(be) // 2)
    ssnd = struct.pack(">II", 0, 0) + be
    want = audio_id(comm_body + ssnd)
    plain_aiff = aiff([iff_chunk(b"COMM", comm_body), iff_chunk(b"SSND", ssnd)])
    fx.put("aiff/plain.aiff", plain_aiff, want, "aiff")
    fx.put("aiff/anno.aif",
           aiff([iff_chunk(b"ANNO", b"an odd comment."), iff_chunk(b"COMM", comm_body),
                 iff_chunk(b"SSND", ssnd)]),
           want, "aiff")

    def aiff_id3(p: Path) -> None:
        a = AIFF(p)
        a.add_tags()
        id3_frames(a.tags)
        a.save()

    fx.tagged("aiff/id3.aiff", plain_aiff, want, "aiff", aiff_id3)
    other_be = pcm16(880, 8000, 0.15, big_endian=True)
    other_ssnd = struct.pack(">II", 0, 0) + other_be
    fx.put("aiff/other-audio.aiff",
           aiff([iff_chunk(b"COMM", comm_body), iff_chunk(b"SSND", other_ssnd)]),
           audio_id(comm_body + other_ssnd), None)

    # ------------------------------------------------------------------ MP4
    def m4a(freq: int, faststart: bool) -> bytes:
        out = work / f"sine{freq}-{int(faststart)}.m4a"
        extra = ["-movflags", "+faststart"] if faststart else []
        ffmpeg(*sine(freq, 22050, 0.3), *BITEXACT, "-c:a", "aac", "-b:a", "32k", *extra, str(out))
        return out.read_bytes()

    late = m4a(440, faststart=False)
    early = m4a(440, faststart=True)
    kinds = lambda d: [k for k, _, _ in mp4_atoms(d)]  # noqa: E731
    assert kinds(late).index(b"mdat") < kinds(late).index(b"moov")
    assert kinds(early).index(b"moov") < kinds(early).index(b"mdat")
    assert mdat_payload(late) == mdat_payload(early), "ffmpeg changed the audio between layouts"
    want = audio_id(mdat_payload(late))
    fx.put("m4a/moov-after-mdat.m4a", late, want, "m4a")
    fx.put("m4a/moov-before-mdat.m4a", early, want, "m4a")

    def mp4_tags(p: Path) -> None:
        f = MP4(p)
        f["\xa9nam"] = "Night Drive"
        f["\xa9ART"] = ["Some Artist", "Other Artist"]
        f["\xa9gen"] = "House"
        f["\xa9day"] = "2019"
        f["\xa9cmt"] = "x" * 2000  # grows moov, so mdat moves when moov is first
        f.save()

    def mp4_cover(p: Path) -> None:
        mp4_tags(p)
        f = MP4(p)
        f["covr"] = [MP4Cover(COVER, imageformat=MP4Cover.FORMAT_PNG)]
        f.save()

    fx.tagged("m4a/tags-moov-before.m4a", early, want, "m4a", mp4_tags)
    fx.tagged("m4a/tags-moov-after.m4a", late, want, "m4a", mp4_tags)
    fx.tagged("m4a/cover.m4a", early, want, "m4a", mp4_cover)
    other = m4a(880, faststart=True)
    fx.put("m4a/other-audio.m4a", other, audio_id(mdat_payload(other)), None)

    # ------------------------------------------------------------ fallbacks
    def fallback(rel: str, data: bytes) -> None:
        fx.put(rel, data, fallback_id(data), None)

    ogg = work / "sine.ogg"
    ffmpeg(*sine(440, 8000, 0.2), *BITEXACT, "-c:a", "libvorbis", str(ogg))
    fallback("fallback/vorbis.ogg", ogg.read_bytes())
    opus = work / "sine.opus"
    ffmpeg(*sine(440, 8000, 0.2), *BITEXACT, "-c:a", "libopus", "-b:a", "16k", str(opus))
    fallback("fallback/opus.opus", opus.read_bytes())
    adts = work / "sine.aac"
    ffmpeg(*sine(440, 22050, 0.2), *BITEXACT, "-c:a", "aac", "-b:a", "32k", "-f", "adts", str(adts))
    fallback("fallback/raw.aac", adts.read_bytes())
    fallback("fallback/truncated.wav", plain_wav[: len(plain_wav) // 2])
    fallback("fallback/truncated.aiff", plain_aiff[: len(plain_aiff) // 2])
    fallback("fallback/truncated.m4a", late[: len(late) // 2])
    fallback("fallback/not-flac.flac", b"fLaX" + bare[4:])
    fallback("fallback/no-frames.mp3", id3v24_with_footer() + bytes(range(256)) * 4)
    tag_too_long = b"ID3\x04\x00\x00" + syncsafe(100000) + plain[:500]
    fallback("fallback/tag-past-end.mp3", tag_too_long)
    fallback("fallback/rf64.wav", b"RF64" + plain_wav[4:])

    # ------------------------------------------------------- must differ
    reps = [files[0] for files in fx.same.values()]
    singles = [rel for rel in fx.files if not any(rel in g for g in fx.same.values())]
    fx.different.append(sorted(reps + singles))
    return fx


def main() -> None:
    for sub in ("mp3", "flac", "wav", "aiff", "m4a", "fallback"):
        shutil.rmtree(HERE / sub, ignore_errors=True)
    with tempfile.TemporaryDirectory() as tmp:
        fx = build(Path(tmp))
    version = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True,
                             check=True).stdout.splitlines()[0]
    doc = {
        "version": 1,
        "made_with": version,
        "files": dict(sorted(fx.files.items())),
        "same": {k: sorted(v) for k, v in sorted(fx.same.items())},
        "different": fx.different,
    }
    (HERE / "expected.json").write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
    sizes = {rel: (HERE / rel).stat().st_size for rel in fx.files}
    print(f"{len(sizes)} files, largest {max(sizes.values())} bytes, "
          f"{sum(sizes.values())} bytes in all")


if __name__ == "__main__":
    main()
