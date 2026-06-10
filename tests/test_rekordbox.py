import xml.etree.ElementTree as ET
from pathlib import Path

from app.rekordbox import add_track

META = {
    "title": "Test Track",
    "artist": "Tester",
    "album": "Singles",
    "genre": "House",
    "url": "https://example.com/v",
    "duration": 120,
}


def _audio(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 413)
    return p


def test_creates_collection_and_playlist(tmp_path: Path):
    xml = tmp_path / "rb.xml"
    tid = add_track(str(xml), META, str(_audio(tmp_path, "a.mp3")), "Inbox")
    assert tid == 1
    root = ET.parse(xml).getroot()
    assert root.tag == "DJ_PLAYLISTS"
    coll = root.find("COLLECTION")
    assert coll.get("Entries") == "1"
    node = root.find(".//NODE[@Name='Inbox']")
    assert node.get("Entries") == "1"
    assert node.find("TRACK").get("Key") == "1"


def test_track_ids_increment(tmp_path: Path):
    xml = tmp_path / "rb.xml"
    add_track(str(xml), META, str(_audio(tmp_path, "a.mp3")), "Inbox")
    tid = add_track(str(xml), META, str(_audio(tmp_path, "b.mp3")), "Inbox")
    assert tid == 2
    coll = ET.parse(xml).getroot().find("COLLECTION")
    assert [t.get("TrackID") for t in coll] == ["1", "2"]


def test_location_is_file_uri(tmp_path: Path):
    xml = tmp_path / "rb.xml"
    audio = _audio(tmp_path, "a track.mp3")
    add_track(str(xml), META, str(audio), "Inbox")
    loc = ET.parse(xml).getroot().find("COLLECTION/TRACK").get("Location")
    assert loc.startswith("file://localhost/")
    assert " " not in loc  # quoted


def test_corrupt_xml_recovers(tmp_path: Path):
    xml = tmp_path / "rb.xml"
    xml.write_text("<not-xml")
    tid = add_track(str(xml), META, str(_audio(tmp_path, "a.mp3")), "Inbox")
    assert tid == 1
    assert (tmp_path / "rb.corrupt.xml").exists()
    assert ET.parse(xml).getroot().tag == "DJ_PLAYLISTS"
