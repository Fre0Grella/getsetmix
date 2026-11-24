"""Delete, restore and purge (docs/design/library.md, 4.4), in the index and over HTTP."""
import pytest
from conftest import fresh_modules
from fastapi.testclient import TestClient

DAY = 24 * 3600


def row(lib, path):
    with lib.db.transaction() as conn:
        found = conn.execute("SELECT * FROM library_files WHERE path = ? ORDER BY id DESC",
                             (path,)).fetchone()
    return dict(found) if found else None


def trash_folders(music):
    trash = music.root / ".trash"
    return sorted(p.name for p in trash.iterdir()) if trash.exists() else []


@pytest.fixture()
def shelf(lib, music):
    music.mp3("a.mp3", seed=1, title="A")
    music.mp3("House/deep/b.mp3", seed=2, title="B")
    music.mp3("c.mp3", seed=3, title="C")
    lib.reconcile()
    return lib


# ------------------------------------------------------------------ delete
def test_delete_moves_the_file_into_the_trash(shelf, music, clock):
    lib = shelf
    before = row(lib, "House/deep/b.mp3")
    rev = lib.status()["rev"]
    out = lib.trash(before["id"])

    assert out == {"id": before["id"], "state": "trashed", "rev": rev + 1}
    after = row(lib, "House/deep/b.mp3")
    assert after["state"] == "trashed" and after["rev"] == rev + 1
    assert after["path"] == "House/deep/b.mp3"  # the tombstone keeps its path
    assert after["trash_path"].startswith(".trash/") and after["trash_path"].endswith(
        f"-{before['id']}/House/deep/b.mp3")
    assert not music.path("House/deep/b.mp3").exists()
    assert music.path(after["trash_path"]).read_bytes()  # the bytes are all there
    assert music.path(after["trash_path"]).stat().st_size == before["size"]


def test_a_trashed_file_leaves_the_list_and_the_link(shelf, music):
    lib = shelf
    fid = row(lib, "a.mp3")["id"]
    aid = row(lib, "a.mp3")["audio_id"]
    lib.trash(fid)
    lib.reconcile()  # the trash is not walked: nothing new, nothing missing

    assert sorted(i["path"] for i in lib.list()["items"]) == ["House/deep/b.mp3", "c.mp3"]
    assert [i["id"] for i in lib.list(state="trashed")["items"]] == [fid]
    assert lib.status()["counts"] == {"present": 2, "trashed": 1}

    body = lib.link_listing()
    assert "a.mp3" not in [f["path"] for f in body["files"]]
    [gone] = body["removed"]
    assert gone["id"] == aid and gone["path"] == "a.mp3" and gone["reason"] == "deleted"
    from app import link
    assert link.resolve(music.root, "a.mp3") is None
    assert link.resolve(music.root, row(lib, "a.mp3")["trash_path"]) is None


def test_delete_refuses_what_it_cannot_delete(shelf, music):
    from app.library import LibraryError
    lib = shelf
    fid = row(lib, "a.mp3")["id"]
    with pytest.raises(LibraryError) as e:
        lib.trash(9999)
    assert e.value.status == 404
    lib.trash(fid)
    with pytest.raises(LibraryError) as e:
        lib.trash(fid)
    assert e.value.status == 410
    music.remove("c.mp3")
    lib.reconcile()
    with pytest.raises(LibraryError) as e:
        lib.trash(row(lib, "c.mp3")["id"])  # missing: nothing to move
    assert e.value.status == 409


# ----------------------------------------------------------------- restore
def test_restore_brings_it_back_as_it_was(shelf, music):
    lib = shelf
    before = row(lib, "House/deep/b.mp3")
    listed = {f["path"]: f for f in lib.link_listing()["files"]}["House/deep/b.mp3"]
    lib.trash(before["id"])
    out = lib.restore(before["id"])

    after = row(lib, "House/deep/b.mp3")
    assert out == {"id": before["id"], "state": "present", "rev": after["rev"]}
    assert after["state"] == "present" and after["trash_path"] is None
    assert after["rev"] > before["rev"] and after["content_rev"] == before["content_rev"]
    assert music.path("House/deep/b.mp3").stat().st_mtime_ns == before["mtime_ns"]
    assert trash_folders(music) == []  # the empty trash folder is tidied away
    lib.reconcile()
    assert row(lib, "House/deep/b.mp3")["rev"] == after["rev"]  # nothing to reconcile
    body = lib.link_listing()
    again = {f["path"]: f for f in body["files"]}["House/deep/b.mp3"]
    assert again == listed and body["removed"] == []  # not downloaded again


