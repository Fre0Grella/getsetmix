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
    "output_format": "mp3",            # "mp3" (320 kbps) | "flac"  -- global only
    "concurrency": 2,                   # global default parallel downloads
    "filename_template": "{artist} - {title}",
    "language": "en",                   # "en" | "it"
    "trash_days": 30,                   # Library trash kept this long; 0 = until emptied by hand
}

ENV_MAP = {
    "GSM_LIBRARY_ROOT": "library_root",
    "GSM_OUTPUT_FORMAT": "output_format",
    "GSM_CONCURRENCY": "concurrency",
    "GSM_FILENAME_TEMPLATE": "filename_template",
    "GSM_LANGUAGE": "language",
    "GSM_TRASH_DAYS": "trash_days",
}
INT_KEYS = ("concurrency", "trash_days")

# The values a setting may take. A stored or env value outside them is coerced
# on load (`Settings._normalize`); one sent to PUT /api/settings is refused
# (`patch_problem`).
OUTPUT_FORMATS = ("mp3", "flac")
LANGUAGES = ("it", "en")
CONCURRENCY_MIN, CONCURRENCY_MAX = 1, 8
TRASH_DAYS_MAX = 3650


def clamp_concurrency(n: int) -> int:
    """`n` parallel downloads, brought within CONCURRENCY_MIN..CONCURRENCY_MAX."""
    return max(CONCURRENCY_MIN, min(CONCURRENCY_MAX, n))


def patch_problem(patch: dict) -> str | None:
    """Why a settings patch is refused (the first value not allowed), or None."""
    if "output_format" in patch and patch["output_format"] not in OUTPUT_FORMATS:
        return "output_format must be 'mp3' or 'flac'"
    if "language" in patch and patch["language"] not in LANGUAGES:
        return "language must be 'it' or 'en'"
    if "concurrency" in patch and not (
            CONCURRENCY_MIN <= int(patch["concurrency"]) <= CONCURRENCY_MAX):
        return f"concurrency must be between {CONCURRENCY_MIN} and {CONCURRENCY_MAX}"
    if "trash_days" in patch and not 0 <= int(patch["trash_days"]) <= TRASH_DAYS_MAX:
        return f"trash_days must be between 0 and {TRASH_DAYS_MAX}"
    if "filename_template" in patch and not str(patch["filename_template"]).strip():
        return "filename_template cannot be empty"
    return None


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
                    # Keys this version no longer has (the Rekordbox XML
                    # settings, say) are dropped, not an error.
                    self.data.update({k: v for k, v in stored.items() if k in DEFAULTS})
                except Exception:
                    pass  # corrupt config -> fall back to defaults
            for env, key in ENV_MAP.items():
                if env in os.environ and os.environ[env] != "":
                    raw = os.environ[env]
                    if key in INT_KEYS:
                        try:
                            self.data[key] = int(raw)
                        except ValueError:
                            pass
                    else:
                        self.data[key] = raw
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
        fmt = str(self.data.get("output_format", DEFAULTS["output_format"])).lower()
        self.data["output_format"] = fmt if fmt in OUTPUT_FORMATS else DEFAULTS["output_format"]
        try:
            self.data["concurrency"] = clamp_concurrency(
                int(self.data.get("concurrency", DEFAULTS["concurrency"])))
        except (TypeError, ValueError):
            self.data["concurrency"] = DEFAULTS["concurrency"]
        try:
            days = int(self.data.get("trash_days", DEFAULTS["trash_days"]))
            self.data["trash_days"] = max(0, min(TRASH_DAYS_MAX, days))
        except (TypeError, ValueError):
            self.data["trash_days"] = DEFAULTS["trash_days"]
        if self.data.get("language") not in LANGUAGES:
            self.data["language"] = DEFAULTS["language"]
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
# One more token a paired computer may use on /api/link, besides the ones in
# DATA_DIR/link-tokens (app/link.py).
LINK_TOKEN = os.environ.get("GSM_LINK_TOKEN", "").strip()

settings = Settings()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "covers").mkdir(parents=True, exist_ok=True)
    Path(settings["library_root"]).mkdir(parents=True, exist_ok=True)
