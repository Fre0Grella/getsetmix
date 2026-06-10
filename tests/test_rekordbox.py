import xml.etree.ElementTree as ET
from pathlib import Path

from app.rekordbox import _location, add_track, purge_imported

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


# ----------------------------------------------------------- purge_imported
def _collection_xml(path: Path, tracks: list[dict]) -> None:
    root = ET.Element("DJ_PLAYLISTS", {"Version": "1.0.0"})
    coll = ET.SubElement(root, "COLLECTION", {"Entries": str(len(tracks))})
    for i, attrs in enumerate(tracks, 1):
        ET.SubElement(coll, "TRACK", {"TrackID": str(i), **attrs})
    ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)


def test_purge_removes_tracks_already_in_collection(tmp_path: Path):
    xml = tmp_path / "inbox.xml"
    a, b = _audio(tmp_path, "a.mp3"), _audio(tmp_path, "b.mp3")
    add_track(str(xml), META, str(a), "Inbox")
    add_track(str(xml), {**META, "title": "Other"}, str(b), "Inbox")

    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [{"Name": "X", "Artist": "Y", "Location": _location(str(a))}])

    assert purge_imported(str(xml), str(coll)) == 1
    root = ET.parse(xml).getroot()
    assert root.find("COLLECTION").get("Entries") == "1"
    remaining = root.find("COLLECTION/TRACK")
    assert remaining.get("Name") == "Other"
    node = root.find(".//NODE[@Name='Inbox']")
    assert node.get("Entries") == "1"
    assert node.find("TRACK").get("Key") == remaining.get("TrackID")


def test_purge_matches_by_title_and_artist(tmp_path: Path):
    xml = tmp_path / "inbox.xml"
    add_track(str(xml), META, str(_audio(tmp_path, "a.mp3")), "Inbox")
    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [{
        "Name": "TEST TRACK", "Artist": "tester",
        "Location": "file://localhost/elsewhere/x.mp3",
    }])
    assert purge_imported(str(xml), str(coll)) == 1
    assert ET.parse(xml).getroot().find("COLLECTION").get("Entries") == "0"


def test_purge_is_noop_for_missing_or_self(tmp_path: Path):
    xml = tmp_path / "inbox.xml"
    add_track(str(xml), META, str(_audio(tmp_path, "a.mp3")), "Inbox")
    assert purge_imported(str(xml), str(tmp_path / "missing.xml")) == 0
    assert purge_imported(str(xml), str(xml)) == 0  # never purge against itself
    assert ET.parse(xml).getroot().find("COLLECTION").get("Entries") == "1"