def test_restore_refuses_a_taken_path(shelf, music):
    from app.library import LibraryError
    lib = shelf
    fid = row(lib, "a.mp3")["id"]
    lib.trash(fid)
    music.mp3("a.mp3", seed=9, title="Another track at the same path")
    with pytest.raises(LibraryError) as e:
        lib.restore(fid)
    assert e.value.status == 409 and "a.mp3" in e.value.detail
    lib.reconcile()  # now the new file has the path in the index as well
    with pytest.raises(LibraryError) as e:
        lib.restore(fid)
    assert e.value.status == 409
    assert row(lib, "a.mp3")["title"] == "Another track at the same path"  # untouched
    assert music.path(lib.file(fid)["trash_path"]).exists()  # still in the trash
    assert lib.file(fid)["state"] == "trashed"


def test_restore_refuses_what_is_not_in_the_trash(shelf, music, clock):
    from app.library import LibraryError
    lib = shelf
    for fid, status in ((9999, 404), (row(lib, "a.mp3")["id"], 409)):
        with pytest.raises(LibraryError) as e:
            lib.restore(fid)
        assert e.value.status == status
    fid = row(lib, "c.mp3")["id"]
    lib.trash(fid)
    lib.purge(everything=True)
    with pytest.raises(LibraryError) as e:
        lib.restore(fid)
    assert e.value.status == 410


def test_a_trashed_file_that_vanished_cannot_be_restored(shelf, music):
    from app.library import LibraryError
    lib = shelf
    fid = row(lib, "a.mp3")["id"]
    lib.trash(fid)
    music.path(lib.file(fid)["trash_path"]).unlink()
    with pytest.raises(LibraryError) as e:
        lib.restore(fid)
    assert e.value.status == 410 and lib.file(fid)["state"] == "gone"
    [entry] = lib.link_listing()["removed"]
    assert entry["reason"] == "deleted"


# ------------------------------------------------------------------- purge
def test_purge_by_age(shelf, music, clock):
    lib = shelf
    old, new = row(lib, "a.mp3")["id"], row(lib, "c.mp3")["id"]
    lib.trash(old)
    clock.advance(20 * DAY)
    lib.trash(new)
    clock.advance(9 * DAY)
    assert lib.purge() == 0  # 29 days: both kept

    clock.advance(DAY + 1)
    rev = lib.status()["rev"]
    assert lib.purge() == 1
    assert lib.file(old)["state"] == "gone" and lib.file(new)["state"] == "trashed"
    assert lib.file(old)["rev"] == rev + 1
    assert trash_folders(music) == [lib.file(new)["trash_path"].split("/")[1]]
    # A purged tombstone still says it was deleted in GetSetMix, and stays.
    removed = {r["path"]: r for r in lib.link_listing()["removed"]}
    assert removed["a.mp3"]["reason"] == "deleted" and removed["c.mp3"]["reason"] == "deleted"
    assert lib.status()["counts"] == {"present": 1, "trashed": 1, "gone": 1}


def test_purge_on_demand_empties_the_whole_trash(shelf, music):
    lib = shelf
    for path in ("a.mp3", "House/deep/b.mp3"):
        lib.trash(row(lib, path)["id"])
    assert lib.purge(everything=True) == 2
    assert lib.list(state="trashed")["total"] == 0
    assert trash_folders(music) == []
    assert music.path("c.mp3").exists()


def test_trash_days_0_keeps_the_trash_until_emptied_by_hand(lib, music, clock):
    from app import library
    lib = library.Library(lib.db, root=lambda: music.root, clock=clock, trash_days=lambda: 0)
    music.mp3("a.mp3", seed=1)
    lib.reconcile()
    fid = row(lib, "a.mp3")["id"]
    lib.trash(fid)
    clock.advance(1000 * DAY)
    assert lib.purge() == 0 and lib.purge_due() == 0
    assert lib.file(fid)["state"] == "trashed"
    assert lib.purge(everything=True) == 1
    assert lib.file(fid)["state"] == "gone"


def test_the_daily_purge_runs_once_a_day(shelf, music, clock):
    lib = shelf
    fid = row(lib, "a.mp3")["id"]
    lib.trash(fid)
    clock.advance(31 * DAY)
    assert lib.purge_due() == 1
    fid2 = row(lib, "c.mp3")["id"]
    lib.trash(fid2)
    lib.trash(row(lib, "House/deep/b.mp3")["id"])
    clock.advance(DAY - 60)
    assert lib.purge_due() == 0  # less than a day since the last run
    clock.advance(30 * DAY)
    assert lib.purge_due() == 2
    assert lib.file(fid2)["state"] == "gone"


def test_purge_leaves_anything_outside_its_own_folders(shelf, music):
    lib = shelf
    music.write(".trash/notes.txt", b"mine")
    music.write(".trash/other/x.mp3", b"mine too")
    lib.trash(row(lib, "a.mp3")["id"])
    lib.purge(everything=True)
    assert music.path(".trash/notes.txt").exists() and music.path(".trash/other/x.mp3").exists()


# ------------------------------------------- vanished outside GetSetMix
def test_a_vanished_file_is_removed_only_after_the_grace_time(lib, music, clock):
    for i in range(20):
        music.mp3(f"t{i}.mp3", seed=i)
    lib.reconcile()
    music.remove("t0.mp3")
    lib.reconcile()
    clock.advance(23 * 3600)
    lib.reconcile()
    assert lib.link_listing()["removed"] == []
    clock.advance(2 * 3600)
    lib.reconcile()
    [entry] = lib.link_listing()["removed"]
    assert entry["path"] == "t0.mp3" and entry["reason"] == "missing"


