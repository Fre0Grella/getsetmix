"""The link health checks — the layer that makes a broken setup visible."""
import importlib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    import app.config
    import app.db
    import app.health
    importlib.reload(app.config)
    importlib.reload(app.db)
    importlib.reload(app.health)
    app.config.ensure_dirs()
    return app.config, app.health, tmp_path


def _levels(report, check_id):
    return [c["level"] for c in report["checks"] if c["id"] == check_id]


def test_clean_install_reports_the_unrun_wizard(env):
    _, health, _ = env
    report = health.run()
    assert _levels(report, "setup") == ["warn"]
    assert _levels(report, "library") == ["ok"]


def test_unwritable_library_is_an_error(env):
    config, health, _ = env
    config.settings.update({"library_root": "/proc/nope/library"})
    report = health.run()
    assert _levels(report, "library") == ["error"]
    assert report["status"] == "error"


def test_resolvable_locations_pass(env):
    config, health, _ = env
    from app.rekordbox import add_track
    audio = Path(config.settings["library_root"]) / "a.mp3"
    audio.write_bytes(b"\xff\xfb\x90\x00")
    add_track(config.settings["xml_path"], {"title": "A", "artist": "B"}, str(audio), "Inbox")
    report = health.run()
    assert _levels(report, "locations") == ["ok"]


def test_missing_files_are_caught(env):
    """The exact failure the old writer produced: XML entries whose files
    aren't where the Location says."""
    config, health, _ = env
    from app.rekordbox import add_track
    audio = Path(config.settings["library_root"]) / "gone.mp3"
    audio.write_bytes(b"\xff\xfb\x90\x00")
    add_track(config.settings["xml_path"], {"title": "A", "artist": "B"}, str(audio), "Inbox")
    audio.unlink()
    report = health.run()
    assert _levels(report, "locations") == ["error"]
    assert report["status"] == "error"


def test_profile_locations_are_verified_by_mapping_back(env):
    config, health, tmp_path = env
    from app.rekordbox import add_track
    library = config.settings["library_root"]
    audio = Path(library) / "Sub" / "a.mp3"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"\xff\xfb\x90\x00")

    import app.profiles as pm
    profile = pm.Profile(id="studio", name="Studio", os="windows",
                         library_root="C:\\DJ",
                         server_xml_path=str(tmp_path / "studio.xml"))
    config.settings.upsert_profile(profile)

    add_track(str(tmp_path / "studio.xml"), {"title": "A", "artist": "B"},
              str(audio), "Inbox",
              location=profile.location_for(str(audio), library))
    # The XML holds C:\DJ\Sub\a.mp3; health maps it back to the server path.
    assert _levels(health.run(), "locations") == ["ok"]


def test_stale_collection_export_warns(env):
    config, health, tmp_path = env
    import os
    import time
    coll = tmp_path / "collection.xml"
    ET.ElementTree(ET.Element("DJ_PLAYLISTS")).write(coll)
    old = time.time() - 60 * 86400
    os.utime(coll, (old, old))
    config.settings.update({"collection_xml_path": str(coll)})
    report = health.run()
    assert _levels(report, "collection") == ["warn"]
    title = next(c["title"] for c in report["checks"] if c["id"] == "collection")
    assert "stale" in title


def test_missing_collection_export_is_an_error(env):
    config, health, tmp_path = env
    config.settings.update({"collection_xml_path": str(tmp_path / "nope.xml")})
    assert _levels(health.run(), "collection") == ["error"]


def test_unpaired_profile_warns_and_offline_agent_warns(env):
    config, health, tmp_path = env
    import app.profiles as pm
    config.settings.upsert_profile(pm.Profile(
        id="studio", name="Studio", os="windows", library_root="C:\\DJ",
        server_xml_path=str(tmp_path / "s.xml")))
    assert _levels(health.run(), "agent") == ["warn"]

    config.settings.upsert_profile(pm.Profile(
        id="studio", name="Studio", os="windows", library_root="C:\\DJ",
        server_xml_path=str(tmp_path / "s.xml"),
        agent_token="tok", last_seen="2020-01-01T00:00:00+00:00"))
    assert _levels(health.run(), "agent") == ["warn"]


def test_agent_report_of_missing_files_is_an_error(env):
    config, health, tmp_path = env
    import app.profiles as pm
    from app.db import now_iso
    config.settings.upsert_profile(pm.Profile(
        id="studio", name="Studio", os="windows", library_root="C:\\DJ",
        server_xml_path=str(tmp_path / "s.xml"), agent_token="tok",
        last_seen=now_iso(),
        last_report={"checked": 10, "resolved": 4, "missing": ["C:\\DJ\\a.mp3"]}))
    report = health.run()
    assert _levels(report, "agent_files") == ["error"]
    assert report["status"] == "error"


def test_profile_without_library_root_is_flagged(env):
    config, health, _ = env
    import app.profiles as pm
    config.settings.upsert_profile(pm.Profile(id="broken", name="Broken"))
    assert _levels(health.run(), "profiles") == ["error"]
