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
from urllib.parse import quote

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
