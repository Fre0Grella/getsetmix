"""Whole-page checks: no console errors anywhere, and the same screens in Italian."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from .conftest import state

pytestmark = pytest.mark.ui


def test_no_page_logs_a_console_error(open_tab, downloads):
    tab = open_tab("/")
    expect(state(tab, "d-present")).to_contain_text("In your library")
    tab.page.locator("#btnSettings").click()
    expect(tab.page.locator("#settingsModal")).to_be_visible()
    tab.page.keyboard.press("Escape")

    tab.page.locator('[data-view="library"]').click()
    expect(tab.page.locator(".lib-row[data-id]").first).to_be_visible()
    tab.page.locator(".lib-row[data-id]").first.click()
    expect(tab.page.locator("#libSheet")).to_be_visible()
    tab.page.keyboard.press("Escape")
    tab.page.locator("#libTrashBtn").click()
    expect(tab.page.locator("#libBack")).to_be_visible()
    tab.page.wait_for_timeout(500)  # let cover and status requests finish
    assert tab.errors == [], tab.errors
    assert tab.dialogs == []


def test_the_italian_downloads_and_library_screens_use_italian_words(open_tab, downloads):
    assert downloads.http.put("/api/settings", json={"language": "it"}).status_code == 200
    tab = open_tab("/")
    expect(tab.page.locator("html")).to_have_attribute("lang", "it")
    expect(state(tab, "d-present")).to_contain_text("Nella libreria")
    expect(state(tab, "d-trashed")).to_contain_text("Nel cestino")
    expect(state(tab, "d-gone")).to_contain_text("Non è più nella libreria")

    # what a screen reader says is Italian too
    expect(tab.page.locator("#settingsModal .modal-close")).to_have_attribute("aria-label", "Chiudi")
    expect(tab.page.locator("#coverQuery")).to_have_attribute("aria-label", "Cerca")

    tab.page.locator('[data-view="library"]').click()
    midnight = tab.page.locator(".lib-row", has_text="Midnight Drive")
    midnight.locator('[data-act="delete"]').click()
    expect(tab.page.locator("#confirmText")).to_have_text("Spostare “Midnight Drive” nel cestino?")
    expect(tab.page.locator("#confirmYes")).to_have_text("Elimina")
    expect(tab.page.locator("#confirmNo")).to_have_text("Annulla")
    tab.page.keyboard.press("Escape")
    expect(tab.page.locator("#libEmptyTrash")).to_be_hidden()
    assert tab.errors == []