def test_nothing_is_removed_while_the_guard_is_tripped(lib, music, clock, tmp_path):
    for i in range(20):
        music.mp3(f"t{i}.mp3", seed=i)
    lib.reconcile()
    for i in range(12):  # 60% at once: a drive unplugged, not a delete
        music.hide(f"t{i}.mp3", tmp_path / "away")
    for _ in range(3):
        lib.reconcile()
        clock.advance(25 * 3600)
    lib.reconcile()
    assert lib.status()["unavailable"] is True
    assert lib.status()["counts"] == {"present": 20}
    assert lib.link_listing()["removed"] == []


# -------------------------------------------------------------------- HTTP
@pytest.fixture()
def api(tmp_path, monkeypatch, music):
    fresh_modules(tmp_path, monkeypatch, "app.worker", "app.main")
    import app.main
    with TestClient(app.main.app) as c:
        yield c


def index(api):
    from app import library
    lib = library.current()
    assert lib.wait(10)
    assert lib.reconcile() is not None
    return lib


def test_delete_and_restore_over_http(api, music):
    music.mp3("a.mp3", seed=1, title="A")
    music.mp3("b.mp3", seed=2, title="B")
    lib = index(api)
    fid = row(lib, "a.mp3")["id"]

    r = api.delete(f"/api/library/{fid}")
    assert r.status_code == 200 and r.json()["state"] == "trashed"
    assert api.delete(f"/api/library/{fid}").status_code == 410
    trashed = api.get("/api/library", params={"state": "trashed"}).json()
    assert [i["id"] for i in trashed["items"]] == [fid]
    assert [i["path"] for i in api.get("/api/library").json()["items"]] == ["b.mp3"]

    r = api.post(f"/api/library/{fid}/restore")
    assert r.status_code == 200 and r.json()["state"] == "present"
    assert music.path("a.mp3").exists()
    assert api.post(f"/api/library/{fid}/restore").status_code == 409
    assert api.delete("/api/library/9999").status_code == 404
    assert api.post("/api/library/9999/restore").status_code == 404


def test_restore_over_http_answers_409_when_the_path_is_taken(api, music):
    music.mp3("a.mp3", seed=1)
    lib = index(api)
    fid = row(lib, "a.mp3")["id"]
    api.delete(f"/api/library/{fid}")
    music.mp3("a.mp3", seed=5)
    r = api.post(f"/api/library/{fid}/restore")
    assert r.status_code == 409 and "a.mp3" in r.json()["detail"]


def test_empty_trash_over_http(api, music):
    music.mp3("a.mp3", seed=1)
    music.mp3("b.mp3", seed=2)
    lib = index(api)
    for path in ("a.mp3", "b.mp3"):
        api.delete(f"/api/library/{row(lib, path)['id']}")
    r = api.delete("/api/library/trash")
    assert r.status_code == 200 and r.json() == {"purged": 2}
    assert api.get("/api/library/status").json()["counts"] == {"gone": 2}


def test_fixed_paths_are_not_read_as_an_id(api):
    assert api.get("/api/library/rules").status_code == 200
    assert api.get("/api/library/status").status_code == 200
    assert api.post("/api/library/trash/restore").status_code in (404, 405)
    assert api.delete("/api/library/abc").status_code in (404, 405)


def test_the_trash_needs_the_app_token(tmp_path, monkeypatch, music):
    fresh_modules(tmp_path, monkeypatch, "app.worker", "app.main", token="sekret")
    import app.main
    with TestClient(app.main.app) as c:
        for method, url in (("delete", "/api/library/1"), ("post", "/api/library/1/restore"),
                            ("delete", "/api/library/trash")):
            assert getattr(c, method)(url).status_code == 401, url


# ---------------------------------------------------------------- setting
def test_trash_days_setting(api, monkeypatch):
    assert api.get("/api/settings").json()["trash_days"] == 30
    r = api.put("/api/settings", json={"trash_days": 0})
    assert r.status_code == 200 and r.json()["trash_days"] == 0
    assert api.put("/api/settings", json={"trash_days": 7}).json()["trash_days"] == 7
    assert api.put("/api/settings", json={"trash_days": -1}).status_code == 400
    assert api.put("/api/settings", json={"trash_days": 99999}).status_code == 400
    from app import library
    assert library.current().trash_days() == 7


def test_trash_days_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GSM_TRASH_DAYS", "12")
    fresh_modules(tmp_path, monkeypatch)
    from app import config
    assert config.settings["trash_days"] == 12
    monkeypatch.setenv("GSM_TRASH_DAYS", "soon")
    fresh_modules(tmp_path, monkeypatch)
    assert config.settings["trash_days"] == 30
