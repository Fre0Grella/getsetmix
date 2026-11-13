"""The library index: reconcile, the guard, the settle and grace times, resume."""
import threading

import pytest

from app import audiohash

HOUR = 3600


def by_path(lib, **filters):
    """The listed items by path, each with the row's `rev` (not part of a list item)."""
    items = lib.list(limit=500, **filters)["items"]
    return {item["path"]: {**item, "rev": lib.file(item["id"])["rev"]} for item in items}


def counts(lib):
    return lib.status()["counts"]


# ------------------------------------------------------------------ new
def test_first_pass_indexes_every_audio_file_with_the_link_rules(lib, music):
    music.mp3("Artist - Song.mp3", title="Song", artist="Artist", genre="House")
    music.wav("sub/dir/take.wav")
    music.mp3(".hidden.mp3")
    music.mp3("~lock.mp3")
    music.mp3("fetching.mp3.part")
    music.mp3("upload.tmp")
    music.mp3(".trash/old/deleted.mp3")
    music.write("notes.txt", b"not audio")
    music.write("empty.mp3", b"")

    lib.reconcile()

    items = by_path(lib)
    assert set(items) == {"Artist - Song.mp3", "sub/dir/take.wav"}
    song = items["Artist - Song.mp3"]
    assert (song["title"], song["artist"], song["genre"], song["format"]) == (
        "Song", "Artist", "House", "mp3")
    assert song["audio_id"] == audiohash.audio_id(music.path("Artist - Song.mp3"))
    assert song["editable"] is True
    assert items["sub/dir/take.wav"]["editable"] is False  # read-only format
    status = lib.status()
    assert status["indexed"] is True and status["last_reconcile"]
    assert status["counts"]["present"] == 2


def test_tag_values_are_stored_exactly_as_the_file_holds_them(lib, music):
    music.mp3("a.mp3", title="  Café  del MAR ", artist=["Ätna", "Bob"], album="X",
              genre="deep house", year="2019-06-14", comment="Source: https://x | via GetSetMix")
    lib.reconcile()
    item = by_path(lib)["a.mp3"]
    assert item["title"] == "  Café  del MAR "
    assert item["artist"] == "Ätna; Bob"
    assert item["multi"] == ["artist"]
    assert item["genre"] == "deep house"
    assert item["year"] == 2019
    full = lib.file(item["id"])
    assert full["comment"] == "Source: https://x | via GetSetMix"
    assert full["sample_rate"] == 22050 and full["bitrate"] and full["duration"] > 0


def test_search_ignores_case_and_accents(lib, music):
    music.mp3("a.mp3", seed=1, title="Café del Mar", artist="Energy 52")
    music.mp3("b.mp3", seed=2, title="Other", artist="ÄTNA")
    music.mp3("folder/Coffee Shop.mp3", seed=3, title="Untitled")
    lib.reconcile()

    def found(q):
        return sorted(by_path(lib, q=q))

    assert found("cafe") == ["a.mp3"]
    assert found("CAFÉ DEL") == ["a.mp3"]
    assert found("atna") == ["b.mp3"]
    assert found("coffee") == ["folder/Coffee Shop.mp3"]  # the file name counts
    assert found("mar energy") == ["a.mp3"]               # every word must match
    assert found("100%") == []                            # LIKE wildcards are literal


def test_every_change_takes_the_next_rev(lib, music):
    music.mp3("a.mp3", seed=1)
    music.mp3("b.mp3", seed=2)
    lib.reconcile()
    revs = sorted(item["rev"] for item in by_path(lib).values())
    assert revs == [1, 2]
    assert lib.status()["rev"] == 2
    lib.reconcile()
    assert lib.status()["rev"] == 2  # nothing changed, nothing taken


# ------------------------------------------------------------ unchanged
def test_an_unchanged_file_is_not_read_again(lib, music, monkeypatch):
    music.mp3("a.mp3", title="Song")
    lib.reconcile()

    def no_reading(path):
        raise AssertionError("an unchanged file was hashed")

    monkeypatch.setattr(audiohash, "audio_id", no_reading)
    lib.reconcile()
    assert by_path(lib)["a.mp3"]["title"] == "Song"


