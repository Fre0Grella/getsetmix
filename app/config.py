"""GetSetMix configuration.

Settings live in DATA_DIR/config.json and can be overridden by environment
variables (useful for Docker/Kubernetes). Env always wins at boot; values
changed from the UI are persisted back to config.json.
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path

from . import profiles as profiles_mod

DATA_DIR = Path(os.environ.get("GSM_DATA_DIR", "./data")).resolve()

DEFAULTS = {
    "library_root": str(DATA_DIR / "library"),
    "xml_path": str(DATA_DIR / "rekordbox" / "getsetmix.xml"),
    "collection_xml_path": "",          # full Rekordbox collection export (optional)
    "playlist_name": "Inbox",
    "output_format": "mp3",            # "mp3" (320 kbps) | "flac"  -- global only
    "concurrency": 2,                   # global default parallel downloads
    "filename_template": "{artist} - {title}",
    "language": "en",                   # "en" | "it"
    "theme": "dark",                    # "dark" | "light" | "auto"
    "setup_complete": False,            # has the setup wizard been run?
    # One entry per machine that runs Rekordbox. Empty -> legacy single-XML mode.
    "profiles": [],
    # How files reach the DJ machine. "filesystem" = the library root is already
    # shared (mount / sync client on the server); "webdav" = push to Nextcloud.
    "delivery_mode": "filesystem",
    "webdav_url": "",                   # .../remote.php/dav/files/<user>
    "webdav_user": "",
    "webdav_pass": "",                  # Nextcloud *app password*, not the login
    "webdav_root": "",                  # remote folder the library maps onto
}

# Written by the UI but never echoed back to it.
SECRET_KEYS = ("webdav_pass",)

ENV_MAP = {
    "GSM_LIBRARY_ROOT": "library_root",
    "GSM_XML_PATH": "xml_path",
    "GSM_COLLECTION_XML_PATH": "collection_xml_path",
    "GSM_PLAYLIST_NAME": "playlist_name",
    "GSM_OUTPUT_FORMAT": "output_format",
    "GSM_CONCURRENCY": "concurrency",
    "GSM_FILENAME_TEMPLATE": "filename_template",
    "GSM_LANGUAGE": "language",
    "GSM_THEME": "theme",
    "GSM_DELIVERY_MODE": "delivery_mode",
    "GSM_WEBDAV_URL": "webdav_url",
    "GSM_WEBDAV_USER": "webdav_user",
    "GSM_WEBDAV_PASS": "webdav_pass",
    "GSM_WEBDAV_ROOT": "webdav_root",
}

_lock = threading.Lock()


class Settings:
    def __init__(self) -> None:
        self.path = DATA_DIR / "config.json"
        # deep copy: DEFAULTS holds a mutable list ("profiles") that must not be
        # shared between Settings instances (the test suite reloads the module).
        self.data: dict = copy.deepcopy(DEFAULTS)
        self.load()

    # ------------------------------------------------------------------ io
    def load(self) -> None:
        with _lock:
            if self.path.exists():
                try:
                    stored = json.loads(self.path.read_text("utf-8"))
                    self.data.update({k: v for k, v in stored.items() if k in DEFAULTS})
                except Exception:
                    pass  # corrupt config -> fall back to defaults
            for env, key in ENV_MAP.items():
                if env in os.environ and os.environ[env] != "":
                    val: object = os.environ[env]
                    if key == "concurrency":
                        try:
                            val = int(val)  # type: ignore[arg-type]
                        except ValueError:
                            continue
                    self.data[key] = val
            self._normalize()

    def save(self) -> None:
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2), "utf-8")

    # --------------------------------------------------------------- update
    def update(self, patch: dict) -> dict:
        clean = {k: v for k, v in patch.items() if k in DEFAULTS and v is not None}
        self.data.update(clean)
        self._normalize()
        self.save()
        return self.data

    def _normalize(self) -> None:
        self.data["output_format"] = str(self.data.get("output_format", "mp3")).lower()
        if self.data["output_format"] not in ("mp3", "flac"):
            self.data["output_format"] = "mp3"
        try:
            self.data["concurrency"] = max(1, min(8, int(self.data.get("concurrency", 2))))
        except (TypeError, ValueError):
            self.data["concurrency"] = 2
        if self.data.get("language") not in ("it", "en"):
            self.data["language"] = "en"
        if not str(self.data.get("filename_template") or "").strip():
            self.data["filename_template"] = DEFAULTS["filename_template"]
        if self.data.get("theme") not in ("dark", "light", "auto"):
            self.data["theme"] = "dark"
        if self.data.get("delivery_mode") not in ("filesystem", "webdav"):
            self.data["delivery_mode"] = "filesystem"
        self.data["setup_complete"] = bool(self.data.get("setup_complete"))
        raw = self.data.get("profiles")
        self.data["profiles"] = [p for p in (raw if isinstance(raw, list) else []) if p]

    # ------------------------------------------------------------ profiles
    def profiles(self) -> list[profiles_mod.Profile]:
        return [profiles_mod.from_dict(p) for p in self.data.get("profiles", [])]

    def active_profiles(self) -> list[profiles_mod.Profile]:
        return [p for p in self.profiles() if p.enabled and p.library_root.strip()]

    def get_profile(self, pid: str) -> profiles_mod.Profile | None:
        for p in self.profiles():
            if p.id == pid:
                return p
        return None

    def save_profiles(self, items: list[profiles_mod.Profile]) -> None:
        self.data["profiles"] = [p.to_dict() for p in items]
        self.save()

    def upsert_profile(self, profile: profiles_mod.Profile) -> profiles_mod.Profile:
        items = self.profiles()
        for i, p in enumerate(items):
            if p.id == profile.id:
                items[i] = profile
                break
        else:
            items.append(profile)
        self.save_profiles(items)
        return profile

    def delete_profile(self, pid: str) -> bool:
        items = self.profiles()
        kept = [p for p in items if p.id != pid]
        if len(kept) == len(items):
            return False
        self.save_profiles(kept)
        return True

    def public(self) -> dict:
        """Settings as handed to the UI: secrets masked, profiles sanitised."""
        out = {k: v for k, v in self.data.items() if k not in SECRET_KEYS}
        for key in SECRET_KEYS:
            out[f"{key}_set"] = bool(str(self.data.get(key) or "").strip())
        out["profiles"] = [p.public() for p in self.profiles()]
        return out

    # --------------------------------------------------------------- access
    def __getitem__(self, key: str):
        return self.data[key]

    def get(self, key: str, default=None):
        return self.data.get(key, default)


# Optional access protection (private-by-default; set one of these only if
# the instance is exposed publicly).
AUTH_TOKEN = os.environ.get("GSM_AUTH_TOKEN", "").strip()
BASIC_USER = os.environ.get("GSM_BASIC_USER", "").strip()
BASIC_PASS = os.environ.get("GSM_BASIC_PASS", "").strip()

settings = Settings()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "covers").mkdir(parents=True, exist_ok=True)
    Path(settings["library_root"]).mkdir(parents=True, exist_ok=True)
    Path(settings["xml_path"]).parent.mkdir(parents=True, exist_ok=True)
    # Each machine profile writes its own XML; make sure those dirs exist too.
    fallback = str(Path(settings["xml_path"]).parent)
    for profile in settings.active_profiles():
        target = profile.server_xml(str(settings["library_root"]), fallback)
        if target:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
