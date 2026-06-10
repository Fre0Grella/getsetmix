"""Rekordbox XML writer.

Maintains a DJ_PLAYLISTS XML file (rekordbox import format). Tracks are added
to the COLLECTION and referenced from the configured playlist (default
"Inbox"). Rekordbox must reload the XML source manually after ingestion.
"""
from __future__ import annotations

import re
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


def purge_imported(inbox_xml: str, collection_xml: str) -> int:
    """Drop inbox tracks that already exist in the user's full Rekordbox
    collection export, so the inbox XML only lists not-yet-imported songs.
    Matching is by URL / Location / title+artist token sets (see _same_song),
    so punctuation and filename differences don't hide a match.
    Returns how many tracks were removed."""
    with _lock:
        inbox = Path(inbox_xml)
        collection = Path(collection_xml)
        if not inbox.exists() or not collection.exists():
            return 0
        if inbox.resolve() == collection.resolve():
            return 0  # misconfiguration guard: never purge the inbox against itself

        # Unreadable collection -> _records returns [] -> nothing removed.
        imported = _records(collection_xml, "")

        tree = _load(inbox)
        root = tree.getroot()
        coll = root.find("COLLECTION")
        if coll is None:
            return 0
        removed_ids: set[str] = set()
        for t in list(coll.findall("TRACK")):
            rec = _track_record(t)
            if any(_same_song(rec, c) for c in imported):
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


# ---------------------------------------------------- duplicate detection
# Two entries are "the same song" when the exact source URL matches, the file
# Location matches, or the title+artist match as *token sets* — independent of
# punctuation and of the filename (the naming template can change). Token-set
# matching is what makes real-world variants line up, e.g.:
#   "Fantasm, The Straikerz"            == "Fantasm & The Straikerz"
#   "Hardtechno Tacata" / "Dustin H..." == "Hardtechno Tacata (Extended)" / "Dustin H."
#   "Woops (... Remix)" / "A, B, C, D"  == "Woops (... Remix)" / "A, B & C"
# while still keeping genuinely different versions apart, e.g.
#   "Night Drive (Extended Mix)"        != "Night Drive (Radio Edit)".

# Platform cruft stripped before tokenizing. We deliberately keep remix/mix/edit
# words so different versions of a track stay distinct.
_NOISE = re.compile(
    r"\b(official|officiel|video|videoclip|audio|lyrics?|visuali[sz]er|hd|hq|4k|"
    r"mv|m/v|explicit|feat\.?|ft\.?)\b",
    re.I,
)


def _norm(value: str) -> str:
    s = (value or "").lower()
    s = _NOISE.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(value: str) -> frozenset[str]:
    return frozenset(_norm(value).split())


def _norm_url(value: str) -> str:
    return (value or "").strip().lower().rstrip("/")


def _loc_key(location: str) -> str:
    return unquote(location).strip().lower() if location else ""


def _source_url(track: ET.Element) -> str:
    """Source URL we stamp into Comments as 'Source: <url>' when ingesting."""
    comments = (track.get("Comments") or "").strip()
    if comments.lower().startswith("source:"):
        return comments.split(":", 1)[1].strip()
    return ""


def _subset(a: frozenset[str], b: frozenset[str], *, allow_single: bool) -> bool:
    """True if the smaller token set is contained in the larger. A single-token
    set only matches a larger one when `allow_single` (used for artists, where
    'Avicii' ⊆ 'Avicii & X' is fine, but a one-word *title* must match exactly)."""
    if not a or not b:
        return False
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    if not small <= big:
        return False
    return small == big or len(small) >= 2 or allow_single


def _same_song(a: dict, b: dict) -> bool:
    """a/b are records: {name, artist, url, loc} (any field may be "")."""
    if a["url"] and b["url"] and a["url"] == b["url"]:
        return True
    if a["loc"] and b["loc"] and a["loc"] == b["loc"]:
        return True
    if not _subset(_tokens(a["name"]), _tokens(b["name"]), allow_single=False):
        return False
    aa, ab = _tokens(a["artist"]), _tokens(b["artist"])
    if not aa and not ab:
        return True  # both artist-less and titles already line up
    return _subset(aa, ab, allow_single=True)


def _meta_record(meta: dict) -> dict:
    return {
        "name": meta.get("title") or "", "artist": meta.get("artist") or "",
        "url": _norm_url(meta.get("url") or ""), "loc": "",
    }


def _track_record(track: ET.Element, where: str = "") -> dict:
    return {
        "name": (track.get("Name") or "").strip(),
        "artist": (track.get("Artist") or "").strip(),
        "url": _norm_url(_source_url(track)),
        "loc": _loc_key(track.get("Location") or ""),
        "where": where,
    }


# Parsed records are cached per (path, mtime) so a fan-out of fetches that each
# check the same (possibly large) collection XML parses it only once.
_id_cache: dict[str, tuple[float, list[dict]]] = {}


def _records(path_str: str, where: str) -> list[dict]:
    p = Path(path_str)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return []
    cached = _id_cache.get(path_str)
    if cached and cached[0] == mtime:
        return cached[1]
    recs: list[dict] = []
    try:
        for t in ET.parse(p).getroot().iter("TRACK"):
            if t.get("Location"):  # collection entries; playlist refs only have Key
                recs.append(_track_record(t, where))
    except ET.ParseError:
        recs = []
    _id_cache[path_str] = (mtime, recs)
    return recs


def find_duplicate(meta: dict, sources: list[tuple[str, str]]) -> str:
    """Return a human-readable reason if `meta` already exists in any of the
    given (xml_path, label) sources, else "". Matches by source URL, file
    Location, or title+artist token sets — never by raw filename."""
    cand = _meta_record(meta)
    if not cand["url"] and not _tokens(cand["name"]):
        return ""
    for path, where in sources:
        for rec in _records(path, where):
            if _same_song(cand, rec):
                if cand["url"] and rec["url"] and cand["url"] == rec["url"]:
                    return f"same source URL already in {where}"
                label = f'{rec["artist"]} – {rec["name"]}'.strip(" –")
                return f'“{label}” already in {where}'
    return ""