# -------------------------------------------------------------- changed
def test_tags_changed_outside_are_read_again_and_keep_the_row(lib, music):
    music.mp3("a.mp3", title="Old", genre="House")
    lib.reconcile()
    before = by_path(lib)["a.mp3"]

    music.tag("a.mp3", title="New", genre="Techno", age=100)
    lib.reconcile()

    after = by_path(lib)["a.mp3"]
    assert after["id"] == before["id"] and after["audio_id"] == before["audio_id"]
    assert (after["title"], after["genre"]) == ("New", "Techno")
    assert after["rev"] > before["rev"]


def test_replaced_audio_is_the_old_track_gone_and_a_new_one(lib, music):
    music.mp3("a.mp3", seed=1, title="First")
    lib.reconcile()
    old = by_path(lib)["a.mp3"]

    music.mp3("a.mp3", seed=2, title="Second", age=100)
    lib.reconcile()

    new = by_path(lib)["a.mp3"]
    assert new["id"] != old["id"] and new["audio_id"] != old["audio_id"]
    assert new["title"] == "Second"
    gone = lib.file(old["id"])
    assert gone["state"] == "gone" and gone["path"] == "a.mp3"
    assert counts(lib) == {"present": 1, "gone": 1}


# ---------------------------------------------------------------- moved
def test_a_file_moved_outside_keeps_its_row(lib, music):
    music.mp3("a.mp3", seed=1, title="Song")
    music.mp3("b.mp3", seed=2)
    lib.reconcile()
    before = by_path(lib)["a.mp3"]

    music.move("a.mp3", "House/renamed.mp3")
    lib.reconcile()

    items = by_path(lib)
    assert set(items) == {"House/renamed.mp3", "b.mp3"}
    moved = items["House/renamed.mp3"]
    assert moved["id"] == before["id"] and moved["title"] == "Song"
    assert moved["rev"] > before["rev"]
    assert counts(lib) == {"present": 2}


def test_a_missing_file_that_comes_back_elsewhere_keeps_its_row(lib, music, tmp_path):
    music.mp3("a.mp3", seed=1)
    lib.reconcile()
    row = by_path(lib)["a.mp3"]
    music.hide("a.mp3", tmp_path / "away")
    lib.reconcile()
    assert lib.file(row["id"])["state"] == "missing"

    music.unhide("a.mp3", tmp_path / "away")
    music.move("a.mp3", "elsewhere/a.mp3")
    lib.reconcile()
    assert by_path(lib)["elsewhere/a.mp3"]["id"] == row["id"]


# ------------------------------------------------ missing, back, gone
def test_missing_and_back(lib, music, tmp_path):
    music.mp3("a.mp3", seed=1)
    music.mp3("b.mp3", seed=2)
    lib.reconcile()
    row = by_path(lib)["a.mp3"]

    music.hide("a.mp3", tmp_path / "away")
    lib.reconcile()
    assert set(by_path(lib)) == {"b.mp3"}
    missing = lib.file(row["id"])
    assert missing["state"] == "missing" and missing["state_changed_at"]
    assert missing["rev"] > row["rev"]

    music.unhide("a.mp3", tmp_path / "away")
    lib.reconcile()
    back = by_path(lib)["a.mp3"]
    assert back["id"] == row["id"] and back["rev"] > missing["rev"]
    assert counts(lib) == {"present": 2}


def test_missing_turns_gone_only_after_the_grace_time(lib, music, clock):
    music.mp3("a.mp3", seed=1)
    music.mp3("b.mp3", seed=2)
    lib.reconcile()
    row = by_path(lib)["a.mp3"]
    music.remove("a.mp3")
    lib.reconcile()

    clock.advance(23 * HOUR)
    lib.reconcile()
    assert lib.file(row["id"])["state"] == "missing"

    clock.advance(HOUR + 1)
    lib.reconcile()
    gone = lib.file(row["id"])
    assert gone["state"] == "gone" and gone["audio_id"] == row["audio_id"]
    assert counts(lib) == {"present": 1, "gone": 1}


