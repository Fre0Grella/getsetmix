"""Batch editing, slice 2: one field operation, previewed, stored and applied
(app/edits.py; docs/design/batch-editing.md 4.3 and 4.4)."""
import threading

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from test_library_edit import _flac, _id3, rich_flac, rich_mp3  # noqa: F401 (fixtures)

from app import audiohash, edits, library


@pytest.fixture()
def ed(lib, clock):
    return edits.Edits(lib.db, lib, clock=clock)


def ids(lib):
    return {i["path"]: i["id"] for i in lib.list(limit=500)["items"]}


def set_genre(value="Tech House"):
    return [{"op": "set", "field": "genre", "value": value}]


def preview(ed, fids, steps=None):
    return ed.preview({"selection": {"ids": fids}, "steps": steps or set_genre()})


def apply(ed, eid):
    out = ed.apply(eid)
    assert ed.wait(10)
    return out


def states(ed, eid):
    return {(c["path"], c["field"]): c["state"] for c in ed.changes(eid)["items"]}


@pytest.fixture()
def shelf(lib, music, rich_mp3, rich_flac):  # noqa: F811
    music.mp3("plain.mp3", seed=7, title="Plain", artist="Nova", genre="House")
    music.wav("take.wav")
    music.fixture("broken.mp3", "fallback/no-frames.mp3")
    lib.reconcile()
    return ids(lib)


# -------------------------------------------------------------- preview
def test_a_preview_stores_the_changes_and_writes_nothing(ed, lib, music, shelf):
    before = {p: music.path(p).read_bytes() for p in shelf}
    rev = lib.rev()
    out = preview(ed, [shelf["Night Drive.mp3"], shelf["plain.mp3"], shelf["Night Drive.flac"]])

    assert out["state"] == "preview" and out["library_rev"] == rev
    assert out["counts"]["selected"] == 3 and out["counts"]["changed"] == 3
    assert out["counts"]["changes"] == 3 and out["counts"]["by_field"] == {"genre": 3}
    assert out["label"] == "genre = Tech House"
    assert {p: music.path(p).read_bytes() for p in shelf} == before
    assert lib.rev() == rev
    items = ed.changes(out["id"])["items"]
    assert [(c["path"], c["old"], c["new"], c["state"]) for c in items] == [
        ("Night Drive.mp3", "House", "Tech House", "pending"),
        ("plain.mp3", "House", "Tech House", "pending"),
        ("Night Drive.flac", lib.file(shelf["Night Drive.flac"])["genre"], "Tech House", "pending"),
    ]
    assert items[0]["by"] == [{"step": 0, "op": "set"}] and items[0]["warnings"] == []


def test_unchanged_and_skipped_tracks_are_counted_with_their_reasons(ed, lib, music, shelf):
    trashed = shelf["plain.mp3"]
    lib.trash(trashed)
    out = preview(ed, [shelf["Night Drive.mp3"], shelf["take.wav"], shelf["broken.mp3"],
                       trashed, 9999], set_genre("House"))
    c = out["counts"]
    assert (c["selected"], c["changed"], c["unchanged"], c["skipped"]) == (5, 0, 1, 4)
    assert c["skipped_by_reason"] == {"read-only format": 1, "damaged file": 1,
                                      "in the trash": 1, "no such track": 1}
    assert ed.changes(out["id"])["items"] == []


def test_a_change_that_would_empty_the_title_or_is_too_long_is_blocked(ed, shelf):
    fid = shelf["plain.mp3"]
    empty = preview(ed, [fid], [{"op": "set", "field": "title", "value": "  "}])
    [change] = ed.changes(empty["id"])["items"]
    assert change["state"] == "blocked" and change["warnings"] == ["would_empty"]
    long = preview(ed, [fid], [{"op": "set", "field": "album", "value": "x" * 256}])
    [change] = ed.changes(long["id"])["items"]
    assert change["state"] == "blocked" and change["warnings"] == ["too_long"]
    with pytest.raises(library.LibraryError) as err:
        ed.apply(long["id"])   # nothing pending: nothing to write
    assert err.value.status == 409


def test_editing_a_field_with_several_values_warns_and_stays_pending(ed, shelf):
    out = preview(ed, [shelf["Night Drive.mp3"]],
                  [{"op": "set", "field": "artist", "value": "Some Artist"}])
    [change] = ed.changes(out["id"])["items"]
    assert change["warnings"] == ["merges_values"] and change["state"] == "pending"
    assert ed.get(out["id"])["counts"]["warnings"] == 1


