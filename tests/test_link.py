import importlib

import pytest
from fastapi.testclient import TestClient


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
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "link-tokens").write_text("pc-token  Studio PC\n")
    (tmp_path / "secret.mp3").write_bytes(b"outside")
    with TestClient(app.main.app) as c:
        yield c


AUTH = {"Authorization": "Bearer pc-token"}


def test_lists_only_finished_audio(server):
    r = server.get("/api/link/files", headers=AUTH)
    assert r.status_code == 200
    paths = [f["path"] for f in r.json()["files"]]
    assert paths == ["B - Two.flac", "House/A - One.mp3"]
    assert r.json()["files"][0]["size"] == 7


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
