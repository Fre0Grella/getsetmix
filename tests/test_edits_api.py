"""The batch-editing API (docs/design/batch-editing.md 3.5): make a preview,
read it and its changes, apply it, and every answer in between."""
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
    music.mp3("a.mp3", seed=1, title="A", artist="Nova", genre="House")
    music.mp3("b.mp3", seed=2, title="B", artist="Kito", genre="House")
    music.wav("c.wav", seed=3)
    rescan(api)
    return api


def make(api, fids, field="genre", value: object = "Tech House"):
    return api.post("/api/library/edits", json={
        "selection": {"ids": fids}, "steps": [{"op": "set", "field": field, "value": value}]})


def finished(api, eid):
    from app import edits
    assert edits.current().wait(10)
    return api.get(f"/api/library/edits/{eid}").json()


def test_preview_then_apply_over_http(shelf, music):
    by_path = ids(shelf)
    before = music.path("a.mp3").read_bytes()
    r = make(shelf, [by_path["a.mp3"], by_path["b.mp3"], by_path["c.wav"]])
    assert r.status_code == 201, r.text
    edit = r.json()
    assert edit["state"] == "preview"
    assert edit["counts"]["changed"] == 2 and edit["counts"]["skipped_by_reason"] == {
        "read-only format": 1}
    assert music.path("a.mp3").read_bytes() == before

    changes = shelf.get(f"/api/library/edits/{edit['id']}/changes").json()
    assert [(c["path"], c["old"], c["new"]) for c in changes["items"]] == [
        ("a.mp3", "House", "Tech House"), ("b.mp3", "House", "Tech House")]

    r = shelf.post(f"/api/library/edits/{edit['id']}/apply")
    assert r.status_code == 202 and r.json()["state"] == "applying"
    done = finished(shelf, edit["id"])
    assert done["state"] == "applied" and done["progress"]["files_done"] == 2
    for name in ("a.mp3", "b.mp3"):
        assert ID3(music.path(name))["TCON"].text == ["Tech House"]
    assert {i["genre"] for i in shelf.get("/api/library").json()["items"]
            if i["path"] != "c.wav"} == {"Tech House"}
    assert shelf.post(f"/api/library/edits/{edit['id']}/apply").status_code == 409


def test_a_year_is_set_as_an_integer(shelf, music):
    fid = ids(shelf)["a.mp3"]
    edit = make(shelf, [fid], "year", 2021).json()
    [c] = shelf.get(f"/api/library/edits/{edit['id']}/changes").json()["items"]
    assert c["old"] is None and c["new"] == 2021
    shelf.post(f"/api/library/edits/{edit['id']}/apply")
    finished(shelf, edit["id"])
    assert str(ID3(music.path("a.mp3"))["TDRC"].text[0]) == "2021"


@pytest.mark.parametrize("body", [{}, {"selection": {"ids": [1]}},
                                  {"selection": {"ids": [1]}, "steps": [{"op": "set"}]}])
def test_a_request_that_is_not_valid_is_400(shelf, body):
    assert shelf.post("/api/library/edits", json=body).status_code == 400


def test_unknown_edits_are_404(shelf):
    assert shelf.get("/api/library/edits/9999").status_code == 404
    assert shelf.get("/api/library/edits/9999/changes").status_code == 404
    assert shelf.post("/api/library/edits/9999/apply").status_code == 404


def test_bad_change_filters_are_400(shelf):
    edit = make(shelf, [ids(shelf)["a.mp3"]]).json()
    for params in ({"field": "bpm"}, {"state": "x"}, {"limit": 0}, {"cursor": "x"}):
        r = shelf.get(f"/api/library/edits/{edit['id']}/changes", params=params)
        assert r.status_code == 400, params


def test_edits_need_the_app_token(tmp_path, monkeypatch, music):
    with _client(tmp_path, monkeypatch, token="sekret") as c:
        body = {"selection": {"ids": [1]}, "steps": [{"op": "set", "field": "genre", "value": "x"}]}
        assert c.post("/api/library/edits", json=body).status_code == 401
        assert c.get("/api/library/edits/1").status_code == 401
        assert c.post("/api/library/edits/1/apply").status_code == 401
