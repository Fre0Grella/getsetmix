import importlib
import os
import sqlite3
import threading
import time

import pytest
from conftest import SETTLED, fresh_modules
from fastapi.testclient import TestClient

HOUR = 3600
OLD_FIELDS = ("path", "size", "mtime")


def _settle(*paths):
    """Make generated files look finished: the index leaves files younger than 10 s alone."""
    when = time.time() - SETTLED
    for path in paths:
        os.utime(path, (when, when))


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    monkeypatch.delenv("GSM_LINK_TOKEN", raising=False)
    monkeypatch.setenv("GSM_AUTH_TOKEN", "ui-secret")
    import app.config
    import app.db
    import app.link
    import app.main
    import app.worker
    for mod in (app.config, app.db, app.link, app.worker, app.main):
        importlib.reload(mod)
    music = tmp_path / "music"
    (music / "House").mkdir(parents=True)
    (music / "House" / "A - One.mp3").write_bytes(b"ID3one")
    (music / "B - Two.flac").write_bytes(b"fLaCtwo")
    (music / ".B - Three.flac.part").write_bytes(b"half")       # still landing
    (music / "cover.jpg").write_bytes(b"jpg")                   # not a track
    (music / "Empty.mp3").write_bytes(b"")
    _settle(*music.rglob("*"))
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "link-tokens").write_text("pc-token  Studio PC\n")
    (tmp_path / "secret.mp3").write_bytes(b"outside")
    with TestClient(app.main.app) as c:
        yield c


AUTH = {"Authorization": "Bearer pc-token"}


def index_now():
    """Finish the first index (the app starts it in the background) and run one more pass."""
    from app import library
    lib = library.current()
    while lib.reconcile() is None:
        assert lib.wait(10)
    return lib


