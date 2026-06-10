import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    monkeypatch.delenv("GSM_AUTH_TOKEN", raising=False)
    # fresh module state per test
    import app.config
    import app.db
    import app.worker
    import app.main
    importlib.reload(app.config)
    importlib.reload(app.db)
    importlib.reload(app.worker)
    importlib.reload(app.main)
    with TestClient(app.main.app) as c:
        yield c


@pytest.fixture()
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    monkeypatch.setenv("GSM_AUTH_TOKEN", "sekret")
    import app.config
    import app.db
    import app.worker
    import app.main
    importlib.reload(app.config)
    importlib.reload(app.db)
    importlib.reload(app.worker)
    importlib.reload(app.main)
    with TestClient(app.main.app) as c:
        yield c


def test_healthz(client):
    assert client.get("/healthz").text == "ok"


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "getsetmix" in r.text.lower()


def test_settings_roundtrip(client):
    r = client.put("/api/settings", json={"output_format": "flac", "concurrency": 3})
    assert r.status_code == 200
    s = client.get("/api/settings").json()
    assert s["output_format"] == "flac" and s["concurrency"] == 3


def test_settings_rejects_bad_format(client):
    assert client.put("/api/settings", json={"output_format": "ogg"}).status_code in (400, 422)


def test_tracks_empty(client):
    body = client.get("/api/tracks").json()
    assert body["tracks"] == [] and body["busy"] is False


def test_patch_missing_track_404(client):
    assert client.patch("/api/tracks/nope", json={}).status_code == 404


def test_metrics_format(client):
    text = client.get("/metrics").text
    assert "getsetmix_healthy 1" in text
    assert "{}" not in text  # no invalid empty label sets


def test_auth_blocks_api(auth_client):
    assert auth_client.get("/api/tracks").status_code == 401
    assert auth_client.get("/metrics").status_code == 401
    assert auth_client.get("/api/ping").status_code == 200
    ok = auth_client.get("/api/tracks", headers={"X-Auth-Token": "sekret"})
    assert ok.status_code == 200
    bearer = auth_client.get("/api/tracks", headers={"Authorization": "Bearer sekret"})
    assert bearer.status_code == 200
