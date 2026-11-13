"""Shared fixtures: a music folder filled with small generated audio files."""
import importlib
import os
import shutil
import struct
import time
from pathlib import Path

import pytest
from mutagen.id3 import COMM, ID3, TALB, TCON, TDRC, TIT2, TPE1

AUDIOHASH = Path(__file__).resolve().parent.parent / "testdata" / "audiohash"
SETTLED = 3600  # files are made this many seconds before the clock's start


class Clock:
    """Injectable time for the library: call it for 'now', advance it by hand."""

    def __init__(self, start: float) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Music:
    """A library root, and ways to put audio files in it."""

    def __init__(self, root: Path, clock: Clock) -> None:
        self.root = root
        self.clock = clock

    def path(self, rel: str) -> Path:
        return self.root / rel

    def write(self, rel: str, data: bytes, age: float = SETTLED) -> Path:
        path = self.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.age(rel, age)
        return path

    def age(self, rel: str, age: float) -> None:
        when = self.clock.now - age
        os.utime(self.path(rel), (when, when))

    def mp3(self, rel: str, seed: int = 0, age: float = SETTLED, **tags) -> Path:
        """An MP3; `seed` changes its audio, `tags` (title, artist, ...) its ID3 tag."""
        data = (AUDIOHASH / "mp3" / "plain.mp3").read_bytes()
        data = data[:-4] + struct.pack(">I", seed)
        path = self.write(rel, data, age)
        if tags:
            self.tag(rel, age=age, **tags)
        return path

    def tag(self, rel: str, age: float = SETTLED, **tags) -> None:
        frames = {"title": TIT2, "artist": TPE1, "album": TALB, "genre": TCON, "year": TDRC}
        id3 = ID3()
        for key, value in tags.items():
            if key == "comment":
                id3.add(COMM(encoding=3, lang="eng", desc="", text=value))
            else:
                id3.add(frames[key](encoding=3, text=value))
        id3.save(self.path(rel), v2_version=4)
        self.age(rel, age)

    def wav(self, rel: str, seed: int = 0, age: float = SETTLED) -> Path:
        fmt = struct.pack("<HHIIHH", 1, 1, 8000, 16000, 2, 16)
        data = struct.pack("<I", seed) * 200
        body = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
                + b"data" + struct.pack("<I", len(data)) + data)
        return self.write(rel, b"RIFF" + struct.pack("<I", len(body)) + body, age)

    def fixture(self, rel: str, fixture: str, age: float = SETTLED) -> Path:
        return self.write(rel, (AUDIOHASH / fixture).read_bytes(), age)

    def move(self, src: str, dest: str) -> None:
        self.path(dest).parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.path(src), self.path(dest))

    def remove(self, rel: str) -> None:
        self.path(rel).unlink()

    def hide(self, rel: str, where: Path) -> None:
        """Take a file away and keep its bytes and time, to bring it back later."""
        where.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.path(rel)), where / rel.replace("/", "__"))

    def unhide(self, rel: str, where: Path) -> None:
        self.path(rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(where / rel.replace("/", "__")), self.path(rel))


def fresh_modules(tmp_path: Path, monkeypatch, *names: str, token: str = "") -> None:
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    if token:
        monkeypatch.setenv("GSM_AUTH_TOKEN", token)
    else:
        monkeypatch.delenv("GSM_AUTH_TOKEN", raising=False)
    for name in ("app.config", "app.db", *names):
        importlib.reload(importlib.import_module(name))


@pytest.fixture()
def clock() -> Clock:
    return Clock(time.time())


@pytest.fixture()
def music(tmp_path, clock) -> Music:
    root = tmp_path / "music"
    root.mkdir()
    return Music(root, clock)


@pytest.fixture()
def lib(tmp_path, monkeypatch, music, clock):
    """A Library over a fresh database and the `music` folder, on the test clock."""
    fresh_modules(tmp_path, monkeypatch)
    import app.db
    from app import library
    return library.Library(app.db.db, root=lambda: music.root, clock=clock)
