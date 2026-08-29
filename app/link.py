"""Pairing and sync for the gsm-link companion.

The server cannot know where Nextcloud actually synced the library on the DJ
machine, nor where Rekordbox keeps its preferences. The companion can. It pairs
once with a short-lived code, then polls: pushing what it found and what it can
see, and receiving the configuration it should apply.

Transport is deliberately plain polling — no websockets to keep alive through a
homelab reverse proxy, and an agent that dies just stops reporting.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from . import config
from .profiles import Profile, normalize_os, slugify, unique_id

CODE_TTL_SECONDS = 10 * 60
# A 6-digit code is only safe because it is short-lived and gives up quickly.
MAX_CODE_ATTEMPTS = 8


@dataclass
class PairingCode:
    code: str
    profile_id: str        # "" -> create a new profile on claim
    expires_at: float
    attempts: int = 0

    @property
    def expired(self) -> bool:
        return time.time() > self.expires_at


class _CodeStore:
    """In-memory and deliberately so: a pairing code must not survive a restart."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._codes: dict[str, PairingCode] = {}

    def _sweep(self) -> None:
        for code in [c for c, v in self._codes.items() if v.expired]:
            self._codes.pop(code, None)

    def issue(self, profile_id: str = "") -> PairingCode:
        with self._lock:
            self._sweep()
            code = f"{secrets.randbelow(1_000_000):06d}"
            entry = PairingCode(code, profile_id, time.time() + CODE_TTL_SECONDS)
            self._codes[code] = entry
            return entry

    def claim(self, code: str) -> PairingCode | None:
        """One-shot: a successful claim consumes the code."""
        with self._lock:
            self._sweep()
            entry = self._codes.get((code or "").strip())
            if entry is None:
                # Burn an attempt on every outstanding code so guessing at the
                # keyspace exhausts the codes rather than finding one.
                for other in self._codes.values():
                    other.attempts += 1
                    if other.attempts >= MAX_CODE_ATTEMPTS:
                        other.expires_at = 0
                self._sweep()
                return None
            self._codes.pop(entry.code, None)
            return entry

    def clear(self) -> None:
        with self._lock:
            self._codes.clear()


codes = _CodeStore()


# ------------------------------------------------------------- suggestions
def suggest_library_root(machine: dict) -> str:
    """Best guess at the DJ machine's library root, from what it detected.

    Prefers a Nextcloud sync folder whose remote path lines up with where the
    server puts files; falls back to a folder that merely looks like a music
    library. Returning "" is fine — the wizard then asks.
    """
    folders = [f for f in (machine.get("nextcloud") or []) if f.get("local")]
    remote_root = str(config.settings.get("webdav_root") or "").strip("/")

    if remote_root:
        for folder in folders:
            remote = str(folder.get("remote") or "").strip("/")
            if not remote:
                continue
            if remote_root == remote:
                return str(folder["local"])
            if remote_root.startswith(remote + "/"):
                rest = remote_root[len(remote) + 1:]
                from .profiles import join_relative
                return join_relative(str(folder["local"]), rest,
                                     normalize_os(machine.get("os", "")))

    library_name = str(config.settings["library_root"]).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    for folder in folders:
        remote = str(folder.get("remote") or "").strip("/")
        if remote and remote.rsplit("/", 1)[-1].lower() == library_name.lower():
            return str(folder["local"])
    if len(folders) == 1:
        return str(folders[0]["local"])

    candidates = machine.get("music_dirs") or []
    return str(candidates[0]) if len(candidates) == 1 else ""


def profile_config(profile: Profile) -> dict:
    """What the agent should apply on its machine."""
    return {
        "profile_id": profile.id,
        "name": profile.name or profile.id,
        "library_root": profile.library_root,
        "xml_path": profile.dj_xml_path(),
        "playlist_name": str(config.settings["playlist_name"]),
        "verify_sample": 25,
    }


# ------------------------------------------------------------------ pairing
def pair(code: str, machine: dict) -> tuple[Profile, str] | None:
    """Claim a pairing code. Returns (profile, agent_token) or None."""
    entry = codes.claim(code)
    if entry is None:
        return None

    os_name = normalize_os(str(machine.get("os") or ""))
    hostname = str(machine.get("hostname") or "").strip() or "DJ machine"

    profile = config.settings.get_profile(entry.profile_id) if entry.profile_id else None
    if profile is None:
        taken = [p.id for p in config.settings.profiles()]
        pid = entry.profile_id or unique_id(slugify(hostname), taken)
        profile = Profile(id=pid, name=hostname)

    profile.os = os_name
    profile.machine = machine
    profile.agent_token = secrets.token_urlsafe(32)
    if not profile.library_root.strip():
        profile.library_root = suggest_library_root(machine)
    config.settings.upsert_profile(profile)
    return profile, profile.agent_token


def authenticate(token: str) -> Profile | None:
    if not token:
        return None
    for profile in config.settings.profiles():
        if profile.agent_token and secrets.compare_digest(profile.agent_token, token):
            return profile
    return None


def record_sync(profile: Profile, machine: dict, report: dict, seen_at: str) -> Profile:
    """Store what the agent reported and hand back the desired config."""
    if machine:
        profile.machine = machine
        profile.os = normalize_os(str(machine.get("os") or profile.os))
        if not profile.library_root.strip():
            profile.library_root = suggest_library_root(machine)
    if report:
        profile.last_report = report
        # The agent is the only thing that knows where that machine's own
        # collection export lives, once the user points Rekordbox at it.
        remote_coll = str(report.get("collection_xml_path") or "").strip()
        if remote_coll and not profile.collection_xml_path.strip():
            profile.collection_xml_path = remote_coll
    profile.last_seen = seen_at
    config.settings.upsert_profile(profile)
    return profile
