"""GetSetMix configuration.

Settings live in DATA_DIR/config.json and can be overridden by environment
variables (useful for Docker/Kubernetes). Env always wins at boot; values
changed from the UI are persisted back to config.json.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

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
}

ENV_MAP = {
    "GSM_LIBRARY_ROOT": "library_root",
    "GSM_XML_PATH": "xml_path",
    "GSM_COLLECTION_XML_PATH": "collection_xml_path",
    "GSM_PLAYLIST_NAME": "playlist_name",
    "GSM_OUTPUT_FORMAT": "output_format",
    "GSM_CONCURRENCY": "concurrency",
    "GSM_FILENAME_TEMPLATE": "filename_template",
    "GSM_LANGUAGE": "language",
}

_lock = threading.Lock()


class Settings:
    def __init__(self) -> None:
        self.path = DATA_DIR / "config.json"
        self.data: dict = dict(DEFAULTS)
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
