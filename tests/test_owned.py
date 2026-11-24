"""Downloads checked against the Library index (issue #71): where a finished
download is now, and whether a staged one is a song the Library already has."""
import pytest
from conftest import fresh_modules
from fastapi.testclient import TestClient

SOURCE = "Source: https://youtu.be/abc | via GetSetMix"


def row(lib, path):
    with lib.db.transaction() as conn:
        found = conn.execute("SELECT * FROM library_files WHERE path = ? ORDER BY id DESC",
                             (path,)).fetchone()
    return dict(found) if found else None


def meta(title="", artist="", url=""):
    return {"title": title, "artist": artist, "url": url}


# --------------------------------------------------------------- same_song
def test_the_source_url_on_the_row_is_a_match(lib, music):
    path = music.mp3("x.mp3", seed=1, title="Renamed", artist="Someone")
    fid = lib.add_file(path, source_url="https://youtu.be/abc")
    found = lib.same_song(meta("Totally Different", "Nobody", "https://YOUTU.BE/abc/"))
    assert found["id"] == fid


def test_the_source_url_in_the_comment_is_a_match(lib, music):
    # A file the reconcile found (no source_url on its row) still carries
    # the link in the comment the tagger wrote.
    music.mp3("x.mp3", seed=1, title="Renamed", artist="Someone", comment=SOURCE)
    lib.reconcile()
    found = lib.same_song(meta("Other", "Else", "https://youtu.be/abc"))
    assert found["path"] == "x.mp3"
    assert lib.same_song(meta("Other", "Else", "https://youtu.be/abcd")) is None


def test_title_and_artist_tokens_match(lib, music):
    music.mp3("Shake.mp3", seed=1, title="Shake That Bunda", artist="Fantasm & The Straikerz")
    music.mp3("Tacata.mp3", seed=2, title="Tacata' OFFICIAL VIDEO", artist="Tacabro")
    lib.reconcile()
    found = lib.same_song(meta("Shake That Bunda", "Fantasm, The Straikerz", "https://x/1"))
    assert found["path"] == "Shake.mp3"
    assert lib.same_song(meta("Hardtechno Tacata", "Dustin Hertz", "https://x/2")) is None


def test_accented_titles_pass_the_sql_prefilter(lib, music):
    music.mp3("cafe.mp3", seed=1, title="Café del Mar", artist="Energy 52")
    lib.reconcile()
    assert lib.same_song(meta("Café del Mar (Official Video)", "Energy 52"))["path"] == "cafe.mp3"


def test_the_url_wins_over_a_title_match(lib, music):
    music.mp3("a.mp3", seed=1, title="Night Drive", artist="DJ A")
    music.mp3("b.mp3", seed=2, title="Other", artist="Else", comment=SOURCE)
    lib.reconcile()
    found = lib.same_song(meta("Night Drive", "DJ A", "https://youtu.be/abc"))
    assert found["path"] == "b.mp3"


def test_only_present_files_are_owned(lib, music):
    music.mp3("a.mp3", seed=1, title="Night Drive", artist="DJ A")
    lib.reconcile()
    fid = row(lib, "a.mp3")["id"]
    lib.trash(fid)
    assert lib.same_song(meta("Night Drive", "DJ A")) is None
    lib.restore(fid)
    assert lib.same_song(meta("Night Drive", "DJ A"))["id"] == fid


def test_nothing_to_match_on(lib, music):
    music.mp3("a.mp3", seed=1, title="Official Video", artist="X")
    lib.reconcile()
    assert lib.same_song(meta("Official Video", "X")) is None  # all noise: no title tokens
    assert lib.same_song(meta()) is None


def test_the_prefilter_keeps_the_scan_small(lib, music):
    for i in range(30):
        music.mp3(f"t{i}.mp3", seed=i + 1, title=f"Track Number{i}", artist=f"Artist{i}")
    lib.reconcile()
    rows = lib._song_candidates("", frozenset({"number7"}), frozenset({"artist7"}))
    assert [r["path"] for r in rows] == ["t7.mp3"]


# ------------------------------------------------------------------ locate
def test_locate_follows_the_audio_id_through_a_move(lib, music):
    music.mp3("a.mp3", seed=1, title="A")
    lib.reconcile()
    before = row(lib, "a.mp3")
    music.move("a.mp3", "House/a.mp3")
    lib.reconcile()
    [found] = lib.locate([(before["audio_id"], str(music.path("a.mp3")))])
    assert found == {"id": before["id"], "state": "present"}


def test_locate_by_path_without_an_audio_id(lib, music):
    music.mp3("a.mp3", seed=1, title="A")
    lib.reconcile()
    fid = row(lib, "a.mp3")["id"]
    found = lib.locate([("", str(music.path("a.mp3"))), ("", "/elsewhere/a.mp3"), ("", "")])
    assert found == [{"id": fid, "state": "present"}, None, None]