def files(client) -> dict:
    r = client.get("/api/link/files", headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def test_lists_only_finished_audio(server):
    index_now()
    body = files(server)
    assert body["protocol"] == 2
    paths = [f["path"] for f in body["files"]]
    assert paths == ["B - Two.flac", "House/A - One.mp3"]
    assert body["files"][0]["size"] == 7


def test_downloads_a_track(server):
    r = server.get("/api/link/file", params={"path": "House/A - One.mp3"}, headers=AUTH)
    assert r.status_code == 200 and r.content == b"ID3one"


@pytest.mark.parametrize("path", ["../secret.mp3", "/etc/passwd", "House\\..\\..\\secret.mp3",
                                  ".B - Three.flac.part", "cover.jpg", "missing.mp3"])
def test_refuses_anything_else(server, path):
    assert server.get("/api/link/file", params={"path": path}, headers=AUTH).status_code == 404


def test_needs_a_paired_token(server):
    assert server.get("/api/link/files").status_code == 401
    assert server.get("/api/link/files", headers={"Authorization": "Bearer nope"}).status_code == 401
    # the UI token doesn't open the link, and the link token doesn't open the UI
    assert server.get("/api/link/files", headers={"X-Auth-Token": "ui-secret"}).status_code == 401
    assert server.get("/api/tracks", headers=AUTH).status_code == 401


def test_tokens_are_read_live(server, tmp_path):
    (tmp_path / "data" / "link-tokens").write_text("pc-token\nlaptop-token  Laptop\n")
    r = server.get("/api/link/files", headers={"Authorization": "Bearer laptop-token"})
    assert r.status_code == 200


# ------------------------------------------------- protocol 2, the index
def listed(lib) -> dict:
    return {f["path"]: f for f in lib.link_listing()["files"]}


def removed(lib) -> dict:
    return {r["path"]: r for r in lib.link_listing()["removed"]}


def test_nothing_is_served_from_the_index_before_the_first_pass(lib, music):
    music.mp3("a.mp3", seed=1)
    assert lib.link_listing() is None


def test_a_listed_file_carries_its_audio_id_and_rev(lib, music):
    music.mp3("House/a.mp3", seed=1, title="A")
    music.wav("b.wav", seed=2)
    lib.reconcile()

    body = lib.link_listing()
    assert body["protocol"] == 2 and body["rev"] == lib.status()["rev"] == 2
    [a, b] = body["files"]
    assert set(a) == {"path", "size", "mtime", "id", "rev"}
    st = music.path("House/a.mp3").stat()
    assert a["path"] == "House/a.mp3" and a["size"] == st.st_size
    assert a["mtime"] == int(st.st_mtime)
    assert a["id"].startswith("a1_") and a["rev"] == 1
    assert b["path"] == "b.wav" and b["rev"] == 2
    assert body["removed"] == []


def test_the_old_fields_are_what_protocol_1_serves(lib, music):
    # An old companion reads path, size and mtime and ignores the rest.
    from app import link
    music.mp3("A - One.mp3", seed=1)
    music.mp3("House/deep/B - Two.mp3", seed=2)
    music.wav("C - Three.wav", seed=3)
    music.fixture("D - Four.ogg", "fallback/vorbis.ogg")
    music.write(".hidden.mp3", b"x")
    music.write("Half.mp3.part", b"x")
    lib.reconcile()
    old = sorted((f["path"], f["size"], f["mtime"]) for f in link.list_files(music.root))
    new = sorted(tuple(f[k] for k in OLD_FIELDS) for f in lib.link_listing()["files"])
    assert new == old and len(new) == 4


def test_files_rekordbox_cannot_import_are_still_listed(lib, music):
    music.fixture("x.ogg", "fallback/vorbis.ogg")
    music.fixture("y.opus", "fallback/opus.opus")
    music.mp3("z.mp3", seed=1)
    lib.reconcile()
    assert set(listed(lib)) == {"x.ogg", "y.opus", "z.mp3"}


def test_a_tag_edit_outside_makes_the_file_newer(lib, music):
    music.mp3("a.mp3", seed=1, title="Old")
    music.mp3("b.mp3", seed=2)
    lib.reconcile()
    before = listed(lib)["a.mp3"]

    music.tag("a.mp3", age=100, title="New title, longer than before")
    lib.reconcile()

    after = listed(lib)["a.mp3"]
    assert after["id"] == before["id"]
    # The tag fits its padding: same size, only the time says the bytes changed.
    assert after["size"] == before["size"] and after["mtime"] != before["mtime"]
    assert after["rev"] > before["rev"]
    assert lib.link_listing()["rev"] == after["rev"]
    assert listed(lib)["b.mp3"]["rev"] == 2


def test_a_move_outside_is_not_a_change_of_bytes(lib, music):
    music.mp3("a.mp3", seed=1)
    lib.reconcile()
    before = listed(lib)["a.mp3"]

    music.move("a.mp3", "House/renamed.mp3")
    lib.reconcile()

    body = lib.link_listing()
    [after] = body["files"]
    assert after["path"] == "House/renamed.mp3"
    assert after["id"] == before["id"] and after["rev"] == before["rev"]
    assert body["rev"] > before["rev"]  # the library changed, the file's bytes did not
    assert body["removed"] == []


def test_a_file_back_from_missing_keeps_its_rev(lib, music, tmp_path):
    music.mp3("a.mp3", seed=1)
    music.mp3("b.mp3", seed=2)
    lib.reconcile()
    before = listed(lib)["a.mp3"]
    music.hide("a.mp3", tmp_path / "away")
    lib.reconcile()
    music.unhide("a.mp3", tmp_path / "away")
    lib.reconcile()
    assert listed(lib)["a.mp3"]["rev"] == before["rev"]


def test_a_missing_file_is_not_listed_and_not_yet_removed(lib, music, clock):
    music.mp3("a.mp3", seed=1)
    music.mp3("b.mp3", seed=2)
    lib.reconcile()
    music.remove("a.mp3")
    lib.reconcile()
    assert set(listed(lib)) == {"b.mp3"}
    assert removed(lib) == {}


def test_a_file_gone_outside_getsetmix_is_removed_as_missing(lib, music, clock):
    music.mp3("a.mp3", seed=1)
    music.mp3("b.mp3", seed=2)
    lib.reconcile()
    aid = listed(lib)["a.mp3"]["id"]
    music.remove("a.mp3")
    lib.reconcile()
    clock.advance(25 * HOUR)
    lib.reconcile()

    body = lib.link_listing()
    assert [f["path"] for f in body["files"]] == ["b.mp3"]
    [gone] = body["removed"]
    assert gone["id"] == aid and gone["path"] == "a.mp3" and gone["reason"] == "missing"
    assert gone["at"] == lib.file(_row_id(lib, "a.mp3"))["state_changed_at"]


def test_replaced_audio_removes_the_old_id(lib, music):
    music.mp3("a.mp3", seed=1)
    lib.reconcile()
    old = listed(lib)["a.mp3"]
    music.mp3("a.mp3", seed=2, age=100)
    lib.reconcile()
    new = listed(lib)["a.mp3"]
    assert new["id"] != old["id"]
    assert [r["id"] for r in lib.link_listing()["removed"]] == [old["id"]]


def test_a_trashed_file_is_removed_as_deleted_and_not_served(lib, music, tmp_path,
                                                             monkeypatch):
    # The trash itself is a later slice; this is the state it leaves behind.
    music.mp3("a.mp3", seed=1)
    music.mp3("b.mp3", seed=2)
    lib.reconcile()
    aid = listed(lib)["a.mp3"]["id"]
    fid = _row_id(lib, "a.mp3")
    music.move("a.mp3", ".trash/20261112T221003Z-1/a.mp3")
    with lib.db.transaction() as conn:
        conn.execute("UPDATE library_files SET state = 'trashed', state_changed_at = ?, "
                     "trash_path = ?, rev = rev + 100 WHERE id = ?",
                     ("2026-11-12T22:10:03+00:00", ".trash/20261112T221003Z-1/a.mp3", fid))
    lib.reconcile()

    body = lib.link_listing()
    assert [f["path"] for f in body["files"]] == ["b.mp3"]
    assert body["removed"] == [{"id": aid, "path": "a.mp3", "at": "2026-11-12T22:10:03+00:00",
                                "reason": "deleted"}]
    from app import link
    assert link.resolve(music.root, "a.mp3") is None
    assert link.resolve(music.root, ".trash/20261112T221003Z-1/a.mp3") is None


def _row_id(lib, path):
    with lib.db.transaction() as conn:
        return conn.execute("SELECT id FROM library_files WHERE path = ? ORDER BY id DESC",
                            (path,)).fetchone()[0]


def test_exact_duplicates_are_listed_once_the_oldest_row(lib, music):
    music.mp3("a.mp3", seed=9, title="One")
    music.mp3("copy/a.mp3", seed=9, title="Other tags")
    music.mp3("b.mp3", seed=1)
    lib.reconcile()
    files = lib.link_listing()["files"]
    assert [f["path"] for f in files] == ["a.mp3", "b.mp3"]
    assert len({f["id"] for f in files}) == 2


def test_a_duplicate_that_vanishes_is_not_a_removed_track(lib, music, clock):
    music.mp3("a.mp3", seed=9, title="One")
    music.mp3("copy/a.mp3", seed=9, title="Other tags")
    lib.reconcile()
    aid = listed(lib)["a.mp3"]["id"]
    music.remove("a.mp3")
    lib.reconcile()
    clock.advance(25 * HOUR)
    lib.reconcile()

    body = lib.link_listing()
    # The audio is still on the server: the copy takes its place, nothing is removed.
    assert [(f["path"], f["id"]) for f in body["files"]] == [("copy/a.mp3", aid)]
    assert body["removed"] == []


def test_one_removed_entry_per_audio_id(lib, music, clock):
    music.mp3("a.mp3", seed=9)
    music.mp3("b.mp3", seed=1)
    lib.reconcile()
    music.remove("a.mp3")
    lib.reconcile()
    clock.advance(25 * HOUR)
    lib.reconcile()
    music.mp3("again/a.mp3", seed=9, age=100)   # the same audio comes back, as a new row
    lib.reconcile()
    music.remove("again/a.mp3")
    lib.reconcile()
    clock.advance(25 * HOUR)
    lib.reconcile()

    [entry] = lib.link_listing()["removed"]
    assert entry["path"] == "again/a.mp3"


# ------------------------------------------------- protocol 2, over HTTP
@pytest.fixture()
def link2(tmp_path, monkeypatch, music):
    fresh_modules(tmp_path, monkeypatch, "app.link", "app.worker", "app.main")
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "link-tokens").write_text("pc-token\n")
    import app.main
    with TestClient(app.main.app) as c:
        yield c


