"""Selection and the bulk bar in a real browser (design 4.5): a long press on a
phone, Ctrl- and Shift-click on a desktop, then Delete, Restore and Set genre."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from .conftest import BLUE_HOUR, MIDNIGHT, PHONE, TRACKS

pytestmark = pytest.mark.ui


def row(tab, title: str):
    return tab.page.locator(".lib-row", has_text=title)


def long_press(tab, title: str) -> None:
    """A finger resting on a row: touch pointer events, no move, then up."""
    target = row(tab, title).locator(".lib-who")
    box = target.bounding_box()
    at = {"pointerType": "touch", "isPrimary": True, "bubbles": True,
          "clientX": box["x"] + 10, "clientY": box["y"] + 10}
    target.dispatch_event("pointerdown", at)
    tab.page.wait_for_timeout(700)
    target.dispatch_event("pointerup", at)


def bar(tab):
    return tab.page.locator("#libSelBar")


def test_ctrl_and_shift_click_select_and_the_bar_counts_them(open_tab):
    tab = open_tab("/#library")
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(len(TRACKS))
    expect(bar(tab)).to_be_hidden()
    rows = tab.page.locator(".lib-row[data-id]")

    rows.nth(0).click(modifiers=["Control"])
    expect(bar(tab)).to_be_visible()
    expect(tab.page.locator("#libSelCount")).to_have_text("1 selected")
    expect(tab.page.locator("#libSheet")).to_be_hidden()   # selecting is not opening
    expect(tab.page.locator("#libSearchForm")).to_be_hidden()

    rows.nth(2).click(modifiers=["Shift"])
    expect(tab.page.locator("#libSelCount")).to_have_text("3 selected")
    expect(tab.page.locator(".lib-row.is-selected")).to_have_count(3)

    rows.nth(1).click()   # while selecting, a plain click takes a row out
    expect(tab.page.locator("#libSelCount")).to_have_text("2 selected")

    tab.page.keyboard.press("Escape")
    expect(bar(tab)).to_be_hidden()
    expect(tab.page.locator(".lib-row.is-selected")).to_have_count(0)
    expect(tab.page.locator("#libSearchForm")).to_be_visible()
    rows.nth(0).click()   # with nothing selected, a click opens the sheet as before
    expect(tab.page.locator("#libSheet")).to_be_visible()
    assert tab.errors == []


def test_bulk_set_genre_writes_every_selected_file(open_tab, server):
    tab = open_tab("/#library")
    row(tab, "Midnight Drive").click(modifiers=["Control"])
    row(tab, "Blue Hour").click(modifiers=["Control"])
    bar(tab).locator('[data-bulk="set_genre"]').click()
    modal = tab.page.locator("#libGenreModal")
    expect(modal).to_be_visible()
    expect(tab.page.locator("#libGenreTitle")).to_have_text("Genre for 2 tracks")
    tab.page.locator("#libGenreInput").fill("Tech House")
    tab.page.locator("#libGenreApply").click()

    expect(modal).to_be_hidden()
    expect(tab.page.locator("#toast")).to_contain_text("Tech House")
    expect(bar(tab)).to_be_hidden()
    expect(row(tab, "Midnight Drive")).to_contain_text("Tech House")
    expect(row(tab, "Blue Hour")).to_contain_text("Tech House")
    assert server.item(MIDNIGHT)["genre"] == server.item(BLUE_HOUR)["genre"] == "Tech House"
    assert server.item("Late Train.mp3")["genre"] == "Disco"
    assert tab.errors == []


def test_on_a_phone_a_long_press_selects_and_bulk_delete_asks_with_the_count(open_tab, server):
    tab = open_tab("/#library", PHONE)
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(len(TRACKS))
    long_press(tab, "Midnight Drive")
    expect(bar(tab)).to_be_visible()
    expect(tab.page.locator("#libSheet")).to_be_hidden()
    row(tab, "Blue Hour").click()   # a tap while selecting adds the row
    expect(tab.page.locator("#libSelCount")).to_have_text("2 selected")
    expect(bar(tab).locator('[data-bulk="restore"]')).to_be_hidden()

    bar(tab).locator('[data-bulk="delete"]').click()
    expect(tab.page.locator("#confirmText")).to_have_text("Move 2 tracks to the trash?")
    tab.page.locator("#confirmYes").click()

    expect(row(tab, "Midnight Drive")).to_have_count(0)
    expect(row(tab, "Blue Hour")).to_have_count(0)
    assert {i["path"] for i in server.items("trashed")} == {MIDNIGHT, BLUE_HOUR}
    # the toast offers Undo, which brings both back
    tab.page.locator(".toast-act").click()
    expect(row(tab, "Midnight Drive")).to_be_visible()
    expect(row(tab, "Blue Hour")).to_be_visible()
    assert server.items("trashed") == []
    box = bar(tab).bounding_box()
    assert box is None or box["width"] <= PHONE["width"]
    assert tab.page.evaluate("document.documentElement.scrollWidth") <= PHONE["width"]
    assert tab.dialogs == [] and tab.errors == []


def test_in_the_trash_the_bar_restores_the_selection(open_tab, server):
    for name in (MIDNIGHT, BLUE_HOUR):
        server.http.delete(f"/api/library/{server.item(name)['id']}")
    tab = open_tab("/#library")
    tab.page.locator("#libTrashBtn").click()
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(2)
    rows = tab.page.locator(".lib-row[data-id]")
    rows.nth(0).click(modifiers=["Control"])
    rows.nth(1).click(modifiers=["Shift"])
    expect(bar(tab).locator('[data-bulk="delete"]')).to_be_hidden()
    expect(bar(tab).locator('[data-bulk="set_genre"]')).to_be_hidden()
    bar(tab).locator('[data-bulk="restore"]').click()
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(0)
    assert server.items("trashed") == []
    assert server.music.path(MIDNIGHT).exists() and server.music.path(BLUE_HOUR).exists()


def test_the_bar_speaks_italian(open_tab, server):
    assert server.http.put("/api/settings", json={"language": "it"}).status_code == 200
    tab = open_tab("/#library", PHONE)
    expect(tab.page.locator("html")).to_have_attribute("lang", "it")
    long_press(tab, "Midnight Drive")
    expect(tab.page.locator("#libSelCount")).to_have_text("1 selezionato")
    expect(bar(tab).locator('[data-bulk="set_genre"]')).to_have_text("Imposta genere")
    expect(bar(tab).locator('[data-bulk="delete"]')).to_have_text("Elimina")
