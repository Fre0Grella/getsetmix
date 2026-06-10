"""Rekordbox XML writer.

Maintains a DJ_PLAYLISTS XML file (rekordbox import format). Tracks are added
to the COLLECTION and referenced from the configured playlist (default
"Inbox"). Rekordbox must reload the XML source manually after ingestion.
"""
from __future__ import annotations

import threading
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote

_lock = threading.Lock()

KIND_BY_EXT = {".mp3": "MP3 File", ".flac": "FLAC File"}


def _location(file_path: str) -> str:
    p = Path(file_path).resolve().as_posix()
    if not p.startswith("/"):
        p = "/" + p  # Windows drive paths: C:/x -> /C:/x
    return "file://localhost" + quote(p, safe="/:()&'!$+,;=@~._-")


def _empty_doc() -> ET.ElementTree:
    root = ET.Element("DJ_PLAYLISTS", {"Version": "1.0.0"})
    ET.SubElement(root, "PRODUCT", {
        "Name": "GetSetMix", "Version": "1.0.0", "Company": "homelab",
    })
    ET.SubElement(root, "COLLECTION", {"Entries": "0"})
    playlists = ET.SubElement(root, "PLAYLISTS")
    ET.SubElement(playlists, "NODE", {"Type": "0", "Name": "ROOT", "Count": "0"})
    return ET.ElementTree(root)


def _load(path: Path) -> ET.ElementTree:
    if path.exists() and path.stat().st_size > 0:
        try:
            return ET.parse(path)
        except ET.ParseError:
            backup = path.with_suffix(".corrupt.xml")
            path.replace(backup)
    return _empty_doc()


def _playlist_node(tree: ET.ElementTree, name: str) -> ET.Element:
    root = tree.getroot()
    playlists = root.find("PLAYLISTS")
    if playlists is None:
        playlists = ET.SubElement(root, "PLAYLISTS")
    root_node = playlists.find("NODE")
    if root_node is None:
        root_node = ET.SubElement(playlists, "NODE", {"Type": "0", "Name": "ROOT", "Count": "0"})
    for node in root_node.findall("NODE"):
        if node.get("Name") == name:
            return node
    node = ET.SubElement(root_node, "NODE", {
        "Name": name, "Type": "1", "KeyType": "0", "Entries": "0",
    })
    root_node.set("Count", str(len(root_node.findall("NODE"))))
    return node


def add_track(xml_path: str, meta: dict, file_path: str, playlist_name: str) -> int:
    """Append one track to collection + playlist. Returns the TrackID."""
    with _lock:
        path = Path(xml_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tree = _load(path)
        root = tree.getroot()
        collection = root.find("COLLECTION")
        if collection is None:
            collection = ET.SubElement(root, "COLLECTION", {"Entries": "0"})

        existing = collection.findall("TRACK")
        track_id = 1 + max((int(t.get("TrackID", "0")) for t in existing), default=0)

        ext = Path(file_path).suffix.lower()
        size = 0
        try:
            size = Path(file_path).stat().st_size
        except OSError:
            pass

        ET.SubElement(collection, "TRACK", {
            "TrackID": str(track_id),
            "Name": meta.get("title") or "",
            "Artist": meta.get("artist") or "",
            "Album": meta.get("album") or "",
            "Genre": meta.get("genre") or "",
            "Kind": KIND_BY_EXT.get(ext, "MP3 File"),
            "Size": str(size),
            "TotalTime": str(int(round(float(meta.get("duration") or 0)))),
            "DateAdded": date.today().isoformat(),
            "Comments": f"Source: {meta.get('url', '')}",
            "Location": _location(file_path),
        })
        collection.set("Entries", str(len(collection.findall("TRACK"))))

        node = _playlist_node(tree, playlist_name)
        ET.SubElement(node, "TRACK", {"Key": str(track_id)})
        node.set("Entries", str(len(node.findall("TRACK"))))

        ET.indent(tree, space="  ")
        tmp = path.with_suffix(".tmp")
        tree.write(tmp, encoding="UTF-8", xml_declaration=True)
        tmp.replace(path)
        return track_id


def _identity_keys(track: ET.Element) -> set[tuple]:
    """Keys that identify the same song across XML files: the file Location
    (case-insensitive, unquoted) and, as a fallback for moved/re-encoded
    files, the (title, artist) pair."""
    keys: set[tuple] = set()
    loc = (track.get("Location") or "").strip()
    if loc:
        keys.add(("loc", unquote(loc).lower()))
    name = (track.get("Name") or "").strip().lower()
    artist = (track.get("Artist") or "").strip().lower()
    if name and artist:
        keys.add(("meta", name, artist))
    return keys


def purge_imported(inbox_xml: str, collection_xml: str) -> int:
    """Drop inbox tracks that already exist in the user's full Rekordbox
    collection export, so the inbox XML only lists not-yet-imported songs.
    Returns how many tracks were removed."""
    with _lock:
        inbox = Path(inbox_xml)
        collection = Path(collection_xml)
        if not inbox.exists() or not collection.exists():
            return 0
        if inbox.resolve() == collection.resolve():
            return 0  # misconfiguration guard: never purge the inbox against itself
        try:
            imported: set[tuple] = set()
            for t in ET.parse(collection).getroot().iter("TRACK"):
                if t.get("Location"):  # collection entries; playlist refs only have Key
                    imported |= _identity_keys(t)
        except ET.ParseError:
            return 0  # unreadable collection -> leave the inbox untouched

        tree = _load(inbox)
        root = tree.getroot()
        coll = root.find("COLLECTION")
        if coll is None:
            return 0
        removed_ids: set[str] = set()
        for t in list(coll.findall("TRACK")):
            if _identity_keys(t) & imported:
                coll.remove(t)
                removed_ids.add(t.get("TrackID", ""))
        if not removed_ids:
            return 0
        coll.set("Entries", str(len(coll.findall("TRACK"))))

        playlists = root.find("PLAYLISTS")
        if playlists is not None:
            for node in playlists.iter("NODE"):
                if node.get("Type") != "1":
                    continue
                for ref in list(node.findall("TRACK")):
                    if ref.get("Key") in removed_ids:
                        node.remove(ref)
                node.set("Entries", str(len(node.findall("TRACK"))))

        ET.indent(tree, space="  ")
        tmp = inbox.with_suffix(".tmp")
        tree.write(tmp, encoding="UTF-8", xml_declaration=True)
        tmp.replace(inbox)
        return len(removed_ids)
