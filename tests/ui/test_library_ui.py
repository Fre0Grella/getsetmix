"""The Library view in a real browser: the list, the detail sheet, delete, restore, the trash."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from .conftest import LONG_NAME, MIDNIGHT, PHONE, TRACKS

pytestmark = pytest.mark.ui

def row(tab, title: str):
    return tab.page.locator(".lib-row", has_text=title)


def test_library_shows_a_row_for_every_file_in_the_music_folder(open_tab):
    tab = open_tab("/#library")
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(len(TRACKS))
    expect(row(tab, "Midnight Drive")).to_contain_text("Nova Kid")
    expect(row(tab, "Blue Hour")).to_be_visible()


def test_a_long_file_name_does_not_make_the_detail_sheet_wider_than_a_phone(open_tab):
    tab = open_tab("/#library", PHONE)
    tab.page.locator(".lib-row", has_text=LONG_NAME[:20]).click()
    expect(tab.page.locator("#libSheet")).to_be_visible()
    card = tab.page.locator("#libSheetForm")
    expect(card).to_be_visible()
    tab.page.wait_for_timeout(500)  # the sheet slides in
    box = card.bounding_box()
    assert box["width"] == PHONE["width"], f"card is {box['width']} px wide on a {PHONE['width']} px screen"
    assert box["x"] == 0
    assert tab.page.evaluate("document.documentElement.scrollWidth") <= PHONE["width"]


def test_a_text_selection_that_ends_on_the_backdrop_keeps_the_sheet_open_and_a_click_closes_it(open_tab):
    tab = open_tab("/#library")
    row(tab, "Midnight Drive").click()
    sheet = tab.page.locator("#libSheet")
    expect(sheet).to_be_visible()
    field = tab.page.locator("#libFTitle")
    expect(field).to_have_value("Midnight Drive")
    tab.page.wait_for_timeout(500)
    box = field.bounding_box()
    tab.page.mouse.move(box["x"] + box["width"] - 4, box["y"] + box["height"] / 2)
    tab.page.mouse.down()
    tab.page.mouse.move(8, 8, steps=5)  # drag out of the card, onto the backdrop
    tab.page.mouse.up()
    tab.page.wait_for_timeout(300)
    expect(sheet).to_be_visible()
    tab.page.mouse.click(8, 8)  # a plain click on the backdrop
    expect(sheet).to_be_hidden()


def test_delete_asks_first_and_cancel_or_escape_delete_nothing(open_tab, server):
    tab = open_tab("/#library")
    confirm = tab.page.locator("#confirmModal")
    delete = row(tab, "Midnight Drive").locator('[data-act="delete"]')

    delete.click()
    expect(confirm).to_be_visible()
    expect(tab.page.locator("#confirmText")).to_contain_text("Midnight Drive")
    tab.page.locator("#confirmNo").click()
    expect(confirm).to_be_hidden()

    delete.click()
    expect(confirm).to_be_visible()
    tab.page.keyboard.press("Escape")
    expect(confirm).to_be_hidden()

    assert len(server.items("present")) == len(TRACKS)
    assert server.items("trashed") == []
    expect(row(tab, "Midnight Drive")).to_be_visible()
    assert tab.dialogs == []


def test_confirming_a_delete_moves_the_track_to_the_trash(open_tab, server):
    tab = open_tab("/#library")
    row(tab, "Midnight Drive").locator('[data-act="delete"]').click()
    tab.page.locator("#confirmYes").click()
    expect(row(tab, "Midnight Drive")).to_have_count(0)
    assert [i["title"] for i in server.items("trashed")] == ["Midnight Drive"]
    assert len(server.items("present")) == len(TRACKS) - 1
    assert not server.music.path(MIDNIGHT).exists()


def test_restore_in_the_trash_view_asks_first_and_then_puts_the_track_back(open_tab, server):
    server.http.delete(f"/api/library/{server.item(MIDNIGHT)['id']}")
    tab = open_tab("/#library")
    tab.page.locator("#libTrashBtn").click()
    restore = row(tab, "Midnight Drive").locator('[data-act="restore"]')
    confirm = tab.page.locator("#confirmModal")

    restore.click()
    expect(confirm).to_be_visible()
    tab.page.locator("#confirmNo").click()
    expect(confirm).to_be_hidden()
    assert len(server.items("trashed")) == 1  # Cancel restored nothing

    restore.click()
    tab.page.locator("#confirmYes").click()
    expect(row(tab, "Midnight Drive")).to_have_count(0)
    assert server.items("trashed") == []
    assert server.music.path(MIDNIGHT).exists()


def test_empty_trash_uses_the_app_dialog_and_never_the_browsers(open_tab, server):
    server.http.delete(f"/api/library/{server.item(MIDNIGHT)['id']}")
    tab = open_tab("/#library")
    tab.page.locator("#libTrashBtn").click()
    expect(row(tab, "Midnight Drive")).to_be_visible()
    confirm = tab.page.locator("#confirmModal")

    tab.page.locator("#libEmptyTrash").click()
    expect(confirm).to_be_visible()
    tab.page.locator("#confirmNo").click()
    expect(confirm).to_be_hidden()
    assert len(server.items("trashed")) == 1  # Cancel removed nothing

    tab.page.locator("#libEmptyTrash").click()
    tab.page.locator("#confirmYes").click()
    expect(row(tab, "Midnight Drive")).to_have_count(0)
    assert server.items("trashed") == []
    assert tab.dialogs == [], f"the browser's own dialog appeared: {tab.dialogs}"
