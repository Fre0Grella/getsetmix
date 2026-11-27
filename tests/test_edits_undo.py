"""Batch editing, slice 3: undo, the history and retention (app/edits.py;
docs/design/batch-editing.md 4.7)."""
import pytest
from mutagen.id3 import ID3
from test_edits import apply, ids, preview, states
from test_library_edit import _flac, _id3, rich_flac, rich_mp3  # noqa: F401 (fixtures)

from app import edits, library

DAY = 24 * 3600
TWO_FIELDS = [{"op": "set", "field": "genre", "value": "Tech House"},
              {"op": "set", "field": "album", "value": "Late Nights"}]


@pytest.fixture()
def days():
    return {"n": 30}


@pytest.fixture()
def ed(lib, clock, days):
    return edits.Edits(lib.db, lib, clock=clock, history_days=lambda: days["n"])


@pytest.fixture()
def shelf(lib, music, rich_mp3, rich_flac):  # noqa: F811
    music.mp3("plain.mp3", seed=7, title="Plain", artist="Nova", genre="House")
    lib.reconcile()
    return ids(lib)


def applied(ed, fids, steps=TWO_FIELDS):
    out = preview(ed, fids, steps)
    apply(ed, out["id"])
    return out["id"]


def undo(ed, eid, files=None):
    out = ed.undo(eid, files)
    assert ed.wait(10)
    return ed.get(out["id"])


def genre(music, name):
    return ID3(music.path(name))["TCON"].text[0]


def test_a_full_undo_puts_every_tag_back(ed, music, shelf, rich_mp3, rich_flac):  # noqa: F811
    before = (_id3(rich_mp3), _flac(rich_flac), _id3(music.path("plain.mp3")))
    eid = applied(ed, [shelf["Night Drive.mp3"], shelf["Night Drive.flac"], shelf["plain.mp3"]])
    assert genre(music, "plain.mp3") == "Tech House"

    back = undo(ed, eid)

    assert back["undo_of"] == eid and back["state"] == "applied"
    assert back["label"] == "undo: genre = Tech House; album = Late Nights"
    assert set(states(ed, back["id"]).values()) == {"applied"}
    assert (_id3(rich_mp3), _flac(rich_flac), _id3(music.path("plain.mp3"))) == before
    original = ed.get(eid)
    assert set(states(ed, eid).values()) == {"undone"}
    assert original["undone"] == "all" and original["undoable"] is False


def test_a_partial_undo_reverts_only_the_tracks_asked_for(ed, music, shelf):
    eid = applied(ed, [shelf["Night Drive.mp3"], shelf["plain.mp3"]])
    undo(ed, eid, [shelf["plain.mp3"]])
    assert genre(music, "plain.mp3") == "House"
    assert genre(music, "Night Drive.mp3") == "Tech House"
    line = ed.get(eid)
    assert line["undone"] == "some" and line["undoable"] is True
    assert states(ed, eid) == {("Night Drive.mp3", "genre"): "applied",
                               ("Night Drive.mp3", "album"): "applied",
                               ("plain.mp3", "genre"): "undone", ("plain.mp3", "album"): "undone"}
    # the rest can still be undone later
    undo(ed, eid)
    assert genre(music, "Night Drive.mp3") == "House"
    assert ed.get(eid)["undone"] == "all"


def test_undo_never_overwrites_a_field_changed_since_and_reports_a_trashed_track_gone(
        ed, lib, music, shelf):
    eid = applied(ed, [shelf["Night Drive.mp3"], shelf["plain.mp3"]],
                  [{"op": "set", "field": "genre", "value": "Tech House"}])
    lib.write_tags(shelf["plain.mp3"], {"genre": "Disco"})   # newer work, by hand
    lib.trash(shelf["Night Drive.mp3"])

    back = undo(ed, eid)

    by = {c["path"]: c for c in ed.changes(back["id"])["items"]}
    assert by["plain.mp3"]["state"] == "conflict"
    assert genre(music, "plain.mp3") == "Disco"
    assert by["Night Drive.mp3"]["state"] == "failed"
    assert by["Night Drive.mp3"]["error"].startswith("gone: ")
    # restored, the trashed track can be undone by applying the undo again
    lib.restore(shelf["Night Drive.mp3"])
    apply(ed, back["id"])
    assert genre(music, "Night Drive.mp3") == "House"
    assert states(ed, eid)[("Night Drive.mp3", "genre")] == "undone"


def test_an_undo_can_be_undone(ed, music, shelf):
    eid = applied(ed, [shelf["plain.mp3"]], [{"op": "set", "field": "genre", "value": "Tech House"}])
    first = undo(ed, eid)
    assert genre(music, "plain.mp3") == "House"
    again = undo(ed, first["id"])
    assert again["undo_of"] == first["id"]
    assert genre(music, "plain.mp3") == "Tech House"
    # the original edit holds again, so it can be undone once more
    assert ed.get(eid)["undoable"] is True and ed.get(eid)["undone"] is None
    assert ed.get(first["id"])["undone"] == "all"


