import xml.etree.ElementTree as ET
from pathlib import Path

from app.rekordbox import _location, add_track, find_duplicate, purge_imported

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


def test_purge_matches_real_world_variants(tmp_path: Path):
    """Regression for the reported failure: same songs whose artist punctuation
    and filenames differ between the GetSetMix inbox and the Rekordbox export
    must still be purged; genuinely-absent tracks must remain."""
    xml = tmp_path / "inbox.xml"
    # Inbox tracks exactly as GetSetMix wrote them (comma-joined artists).
    add_track(str(xml), {"title": "Wait So Long (RIOTZ Remix)",
                         "artist": "Swedish House Mafia"},
              str(_audio(tmp_path, "wait.mp3")), "Inbox")
    add_track(str(xml), {"title": "Woops (Dimitri Vegas & Junkie Kid Remix)",
                         "artist": "Bountyhunter, Dimitri Vegas, Junkie Kid, Stefan Melis"},
              str(_audio(tmp_path, "woops.mp3")), "Inbox")
    add_track(str(xml), {"title": "Hardtechno Tacata",
                         "artist": "Dustin Hertz, Tiago Garcia-Arenas"},
              str(_audio(tmp_path, "tacata.mp3")), "Inbox")
    add_track(str(xml), {"title": "Shake That Bunda", "artist": "Fantasm, The Straikerz"},
              str(_audio(tmp_path, "bunda.mp3")), "Inbox")

    # Collection variants as exported by Rekordbox (&-joined, extra suffix,
    # subset artist, different on-disk filename).
    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [
        {"Name": "Woops (Dimitri Vegas & Junkie Kid Remix)",
         "Artist": "Bountyhunter, Dimitri Vegas & Junkie Kid",
         "Location": "file://localhost/C:/Music/woops.mp3"},
        {"Name": "Hardtechno Tacata (Extended)", "Artist": "Dustin Hertz",
         "Location": "file://localhost/C:/Music/tacata-ext.mp3"},
        {"Name": "Shake That Bunda", "Artist": "Fantasm & The Straikerz",
         "Location": "file://localhost/C:/Music/Shake%20-%20Fantasm%20%26%20Straikerz.mp3"},
    ])

    assert purge_imported(str(xml), str(coll)) == 3
    remaining = [t.get("Name") for t in ET.parse(xml).getroot().iter("TRACK")
                 if t.get("Location")]
    assert remaining == ["Wait So Long (RIOTZ Remix)"]  # only the absent one stays


# ------------------------------------------------------------ find_duplicate
def test_duplicate_by_source_url(tmp_path: Path):
    xml = tmp_path / "inbox.xml"
    add_track(str(xml), META, str(_audio(tmp_path, "a.mp3")), "Inbox")
    # Same URL, even with totally different title -> caught via Comments source.
    reason = find_duplicate(
        {"url": META["url"], "title": "Renamed", "artist": "Someone"},
        [(str(xml), "the inbox")],
    )
    assert "the inbox" in reason


def test_duplicate_by_title_artist_ignores_filename(tmp_path: Path):
    # The collection only carries Name/Artist (no source URL, different file).
    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [{
        "Name": "Test Track", "Artist": "Tester",
        "Location": "file://localhost/wherever/RENAMED-BY-TEMPLATE.mp3",
    }])
    reason = find_duplicate(
        {"url": "https://other.example/x", "title": "Test Track", "artist": "Tester"},
        [(str(coll), "your collection")],
    )
    assert "your collection" in reason


def test_duplicate_fuzzy_strips_platform_noise(tmp_path: Path):
    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [{"Name": "Test Track", "Artist": "Tester",
                            "Location": "file://localhost/x.mp3"}])
    reason = find_duplicate(
        {"title": "Test Track (Official Video) [HD]", "artist": "Tester"},
        [(str(coll), "your collection")],
    )
    assert reason


def test_distinct_mixes_are_not_duplicates(tmp_path: Path):
    # Extended Mix vs Radio Edit are different tracks for a DJ -> no false match.
    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [{"Name": "Night Drive (Extended Mix)", "Artist": "DJ A",
                            "Location": "file://localhost/x.mp3"}])
    reason = find_duplicate(
        {"title": "Night Drive (Radio Edit)", "artist": "DJ A"},
        [(str(coll), "your collection")],
    )
    assert reason == ""


def test_no_duplicate_for_new_song(tmp_path: Path):
    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [{"Name": "Test Track", "Artist": "Tester",
                            "Location": "file://localhost/x.mp3"}])
    assert find_duplicate(
        {"title": "Brand New", "artist": "Nobody", "url": "https://x/y"},
        [(str(coll), "your collection"), (str(tmp_path / "missing.xml"), "the inbox")],
    ) == ""


def test_duplicate_artist_punctuation_differs(tmp_path: Path):
    # "Fantasm, The Straikerz" (inbox) vs "Fantasm & The Straikerz" (collection).
    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [{"Name": "Shake That Bunda",
                            "Artist": "Fantasm & The Straikerz",
                            "Location": "file://localhost/x.mp3"}])
    assert find_duplicate(
        {"title": "Shake That Bunda", "artist": "Fantasm, The Straikerz"},
        [(str(coll), "your collection")],
    )


def test_duplicate_extra_artist_and_version_suffix(tmp_path: Path):
    # "Hardtechno Tacata"/"Dustin Hertz, Tiago ..." matches the collection's
    # "Hardtechno Tacata (Extended)"/"Dustin Hertz" (subset title + artist).
    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [{"Name": "Hardtechno Tacata (Extended)",
                            "Artist": "Dustin Hertz",
                            "Location": "file://localhost/x.mp3"}])
    assert find_duplicate(
        {"title": "Hardtechno Tacata", "artist": "Dustin Hertz, Tiago Garcia-Arenas"},
        [(str(coll), "your collection")],
    )


def test_single_word_title_needs_exact_match(tmp_path: Path):
    # Guard against over-eager subset matching: "Go" is not "Go Hard".
    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [{"Name": "Go Hard", "Artist": "Same Artist",
                            "Location": "file://localhost/x.mp3"}])
    assert find_duplicate(
        {"title": "Go", "artist": "Same Artist"}, [(str(coll), "your collection")],
    ) == ""


def test_shared_word_is_not_a_duplicate(tmp_path: Path):
    # Real trap: "Hardtechno Tacata" must NOT match the unrelated Eurodance
    # "Tacata' OFFICIAL VIDEO" by Tacabro just because both contain "tacata".
    coll = tmp_path / "collection.xml"
    _collection_xml(coll, [{"Name": "Tacata' OFFICIAL VIDEO", "Artist": "Tacabro",
                            "Location": "file://localhost/x.mp3"}])
    assert find_duplicate(
        {"title": "Hardtechno Tacata", "artist": "Dustin Hertz, Tiago Garcia-Arenas"},
        [(str(coll), "your collection")],
    ) == ""
