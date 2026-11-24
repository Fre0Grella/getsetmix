"""The edit path: library.write_tags and the tagger's atomic write (design 4.3)."""
import threading

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TBPM, TKEY, TPE4, TXXX

from app import audiohash, library, tagger


def _id3(path):
    """Every frame of the file, by key, as comparable text."""
    return {k: repr(v) for k, v in ID3(path).items()}


def _flac(path):
    audio = FLAC(path)
    return {k: list(v) for k, v in audio.tags.items()}, [p.data for p in audio.pictures]


@pytest.fixture()
def rich_mp3(music):
    """An MP3 with a cover, two artists, a full date, a source comment, a
    described comment and the tags a DJ app writes."""
    path = music.fixture("Night Drive.mp3", "mp3/all-tags.mp3")
    tags = ID3(path)
    tags.add(TBPM(encoding=3, text="124"))
    tags.add(TKEY(encoding=3, text="8A"))
    tags.add(TPE4(encoding=3, text="Some Remixer"))
    tags.add(TXXX(encoding=3, desc="SERATO_PLAYCOUNT", text="3"))
    tags.save(path, v2_version=4)
    music.age("Night Drive.mp3", 3600)
    return path


@pytest.fixture()
def rich_flac(music):
    path = music.fixture("Night Drive.flac", "flac/cover.flac")
    audio = FLAC(path)
    audio["bpm"] = "124"
    audio["initialkey"] = "8A"
    audio["comment"] = "Source: https://example.test/x | via GetSetMix"
    audio["date"] = "2019-06-14"
    audio.save()
    music.age("Night Drive.flac", 3600)
    return path


def _row(lib, rel):
    [item] = [i for i in lib.list(limit=500)["items"] if i["path"] == rel]
    return lib.file(item["id"])


# ------------------------------------------------------- only the given fields
def test_an_mp3_edit_changes_only_the_fields_given(lib, music, rich_mp3):
    lib.reconcile()
    row = _row(lib, "Night Drive.mp3")
    before = _id3(rich_mp3)
    aid = audiohash.audio_id(rich_mp3)

    result = lib.write_tags(row["id"], {"genre": "Tech House"})

    assert result.written and result.item["genre"] == "Tech House"
    after = _id3(rich_mp3)
    assert ID3(rich_mp3)["TCON"].text == ["Tech House"]
    changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    assert changed == {"TCON"}  # cover, both artists, the date, both comments, DJ tags kept
    assert audiohash.audio_id(rich_mp3) == aid == row["audio_id"]


def test_a_flac_edit_changes_only_the_fields_given(lib, music, rich_flac):
    lib.reconcile()
    row = _row(lib, "Night Drive.flac")
    tags_before, pictures_before = _flac(rich_flac)
    aid = audiohash.audio_id(rich_flac)

    lib.write_tags(row["id"], {"title": "Night Drive (Extended)"})

    tags_after, pictures_after = _flac(rich_flac)
    assert tags_after == {**tags_before, "title": ["Night Drive (Extended)"]}
    assert pictures_after == pictures_before and pictures_after
    assert audiohash.audio_id(rich_flac) == aid


@pytest.mark.parametrize("name, fixture", [("a.mp3", "mp3/all-tags.mp3"),
                                           ("a.flac", "flac/cover.flac")])
def test_several_fields_make_one_copy_and_one_rev(lib, music, clock, monkeypatch, name, fixture):
    music.fixture(name, fixture)
    lib.reconcile()
    row = _row(lib, name)
    rev_before = lib.status()["rev"]
    copies = []
    real_copy = tagger.shutil.copy2
    monkeypatch.setattr(tagger.shutil, "copy2", lambda a, b: copies.append(b) or real_copy(a, b))

    result = lib.write_tags(row["id"], {"title": "T", "artist": "A", "album": "B", "genre": "G",
                                       "year": 2021, "comment": "C"})

    assert len(copies) == 1 and copies[0].name == f".{name}.part"
    assert not copies[0].exists()  # renamed over the original
    assert lib.status()["rev"] == rev_before + 1
    after = lib.file(row["id"])
    assert after["rev"] == after["content_rev"] == rev_before + 1
    item = result.item
    assert (item["title"], item["artist"], item["album"], item["genre"], item["year"],
            item["comment"]) == ("T", "A", "B", "G", 2021, "C")
    assert item["multi"] == []
    assert after["size"] == music.path(name).stat().st_size
    assert after["mtime_ns"] == music.path(name).stat().st_mtime_ns
    assert audiohash.audio_id(music.path(name)) == row["audio_id"]
    clock.advance(60)  # past the settle time, so the pass really looks at the file
    assert lib.reconcile() == {k: 0 for k in ("new", "changed", "replaced", "moved", "back",
                                              "missing", "gone")}  # the row is up to date


