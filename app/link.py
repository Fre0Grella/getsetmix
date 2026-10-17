"""Direct delivery to the computer that runs Rekordbox.

The companion there downloads finished tracks from here, one way: nothing it
does can change the server's library, which stays the full copy (and the
backup). Each paired computer has its own token, one per line in
DATA_DIR/link-tokens; the setup's server script appends them, and the file is
read on every request, so pairing a computer needs no restart.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from .config import DATA_DIR

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".aac", ".aif", ".aiff", ".wav", ".ogg", ".opus"}
TOKENS_FILE = DATA_DIR / "link-tokens"


def tokens() -> list[str]:
    found = []
    env = os.environ.get("GSM_LINK_TOKEN", "").strip()
    if env:
        found.append(env)
    try:
        lines = TOKENS_FILE.read_text("utf-8").splitlines()
    except OSError:
        lines = []
    # "token  optional label" -> token
    found += [ln.split()[0] for ln in lines if ln.strip() and not ln.startswith("#")]
    return found


def authorized(header: str) -> bool:
    scheme, _, supplied = header.partition(" ")
    if scheme.lower() != "bearer" or not supplied.strip():
        return False
    supplied = supplied.strip()
    # compare against every token, without stopping early
    return any([secrets.compare_digest(supplied, t) for t in tokens()])


def _skip(name: str) -> bool:
    return name.startswith((".", "~")) or name.endswith((".part", ".tmp"))


def list_files(root: Path) -> list[dict]:
    """Every finished audio file under root, as library-relative paths."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _skip(d))
        for name in sorted(filenames):
            if _skip(name) or Path(name).suffix.lower() not in AUDIO_EXTS:
                continue
            path = Path(dirpath) / name
            try:
                st = path.stat()
            except OSError:
                continue
            if st.st_size == 0:
                continue
            out.append({
                "path": path.relative_to(root).as_posix(),
                "size": st.st_size,
                "mtime": int(st.st_mtime),
            })
    return out


def resolve(root: Path, rel: str) -> Path | None:
    """The file `rel` names inside root, or None if it escapes root or isn't served."""
    if not rel or "\\" in rel or rel.startswith("/"):
        return None
    root = root.resolve()
    path = (root / rel).resolve()
    if root not in path.parents or not path.is_file():
        return None
    if any(_skip(part) for part in path.relative_to(root).parts):
        return None
    if path.suffix.lower() not in AUDIO_EXTS:
        return None
    return path