@pytest.mark.parametrize("body", [
    None, [], {"selection": {"ids": [1]}},
    {"selection": {"ids": [1]}, "steps": []},
    {"selection": {"filter": {"bpm": "124"}}, "steps": set_genre()},
    {"selection": {"filter": {"q": 3}}, "steps": set_genre()},
    {"selection": {"ids": []}, "steps": set_genre()},
    {"selection": {"ids": ["1"]}, "steps": set_genre()},
    {"selection": {"ids": [1]}, "steps": [{"op": "set", "field": "cover", "value": "x"}]},
    {"selection": {"ids": [1]}, "steps": [{"op": "set", "field": "year", "value": 99}]},
    {"selection": {"ids": [1]}, "steps": [{"op": "set", "field": "genre", "value": None}]},
    {"selection": {"ids": [1]}, "steps": [{"op": "shout", "field": "genre", "value": "x"}]},
    {"selection": {"ids": [1]}, "steps": [{"rule": "nope"}]},
])
def test_a_request_that_is_not_valid_is_400_and_stores_nothing(ed, shelf, body):
    with pytest.raises(library.LibraryError) as err:
        ed.preview(body)
    assert err.value.status == 400
    with ed.db.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM edits").fetchone()[0] == 0


def test_more_tracks_than_the_limit_is_413(ed, shelf, monkeypatch):
    monkeypatch.setattr(library, "MAX_SELECTION", 2)
    with pytest.raises(library.LibraryError) as err:
        preview(ed, [1, 2, 3])
    assert err.value.status == 413


# ---------------------------------------------------------------- apply
def test_apply_writes_exactly_the_stored_change_into_an_mp3_and_a_flac(ed, lib, shelf,
                                                                     rich_mp3, rich_flac):  # noqa: F811
    mp3_before, (flac_tags, flac_pics) = _id3(rich_mp3), _flac(rich_flac)
    aids = (audiohash.audio_id(rich_mp3), audiohash.audio_id(rich_flac))
    out = preview(ed, [shelf["Night Drive.mp3"], shelf["Night Drive.flac"]])
    rev = lib.rev()

    started = apply(ed, out["id"])
    assert started["state"] == "applying"

    done = ed.get(out["id"])
    assert done["state"] == "applied" and done["finished_at"]
    assert done["progress"] == {"files_total": 2, "files_done": 2, "files_failed": 0,
                                "files_conflict": 0}
    assert set(states(ed, out["id"]).values()) == {"applied"}
    assert lib.rev() == rev + 2    # one write per file
    # the new value is in each file, and nothing else changed
    mp3_after = _id3(rich_mp3)
    assert ID3(rich_mp3)["TCON"].text == ["Tech House"]
    assert {k for k in mp3_before.keys() | mp3_after.keys()
            if mp3_before.get(k) != mp3_after.get(k)} == {"TCON"}
    tags, pics = _flac(rich_flac)
    assert FLAC(rich_flac)["genre"] == ["Tech House"]
    assert {k: v for k, v in tags.items() if k != "genre"} == \
        {k: v for k, v in flac_tags.items() if k != "genre"}
    assert pics == flac_pics
    assert (audiohash.audio_id(rich_mp3), audiohash.audio_id(rich_flac)) == aids
    assert lib.file(shelf["Night Drive.mp3"])["genre"] == "Tech House"   # the index too


def test_a_file_changed_after_the_preview_is_a_conflict_and_is_not_written(ed, lib, music, shelf):
    out = preview(ed, [shelf["plain.mp3"], shelf["Night Drive.mp3"]])
    lib.write_tags(shelf["plain.mp3"], {"genre": "Disco"})    # someone else, meanwhile
    changed = music.path("plain.mp3").read_bytes()

    apply(ed, out["id"])

    assert states(ed, out["id"]) == {("plain.mp3", "genre"): "conflict",
                                     ("Night Drive.mp3", "genre"): "applied"}
    [c] = ed.changes(out["id"], state="conflict")["items"]
    assert c["error"] == "the file changed: genre"
    assert music.path("plain.mp3").read_bytes() == changed
    assert ed.get(out["id"])["progress"]["files_conflict"] == 1
    with pytest.raises(library.LibraryError) as err:
        ed.apply(out["id"])   # a conflict is not retried
    assert err.value.status == 409


def test_one_failing_file_does_not_stop_the_others_and_apply_again_retries_only_it(
        ed, lib, music, shelf, monkeypatch):
    fails, calls = {shelf["plain.mp3"]}, []
    real = lib.write_tags

    def flaky(fid, changes, expect=None):
        calls.append(fid)
        if fid in fails:
            raise library.LibraryError(423, "the file is in use by another program")
        return real(fid, changes, expect)

    monkeypatch.setattr(lib, "write_tags", flaky)
    fids = [shelf["Night Drive.mp3"], shelf["plain.mp3"], shelf["Night Drive.flac"]]
    out = preview(ed, fids)
    apply(ed, out["id"])

    assert calls == fids
    done = ed.get(out["id"])
    assert done["state"] == "applied"
    assert done["progress"]["files_failed"] == 1 and done["progress"]["files_done"] == 2
    [failed] = ed.changes(out["id"], state="failed")["items"]
    assert failed["path"] == "plain.mp3" and failed["error"].startswith("in use: ")
    assert ID3(music.path("plain.mp3"))["TCON"].text == ["House"]

    fails.clear()
    calls.clear()
    apply(ed, out["id"])
    assert calls == [shelf["plain.mp3"]]
    assert set(states(ed, out["id"]).values()) == {"applied"}
    assert ID3(music.path("plain.mp3"))["TCON"].text == ["Tech House"]