def test_undo_of_an_interrupted_edit_drops_what_was_pending(ed, music, shelf):
    out = preview(ed, [shelf["plain.mp3"], shelf["Night Drive.mp3"]],
                  [{"op": "set", "field": "genre", "value": "Tech House"}])
    apply(ed, out["id"])
    with ed.db.transaction() as conn:  # as if it had stopped after the first file
        conn.execute("UPDATE edits SET state = 'interrupted' WHERE id = ?", (out["id"],))
        conn.execute("UPDATE edit_changes SET state = 'pending' WHERE edit_id = ? AND file_id = ?",
                     (out["id"], shelf["Night Drive.mp3"]))
    undo(ed, out["id"])
    assert states(ed, out["id"]) == {("plain.mp3", "genre"): "undone",
                                     ("Night Drive.mp3", "genre"): "excluded"}
    assert genre(music, "plain.mp3") == "House"


def test_what_cannot_be_undone(ed, shelf):
    eid = applied(ed, [shelf["plain.mp3"]])
    never = preview(ed, [shelf["plain.mp3"]])
    for target, files, status in ((9999, None, 404), (never["id"], None, 409),
                                  (eid, [shelf["Night Drive.mp3"]], 409), (eid, "x", 400)):
        with pytest.raises(library.LibraryError) as err:
            ed.undo(target, files)
        assert err.value.status == status, (target, files)


def test_the_history_lists_applied_edits_newest_first(ed, shelf):
    first = applied(ed, [shelf["plain.mp3"]])
    preview(ed, [shelf["plain.mp3"]])   # never applied: not history
    second = applied(ed, [shelf["Night Drive.mp3"]])
    third = undo(ed, second)["id"]

    page = ed.history(limit=2)
    assert [i["id"] for i in page["items"]] == [third, second]
    rest = ed.history(limit=2, cursor=page["next"])
    assert [i["id"] for i in rest["items"]] == [first] and rest["next"] is None
    assert page["items"][1]["undone"] == "all"


def test_unused_previews_go_after_a_day_and_old_journals_after_the_setting(ed, clock, shelf, days):
    old = applied(ed, [shelf["plain.mp3"]])
    unused = preview(ed, [shelf["plain.mp3"]])["id"]
    clock.advance(DAY + 1)
    assert ed.purge() == {"previews": 1, "journals": 0}
    assert ed.get(unused) is None
    counts = ed.get(old)["counts"]

    clock.advance(30 * DAY)
    assert ed.purge() == {"previews": 0, "journals": 1}
    line = ed.get(old)
    assert line["purged"] is True and line["undoable"] is False
    assert line["counts"] == counts               # the line keeps its numbers
    assert ed.changes(old)["items"] == []
    assert [i["id"] for i in ed.history()["items"]] == [old]
    with pytest.raises(library.LibraryError) as err:
        ed.undo(old)
    assert err.value.status == 410


def test_edit_history_days_0_keeps_journals_for_good(ed, clock, shelf, days):
    days["n"] = 0
    eid = applied(ed, [shelf["plain.mp3"]])
    clock.advance(3650 * DAY)
    assert ed.purge()["journals"] == 0
    assert ed.get(eid)["undoable"] is True


def test_the_purge_runs_once_a_day(ed, clock, monkeypatch):
    runs = []
    monkeypatch.setattr(ed, "purge", lambda: runs.append(1) or {})
    assert ed.purge_due() is True and ed.purge_due() is False
    clock.advance(DAY)
    assert ed.purge_due() is True and len(runs) == 2


# ------------------------------------------------------------------ HTTP
def test_undo_and_history_over_http(tmp_path, monkeypatch, music):
    from test_library_api import _client, rescan
    music.mp3("a.mp3", seed=1, title="A", genre="House")
    with _client(tmp_path, monkeypatch) as api:
        rescan(api)
        fid = api.get("/api/library").json()["items"][0]["id"]
        made = api.post("/api/library/edits", json={
            "selection": {"ids": [fid]},
            "steps": [{"op": "set", "field": "genre", "value": "Techno"}]}).json()
        api.post(f"/api/library/edits/{made['id']}/apply")
        assert edits.current().wait(10)

        r = api.post(f"/api/library/edits/{made['id']}/undo")
        assert r.status_code == 202 and r.json()["undo_of"] == made["id"]
        assert edits.current().wait(10)
        assert ID3(music.path("a.mp3"))["TCON"].text == ["House"]
        history = api.get("/api/library/edits").json()["items"]
        assert [i["id"] for i in history] == [r.json()["id"], made["id"]]
        assert history[1]["undone"] == "all"
        assert api.post(f"/api/library/edits/{made['id']}/undo",
                        json={"files": "x"}).status_code == 400
        assert api.get("/api/library/edits", params={"limit": 0}).status_code == 400
