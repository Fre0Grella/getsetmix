"""Batch editing, slice 8: cancel, restart and injected failures
(docs/design/batch-editing.md 4.4 and 5)."""
import errno
import os
import stat
import sys
import threading

import pytest
from mutagen.id3 import ID3
from test_edits import apply, ed, ids, preview, states  # noqa: F401 (ed is a fixture)

from app import edits, library, tagger


@pytest.fixture()
def shelf(lib, music):
    for n in range(6):
        music.mp3(f"{n}.mp3", seed=n + 1, title=f"T{n}", artist="Nova", genre="House")
    lib.reconcile()
    return ids(lib)


def genre(music, name):
    return ID3(music.path(name))["TCON"].text[0]


def everything(shelf):
    return [shelf[f"{n}.mp3"] for n in range(6)]


def journal_matches_disk(ed, music, eid):  # noqa: F811
    """Every applied change is in its file and every other one is not."""
    for c in ed.changes(eid)["items"]:
        held = genre(music, c["path"])
        assert held == (c["new"] if c["state"] == "applied" else c["old"]), c
        assert not list(music.root.glob(".*.part")), "a hidden copy was left behind"


def held_by(monkeypatch, lib, when):
    """write_tags that runs `when(n)` before the n-th file (counted from 1)."""
    real, calls = lib.write_tags, []

    def write(fid, changes, expect=None, **kw):
        calls.append(fid)
        when(len(calls))
        return real(fid, changes, expect, **kw)

    monkeypatch.setattr(lib, "write_tags", write)
    return calls


# ------------------------------------------------------------------ cancel
def test_cancel_stops_after_the_file_in_hand_and_apply_carries_on(ed, lib, music, shelf, monkeypatch):  # noqa: F811
    third, go = threading.Event(), threading.Event()

    def hold(n):
        if n == 3:
            third.set()
            go.wait(10)

    held_by(monkeypatch, lib, hold)
    out = preview(ed, everything(shelf), [{"op": "set", "field": "genre", "value": "Techno"}])
    ed.apply(out["id"])
    assert third.wait(10)
    assert ed.cancel(out["id"])["state"] == "applying"
    go.set()
    assert ed.wait(10)

    done = ed.get(out["id"])
    assert done["state"] == "cancelled"
    assert done["progress"]["files_done"] == 3       # the file in hand was finished
    journal_matches_disk(ed, music, out["id"])
    with pytest.raises(library.LibraryError) as err:
        ed.cancel(out["id"])
    assert err.value.status == 409

    apply(ed, out["id"])   # carry on: only the rest is written
    assert ed.get(out["id"])["state"] == "applied"
    assert {genre(music, f"{n}.mp3") for n in range(6)} == {"Techno"}


def test_a_cancelled_edit_can_be_undone(ed, lib, music, shelf, monkeypatch):  # noqa: F811
    second, go = threading.Event(), threading.Event()

    def hold(n):
        if n == 2:
            second.set()
            go.wait(10)

    held_by(monkeypatch, lib, hold)
    out = preview(ed, everything(shelf), [{"op": "set", "field": "genre", "value": "Techno"}])
    ed.apply(out["id"])
    assert second.wait(10)
    ed.cancel(out["id"])
    go.set()
    assert ed.wait(10)
    back = ed.undo(out["id"])
    assert ed.wait(10)
    assert ed.get(back["id"])["progress"]["files_done"] == 2
    assert {genre(music, f"{n}.mp3") for n in range(6)} == {"House"}
    assert set(states(ed, out["id"]).values()) == {"undone", "excluded"}


# ------------------------------------------------------- a kill, a restart
def test_a_kill_in_the_middle_leaves_whole_files_and_a_true_journal(ed, lib, music, shelf, monkeypatch):  # noqa: F811
    def kill(n):
        if n == 4:
            raise KeyboardInterrupt   # not an error a file can have: the job dies

    held_by(monkeypatch, lib, kill)
    out = preview(ed, everything(shelf), [{"op": "set", "field": "genre", "value": "Techno"}])
    ed.apply(out["id"])
    assert ed.wait(10)
    assert ed.get(out["id"])["state"] == "interrupted"
    journal_matches_disk(ed, music, out["id"])
    assert sorted(states(ed, out["id"]).values()).count("applied") == 3

    monkeypatch.undo()
    fresh = edits.Edits(lib.db, lib)   # the app started again
    fresh.recover()
    apply(fresh, out["id"])
    assert {genre(music, f"{n}.mp3") for n in range(6)} == {"Techno"}