def test_a_new_file_on_a_gone_path_is_a_new_row(lib, music, clock):
    music.mp3("a.mp3", seed=1)
    lib.reconcile()
    old = by_path(lib)["a.mp3"]
    music.remove("a.mp3")
    lib.reconcile()
    clock.advance(25 * HOUR)
    lib.reconcile()

    music.mp3("a.mp3", seed=2, age=100)
    lib.reconcile()
    assert by_path(lib)["a.mp3"]["id"] != old["id"]
    assert lib.file(old["id"])["state"] == "gone"


# ---------------------------------------------------------------- guard
def _fill(music, n):
    for i in range(n):
        music.mp3(f"t{i:03}.mp3", seed=i)


def test_the_guard_marks_nothing_when_too_many_vanish(lib, music, tmp_path):
    _fill(music, 60)
    lib.reconcile()
    away = tmp_path / "away"
    for i in range(13):  # 21.7% of 60, and more than 10
        music.hide(f"t{i:03}.mp3", away)

    lib.reconcile()
    status = lib.status()
    assert status["unavailable"] is True
    assert status["counts"] == {"present": 60}

    for i in range(13):
        music.unhide(f"t{i:03}.mp3", away)
    lib.reconcile()
    assert lib.status()["unavailable"] is False


def test_the_guard_lets_a_few_files_go(lib, music):
    _fill(music, 60)
    lib.reconcile()
    for i in range(11):  # more than 10, but 18% of 60
        music.remove(f"t{i:03}.mp3")
    lib.reconcile()
    assert lib.status()["unavailable"] is False
    assert counts(lib) == {"present": 49, "missing": 11}


def test_the_guard_needs_more_than_ten_files(lib, music):
    _fill(music, 12)
    lib.reconcile()
    for i in range(10):  # 83%, but only 10 files
        music.remove(f"t{i:03}.mp3")
    lib.reconcile()
    assert counts(lib) == {"present": 2, "missing": 10}


def test_an_unmounted_library_trips_the_guard(lib, music, tmp_path):
    _fill(music, 20)
    lib.reconcile()
    music.root.rename(tmp_path / "unmounted")
    lib.reconcile()
    assert lib.status()["unavailable"] is True
    assert counts(lib) == {"present": 20}


def test_moves_do_not_count_against_the_guard(lib, music):
    _fill(music, 30)
    lib.reconcile()
    for i in range(20):
        music.move(f"t{i:03}.mp3", f"sorted/t{i:03}.mp3")
    lib.reconcile()
    assert lib.status()["unavailable"] is False
    assert counts(lib) == {"present": 30}


# --------------------------------------------------------- settle time
def test_a_file_changed_in_the_last_ten_seconds_waits(lib, music, clock):
    music.mp3("old.mp3", seed=1, title="Old")
    music.mp3("fresh.mp3", seed=2, age=5)
    lib.reconcile()
    assert set(by_path(lib)) == {"old.mp3"}

    music.tag("old.mp3", title="Being written", age=3)
    clock.advance(1)
    lib.reconcile()
    assert by_path(lib)["old.mp3"]["title"] == "Old"  # neither reread nor missing

    clock.advance(10)
    lib.reconcile()
    items = by_path(lib)
    assert set(items) == {"old.mp3", "fresh.mp3"}
    assert items["old.mp3"]["title"] == "Being written"


# ------------------------------------------------------ the first index
def test_an_interrupted_first_index_resumes_where_it_stopped(lib, music, monkeypatch):
    from app import library
    _fill(music, 7)
    monkeypatch.setattr(library, "BATCH", 2)
    real = audiohash.audio_id
    calls = []

    def dies_on_the_fifth(path):
        calls.append(path)
        if len(calls) == 5:
            raise KeyboardInterrupt("the app was stopped")
        return real(path)

    monkeypatch.setattr(audiohash, "audio_id", dies_on_the_fifth)
    with pytest.raises(KeyboardInterrupt):
        lib.reconcile()
    assert len(by_path(lib)) == 4  # two batches were committed
    assert lib.status()["indexed"] is False

    calls.clear()
    monkeypatch.setattr(audiohash, "audio_id", lambda path: (calls.append(path), real(path))[1])
    lib.reconcile()
    assert len(calls) == 3  # only what the first run had not committed
    assert len(by_path(lib)) == 7
    assert lib.status()["indexed"] is True


