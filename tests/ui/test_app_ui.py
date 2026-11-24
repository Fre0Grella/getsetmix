"""App-wide behaviour in a real browser: the health dot, the duplicate question, the token prompt."""
from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui


def test_the_health_dot_stays_red_while_the_engine_has_a_problem(open_tab):
    # Each poll of the track list used to clear the red set by the engine check.
    tab = open_tab("/")
    tab.page.route("**/api/status", lambda route: route.fulfill(
        content_type="application/json", body=json.dumps({"ytdlp": {"problems": ["yt-dlp is stale"]}})))
    tab.page.reload()
    dot = tab.page.locator("#healthDot")
    expect(dot).to_have_class(re.compile(r"\bbad\b"))
    expect(dot).to_have_attribute("title", "yt-dlp is stale")
    tab.page.wait_for_timeout(5000)  # longer than the 4 s poll
    assert "bad" in (dot.get_attribute("class") or "").split()
    expect(dot).to_have_attribute("title", "yt-dlp is stale")


def test_downloading_a_duplicate_asks_in_the_app_dialog_and_skip_keeps_it(open_tab, server):
    server.seed_download("d-dup", status="staged", title="Midnight Drive", artist="Nova Kid")
    tab = open_tab("/")
    expect(tab.page.locator('.track[data-id="d-dup"] .dup')).to_be_visible()
    tab.page.locator("#btnDownload").click()
    ask = tab.page.locator("#confirmModal")
    expect(ask).to_be_visible()
    expect(tab.page.locator("#confirmText")).to_contain_text("already in your library")
    expect(tab.page.locator("#confirmText")).to_contain_text("Nova Kid – Midnight Drive")
    tab.page.locator("#confirmNo").click()
    expect(ask).to_be_hidden()
    staged = {t["id"]: t["status"] for t in server.http.get("/api/tracks").json()["tracks"]}
    assert staged["d-dup"] == "staged"
    assert tab.dialogs == []


def test_a_401_asks_for_the_token_once_however_many_requests_fail(open_tab):
    # Several requests fail together at load; a dismissed question is not asked again.
    tab = open_tab("/")
    tab.page.route("**/api/**", lambda route: route.fulfill(status=401, body="{}"))
    tab.page.reload()
    tab.page.wait_for_timeout(5000)  # past the next poll
    assert len(tab.dialogs) == 1, tab.dialogs
