"""The audio id against the shared fixtures in testdata/audiohash."""
import json
import random
import re
import shutil
from itertools import combinations
from pathlib import Path

import pytest
from mutagen.aiff import AIFF
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, COMM, TALB, TCON, TDRC, TIT2, TPE1
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE

from app import audiohash, tagger

FIXTURES = Path(__file__).resolve().parent.parent / "testdata" / "audiohash"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text("utf-8"))
ID_SHAPE = re.compile(r"^(a1|f1)_[0-9a-f]{32}$")


@pytest.mark.parametrize("rel", sorted(EXPECTED["files"]))
def test_fixture_gets_its_expected_id(rel):
    assert audiohash.audio_id(FIXTURES / rel) == EXPECTED["files"][rel]


@pytest.mark.parametrize("group", sorted(EXPECTED["same"]))
def test_same_audio_shares_one_id(group):
    files = EXPECTED["same"][group]
    assert len(files) >= 3
    ids = {audiohash.audio_id(FIXTURES / rel) for rel in files}
    assert len(ids) == 1 and ids.pop().startswith("a1_")


def test_different_audio_gets_different_ids():
    for files in EXPECTED["different"]:
        ids = [audiohash.audio_id(FIXTURES / rel) for rel in files]
        for (a, ida), (b, idb) in combinations(zip(files, ids), 2):
            assert ida != idb, f"{a} and {b} share {ida}"


def test_every_fixture_is_small_and_listed():
    on_disk = {
        p.relative_to(FIXTURES).as_posix()
        for p in FIXTURES.rglob("*")
        if p.is_file() and p.suffix not in (".json", ".md", ".py")
    }
    assert on_disk == set(EXPECTED["files"])
    assert all((FIXTURES / rel).stat().st_size < 16 * 1024 for rel in on_disk)


def test_ogg_and_opus_get_the_fallback_id():
    assert audiohash.audio_id(FIXTURES / "fallback/vorbis.ogg").startswith("f1_")
    assert audiohash.audio_id(FIXTURES / "fallback/opus.opus").startswith("f1_")


# ------------------------------------------------------------ tag edits
def _copy(tmp_path, rel):
    dest = tmp_path / Path(rel).name
    shutil.copyfile(FIXTURES / rel, dest)
    return dest


def test_the_download_tagger_keeps_the_id(tmp_path, monkeypatch):
    monkeypatch.setattr(tagger, "load_cover", lambda meta: (b"\x89PNG\r\n\x1a\n" + b"0" * 5000,
                                                            "image/png"))
    meta = {"title": "T" * 300, "artist": "Ärtist", "album": "Album", "genre": "Tech House",
            "url": "https://example.test/" + "x" * 500}
    for rel in ("mp3/plain.mp3", "mp3/all-tags.mp3", "flac/plain.flac", "flac/padding.flac"):
        path = _copy(tmp_path, rel)
        before = audiohash.audio_id(path)
        tagger.tag_file(str(path), meta)
        assert audiohash.audio_id(path) == before == EXPECTED["files"][rel], rel


def test_editing_every_mp3_field_keeps_the_id(tmp_path):
    path = _copy(tmp_path, "mp3/id3v24.mp3")
    want = audiohash.audio_id(path)
    for frame in (TIT2(encoding=3, text="New"), TPE1(encoding=3, text=["A", "B"]),
                  TALB(encoding=3, text="Al" * 2000), TCON(encoding=3, text="Techno"),
                  TDRC(encoding=3, text="2001"),
                  COMM(encoding=3, lang="eng", desc="", text="c" * 4000),
                  APIC(encoding=3, mime="image/png", type=3, desc="", data=b"p" * 9000)):
        audio = MP3(path)
        audio.tags.setall(frame.FrameID, [frame])
        audio.save(v2_version=4)
        assert audiohash.audio_id(path) == want, frame.FrameID
    audio = MP3(path)
    audio.save(v2_version=3, v1=2)  # downgrade the tag, add ID3v1
    assert audiohash.audio_id(path) == want
    audio = MP3(path)
    audio.delete()
    assert audiohash.audio_id(path) == want


def test_editing_every_flac_field_keeps_the_id(tmp_path):
    path = _copy(tmp_path, "flac/tags.flac")
    want = audiohash.audio_id(path)
    for key, value in (("title", "New"), ("artist", ["A", "B"]), ("album", "x" * 9000),
                       ("genre", "Techno"), ("date", "2001-02-03"), ("comment", "c")):
        audio = FLAC(path)
        audio[key] = value
        audio.save()
        assert audiohash.audio_id(path) == want, key
    audio = FLAC(path)
    pic = Picture()
    pic.type, pic.mime, pic.data = 3, "image/png", b"p" * 20000
    audio.add_picture(pic)
    audio.save()
    assert audiohash.audio_id(path) == want


def test_editing_m4a_aiff_and_wav_tags_keeps_the_id(tmp_path):
    for rel in ("m4a/moov-before-mdat.m4a", "m4a/moov-after-mdat.m4a"):
        path = _copy(tmp_path, rel)
        want = audiohash.audio_id(path)
        audio = MP4(path)
        audio["\xa9nam"] = "n" * 5000
        audio["covr"] = [MP4Cover(b"\xff\xd8\xff" + b"j" * 8000)]
        audio.save()
        assert audiohash.audio_id(path) == want, rel
    for rel, kind in (("aiff/plain.aiff", AIFF), ("wav/plain.wav", WAVE)):
        path = _copy(tmp_path, rel)
        want = audiohash.audio_id(path)
        audio = kind(path)
        audio.add_tags()
        audio.tags.add(TIT2(encoding=3, text="New"))
        audio.save()
        assert audiohash.audio_id(path) == want, rel


# ------------------------------------------------------ damaged files
def test_a_truncated_file_never_raises(tmp_path):
    for rel in sorted(EXPECTED["files"]):
        data = (FIXTURES / rel).read_bytes()
        for cut in sorted({0, 1, 3, 4, 9, 10, 11, 12, 40, len(data) // 3, len(data) // 2,
                           len(data) - 129, len(data) - 1}):
            if not 0 <= cut < len(data):
                continue
            path = tmp_path / ("cut" + Path(rel).suffix)
            path.write_bytes(data[:cut])
            assert ID_SHAPE.match(audiohash.audio_id(path)), (rel, cut)


def test_corrupt_bytes_never_raise(tmp_path):
    rng = random.Random(7)
    for rel in sorted(EXPECTED["files"]):
        data = bytearray((FIXTURES / rel).read_bytes())
        for _ in range(8):
            spoiled = bytearray(data)
            for _ in range(rng.randint(1, 8)):
                spoiled[rng.randrange(min(len(spoiled), 200))] = rng.randrange(256)
            path = tmp_path / ("bad" + Path(rel).suffix)
            path.write_bytes(bytes(spoiled))
            assert ID_SHAPE.match(audiohash.audio_id(path)), rel


def test_a_header_cut_off_gives_the_fallback_id(tmp_path):
    for rel in ("wav/plain.wav", "aiff/plain.aiff", "m4a/moov-after-mdat.m4a",
                "flac/plain.flac", "mp3/id3v24.mp3"):
        path = tmp_path / ("cut" + Path(rel).suffix)
        path.write_bytes((FIXTURES / rel).read_bytes()[:30])
        assert audiohash.audio_id(path).startswith("f1_"), rel


def test_an_empty_file_gets_the_fallback_id(tmp_path):
    path = tmp_path / "empty.mp3"
    path.write_bytes(b"")
    assert audiohash.audio_id(path) == "f1_e3b0c44298fc1c149afbf4c8996fb924"