def test_year_and_comment_go_to_the_right_frame(lib, music, rich_mp3, rich_flac):
    lib.reconcile()
    lib.write_tags(_row(lib, "Night Drive.mp3")["id"], {"year": 1999, "comment": "mine"})
    lib.write_tags(_row(lib, "Night Drive.flac")["id"], {"year": 1999, "comment": "mine"})

    id3 = ID3(rich_mp3)
    assert str(id3["TDRC"].text[0]) == "1999"  # the year alone (decision 18)
    assert [c.text for c in id3.getall("COMM") if c.desc == ""] == [["mine"]]
    assert id3["COMM:ID3v1 Comment:eng"].text == ["comment"]  # a described comment stays
    flac = FLAC(rich_flac)
    assert flac["date"] == ["1999"] and flac["comment"] == ["mine"]


def test_a_full_date_is_left_alone_when_the_year_is_not_edited(lib, music, rich_mp3, rich_flac):
    lib.reconcile()
    lib.write_tags(_row(lib, "Night Drive.mp3")["id"], {"title": "x"})
    lib.write_tags(_row(lib, "Night Drive.flac")["id"], {"title": "x"})
    assert str(ID3(rich_mp3)["TDRC"].text[0]) == "2019-06-14"
    assert FLAC(rich_flac)["date"] == ["2019-06-14"]
    assert _row(lib, "Night Drive.mp3")["year"] == 2019


def test_empty_values_clear_the_tag(lib, music, rich_mp3, rich_flac):
    lib.reconcile()
    for rel, path in (("Night Drive.mp3", rich_mp3), ("Night Drive.flac", rich_flac)):
        item = lib.write_tags(_row(lib, rel)["id"],
                              {"album": "", "year": None, "comment": ""}).item
        assert (item["album"], item["year"], item["comment"]) == ("", None, "")
    id3 = ID3(rich_mp3)
    assert "TALB" not in id3 and "TDRC" not in id3
    assert not [c for c in id3.getall("COMM") if c.desc == ""]
    flac = FLAC(rich_flac)
    assert "album" not in flac and "date" not in flac and "comment" not in flac


@pytest.mark.parametrize("fixture", [
    "mp3/plain.mp3", "mp3/id3v1.mp3", "mp3/id3v23.mp3", "mp3/id3v24.mp3", "mp3/apev2.mp3",
    "mp3/lyrics3.mp3", "mp3/footer.mp3", "mp3/junk.mp3", "mp3/padding.mp3", "mp3/cover.mp3",
    "flac/plain.flac", "flac/tags.flac", "flac/cover.flac", "flac/padding.flac",
    "flac/id3-in-front.flac", "flac/ffmpeg.flac"])
def test_every_field_can_be_edited_and_the_audio_id_holds(lib, music, fixture):
    name = "track" + fixture[fixture.rindex("."):]
    path = music.fixture(name, fixture)
    aid = audiohash.audio_id(path)
    lib.reconcile()
    row = _row(lib, name)
    item = lib.write_tags(row["id"], {"title": "T", "artist": "A", "album": "B", "genre": "G",
                                     "year": 2001, "comment": "C"}).item
    assert (item["title"], item["artist"], item["album"], item["genre"], item["year"],
            item["comment"]) == ("T", "A", "B", "G", 2001, "C")
    assert audiohash.audio_id(path) == aid