# --------------------------------------------------------- injected failures
def test_a_tagger_that_raises_on_the_nth_file_fails_that_file_only(ed, music, shelf, monkeypatch):  # noqa: F811
    real, calls = tagger.edit_file, []

    def edit_file(path, changes, cover=tagger.KEEP):
        calls.append(path)
        if len(calls) == 3:
            raise RuntimeError("the tagger broke")
        return real(path, changes, cover=cover)

    monkeypatch.setattr(tagger, "edit_file", edit_file)
    out = preview(ed, everything(shelf), [{"op": "set", "field": "genre", "value": "Techno"}])
    apply(ed, out["id"])
    done = ed.get(out["id"])
    assert done["state"] == "applied"
    assert done["progress"] == {"files_total": 6, "files_done": 5, "files_failed": 1, "files_conflict": 0}
    [failed] = ed.changes(out["id"], state="failed")["items"]
    assert failed["path"] == "2.mp3" and failed["error"] == "write error: the tagger broke"
    journal_matches_disk(ed, music, out["id"])
    monkeypatch.undo()
    calls.clear()
    apply(ed, out["id"])
    assert genre(music, "2.mp3") == "Techno"


def test_a_full_disk_at_the_copy_fails_that_file_and_leaves_no_copy(ed, music, shelf, monkeypatch):  # noqa: F811
    real = tagger.shutil.copy2

    def copy(src, dst, *a, **kw):
        if str(src).endswith("4.mp3"):
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(src, dst, *a, **kw)

    monkeypatch.setattr(tagger.shutil, "copy2", copy)
    out = preview(ed, everything(shelf), [{"op": "set", "field": "genre", "value": "Techno"}])
    before = music.path("4.mp3").read_bytes()
    apply(ed, out["id"])
    [failed] = ed.changes(out["id"], state="failed")["items"]
    assert failed["path"] == "4.mp3" and failed["error"].startswith("no space: ")
    assert music.path("4.mp3").read_bytes() == before
    assert ed.get(out["id"])["progress"]["files_done"] == 5
    journal_matches_disk(ed, music, out["id"])


def test_a_file_removed_after_the_preview_fails_as_gone(ed, music, shelf):  # noqa: F811
    out = preview(ed, everything(shelf), [{"op": "set", "field": "genre", "value": "Techno"}])
    music.remove("1.mp3")
    apply(ed, out["id"])
    [failed] = ed.changes(out["id"], state="failed")["items"]
    assert failed["path"] == "1.mp3" and failed["error"].startswith("gone: ")
    assert ed.get(out["id"])["progress"]["files_done"] == 5


def test_a_file_marked_read_only_fails_with_that_reason(ed, music, shelf):  # noqa: F811
    path = music.path("5.mp3")
    os.chmod(path, stat.S_IREAD)
    before = path.read_bytes()
    try:
        out = preview(ed, everything(shelf), [{"op": "set", "field": "genre", "value": "Techno"}])
        apply(ed, out["id"])
        [failed] = ed.changes(out["id"], state="failed")["items"]
        assert failed["path"] == "5.mp3"
        assert failed["error"] == "read-only: the file is marked read-only on disk"
        assert ed.get(out["id"])["progress"]["files_done"] == 5
        assert path.read_bytes() == before and not list(music.root.glob(".*.part"))
    finally:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows refuses to replace an open file")
def test_on_windows_a_file_open_in_another_program_fails_as_in_use(ed, music, shelf):  # noqa: F811
    out = preview(ed, everything(shelf), [{"op": "set", "field": "genre", "value": "Techno"}])
    before = music.path("3.mp3").read_bytes()
    with open(music.path("3.mp3"), "rb"):   # as a deck in Rekordbox holds it
        apply(ed, out["id"])
    [failed] = ed.changes(out["id"], state="failed")["items"]
    assert failed["path"] == "3.mp3" and failed["error"].startswith("in use: ")
    assert music.path("3.mp3").read_bytes() == before
    assert ed.get(out["id"])["progress"]["files_done"] == 5
    apply(ed, out["id"])   # unloaded: applying again writes it
    assert genre(music, "3.mp3") == "Techno"


def test_cancel_over_http(tmp_path, monkeypatch, music):
    from test_library_api import _client, rescan
    music.mp3("a.mp3", seed=1, title="A")
    with _client(tmp_path, monkeypatch) as api:
        rescan(api)
        assert api.post("/api/library/edits/999/cancel").status_code == 404
        fid = api.get("/api/library").json()["items"][0]["id"]
        made = api.post("/api/library/edits", json={
            "selection": {"ids": [fid]}, "steps": [{"op": "set", "field": "genre", "value": "x"}]}).json()
        assert api.post(f"/api/library/edits/{made['id']}/cancel").status_code == 409
