"""Browser smoke tests: the real app in uvicorn, driven by Chromium.

Needs `pip install -r requirements-dev.txt` and `playwright install chromium`.
Without playwright these files are not collected, so a plain `pytest tests/`
on a machine that lacks it just runs the other tests. In CI (`CI` is set) a
missing browser is a failure, not a skip.
"""
from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

try:
    from playwright.sync_api import Browser, Page, expect, sync_playwright
except ImportError:  # no playwright here: leave the browser tests out
    collect_ignore_glob = ["test_*.py"]
else:
    expect.set_options(timeout=10_000)

ROOT = Path(__file__).resolve().parents[2]
PHONE = {"width": 360, "height": 740}
DESKTOP = {"width": 1280, "height": 800}

# The tracks every test starts with (file name, tags). The first two are tagged
# like a real library; "LONG" has no tags and a name with no space to break at.
LONG_NAME = "x" * 150 + ".mp3"
MIDNIGHT = "Nova Kid - Midnight Drive.mp3"
BLUE_HOUR = "Ana Lux - Blue Hour.mp3"
TRACKS = {
    MIDNIGHT: {"title": "Midnight Drive", "artist": "Nova Kid", "genre": "House"},
    BLUE_HOUR: {"title": "Blue Hour", "artist": "Ana Lux", "genre": "Techno"},
    "Sol Park - Late Train.mp3": {"title": "Late Train", "artist": "Sol Park", "genre": "Disco"},
    LONG_NAME: {},
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """The app running on a free port over throwaway data and music folders."""

    def __init__(self, url: str, data_dir: Path, music) -> None:
        self.url = url
        self.data_dir = data_dir
        self.music = music
        self.http = httpx.Client(base_url=url, timeout=20)

    def items(self, state: str = "present") -> list[dict]:
        return self.http.get("/api/library", params={"state": state}).json()["items"]

    def item(self, name: str, state: str = "present") -> dict:
        return next(i for i in self.items(state) if i["path"].endswith(name))

    def wait_for_index(self, present: int) -> None:
        deadline = time.time() + 30
        while time.time() < deadline:
            status = self.http.get("/api/library/status").json()
            if status["indexed"] and status["counts"].get("present", 0) == present:
                return
            time.sleep(0.2)
        raise AssertionError(f"the library was not indexed in time: {status}")

    def seed_download(self, tid: str, status: str = "ingested", **fields) -> None:
        """A row of the Downloads list, written straight into the database."""
        now = datetime.now(UTC).isoformat(timespec="seconds")
        row = {"id": tid, "url": f"https://example.test/{tid}", "status": status,
               "created_at": now, "updated_at": now, "downloaded_at": now, **fields}
        conn = sqlite3.connect(self.data_dir / "getsetmix.db", timeout=20)
        try:
            with conn:
                conn.execute(f"INSERT INTO tracks ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
                             tuple(row.values()))
        finally:
            conn.close()


@pytest.fixture()
def server(tmp_path, music):
    for seed, (name, tags) in enumerate(TRACKS.items(), start=1):
        music.mp3(name, seed=seed, **tags)
    data_dir = tmp_path / "data"
    port = _free_port()
    env = {**os.environ, "GSM_DATA_DIR": str(data_dir), "GSM_LIBRARY_ROOT": str(music.root),
           "GSM_LANGUAGE": "", "GSM_AUTH_TOKEN": "", "PYTHONUNBUFFERED": "1"}
    log = (tmp_path / "server.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    srv = Server(f"http://127.0.0.1:{port}", data_dir, music)
    try:
        deadline = time.time() + 30
        while True:
            try:
                if srv.http.get("/api/ping").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            assert proc.poll() is None and time.time() < deadline, (tmp_path / "server.log").read_text()
            time.sleep(0.2)
        srv.http.post("/api/library/rescan")
        srv.wait_for_index(len(TRACKS))
        yield srv
    finally:
        srv.http.close()
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as pw:
        try:
            chromium = pw.chromium.launch()
        except Exception as exc:  # the browser binary is not installed
            if os.environ.get("CI"):
                raise
            pytest.skip(f"Chromium is not installed (playwright install chromium): {exc}")
        yield chromium
        chromium.close()


@dataclass
class Tab:
    page: Page
    errors: list[str] = field(default_factory=list)   # console errors and uncaught exceptions
    dialogs: list[str] = field(default_factory=list)  # the browser's own alert/confirm/prompt


@pytest.fixture()
def open_tab(browser: Browser, server):
    """`open_tab("/#library", PHONE)` opens the app in a fresh browser context."""
    contexts = []

    def make(path: str = "/", viewport: dict | None = None) -> Tab:
        # no service worker: a page must never come from a cache
        ctx = browser.new_context(viewport=viewport or DESKTOP, base_url=server.url, service_workers="block")
        contexts.append(ctx)
        tab = Tab(ctx.new_page())

        def on_dialog(dialog):
            tab.dialogs.append(dialog.message)
            dialog.dismiss()

        tab.page.on("console", lambda m: m.type == "error" and tab.errors.append(m.text))
        tab.page.on("pageerror", lambda e: tab.errors.append(str(e)))
        tab.page.on("dialog", on_dialog)
        tab.page.goto(path)
        return tab

    yield make
    for ctx in contexts:
        ctx.close()


@pytest.fixture()
def downloads(server):
    """Downloads of a present file, of a trashed one and of one that is gone."""
    server.http.delete(f"/api/library/{server.item(BLUE_HOUR)['id']}")  # into the trash
    for tid, title, name in (("d-present", "Present One", MIDNIGHT), ("d-trashed", "Trashed One", BLUE_HOUR),
                             ("d-gone", "Gone One", "Nowhere - Gone.mp3")):
        server.seed_download(tid, title=title, artist="Seed", file_path=str(server.music.path(name)))
    return server


def state(tab: Tab, tid: str):
    """The status cell of one Downloads row."""
    return tab.page.locator(f'.track[data-id="{tid}"] .state')