# ------------------------------------------------------ several values (17)
def test_a_multi_value_field_is_kept_unless_edited_and_then_written_as_one(lib, music, rich_mp3,
                                                                         rich_flac):
    lib.reconcile()
    mp3, flac = _row(lib, "Night Drive.mp3"), _row(lib, "Night Drive.flac")
    assert mp3["artist"] == flac["artist"] == "Some Artist; Other Artist"
    assert mp3["multi"] == flac["multi"] == "artist"

    lib.write_tags(mp3["id"], {"genre": "Deep"})
    lib.write_tags(flac["id"], {"genre": "Deep"})
    assert ID3(rich_mp3)["TPE1"].text == ["Some Artist", "Other Artist"]
    assert FLAC(rich_flac)["artist"] == ["Some Artist", "Other Artist"]

    # The value is written as given, one value, never split on "; " (decision 17).
    item = lib.write_tags(mp3["id"], {"artist": "Some Artist; Other Artist"}).item
    assert ID3(rich_mp3)["TPE1"].text == ["Some Artist; Other Artist"]
    assert item["artist"] == "Some Artist; Other Artist" and item["multi"] == []
    lib.write_tags(flac["id"], {"artist": "Some Artist"})
    assert FLAC(rich_flac)["artist"] == ["Some Artist"]
    assert lib.file(flac["id"])["multi"] == ""


def test_index_columns_hold_the_written_values_unfolded(lib, music):
    music.mp3("a.mp3", title="x")
    lib.reconcile()
    item = lib.write_tags(_row(lib, "a.mp3")["id"], {"title": "  Café  DEL Mar "}).item
    assert item["title"] == "  Café  DEL Mar "
    assert [i["path"] for i in lib.list(q="cafe del")["items"]] == ["a.mp3"]


# ---------------------------------------------------------------- expect
def test_expect_mismatch_writes_nothing_and_names_the_fields(lib, music, rich_mp3):
    lib.reconcile()
    row = _row(lib, "Night Drive.mp3")
    data = rich_mp3.read_bytes()
    rev = lib.status()["rev"]

    result = lib.write_tags(row["id"], {"genre": "Techno"},
                            expect={"genre": "house", "title": "Night Drive", "year": 2018})

    assert not result.written
    assert result.differs == {"genre": "House", "year": 2019}
    assert rich_mp3.read_bytes() == data and lib.status()["rev"] == rev
    assert not list(music.root.glob(".*.part"))


def test_expect_is_read_from_the_file_not_the_index(lib, music, rich_mp3):
    lib.reconcile()
    row = _row(lib, "Night Drive.mp3")
    tags = ID3(rich_mp3)
    tags.delall("TCON")
    tags.save(rich_mp3)  # changed outside GetSetMix, not reconciled yet
    result = lib.write_tags(row["id"], {"genre": "Techno"}, expect={"genre": "House"})
    assert result.differs == {"genre": ""}


def test_a_matching_expect_writes(lib, music, rich_mp3):
    lib.reconcile()
    row = _row(lib, "Night Drive.mp3")
    result = lib.write_tags(row["id"], {"genre": "Techno"},
                            expect={"genre": "House", "artist": "Some Artist; Other Artist"})
    assert result.written and result.item["genre"] == "Techno"


# ------------------------------------------------------------- refusals
def test_invalid_values_are_refused_before_anything_is_read(lib, music):
    music.mp3("a.mp3")
    lib.reconcile()
    fid = _row(lib, "a.mp3")["id"]
    for changes in ({"year": 999}, {"year": 10000}, {"year": "2019"}, {"year": True},
                    {"year": 2019.0}, {"title": None}, {"title": 5}, {"bpm": "124"}):
        with pytest.raises(library.LibraryError) as refused:
            lib.write_tags(fid, changes)
        assert refused.value.status == 400
    with pytest.raises(library.LibraryError) as refused:
        lib.write_tags(fid, {"title": "x"}, expect={"rating": 5})
    assert refused.value.status == 400


def test_expect_compares_a_year_the_file_holds_outside_the_range(lib, music):
    music.mp3("a.mp3", year="0999")
    lib.reconcile()
    row = _row(lib, "a.mp3")
    assert row["year"] == 999
    assert lib.write_tags(row["id"], {"year": 1999}, expect={"year": 999}).written
    assert _row(lib, "a.mp3")["year"] == 1999


def test_read_only_formats_fallback_ids_and_unknown_ids(lib, music):
    music.wav("a.wav")
    music.fixture("broken.mp3", "fallback/no-frames.mp3")
    lib.reconcile()
    for fid, status in ((_row(lib, "a.wav")["id"], 409), (_row(lib, "broken.mp3")["id"], 409),
                        (4242, 404)):
        with pytest.raises(library.LibraryError) as refused:
            lib.write_tags(fid, {"title": "x"})
        assert refused.value.status == status