def test_locate_prefers_a_trashed_row_to_tombstones(lib, music, clock):
    music.mp3("a.mp3", seed=1, title="A")
    lib.reconcile()
    first = row(lib, "a.mp3")
    lib.trash(first["id"])
    [found] = lib.locate([(first["audio_id"], "")])
    assert found == {"id": first["id"], "state": "trashed"}
    lib.purge(everything=True)
    [found] = lib.locate([(first["audio_id"], "")])
    assert found["state"] == "gone"


# -------------------------------------------------------------------- HTTP
@pytest.fixture()
def api(tmp_path, monkeypatch, music):
    fresh_modules(tmp_path, monkeypatch, "app.worker", "app.main")
    import app.main
    with TestClient(app.main.app) as c:
        yield c


def index():
    from app import library
    lib = library.current()
    assert lib.wait(10)
    assert lib.reconcile() is not None
    return lib


def track(api, tid):
    return next(t for t in api.get("/api/tracks").json()["tracks"] if t["id"] == tid)


def test_a_download_follows_its_file_into_the_trash_and_out(api, music):
    import app.main as m
    path = music.mp3("a.mp3", seed=1, title="Night Drive", artist="DJ A")
    lib = index()
    file = row(lib, "a.mp3")
    tid = m.db.create_track("https://x/1", status="ingested", title="Night Drive",
                            artist="DJ A", file_path=str(path), audio_id=file["audio_id"])
    t = track(api, tid)
    assert (t["library_state"], t["library_id"]) == ("present", file["id"])

    assert api.delete(f"/api/library/{file['id']}").status_code == 200
    t = track(api, tid)
    assert (t["library_state"], t["library_id"]) == ("trashed", file["id"])

    assert api.post(f"/api/library/{file['id']}/restore").status_code == 200
    assert track(api, tid)["library_state"] == "present"

    api.delete(f"/api/library/{file['id']}")
    assert api.request("DELETE", "/api/library/trash").status_code == 200
    t = track(api, tid)
    assert (t["library_state"], t["library_id"]) == ("absent", None)


def test_a_download_from_before_71_is_found_by_its_path(api, music):
    import app.main as m
    path = music.mp3("a.mp3", seed=1, title="A")
    lib = index()
    tid = m.db.create_track("https://x/1", status="ingested", file_path=str(path))
    assert track(api, tid)["library_state"] == "present"
    music.remove("a.mp3")
    lib.reconcile()  # the file is missing now
    assert track(api, tid)["library_state"] == "absent"


def test_only_finished_downloads_get_a_library_state(api, music):
    import app.main as m
    index()
    tid = m.db.create_track("https://x/1", status="staged", title="A", artist="B")
    t = track(api, tid)
    assert t["library_state"] is None and t["library_id"] is None


def test_a_staged_duplicate_follows_the_library(api, music):
    import app.main as m
    music.mp3("a.mp3", seed=1, title="Night Drive", artist="DJ A")
    lib = index()
    fid = row(lib, "a.mp3")["id"]
    tid = m.db.create_track("https://x/1", status="staged", title="Night Drive (Official Video)",
                            artist="DJ A")
    t = track(api, tid)
    assert (t["duplicate"], t["duplicate_reason"], t["duplicate_of"]) == (
        1, "DJ A – Night Drive", fid)
    gate = api.post("/api/batch/start", json={"ids": [tid]}).json()
    assert gate["needs_confirm"] and gate["duplicates"][0]["reason"] == "DJ A – Night Drive"

    api.delete(f"/api/library/{fid}")  # a new rev: the flag is checked again
    t = track(api, tid)
    assert (t["duplicate"], t["duplicate_reason"], t["duplicate_of"]) == (0, "", None)

    api.post(f"/api/library/{fid}/restore")
    assert track(api, tid)["duplicate"] == 1


def test_the_gate_checks_the_flags_again(api, music, monkeypatch):
    # A flag set before the Library changed does not hold a download back.
    import app.main as m

    async def no_download(ids, concurrency=None):
        return list(ids)

    monkeypatch.setattr(m.worker, "start_batch", no_download)
    music.mp3("a.mp3", seed=1, title="Night Drive", artist="DJ A")
    lib = index()
    fid = row(lib, "a.mp3")["id"]
    tid = m.db.create_track("https://x/1", status="staged", title="Night Drive", artist="DJ A")
    assert track(api, tid)["duplicate"] == 1
    lib.trash(fid)
    gate = api.post("/api/batch/start", json={"ids": [tid]}).json()
    assert "needs_confirm" not in gate
