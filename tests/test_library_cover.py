"""The cover edit: library.write_cover and the tagger's read_cover (design 4.3)."""
import struct
import zlib
from pathlib import Path

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import APIC, ID3

from app import audiohash, library, tagger


def png(width: int = 4, height: int = 4, shade: int = 200) -> bytes:
    """A valid PNG, grey, of any size."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    raw = b"".join(b"\x00" + bytes([shade]) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60 + b"\xff\xd9"  # enough to be told as a JPEG


def row(lib, rel):
    [item] = [i for i in lib.list(limit=500)["items"] if i["path"] == rel]
    return lib.file(item["id"])


@pytest.fixture()
def covered(lib, music):
    """One MP3 and one FLAC that have a cover, one MP3 and a WAV that have none."""
    music.fixture("with.mp3", "mp3/cover.mp3")
    music.fixture("with.flac", "flac/cover.flac")
    music.mp3("without.mp3", seed=9, title="Plain")
    music.wav("without.wav")
    lib.reconcile()
    return lib


# ------------------------------------------------------------ reading
@pytest.mark.parametrize("fixture, mime", [
    ("mp3/cover.mp3", "image/png"), ("flac/cover.flac", "image/png"),
    ("m4a/cover.m4a", None),
])
def test_read_cover_per_format(fixture, mime):
    found = tagger.read_cover(Path(__file__).parent.parent / "testdata" / "audiohash" / fixture)
    assert found is not None and found[1] in ("image/png", "image/jpeg")
    assert tagger.image_type(found[0]) == found[1]
    if mime:
        assert found[1] == mime


def test_read_cover_without_a_cover_or_a_readable_file(music):
    music.mp3("a.mp3", title="x")
    assert tagger.read_cover(music.path("a.mp3")) is None
    music.write("junk.mp3", b"not audio at all")
    assert tagger.read_cover(music.path("junk.mp3")) is None
    assert tagger.read_cover(music.path("missing.mp3")) is None


# ------------------------------------------------------------ writing
@pytest.mark.parametrize("name", ["with.mp3", "with.flac"])
def test_the_cover_changes_the_audio_id_does_not_and_the_old_image_comes_back(covered, music,
                                                                              name):
    lib = covered
    before = row(lib, name)
    old = tagger.read_cover(music.path(name))
    new = png(32, 32, 90)
    rev = lib.status()["rev"]

    result = lib.write_cover(before["id"], (new, "image/png"))

    assert result.previous == old and result.previous[0] != new
    assert tagger.read_cover(music.path(name)) == (new, "image/png")
    assert audiohash.audio_id(music.path(name)) == before["audio_id"]  # rehashed from disk
    after = row(lib, name)
    assert after["audio_id"] == before["audio_id"]
    assert after["rev"] == rev + 1 == lib.status()["rev"]  # one rev for the write
    assert after["content_rev"] == after["rev"] and after["content_rev"] > before["content_rev"]
    assert (after["size"], after["mtime_ns"]) == (music.path(name).stat().st_size,
                                                  music.path(name).stat().st_mtime_ns)
    assert result.item["has_cover"] is True and result.item["id"] == before["id"]
    assert result.item["content_rev"] == after["content_rev"]


def test_a_file_without_a_cover_gets_one_and_previous_says_there_was_none(covered, music):
    lib = covered
    before = row(lib, "without.mp3")
    assert before["has_cover"] == 0
    result = lib.write_cover(before["id"], (JPEG, "image/jpeg"))
    assert result.previous is None
    assert result.item["has_cover"] is True
    assert tagger.read_cover(music.path("without.mp3")) == (JPEG, "image/jpeg")


def test_none_removes_the_cover_and_hands_back_the_image(covered, music):
    lib = covered
    old = tagger.read_cover(music.path("with.mp3"))
    result = lib.write_cover(row(lib, "with.mp3")["id"], None)
    assert result.previous == old
    assert result.item["has_cover"] is False
    assert tagger.read_cover(music.path("with.mp3")) is None
    assert ID3(music.path("with.mp3")).getall("APIC") == []


def test_putting_the_previous_image_back_restores_the_cover(covered, music):
    lib = covered
    fid = row(lib, "with.flac")["id"]
    old = tagger.read_cover(music.path("with.flac"))
    undone = lib.write_cover(fid, (png(8, 8), "image/png"))
    lib.write_cover(fid, undone.previous)
    assert tagger.read_cover(music.path("with.flac")) == old


def test_the_declared_type_does_not_matter_the_bytes_do(covered, music):
    lib = covered
    lib.write_cover(row(lib, "with.mp3")["id"], (png(), "image/jpeg"))
    assert tagger.read_cover(music.path("with.mp3"))[1] == "image/png"
    assert ID3(music.path("with.mp3")).getall("APIC")[0].mime == "image/png"


def test_a_cover_edit_leaves_every_tag_and_one_picture(covered, music):
    lib = covered
    mp3 = music.path("with.mp3")
    tags_before = {k: repr(v) for k, v in ID3(mp3).items() if not k.startswith("APIC")}
    lib.write_cover(row(lib, "with.mp3")["id"], (png(16, 16), "image/png"))
    assert {k: repr(v) for k, v in ID3(mp3).items() if not k.startswith("APIC")} == tags_before
    assert len(ID3(mp3).getall("APIC")) == 1 and ID3(mp3).getall("APIC")[0].type == 3

    flac = music.path("with.flac")
    comments_before = dict(FLAC(flac).tags.items())
    lib.write_cover(row(lib, "with.flac")["id"], (png(16, 16), "image/png"))
    assert dict(FLAC(flac).tags.items()) == comments_before
    assert len(FLAC(flac).pictures) == 1 and FLAC(flac).pictures[0].type == 3


def test_the_title_edit_keeps_the_cover_and_the_cover_edit_keeps_the_title(covered, music):
    lib = covered
    fid = row(lib, "with.mp3")["id"]
    cover = tagger.read_cover(music.path("with.mp3"))
    lib.write_tags(fid, {"title": "Renamed"})
    assert tagger.read_cover(music.path("with.mp3")) == cover  # an edit does not touch it
    lib.write_cover(fid, (png(8, 8), "image/png"))
    assert row(lib, "with.mp3")["title"] == "Renamed"


# ------------------------------------------------------------ refusals
def test_what_is_not_an_image_is_refused_before_anything_is_written(covered, music):
    lib = covered
    fid = row(lib, "with.mp3")["id"]
    data = music.path("with.mp3").read_bytes()
    rev = lib.status()["rev"]
    for bad in (b"", b"GIF89a....", b"<html>nope</html>", b"\x00" * 100):
        with pytest.raises(library.LibraryError) as refused:
            lib.write_cover(fid, (bad, "image/jpeg"))
        assert refused.value.status == 400
    with pytest.raises(library.LibraryError) as big:
        lib.write_cover(fid, (JPEG + b"\x00" * tagger.MAX_COVER, "image/jpeg"))
    assert big.value.status == 413
    assert music.path("with.mp3").read_bytes() == data and lib.status()["rev"] == rev


def test_unknown_readonly_damaged_trashed_and_missing_files(covered, music):
    lib = covered
    image = (png(), "image/png")
    with pytest.raises(library.LibraryError) as unknown:
        lib.write_cover(9999, image)
    assert unknown.value.status == 404
    with pytest.raises(library.LibraryError) as readonly:
        lib.write_cover(row(lib, "without.wav")["id"], image)
    assert readonly.value.status == 409
    fid = row(lib, "with.mp3")["id"]
    lib.trash(fid)
    with pytest.raises(library.LibraryError) as trashed:
        lib.write_cover(fid, image)
    assert trashed.value.status == 410
    gone = row(lib, "without.mp3")
    music.remove("without.mp3")
    with pytest.raises(library.LibraryError) as absent:
        lib.write_cover(gone["id"], image)
    assert absent.value.status == 410


def test_a_file_held_by_another_program_keeps_its_cover(covered, music, monkeypatch):
    lib = covered
    path = music.path("with.mp3")
    data = path.read_bytes()

    def held(src, dst):
        raise PermissionError(32, "in use")

    monkeypatch.setattr(tagger.os, "replace", held)
    with pytest.raises(library.LibraryError) as refused:
        lib.write_cover(row(lib, "with.mp3")["id"], (png(), "image/png"))
    assert refused.value.status == 423
    assert path.read_bytes() == data
    assert not list(music.root.glob(".*.part"))


def test_the_cover_is_written_on_a_copy_that_replaces_the_original(covered, music, monkeypatch):
    lib = covered
    copies = []
    real_copy = tagger.shutil.copy2
    monkeypatch.setattr(tagger.shutil, "copy2", lambda a, b: copies.append(b) or real_copy(a, b))
    lib.write_cover(row(lib, "with.flac")["id"], (png(), "image/png"))
    assert [c.name for c in copies] == [".with.flac.part"]
    assert not music.path(".with.flac.part").exists()


def test_a_download_url_must_be_http():
    for url in ("file:///etc/passwd", "ftp://host/x.jpg", "data:image/png;base64,AAAA", "", "x"):
        assert tagger.fetch_image(url) is None


def test_a_picture_claiming_to_be_svg_is_never_served_as_svg(music):
    path = music.fixture("Scripted.mp3", "mp3/all-tags.mp3")
    tags = ID3(path)
    tags.delall("APIC")
    tags.add(APIC(encoding=3, mime="image/svg+xml", type=3, desc="",
                  data=b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"))
    tags.save(path, v2_version=4)
    assert tagger.read_cover(path)[1] == "image/jpeg"