def test_the_endpoint_serves_protocol_2_once_indexed(link2, music):
    music.mp3("a.mp3", seed=1)
    music.fixture("b.ogg", "fallback/vorbis.ogg")
    index_now()
    body = files(link2)
    assert body["protocol"] == 2 and body["version"]
    assert [f["path"] for f in body["files"]] == ["a.mp3", "b.ogg"]
    assert all(f["id"] and f["rev"] for f in body["files"])
    assert body["removed"] == []
    r = link2.get("/api/link/file", params={"path": "b.ogg"}, headers=AUTH)
    assert r.status_code == 200 and r.content == music.path("b.ogg").read_bytes()


def test_protocol_1_until_the_first_index_is_complete(tmp_path, monkeypatch, music):
    # A long first index: the computer gets today's listing at once, not a wait.
    music.mp3("a.mp3", seed=1)
    music.mp3("b.mp3", seed=2)
    music.write(".hidden.mp3", b"x")
    music.write("c.mp3.part", b"x")
    music.write("cover.jpg", b"x")
    release = threading.Event()
    from app import audiohash
    real = audiohash.audio_id

    def slow(path):
        release.wait(20)
        return real(path)

    monkeypatch.setattr(audiohash, "audio_id", slow)
    fresh_modules(tmp_path, monkeypatch, "app.link", "app.worker", "app.main")
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "link-tokens").write_text("pc-token\n")
    import app.main
    try:
        with TestClient(app.main.app) as c:
            started = time.monotonic()
            body = files(c)
            assert time.monotonic() - started < 5
            assert "protocol" not in body and "removed" not in body
            assert [f["path"] for f in body["files"]] == ["a.mp3", "b.mp3"]
            assert set(body["files"][0]) == set(OLD_FIELDS)

            release.set()
            index_now()
            assert files(c)["protocol"] == 2
    finally:
        release.set()


