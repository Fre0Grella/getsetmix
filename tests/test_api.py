import importlib
from pathlib import Path

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
    import app.main
    import app.worker
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
    import app.main
    import app.worker
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


def test_settings_collection_xml_roundtrip(client, tmp_path):
    p = str(tmp_path / "collection.xml")
    r = client.put("/api/settings", json={"collection_xml_path": p})
    assert r.status_code == 200
    assert client.get("/api/settings").json()["collection_xml_path"] == p
    r = client.put("/api/settings", json={"collection_xml_path": ""})
    assert r.json()["collection_xml_path"] == ""  # clearing disables the purge


def test_fs_list(client, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.xml").write_text("<x/>")
    (tmp_path / "b.txt").write_text("hi")
    body = client.get("/api/fs/list", params={"path": str(tmp_path), "ext": ".xml"}).json()
    assert "sub" in [d["name"] for d in body["dirs"]]
    assert [f["name"] for f in body["files"]] == ["a.xml"]  # ext filter applied
    assert body["parent"]


def test_batch_start_gates_on_duplicate(client):
    import app.main as m
    tid = m.db.create_track(
        "https://x/y", status="staged", title="Dup", artist="A",
        duplicate=1, duplicate_reason="already in the inbox",
    )
    # Default (force=false) must not download; it asks for confirmation.
    body = client.post("/api/batch/start", json={"ids": [tid]}).json()
    assert body["needs_confirm"] is True
    assert body["queued"] == []
    assert body["duplicates"][0]["id"] == tid
    assert body["duplicates"][0]["reason"] == "already in the inbox"


def test_purge_inbox_requires_collection_xml(client):
    # Without a collection XML configured, manual inbox clean is a 400.
    r = client.post("/api/purge", json={"scope": "inbox"})
    assert r.status_code == 400


def test_purge_inbox_scope(client, tmp_path):
    import xml.etree.ElementTree as ET

    from app.rekordbox import add_track
    inbox = str(tmp_path / "data" / "rekordbox" / "getsetmix.xml")
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 64)
    add_track(inbox, {"title": "Dup", "artist": "A"}, str(audio), "Inbox")

    coll = tmp_path / "collection.xml"
    root = ET.Element("DJ_PLAYLISTS", {"Version": "1.0.0"})
    c = ET.SubElement(root, "COLLECTION", {"Entries": "1"})
    ET.SubElement(c, "TRACK", {"TrackID": "1", "Name": "Dup", "Artist": "A",
                               "Location": "file://localhost/elsewhere/dup.mp3"})
    ET.ElementTree(root).write(coll, encoding="UTF-8", xml_declaration=True)

    client.put("/api/settings", json={"xml_path": inbox, "collection_xml_path": str(coll)})
    r = client.post("/api/purge", json={"scope": "inbox"})
    assert r.status_code == 200
    assert r.json() == {"purged": 1, "scope": "inbox"}


def test_auth_blocks_api(auth_client):
    assert auth_client.get("/api/tracks").status_code == 401
    assert auth_client.get("/metrics").status_code == 401
    assert auth_client.get("/api/ping").status_code == 200
    ok = auth_client.get("/api/tracks", headers={"X-Auth-Token": "sekret"})
    assert ok.status_code == 200
    bearer = auth_client.get("/api/tracks", headers={"Authorization": "Bearer sekret"})
    assert bearer.status_code == 200


# ----------------------------------------------------------- machine profiles
def test_profile_crud(client):
    r = client.post("/api/profiles", json={
        "name": "Studio PC", "os": "windows",
        "library_root": "C:\\Users\\marco\\Nextcloud\\Music",
    })
    assert r.status_code == 201
    pid = r.json()["id"]
    assert pid == "studio-pc"
    assert r.json()["dj_xml_path"].endswith("getsetmix-studio-pc.xml")

    assert [p["id"] for p in client.get("/api/profiles").json()["profiles"]] == [pid]

    r = client.put(f"/api/profiles/{pid}", json={"library_root": "D:\\DJ"})
    assert r.json()["library_root"] == "D:\\DJ"

    assert client.delete(f"/api/profiles/{pid}").status_code == 204
    assert client.get("/api/profiles").json()["profiles"] == []
    assert client.put(f"/api/profiles/{pid}", json={"name": "x"}).status_code == 404


def test_profile_names_collide_into_distinct_ids(client):
    a = client.post("/api/profiles", json={"name": "Laptop", "library_root": "/a"}).json()
    b = client.post("/api/profiles", json={"name": "Laptop", "library_root": "/b"}).json()
    assert a["id"] == "laptop" and b["id"] == "laptop-2"


def test_path_preview_shows_the_real_location_string(client):
    r = client.post("/api/profiles/preview", json={
        "os": "windows", "library_root": "C:\\Music", "sample": "Artist - Title.mp3",
    })
    body = r.json()
    assert body["mapped"] is True
    assert body["dj_path"] == "C:\\Music\\Artist - Title.mp3"
    assert body["location"] == "file://localhost/C:/Music/Artist%20-%20Title.mp3"


def test_path_preview_flags_a_root_it_cannot_map(client):
    body = client.post("/api/profiles/preview",
                       json={"os": "windows", "library_root": ""}).json()
    assert body["mapped"] is False


def test_ingest_fans_out_one_xml_per_profile(client, tmp_path):
    """One download, two machines, two XMLs, each with its own path space."""
    import xml.etree.ElementTree as ET

    import app.config
    import app.worker

    client.post("/api/profiles", json={
        "name": "Studio", "os": "windows", "library_root": "C:\\DJ",
        "server_xml_path": str(tmp_path / "studio.xml"),
    })
    client.post("/api/profiles", json={
        "name": "Laptop", "os": "macos", "library_root": "/Users/m/Music",
        "server_xml_path": str(tmp_path / "laptop.xml"),
    })

    library = app.config.settings["library_root"]
    audio = Path(library) / "Sub" / "A - B.mp3"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"\xff\xfb\x90\x00")

    app.worker.worker._write_xml({"title": "B", "artist": "A"}, audio)

    win = ET.parse(tmp_path / "studio.xml").getroot().find("COLLECTION/TRACK")
    mac = ET.parse(tmp_path / "laptop.xml").getroot().find("COLLECTION/TRACK")
    assert win.get("Location") == "file://localhost/C:/DJ/Sub/A%20-%20B.mp3"
    assert mac.get("Location") == "file://localhost/Users/m/Music/Sub/A%20-%20B.mp3"


def test_secrets_are_never_echoed_back(client):
    client.put("/api/settings", json={"webdav_pass": "app-password"})
    s = client.get("/api/settings").json()
    assert "webdav_pass" not in s
    assert s["webdav_pass_set"] is True
    # A blank on save means "unchanged", not "delete".
    client.put("/api/settings", json={"webdav_pass": "", "webdav_user": "marco"})
    assert client.get("/api/settings").json()["webdav_pass_set"] is True


def test_theme_and_setup_flag_roundtrip(client):
    client.put("/api/settings", json={"theme": "light", "setup_complete": True})
    s = client.get("/api/settings").json()
    assert s["theme"] == "light" and s["setup_complete"] is True
    assert client.put("/api/settings", json={"theme": "neon"}).status_code in (400, 422)


def test_link_health_endpoint(client):
    body = client.get("/api/health/link").json()
    assert body["status"] in ("ok", "warn", "error")
    assert any(c["id"] == "library" for c in body["checks"])