def test_progress_is_reported_while_a_pass_hashes(lib, music, monkeypatch):
    _fill(music, 3)
    seen = []
    real = audiohash.audio_id

    def spy(path):
        seen.append(dict(lib.status()["indexing"]))
        return real(path)

    monkeypatch.setattr(audiohash, "audio_id", spy)
    lib.reconcile()
    assert [s["total"] for s in seen] == [3, 3, 3]
    assert [s["done"] for s in seen] == [0, 1, 2]
    assert all(s["running"] for s in seen)
    assert lib.status()["indexing"]["running"] is False


# ------------------------------------------------------------- passes
def test_passes_never_overlap(lib, music, monkeypatch):
    music.mp3("a.mp3")
    entered, release = threading.Event(), threading.Event()
    real = audiohash.audio_id

    def slow(path):
        entered.set()
        release.wait(5)
        return real(path)

    monkeypatch.setattr(audiohash, "audio_id", slow)
    first = threading.Thread(target=lib.reconcile)
    first.start()
    assert entered.wait(5)
    assert lib.reconcile() is None   # dropped, not queued
    assert lib.trigger() is False
    release.set()
    first.join(5)
    assert lib.trigger() is True
    assert lib.wait(5)
    assert set(by_path(lib)) == {"a.mp3"}


def test_a_damaged_file_is_listed_with_a_fallback_id(lib, music):
    music.fixture("broken.wav", "fallback/truncated.wav")
    music.fixture("song.ogg", "fallback/vorbis.ogg")
    lib.reconcile()
    items = by_path(lib)
    assert items["broken.wav"]["audio_id"].startswith("f1_")
    assert items["broken.wav"]["editable"] is False
    assert items["song.ogg"]["format"] == "ogg"


def test_files_with_the_same_audio_point_at_each_other(lib, music):
    music.mp3("a.mp3", seed=9, title="One")
    music.mp3("copy/a.mp3", seed=9, title="Other tags")
    music.mp3("b.mp3", seed=1)
    lib.reconcile()
    items = by_path(lib)
    assert items["a.mp3"]["same_audio"] == [items["copy/a.mp3"]["id"]]
    assert items["copy/a.mp3"]["same_audio"] == [items["a.mp3"]["id"]]
    assert items["b.mp3"]["same_audio"] == []


# ----------------------------------------------------------- downloads
def test_a_download_is_indexed_without_a_walk(lib, music, monkeypatch):
    path = music.mp3("New - Track.mp3", title="Track", age=0)
    walks = []
    monkeypatch.setattr(lib, "reconcile", lambda: walks.append(1))
    lib.add_file(path, source_url="https://example.test/v")
    item = by_path(lib)["New - Track.mp3"]
    assert item["added_at"]
    assert item["title"] == "Track" and walks == []
    assert lib.file(item["id"])["source_url"] == "https://example.test/v"
    assert lib.status()["rev"] == item["rev"] == 1


def test_the_first_index_dates_files_by_their_own_time(lib, music, clock):
    # An existing library is indexed in one go: "added" has to mean something,
    # so files found by the first pass are dated by their modification time.
    music.mp3("z-old.mp3", seed=1, age=400 * 86400)
    music.mp3("a-recent.mp3", seed=2, age=3 * 86400)
    lib.reconcile()

    first = [item["path"] for item in lib.list(sort="added", order="desc")["items"]]
    assert first == ["a-recent.mp3", "z-old.mp3"]

    # A file that shows up later is dated by when it was first seen, even if its
    # own time is old (a sync client keeps the original modification time).
    clock.advance(3600)
    music.mp3("synced-later.mp3", seed=3, age=900 * 86400)
    lib.reconcile()

    later = [item["path"] for item in lib.list(sort="added", order="desc")["items"]]
    assert later == ["synced-later.mp3", "a-recent.mp3", "z-old.mp3"]