def test_a_stale_index_is_reconciled_before_it_answers(link2, music):
    music.mp3("a.mp3", seed=1)
    lib = index_now()
    music.mp3("b.mp3", seed=2)
    assert [f["path"] for f in files(link2)["files"]] == ["a.mp3"]  # the last pass is recent

    real = lib.clock
    lib.clock = lambda: real() + 61
    assert [f["path"] for f in files(link2)["files"]] == ["a.mp3", "b.mp3"]


# ----------------------------------------------- the index's new column
SLICE_1_TABLE = """
CREATE TABLE library_files (
    id INTEGER PRIMARY KEY, path TEXT NOT NULL, audio_id TEXT NOT NULL,
    size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, format TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '', artist TEXT NOT NULL DEFAULT '',
    album TEXT NOT NULL DEFAULT '', genre TEXT NOT NULL DEFAULT '', year INTEGER,
    comment TEXT NOT NULL DEFAULT '', has_cover INTEGER NOT NULL DEFAULT 0,
    multi TEXT NOT NULL DEFAULT '', duration REAL, bitrate INTEGER, sample_rate INTEGER,
    source_url TEXT NOT NULL DEFAULT '', search TEXT NOT NULL, added_at TEXT NOT NULL,
    rev INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'present', state_changed_at TEXT,
    trash_path TEXT
);
CREATE TABLE library_meta (key TEXT PRIMARY KEY, value TEXT);
INSERT INTO library_files (path, audio_id, size, mtime_ns, format, search, added_at, rev)
    VALUES ('a.mp3', 'a1_00000000000000000000000000000001', 10, 1, 'mp3', 'a', '2026', 7);
INSERT INTO library_meta VALUES ('rev', '7'), ('indexed', '1');
"""


def test_a_database_from_the_first_slice_is_migrated(tmp_path, monkeypatch, music):
    (tmp_path / "data").mkdir()
    conn = sqlite3.connect(tmp_path / "data" / "getsetmix.db")
    conn.executescript(SLICE_1_TABLE)
    conn.commit()
    conn.close()
    fresh_modules(tmp_path, monkeypatch)
    import app.db
    from app import library
    lib = library.Library(app.db.db, root=lambda: music.root)
    body = lib.link_listing()
    assert body["files"] == [{"path": "a.mp3", "size": 10, "mtime": 0,
                              "id": "a1_00000000000000000000000000000001", "rev": 7}]
