"""POST /api/library/bulk: delete, restore and set genre on many tracks (design 3.3)."""
import pytest
from mutagen.id3 import ID3
from test_library_api import _client, rescan
from test_library_edit_api import ids


@pytest.fixture()
def api(tmp_path, monkeypatch, music):
    with _client(tmp_path, monkeypatch) as c:
        yield c


@pytest.fixture()
def shelf(api, music):
    music.mp3("a.mp3", seed=1, title="A", genre="House")
    music.mp3("b.mp3", seed=2, title="B", genre="House")
    music.wav("c.wav", seed=3)
    rescan(api)
    return api


def bulk(api, **body):
    return api.post("/api/library/bulk", json=body)


def test_set_genre_writes_each_file_once_and_reports_a_read_only_one(shelf, music):
    by_path = ids(shelf)
    rev = shelf.get("/api/library/status").json()["rev"]
    wav = music.path("c.wav").read_bytes()

    r = bulk(shelf, action="set_genre", genre="Tech House",
             ids=[by_path["a.mp3"], by_path["c.wav"], by_path["b.mp3"]])

    assert r.status_code == 200, r.text
    assert r.json()["done"] == [by_path["a.mp3"], by_path["b.mp3"]]
    [failed] = r.json()["failed"]
    assert failed["id"] == by_path["c.wav"] and failed["status"] == 409
    assert "read-only" in failed["detail"]
    for name in ("a.mp3", "b.mp3"):
        assert ID3(music.path(name))["TCON"].text == ["Tech House"]
    assert music.path("c.wav").read_bytes() == wav
    # one write per file: one rev each, through the internal write
    assert shelf.get("/api/library/status").json()["rev"] == rev + 2


def test_delete_and_restore_many_with_an_unknown_id(shelf, music):
    by_path = ids(shelf)
    a, b = by_path["a.mp3"], by_path["b.mp3"]

    r = bulk(shelf, action="delete", ids=[a, 9999, b])
    assert r.json() == {"done": [a, b], "failed": [
        {"id": 9999, "status": 404, "detail": "no such track"}]}
    assert not music.path("a.mp3").exists() and not music.path("b.mp3").exists()
    trashed = shelf.get("/api/library", params={"state": "trashed"}).json()["items"]
    assert {i["id"] for i in trashed} == {a, b}

    r = bulk(shelf, action="restore", ids=[a, b])
    assert r.json() == {"done": [a, b], "failed": []}
    assert music.path("a.mp3").exists() and music.path("b.mp3").exists()


def test_a_repeated_id_is_handled_once(shelf):
    a = ids(shelf)["a.mp3"]
    assert bulk(shelf, action="delete", ids=[a, a]).json() == {"done": [a], "failed": []}


@pytest.mark.parametrize("body", [
    {"action": "rename", "ids": [1]},
    {"action": "delete"},
    {"action": "delete", "ids": []},
    {"action": "delete", "ids": "1,2"},
    {"action": "delete", "ids": [1, "2"]},
    {"action": "delete", "ids": [True]},
    {"action": "set_genre", "ids": [1]},
    {"action": "set_genre", "ids": [1], "genre": 5},
])
def test_a_request_that_is_not_valid_is_400_and_changes_nothing(shelf, music, body):
    before = {p: music.path(p).read_bytes() for p in ("a.mp3", "b.mp3")}
    r = shelf.post("/api/library/bulk", json=body)
    assert r.status_code == 400, (body, r.text)
    assert {p: music.path(p).read_bytes() for p in before} == before


def test_more_than_the_limit_is_413(shelf, monkeypatch):
    from app import library
    monkeypatch.setattr(library, "MAX_SELECTION", 2)
    assert bulk(shelf, action="delete", ids=[1, 2, 3]).status_code == 413


def test_bulk_needs_the_app_token(tmp_path, monkeypatch, music):
    with _client(tmp_path, monkeypatch, token="sekret") as c:
        assert c.post("/api/library/bulk", json={"action": "delete", "ids": [1]}).status_code == 401