def test_a_full_disk_fails_that_file_as_no_space(ed, lib, shelf, monkeypatch):
    import errno

    def full(fid, changes, expect=None):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(lib, "write_tags", full)
    out = preview(ed, [shelf["plain.mp3"]])
    apply(ed, out["id"])
    [c] = ed.changes(out["id"])["items"]
    assert c["state"] == "failed" and c["error"].startswith("no space: ")


def test_a_second_apply_while_one_runs_is_409(ed, lib, shelf, monkeypatch):
    go = threading.Event()
    real = lib.write_tags

    def slow(fid, changes, expect=None):
        go.wait(10)
        return real(fid, changes, expect)

    monkeypatch.setattr(lib, "write_tags", slow)
    first = preview(ed, [shelf["plain.mp3"]])
    second = preview(ed, [shelf["Night Drive.mp3"]])
    ed.apply(first["id"])
    try:
        for eid in (first["id"], second["id"]):
            with pytest.raises(library.LibraryError) as err:
                ed.apply(eid)
            assert err.value.status == 409
        # a preview can still be made meanwhile
        assert preview(ed, [shelf["Night Drive.flac"]])["state"] == "preview"
    finally:
        go.set()
    assert ed.wait(10)
    assert ed.get(first["id"])["state"] == "applied"


def test_a_preview_expires_after_24_hours(ed, clock, shelf):
    out = preview(ed, [shelf["plain.mp3"]])
    clock.advance(24 * 3600 + 1)
    with pytest.raises(library.LibraryError) as err:
        ed.apply(out["id"])
    assert err.value.status == 410
    assert ed.get(out["id"])["state"] == "expired"
    with pytest.raises(library.LibraryError) as err:
        ed.apply(out["id"])
    assert err.value.status == 410


def test_a_preview_older_than_another_applied_edit_expires(ed, clock, shelf):
    older = preview(ed, [shelf["plain.mp3"]])
    clock.advance(5)
    newer = preview(ed, [shelf["Night Drive.mp3"]])
    clock.advance(5)
    apply(ed, newer["id"])
    with pytest.raises(library.LibraryError) as err:
        ed.apply(older["id"])
    assert err.value.status == 410


def test_an_apply_cut_short_is_interrupted_and_carries_on(ed, lib, music, shelf):
    out = preview(ed, [shelf["plain.mp3"]])
    with ed.db.transaction() as conn:   # as if the app stopped in the middle
        conn.execute("UPDATE edits SET state = 'applying' WHERE id = ?", (out["id"],))
    fresh = edits.Edits(lib.db, lib)
    assert fresh.recover() == 1
    assert fresh.get(out["id"])["state"] == "interrupted"
    apply(fresh, out["id"])
    assert fresh.get(out["id"])["state"] == "applied"
    assert ID3(music.path("plain.mp3"))["TCON"].text == ["Tech House"]


def test_unknown_edits_are_404(ed):
    assert ed.get(9999) is None
    for call in (lambda: ed.apply(9999), lambda: ed.changes(9999)):
        with pytest.raises(library.LibraryError) as err:
            call()
        assert err.value.status == 404


# -------------------------------------------------------------- changes
def test_changes_are_paged_and_filtered(ed, shelf):
    fids = [shelf["Night Drive.mp3"], shelf["plain.mp3"], shelf["Night Drive.flac"]]
    out = preview(ed, fids, [{"op": "set", "field": "genre", "value": "Tech House"},
                             {"op": "set", "field": "album", "value": "Night"}])
    first = ed.changes(out["id"], limit=4)
    rest = ed.changes(out["id"], limit=4, cursor=first["next"])
    assert len(first["items"]) == 4 and rest["next"] is None
    every = first["items"] + rest["items"]
    assert [c["file_id"] for c in every] == sorted([c["file_id"] for c in every],
                                                   key=fids.index)  # a track's changes together
    assert {c["field"] for c in ed.changes(out["id"], field="album")["items"]} == {"album"}
    for bad in ({"field": "bpm"}, {"state": "done"}, {"warning": "loud"}, {"limit": 0},
                {"cursor": "nope"}):
        with pytest.raises(library.LibraryError) as err:
            ed.changes(out["id"], **bad)
        assert err.value.status == 400
