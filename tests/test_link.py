"""Pairing and sync with the gsm-link companion."""
import importlib

import pytest
from fastapi.testclient import TestClient

MACHINE = {
    "hostname": "Studio-PC",
    "os": "windows",
    "nextcloud": [{"local": "C:\\Users\\marco\\Nextcloud", "remote": "/"}],
    "music_dirs": ["C:\\Users\\marco\\Music"],
    "rekordbox": {"found": True, "xml_setting": "manual"},
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    monkeypatch.delenv("GSM_AUTH_TOKEN", raising=False)
    import app.config
    import app.db
    import app.link
    import app.main
    import app.worker
    importlib.reload(app.config)
    importlib.reload(app.db)
    importlib.reload(app.worker)
    importlib.reload(app.link)
    importlib.reload(app.main)
    with TestClient(app.main.app) as c:
        yield c


def _pair(client, machine=MACHINE, profile_id=None):
    code = client.post("/api/link/code", json={"profile_id": profile_id}).json()["code"]
    return client.post("/api/link/pair", json={"code": code, "machine": machine})


def test_pairing_creates_a_profile_named_after_the_machine(client):
    r = _pair(client)
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["profile"]["id"] == "studio-pc"
    assert body["profile"]["os"] == "windows"
    assert body["config"]["playlist_name"] == "Inbox"


def test_pairing_code_is_single_use(client):
    code = client.post("/api/link/code", json={}).json()["code"]
    assert client.post("/api/link/pair", json={"code": code, "machine": MACHINE}).status_code == 200
    assert client.post("/api/link/pair", json={"code": code, "machine": MACHINE}).status_code == 403


def test_bad_code_is_rejected(client):
    client.post("/api/link/code", json={})
    assert client.post("/api/link/pair", json={"code": "000000", "machine": {}}).status_code == 403


def test_guessing_burns_the_outstanding_codes(client):
    """A 6-digit code is only acceptable because guessing kills it."""
    import app.link as link
    code = client.post("/api/link/code", json={}).json()["code"]
    wrong = "999999" if code != "999999" else "111111"
    for _ in range(link.MAX_CODE_ATTEMPTS):
        client.post("/api/link/pair", json={"code": wrong, "machine": {}})
    assert client.post("/api/link/pair", json={"code": code, "machine": MACHINE}).status_code == 403


def test_agent_token_is_never_exposed_over_the_ui_api(client):
    token = _pair(client).json()["token"]
    profiles = client.get("/api/profiles").json()["profiles"]
    assert "agent_token" not in profiles[0]
    assert profiles[0]["paired"] is True
    assert token not in client.get("/api/settings").text


def test_sync_requires_the_agent_token(client):
    _pair(client)
    assert client.post("/api/link/sync", json={}).status_code == 401
    assert client.post("/api/link/sync", json={},
                       headers={"X-GSM-Agent-Token": "nope"}).status_code == 401


def test_sync_records_the_report_and_returns_config(client):
    token = _pair(client).json()["token"]
    r = client.post(
        "/api/link/sync",
        headers={"X-GSM-Agent-Token": token},
        json={"machine": MACHINE,
              "report": {"checked": 5, "resolved": 5, "rekordbox_xml": "manual"}},
    )
    assert r.status_code == 200
    assert r.json()["config"]["profile_id"] == "studio-pc"
    assert r.json()["profile"]["last_seen"]
    assert r.json()["profile"]["last_report"]["resolved"] == 5


def test_sync_surfaces_missing_files_in_health(client):
    token = _pair(client).json()["token"]
    client.put("/api/profiles/studio-pc", json={"library_root": "C:\\DJ"})
    client.post("/api/link/sync", headers={"X-GSM-Agent-Token": token},
                json={"report": {"checked": 10, "resolved": 2,
                                 "missing": ["C:\\DJ\\a.mp3"]}})
    body = client.get("/api/health/link").json()
    assert body["status"] == "error"
    assert any(c["id"] == "agent_files" and c["level"] == "error" for c in body["checks"])


def test_agent_learns_the_collection_export_path(client):
    token = _pair(client).json()["token"]
    client.post("/api/link/sync", headers={"X-GSM-Agent-Token": token},
                json={"report": {"collection_xml_path": "/srv/exports/collection.xml"}})
    profile = client.get("/api/profiles").json()["profiles"][0]
    assert profile["collection_xml_path"] == "/srv/exports/collection.xml"


def test_repairing_an_existing_profile_keeps_its_id(client):
    pid = client.post("/api/profiles", json={"name": "Studio", "library_root": "C:\\DJ"}).json()["id"]
    body = _pair(client, profile_id=pid).json()
    assert body["profile"]["id"] == pid
    assert body["profile"]["library_root"] == "C:\\DJ"  # existing config preserved


def test_library_root_is_suggested_from_the_nextcloud_folder_map(client):
    """The auto-config: the user never types the DJ-side path."""
    client.put("/api/settings", json={"webdav_root": "Music/DJ"})
    machine = dict(MACHINE, nextcloud=[
        {"local": "C:\\Users\\marco\\Nextcloud", "remote": "/"},
        {"local": "D:\\Sync\\Music", "remote": "Music"},
    ])
    body = _pair(client, machine=machine).json()
    assert body["profile"]["library_root"] == "D:\\Sync\\Music\\DJ"


def test_single_sync_folder_is_used_when_nothing_else_matches(client):
    machine = dict(MACHINE, nextcloud=[{"local": "/home/m/Nextcloud", "remote": "x"}])
    body = _pair(client, machine=machine).json()
    assert body["profile"]["library_root"] == "/home/m/Nextcloud"


def test_pairing_endpoints_bypass_ui_auth_but_sync_still_needs_its_token(tmp_path, monkeypatch):
    """With GSM_AUTH_TOKEN set the agent has no UI token — it must still pair."""
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    monkeypatch.setenv("GSM_AUTH_TOKEN", "sekret")
    import app.config
    import app.db
    import app.link
    import app.main
    import app.worker
    importlib.reload(app.config)
    importlib.reload(app.db)
    importlib.reload(app.worker)
    importlib.reload(app.link)
    importlib.reload(app.main)
    with TestClient(app.main.app) as c:
        assert c.post("/api/link/code", json={}).status_code == 401
        code = c.post("/api/link/code", json={},
                      headers={"X-Auth-Token": "sekret"}).json()["code"]
        # No UI token on the agent's calls.
        r = c.post("/api/link/pair", json={"code": code, "machine": MACHINE})
        assert r.status_code == 200
        token = r.json()["token"]
        assert c.post("/api/link/sync", json={},
                      headers={"X-GSM-Agent-Token": token}).status_code == 200
        assert c.post("/api/link/sync", json={}).status_code == 401


# --------------------------------------------- end-to-end with the real agent
def test_full_pair_verify_loop_with_the_real_agent(client, tmp_path, monkeypatch):
    """The whole point, exercised end to end: the server writes an XML with
    DJ-side paths, the agent on that machine resolves them, and the server's
    health goes green."""
    import sys
    from pathlib import Path as P
    sys.path.insert(0, str(P(__file__).resolve().parents[1] / "agent"))
    import gsm_link

    import app.config

    # This machine plays the DJ machine: its "library root" is a real folder.
    dj_library = tmp_path / "dj-library"
    dj_library.mkdir()
    monkeypatch.setattr(gsm_link, "CONFIG_PATH", tmp_path / "link.json")
    monkeypatch.setattr(gsm_link, "machine_facts", lambda: {
        "hostname": "Studio-PC", "os": gsm_link.host_os(),
        "nextcloud": [{"local": str(dj_library), "remote": ""}],
        "music_dirs": [str(dj_library)], "rekordbox": {"found": False},
    })
    # Route the agent's HTTP through the test client.
    def fake_request(server, path, payload, token=""):
        headers = {"X-GSM-Agent-Token": token} if token else {}
        r = client.post(path, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()
    monkeypatch.setattr(gsm_link, "request", fake_request)

    code = client.post("/api/link/code", json={}).json()["code"]
    assert gsm_link.cmd_pair(_ns(server="http://test", code=code)) == 0

    stored = gsm_link.load_config()
    assert stored["profile_id"] == "studio-pc"
    # The single sync folder was adopted as this machine's library root.
    assert stored["config"]["library_root"] == str(dj_library)

    # Server ingests a track; the XML it writes for this profile must point at
    # a path the agent can open.
    server_library = P(app.config.settings["library_root"])
    (server_library / "Sub").mkdir(parents=True, exist_ok=True)
    (server_library / "Sub" / "A - B.mp3").write_bytes(b"\xff\xfb\x90\x00")
    (dj_library / "Sub").mkdir(parents=True, exist_ok=True)
    (dj_library / "Sub" / "A - B.mp3").write_bytes(b"\xff\xfb\x90\x00")

    import app.worker
    app.worker.worker._write_xml({"title": "B", "artist": "A"},
                                 server_library / "Sub" / "A - B.mp3")

    # The profile's XML lives on the server; the agent reads it at its own path.
    profile = client.get("/api/profiles").json()["profiles"][0]
    import shutil
    server_xml = P(app.config.settings["library_root"]) / f"getsetmix-{profile['id']}.xml"
    shutil.copy(server_xml, profile["dj_xml_path"])  # stand in for the sync

    report = gsm_link.sync_once(gsm_link.load_config(), apply_prefs=False)
    assert report["checked"] == 1 and report["resolved"] == 1

    health = client.get("/api/health/link").json()
    assert any(c["id"] == "agent_files" and c["level"] == "ok" for c in health["checks"])
    assert not any(c["level"] == "error" for c in health["checks"])


class _ns:
    def __init__(self, **kw):
        self.__dict__.update(kw)
