"""The Downloads view in a real browser: where each finished download is now, restore, "Already owned?"."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from .conftest import BLUE_HOUR, state

pytestmark = pytest.mark.ui



def test_downloads_say_where_each_file_is_in_the_library_now(open_tab, downloads):
    tab = open_tab("/")
    expect(state(tab, "d-present")).to_contain_text("In your library")
    expect(state(tab, "d-trashed")).to_contain_text("In the trash")
    expect(state(tab, "d-gone")).to_contain_text("Not in your library anymore")
    assert tab.errors == []


def test_restoring_a_trashed_download_asks_first_and_then_brings_the_file_back(open_tab, downloads):
    tab = open_tab("/")
    restore = state(tab, "d-trashed").locator('[data-act="restore"]')
    confirm = tab.page.locator("#confirmModal")

    restore.click()
    expect(confirm).to_be_visible()
    expect(tab.page.locator("#confirmText")).to_contain_text("Trashed One")
    tab.page.locator("#confirmNo").click()
    expect(confirm).to_be_hidden()
    expect(state(tab, "d-trashed")).to_contain_text("In the trash")

    restore.click()
    tab.page.locator("#confirmYes").click()
    expect(state(tab, "d-trashed")).to_contain_text("In your library")
    assert downloads.items("trashed") == []
    assert downloads.music.path(BLUE_HOUR).exists()
    assert tab.dialogs == []


def test_already_owned_opens_the_library_sheet_of_the_matching_track(open_tab, server):
    server.seed_download("d-staged", status="staged", title="Midnight Drive", artist="Nova Kid")
    tab = open_tab("/")
    owned = tab.page.locator('.track[data-id="d-staged"] .dup')
    expect(owned).to_have_text("Already owned?")
    owned.click()
    expect(tab.page.locator("#libSheet")).to_be_visible()
    expect(tab.page.locator("#libSheetTitle")).to_have_text("Midnight Drive")
    expect(tab.page.locator("#libFArtist")).to_have_value("Nova Kid")
