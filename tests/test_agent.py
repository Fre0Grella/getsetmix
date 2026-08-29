"""The gsm-link companion — detection, verification, and its safety rules."""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import gsm_link

NEXTCLOUD_CFG = """\
[General]
optionalServerNotifications=true

[Accounts]
0\\Folders\\1\\journalPath=._sync_abc.db
0\\Folders\\1\\localPath=/home/marco/Nextcloud/
0\\Folders\\1\\targetPath=/
0\\Folders\\2\\localPath=/mnt/big/Music/
0\\Folders\\2\\targetPath=/Music
0\\url=https://cloud.example.com
"""


def test_parses_the_nextcloud_folder_map():
    """This is the auto-config: local root derived, never typed."""
    folders = gsm_link.parse_nextcloud_cfg(NEXTCLOUD_CFG)
    assert {"local": "/home/marco/Nextcloud", "remote": ""} in folders
    assert {"local": "/mnt/big/Music", "remote": "Music"} in folders


def test_nextcloud_parser_ignores_unrelated_keys():
    assert gsm_link.parse_nextcloud_cfg("[General]\nfoo=bar\n") == []


def test_windows_style_cfg_is_parsed():
    cfg = "[Accounts]\n0\\Folders\\1\\localPath=C:/Users/m/Nextcloud/\n" \
          "0\\Folders\\1\\targetPath=/\n"
    assert gsm_link.parse_nextcloud_cfg(cfg) == [
        {"local": "C:/Users/m/Nextcloud", "remote": ""}]


def _write_xml(path: Path, locations):
    root = ET.Element("DJ_PLAYLISTS", {"Version": "1.0.0"})
    coll = ET.SubElement(root, "COLLECTION")
    for i, loc in enumerate(locations, 1):
        ET.SubElement(coll, "TRACK", {"TrackID": str(i), "Location": loc})
    ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)


def test_verify_reports_every_track_resolving(tmp_path):
    audio = tmp_path / "a b.mp3"
    audio.write_bytes(b"\xff\xfb")
    xml = tmp_path / "gsm.xml"
    _write_xml(xml, [f"file://localhost{audio.as_posix().replace(' ', '%20')}"])
    report = gsm_link.verify_xml(str(xml))
    assert report["checked"] == 1 and report["resolved"] == 1
    assert report["missing"] == []


def test_verify_reports_the_files_it_cannot_find(tmp_path):
    xml = tmp_path / "gsm.xml"
    _write_xml(xml, ["file://localhost/nowhere/a.mp3"])
    report = gsm_link.verify_xml(str(xml))
    assert report["resolved"] == 0 and report["missing"] == ["/nowhere/a.mp3"]


def test_verify_explains_an_xml_that_has_not_synced_yet(tmp_path):
    report = gsm_link.verify_xml(str(tmp_path / "nope.xml"))
    assert "not arrived" in report["error"]


def test_verify_handles_a_corrupt_xml(tmp_path):
    xml = tmp_path / "bad.xml"
    xml.write_text("<not-xml")
    assert "unreadable" in gsm_link.verify_xml(str(xml))["error"]


def test_verify_respects_the_sample_limit(tmp_path):
    xml = tmp_path / "gsm.xml"
    _write_xml(xml, [f"file://localhost/x/{i}.mp3" for i in range(50)])
    assert gsm_link.verify_xml(str(xml), limit=5)["checked"] == 5


def test_windows_location_round_trip():
    assert gsm_link._path_from_location(
        "file://localhost/C:/Music/A%20Track.mp3") == "C:/Music/A Track.mp3"


# --------------------------------------------- the Rekordbox safety contract
def _options(tmp_path, pairs):
    path = tmp_path / "options.json"
    path.write_text(json.dumps({"options": pairs}), "utf-8")
    return path


def test_finds_an_existing_xml_option(tmp_path):
    path = _options(tmp_path, [["theme", "dark"], ["browse-xml-file", "C:/old.xml"]])
    assert gsm_link._find_xml_option(path) == "browse-xml-file"


def test_ignores_options_that_merely_mention_xml(tmp_path):
    path = _options(tmp_path, [["xml-enabled", "true"], ["other", "C:/x.xml"]])
    assert gsm_link._find_xml_option(path) == ""


def test_never_invents_a_key_when_none_exists(tmp_path, monkeypatch):
    """Writing a guessed key into an undocumented config is how you corrupt
    somebody's library — the agent stands down and reports 'manual' instead."""
    monkeypatch.setattr(gsm_link, "detect_rekordbox",
                        lambda: {"found": True, "xml_setting": "manual"})
    assert gsm_link.apply_rekordbox_xml("C:/new.xml") == "manual"


def test_updates_an_existing_option_and_backs_the_file_up(tmp_path, monkeypatch):
    path = _options(tmp_path, [["browse-xml-file", "C:/old.xml"]])
    monkeypatch.setattr(gsm_link, "detect_rekordbox", lambda: {
        "found": True, "xml_setting": "found",
        "options_file": str(path), "option_key": "browse-xml-file"})
    assert gsm_link.apply_rekordbox_xml("C:/new.xml") == "set"
    assert json.loads(path.read_text())["options"] == [["browse-xml-file", "C:/new.xml"]]
    backup = path.with_suffix(".json.gsm-backup")
    assert json.loads(backup.read_text())["options"] == [["browse-xml-file", "C:/old.xml"]]


def test_already_correct_setting_is_a_no_op(tmp_path, monkeypatch):
    path = _options(tmp_path, [["browse-xml-file", "C:/new.xml"]])
    monkeypatch.setattr(gsm_link, "detect_rekordbox", lambda: {
        "found": True, "xml_setting": "found",
        "options_file": str(path), "option_key": "browse-xml-file"})
    assert gsm_link.apply_rekordbox_xml("C:/new.xml") == "already-set"


def test_dry_run_does_not_touch_the_file(tmp_path, monkeypatch):
    path = _options(tmp_path, [["browse-xml-file", "C:/old.xml"]])
    monkeypatch.setattr(gsm_link, "detect_rekordbox", lambda: {
        "found": True, "xml_setting": "found",
        "options_file": str(path), "option_key": "browse-xml-file"})
    assert gsm_link.apply_rekordbox_xml("C:/new.xml", dry_run=True) == "would-set"
    assert json.loads(path.read_text())["options"] == [["browse-xml-file", "C:/old.xml"]]


def test_linux_reports_no_rekordbox(monkeypatch):
    monkeypatch.setattr(gsm_link, "host_os", lambda: "linux")
    info = gsm_link.detect_rekordbox()
    assert info["found"] is False and info["xml_setting"] == "unknown"


def test_collection_export_is_found_next_to_the_library(tmp_path):
    (tmp_path / "collection.xml").write_text("<x/>")
    assert gsm_link.find_collection_export(
        {"library_root": str(tmp_path)}) == str(tmp_path / "collection.xml")
    assert gsm_link.find_collection_export({"library_root": ""}) == ""


def test_machine_facts_are_json_serialisable():
    json.dumps(gsm_link.machine_facts())
