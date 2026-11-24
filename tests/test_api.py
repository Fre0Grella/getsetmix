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


def test_app_version_is_semver(client):
    # The FastAPI version is wired to app.__version__, which semantic-release
    # bumps; guard that the wiring yields a valid X.Y.Z string.
    import re

    import app
    assert re.fullmatch(r"\d+\.\d+\.\d+", app.__version__)
    assert client.app.version == app.__version__


def test_manifest_served(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    body = r.json()
    assert body["share_target"]["action"] == "/share"


def test_service_worker_served(client):
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]


def test_share_serves_index(client):
    # Web Share Target landing returns the SPA; the link is read client-side.
    r = client.get("/share", params={"text": "https://youtu.be/dQw4w9WgXcQ"})
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


def test_old_xml_settings_are_ignored(tmp_path, monkeypatch):
    # A config.json from before the XML features went (2026-11-24) still loads.
    import json

    data = tmp_path / "data"
    data.mkdir()
    (data / "config.json").write_text(json.dumps({
        "xml_path": "/old/getsetmix.xml", "collection_xml_path": "/old/c.xml",
        "playlist_name": "Inbox", "concurrency": 3,
    }), "utf-8")
    monkeypatch.setenv("GSM_DATA_DIR", str(data))
    monkeypatch.setenv("GSM_XML_PATH", "/old/env.xml")
    import app.config
    importlib.reload(app.config)
    s = app.config.settings.data
    assert s["concurrency"] == 3
    assert not {"xml_path", "collection_xml_path", "playlist_name"} & set(s)


def test_settings_put_ignores_old_xml_fields(client):
    r = client.put("/api/settings", json={"xml_path": "/x.xml", "concurrency": 4})
    assert r.status_code == 200
    assert "xml_path" not in r.json() and r.json()["concurrency"] == 4


def test_fs_list(client, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.xml").write_text("<x/>")
    body = client.get("/api/fs/list", params={"path": str(tmp_path)}).json()
    assert "sub" in [d["name"] for d in body["dirs"]]
    assert "files" not in body  # the folder picker lists folders only
    assert body["parent"]


def test_batch_start_gates_on_duplicate(client):
    import app.main as m
    tid = m.db.create_track(
        "https://x/y", status="staged", title="Dup", artist="A",
        duplicate=1, duplicate_reason="A – Dup", duplicate_of=7,
    )
    m._checked_rev = m.library.current().rev()  # the Library has not changed
    # Default (force=false) must not download; it asks for confirmation.
    body = client.post("/api/batch/start", json={"ids": [tid]}).json()
    assert body["needs_confirm"] is True
    assert body["queued"] == []
    assert body["duplicates"][0]["id"] == tid
    assert body["duplicates"][0]["reason"] == "A – Dup"


def test_purge_inbox_scope_is_gone(client):
    assert client.post("/api/purge", json={"scope": "inbox"}).status_code == 400


def test_auth_blocks_api(auth_client):
    assert auth_client.get("/api/tracks").status_code == 401
    assert auth_client.get("/metrics").status_code == 401
    assert auth_client.get("/api/ping").status_code == 200
    ok = auth_client.get("/api/tracks", headers={"X-Auth-Token": "sekret"})
    assert ok.status_code == 200
    bearer = auth_client.get("/api/tracks", headers={"Authorization": "Bearer sekret"})
    assert bearer.status_code == 200


def test_licenses_are_public_and_readable(auth_client):
    # Readable without the auth token, like /healthz: the footer link is a
    # plain browser navigation.
    r = auth_client.get("/licenses")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "Third-party notices" in r.text
    assert "/licenses/agpl" in r.text
    full = auth_client.get("/licenses/agpl")
    assert full.status_code == 200
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in full.text
