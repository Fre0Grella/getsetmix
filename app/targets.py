"""Where a finished download gets written.

One ingested file fans out into one XML per configured machine profile, each
carrying Locations valid on that machine. With no profiles configured this
collapses to the legacy single `xml_path` with no mapping, so existing installs
behave exactly as before.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Imported as a module, not `from .config import settings`: the test suite
# reloads app.config, which rebinds `settings` to a fresh object. Looking it up
# through the module keeps this file pointing at the live instance.
from . import config
from .profiles import Profile


@dataclass
class XmlTarget:
    xml_path: str                 # server-side file we write
    label: str                    # human name for messages
    profile: Profile | None = None

    def location(self, server_path: str) -> str | None:
        """Location URI to stamp, or None to let the writer use the local path."""
        if self.profile is None:
            return None
        return self.profile.location_for(server_path, config.settings["library_root"])

    def maps_cleanly(self, server_path: str) -> bool:
        if self.profile is None:
            return True
        return self.profile.map_path(server_path, config.settings["library_root"])[1]

    @property
    def collection_xml(self) -> str:
        if self.profile is not None:
            return self.profile.collection_xml_path.strip()
        return str(config.settings.get("collection_xml_path") or "").strip()


def _fallback_xml_dir() -> str:
    return str(Path(config.settings["xml_path"]).parent or (config.DATA_DIR / "rekordbox"))


def write_targets() -> list[XmlTarget]:
    """Every XML a new download must be appended to."""
    profiles = config.settings.active_profiles()
    if not profiles:
        return [XmlTarget(xml_path=str(config.settings["xml_path"]), label="the inbox")]
    library = str(config.settings["library_root"])
    fallback = _fallback_xml_dir()
    return [
        XmlTarget(
            xml_path=p.server_xml(library, fallback),
            label=p.name or p.id,
            profile=p,
        )
        for p in profiles
    ]


def dup_sources() -> list[tuple[str, str]]:
    """(xml_path, label) pairs a candidate track is checked against: every
    inbox we write, plus each machine's full collection export."""
    sources: list[tuple[str, str]] = []
    for t in write_targets():
        sources.append((t.xml_path, "the inbox" if t.profile is None else f"the {t.label} inbox"))
        coll = t.collection_xml
        if coll:
            sources.append((coll, "your collection"))
    # De-duplicate while preserving order: several profiles may share one export.
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for path, label in sources:
        if path and path not in seen:
            seen.add(path)
            out.append((path, label))
    return out


def purge_pairs() -> list[tuple[str, str]]:
    """(inbox_xml, collection_xml) pairs to run the already-imported purge on."""
    return [(t.xml_path, t.collection_xml) for t in write_targets() if t.collection_xml]