def test_a_missing_file_is_gone(lib, music):
    music.mp3("a.mp3")
    lib.reconcile()
    fid = _row(lib, "a.mp3")["id"]
    music.remove("a.mp3")
    for _ in range(2):  # not on disk yet, then marked missing
        with pytest.raises(library.LibraryError) as refused:
            lib.write_tags(fid, {"title": "x"})
        assert refused.value.status == 410
        lib.reconcile()


def test_a_trashed_file_cannot_be_edited_and_comes_back_as_it_was(lib, music):
    path = music.mp3("a.mp3", title="old")
    lib.reconcile()
    fid = _row(lib, "a.mp3")["id"]
    data = path.read_bytes()
    lib.trash(fid)
    with pytest.raises(library.LibraryError) as refused:
        lib.write_tags(fid, {"title": "new"})
    assert refused.value.status == 410
    assert not path.exists()  # the refused edit put nothing back at the path
    lib.restore(fid)
    assert path.read_bytes() == data


def test_a_delete_waits_for_a_tag_write_in_progress(lib, music, monkeypatch):
    music.mp3("a.mp3", title="old")
    lib.reconcile()
    fid = _row(lib, "a.mp3")["id"]
    copying, go_on = threading.Event(), threading.Event()
    real = tagger.os.replace

    def slow(src, dst):
        copying.set()
        assert go_on.wait(5)
        real(src, dst)

    monkeypatch.setattr(tagger.os, "replace", slow)
    writer = threading.Thread(target=lib.write_tags, args=(fid, {"title": "new"}))
    writer.start()
    assert copying.wait(5)
    deleter = threading.Thread(target=lib.trash, args=(fid,))
    deleter.start()
    deleter.join(0.2)
    assert deleter.is_alive()  # the delete waits, so the rename cannot bring the file back
    go_on.set()
    writer.join(5)
    deleter.join(5)
    row = lib.file(fid)
    assert row["state"] == "trashed" and row["title"] == "new"
    assert not music.path("a.mp3").exists()
    assert (music.root / row["trash_path"]).is_file()


def test_a_pass_that_read_a_file_before_an_edit_keeps_the_edit(lib, music, clock, monkeypatch):
    music.mp3("a.mp3", title="old")
    lib.reconcile()
    fid = _row(lib, "a.mp3")["id"]
    music.tag("a.mp3", age=120, title="changed outside")
    real = lib._read

    def edit_after_read(root, rel):
        read = real(root, rel)
        lib.write_tags(fid, {"title": "edited"})
        return read

    monkeypatch.setattr(lib, "_read", edit_after_read)
    lib.reconcile()
    row = lib.file(fid)
    stat = music.path("a.mp3").stat()
    assert row["title"] == "edited"
    assert (row["size"], row["mtime_ns"]) == (stat.st_size, stat.st_mtime_ns)


def test_a_file_held_by_another_program_is_in_use_and_unchanged(lib, music, monkeypatch):
    path = music.mp3("a.mp3", title="old")
    lib.reconcile()
    data = path.read_bytes()

    def held(src, dst):
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(tagger.os, "replace", held)
    with pytest.raises(library.LibraryError) as refused:
        lib.write_tags(_row(lib, "a.mp3")["id"], {"title": "new"})
    assert refused.value.status == 423
    assert path.read_bytes() == data
    assert not list(music.root.glob(".*.part"))
    assert _row(lib, "a.mp3")["title"] == "old"


def test_an_edit_keeps_the_owner_of_the_file(music, rich_mp3, monkeypatch):
    """A library shared with another program must stay accessible to it."""
    calls = []
    monkeypatch.setattr(tagger.os, "chown", lambda p, uid, gid: calls.append((uid, gid)),
                        raising=False)
    st = rich_mp3.stat()
    tagger.edit_file(rich_mp3, {"title": "New"})
    assert calls == [(st.st_uid, st.st_gid)]
    assert ID3(rich_mp3)["TIT2"].text == ["New"]


def test_an_edit_works_without_the_right_to_change_the_owner(music, rich_mp3, monkeypatch):
    def refuse(*_):
        raise PermissionError("not allowed")
    monkeypatch.setattr(tagger.os, "chown", refuse, raising=False)
    tagger.edit_file(rich_mp3, {"title": "New"})
    assert ID3(rich_mp3)["TIT2"].text == ["New"]
