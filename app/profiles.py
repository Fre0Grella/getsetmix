"""Machine profiles and library-relative path mapping.

A track's identity is its path *relative to the library root* — never an
absolute one. The server stores files under its own root (`/music` in Docker);
the machine running Rekordbox sees the same files under a different root
(`C:\\Users\\marco\\Nextcloud\\Music`). A profile records one such machine, and
the XML written for it carries Locations that are valid *there*.

With no profiles configured the writer falls back to the legacy single-XML
behaviour (identity mapping against `xml_path`), so existing installs keep
working untouched.
"""
from __future__ import annotations

import ntpath
import os
import posixpath
import re
from dataclasses import dataclass, field
from urllib.parse import quote

OS_CHOICES = ("windows", "macos", "linux")

# Characters left unescaped in a Location URI. Rekordbox is picky here: it wants
# a percent-encoded UTF-8 file:// URI but tolerates these punctuation marks raw.
_URI_SAFE = "/:()&'!$+,;=@~._-"

_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(value: str, fallback: str = "machine") -> str:
    out = _SLUG.sub("-", (value or "").strip().lower()).strip("-")
    return out[:40] or fallback


def normalize_os(value: str) -> str:
    v = (value or "").strip().lower()
    if v in OS_CHOICES:
        return v
    if v in ("win", "win32", "windows_nt", "nt"):
        return "windows"
    if v in ("darwin", "mac", "osx", "mac os x"):
        return "macos"
    return "linux"


def host_os() -> str:
    return "windows" if os.name == "nt" else normalize_os(os.uname().sysname if hasattr(os, "uname") else "linux")


# ------------------------------------------------------------------- paths
def _mod(os_style: str):
    return ntpath if os_style == "windows" else posixpath


def norm_root(root: str, os_style: str) -> str:
    """Trim a root path to a comparable form: no trailing separator, no
    redundant '.' segments. Deliberately does NOT resolve symlinks — resolving
    would silently rewrite a configured root into a path the user never chose,
    which is exactly how the old writer produced unmappable Locations."""
    r = (root or "").strip()
    if not r:
        return ""
    m = _mod(os_style)
    r = m.normpath(r)
    # normpath leaves "C:\\" and "/" alone; strip separators from anything else
    if len(r) > 1:
        r = r.rstrip("\\/") or r
    return r


def _casefold(value: str, os_style: str) -> str:
    # Windows and macOS are case-insensitive in practice; Linux is not.
    return value.lower() if os_style in ("windows", "macos") else value


def to_relative(abs_path: str, root: str, os_style: str = "") -> str | None:
    """Library-relative, forward-slashed path for `abs_path`, or None when the
    file lives outside `root` (the caller then falls back to no mapping and the
    health check flags it)."""
    style = os_style or host_os()
    m = _mod(style)
    root_n = norm_root(root, style)
    if not root_n:
        return None
    path_n = m.normpath((abs_path or "").strip())
    if not path_n:
        return None
    a, b = _casefold(path_n, style), _casefold(root_n, style)
    if a == b:
        return ""
    sep_variants = tuple(s for s in ("\\", "/") if s in (m.sep, m.altsep or m.sep))
    if not any(a.startswith(b + s) for s in sep_variants):
        return None
    rel = path_n[len(root_n) + 1:]
    return rel.replace("\\", "/")


def join_relative(root: str, rel: str, os_style: str) -> str:
    """Join a forward-slashed relative path onto a root in `os_style` form."""
    root_n = norm_root(root, os_style)
    rel = (rel or "").strip("/")
    if not rel:
        return root_n
    if os_style == "windows":
        return root_n.rstrip("\\") + "\\" + rel.replace("/", "\\")
    return root_n.rstrip("/") + "/" + rel


def location_uri(path: str, os_style: str) -> str:
    """`file://localhost/…` URI as Rekordbox expects it.

    Windows drive paths become `/C:/Users/…` — the leading slash is required or
    Rekordbox reads the drive letter as the host component.
    """
    p = (path or "").replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://localhost" + quote(p, safe=_URI_SAFE)


