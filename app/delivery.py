"""Optional WebDAV delivery (Nextcloud).

The old advice for getting files onto the DJ machine was "mount it or sync it
yourself", which is awkward exactly where GetSetMix is meant to run — a
container that has no business hosting a Nextcloud sync client. Pushing over
WebDAV instead removes the mount entirely, and gives the path mapping a clean
seam: the *remote* path is the shared language between server and DJ machine,
and the companion resolves it to a local one from the sync client's own config.
"""
from __future__ import annotations

import base64
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config
from .profiles import to_relative

log = logging.getLogger("getsetmix.delivery")

TIMEOUT = 120
_QUOTE_SAFE = "/"


class DeliveryError(RuntimeError):
    pass


def enabled() -> bool:
    s = config.settings
    return (
        s.get("delivery_mode") == "webdav"
        and bool(str(s.get("webdav_url") or "").strip())
        and bool(str(s.get("webdav_user") or "").strip())
        and bool(str(s.get("webdav_pass") or "").strip())
    )


def _base_url() -> str:
    return str(config.settings["webdav_url"]).strip().rstrip("/")


def _auth_header() -> str:
    raw = f"{config.settings['webdav_user']}:{config.settings['webdav_pass']}"
    return "Basic " + base64.b64encode(raw.encode("utf-8")).decode("ascii")


def remote_relative(server_path: str) -> str | None:
    """Where a server-side file belongs in the remote tree, relative to the
    WebDAV root. None when the file is outside the library."""
    rel = to_relative(server_path, str(config.settings["library_root"]))
    if rel is None:
        return None
    root = str(config.settings.get("webdav_root") or "").strip("/")
    return f"{root}/{rel}" if root else rel


def _url_for(remote_rel: str) -> str:
    return _base_url() + "/" + urllib.parse.quote(remote_rel.strip("/"), safe=_QUOTE_SAFE)


def _request(method: str, url: str, data=None, headers: dict | None = None):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", _auth_header())
    req.add_header("User-Agent", "GetSetMix")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def _mkcol(remote_dir: str) -> None:
    """Create one collection. 405 means it already exists, which is success."""
    if not remote_dir.strip("/"):
        return
    try:
        _request("MKCOL", _url_for(remote_dir)).close()
    except urllib.error.HTTPError as exc:
        if exc.code not in (405, 301):  # already exists / redirect to existing
            raise DeliveryError(f"MKCOL {remote_dir} failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise DeliveryError(f"cannot reach the WebDAV server: {exc.reason}") from exc


def ensure_parents(remote_rel: str) -> None:
    """WebDAV has no mkdir -p; walk the tree creating each level."""
    parts = [p for p in remote_rel.strip("/").split("/")[:-1] if p]
    for i in range(1, len(parts) + 1):
        _mkcol("/".join(parts[:i]))


def upload(local_path: str, remote_rel: str) -> str:
    """PUT one file, creating parent collections as needed. Returns its URL."""
    path = Path(local_path)
    size = path.stat().st_size
    ensure_parents(remote_rel)
    url = _url_for(remote_rel)
    try:
        # Streamed, not read into memory: a FLAC set is not a small payload.
        with path.open("rb") as handle:
            _request("PUT", url, data=handle, headers={
                "Content-Length": str(size),
                "Content-Type": "application/octet-stream",
            }).close()
    except urllib.error.HTTPError as exc:
        raise DeliveryError(f"upload of {path.name} failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise DeliveryError(f"cannot reach the WebDAV server: {exc.reason}") from exc
    return url


def deliver_file(server_path: str) -> str | None:
    """Push an ingested file if WebDAV delivery is on. Returns the remote path."""
    if not enabled():
        return None
    remote_rel = remote_relative(server_path)
    if remote_rel is None:
        log.warning("%s is outside the library root — not uploaded", server_path)
        return None
    upload(server_path, remote_rel)
    log.info("uploaded %s -> %s", Path(server_path).name, remote_rel)
    return remote_rel


def deliver_xml(xml_path: str) -> str | None:
    """The XML has to travel with the music or Rekordbox has nothing to read."""
    if not enabled():
        return None
    remote_rel = remote_relative(xml_path)
    if remote_rel is None:
        # An XML kept outside the library still belongs in the remote root, or
        # the DJ machine can never see it.
        root = str(config.settings.get("webdav_root") or "").strip("/")
        name = Path(xml_path).name
        remote_rel = f"{root}/{name}" if root else name
    upload(xml_path, remote_rel)
    return remote_rel


def check() -> tuple[bool, str]:
    """Can we actually talk to the configured WebDAV endpoint?"""
    if not enabled():
        return True, "not in use"
    root = str(config.settings.get("webdav_root") or "").strip("/")
    try:
        _request("PROPFIND", _url_for(root) if root else _base_url() + "/",
                 headers={"Depth": "0"}).close()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "authentication rejected — use a Nextcloud app password, not your login"
        if exc.code == 404:
            return False, f"the remote folder '{root}' does not exist"
        return False, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, f"cannot reach the server ({exc.reason})"
    except OSError as exc:
        return False, str(exc)
    return True, "reachable"