def path_from_location(location: str) -> str:
    """Inverse of `location_uri` — the plain path a Location points at."""
    from urllib.parse import unquote

    p = unquote((location or "").strip())
    for prefix in ("file://localhost", "file://"):
        if p.startswith(prefix):
            p = p[len(prefix):]
            break
    # "/C:/Users/x" -> "C:/Users/x"
    if re.match(r"^/[A-Za-z]:", p):
        p = p[1:]
    return p


# ---------------------------------------------------------------- profiles
@dataclass
class Profile:
    id: str
    name: str = ""
    os: str = "linux"
    library_root: str = ""          # DJ-side root
    xml_path: str = ""              # DJ-side XML path Rekordbox should point at
    server_xml_path: str = ""       # server-side file we actually write
    collection_xml_path: str = ""   # server-readable collection export
    enabled: bool = True
    agent_token: str = ""
    last_seen: str = ""
    machine: dict = field(default_factory=dict)   # facts reported by the agent
    last_report: dict = field(default_factory=dict)

    # ------------------------------------------------------------ derived
    def dj_xml_path(self) -> str:
        """Where Rekordbox on that machine should look. Defaults inside the
        library root so the sync tool carries the XML along with the music."""
        if self.xml_path.strip():
            return self.xml_path.strip()
        if not self.library_root.strip():
            return ""
        return join_relative(self.library_root, f"getsetmix-{self.id}.xml", self.os)

    def server_xml(self, server_library_root: str, data_fallback: str) -> str:
        """The file the server writes for this profile."""
        if self.server_xml_path.strip():
            return self.server_xml_path.strip()
        if server_library_root.strip():
            return join_relative(server_library_root, f"getsetmix-{self.id}.xml", host_os())
        return join_relative(data_fallback, f"getsetmix-{self.id}.xml", host_os())

    def map_path(self, server_path: str, server_library_root: str) -> tuple[str, bool]:
        """Server absolute path -> DJ-machine absolute path.

        Returns (path, mapped). `mapped` is False when the file isn't under the
        server library root or the profile has no root — the path is passed
        through unchanged and the health check reports it.
        """
        rel = to_relative(server_path, server_library_root)
        if rel is None or not self.library_root.strip():
            return server_path, False
        return join_relative(self.library_root, rel, self.os), True

    def location_for(self, server_path: str, server_library_root: str) -> str:
        mapped, ok = self.map_path(server_path, server_library_root)
        return location_uri(mapped, self.os if ok else host_os())

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "os": self.os,
            "library_root": self.library_root, "xml_path": self.xml_path,
            "server_xml_path": self.server_xml_path,
            "collection_xml_path": self.collection_xml_path,
            "enabled": self.enabled, "agent_token": self.agent_token,
            "last_seen": self.last_seen, "machine": self.machine,
            "last_report": self.last_report,
        }

    def public(self) -> dict:
        """Same, minus the agent secret."""
        d = self.to_dict()
        d.pop("agent_token", None)
        d["paired"] = bool(self.agent_token)
        d["dj_xml_path"] = self.dj_xml_path()
        return d


def from_dict(raw: dict) -> Profile:
    pid = slugify(str(raw.get("id") or raw.get("name") or ""))
    return Profile(
        id=pid,
        name=str(raw.get("name") or pid),
        os=normalize_os(str(raw.get("os") or "")),
        library_root=str(raw.get("library_root") or ""),
        xml_path=str(raw.get("xml_path") or ""),
        server_xml_path=str(raw.get("server_xml_path") or ""),
        collection_xml_path=str(raw.get("collection_xml_path") or ""),
        enabled=bool(raw.get("enabled", True)),
        agent_token=str(raw.get("agent_token") or ""),
        last_seen=str(raw.get("last_seen") or ""),
        machine=dict(raw.get("machine") or {}),
        last_report=dict(raw.get("last_report") or {}),
    )


def unique_id(base: str, taken: list[str]) -> str:
    pid = slugify(base)
    if pid not in taken:
        return pid
    n = 2
    while f"{pid}-{n}" in taken:
        n += 1
    return f"{pid}-{n}"
