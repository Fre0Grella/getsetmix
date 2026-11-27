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


def set_field(tab, field: str, op: str, value: str = "") -> None:
    """In the edit panel: choose what to do to one field, and its value."""
    frow = tab.page.locator(f'.ed-frow[data-field="{field}"]')
    frow.locator(".ed-op").select_option(op)
    if value:
        frow.locator(".ed-v").fill(value)


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


# ------------------------------------------------ batch editing (#47)
def test_edit_tags_previews_then_writes_one_field_on_the_selection(open_tab, server):
    tab = open_tab("/#library")
    row(tab, "Midnight Drive").click(modifiers=["Control"])
    row(tab, "Blue Hour").click(modifiers=["Control"])
    bar(tab).locator('[data-bulk="edit"]').click()
    panel = tab.page.locator("#edModal")
    expect(panel).to_be_visible()
    expect(tab.page.locator("#edTitle")).to_have_text("Edit tags of 2 tracks")

    set_field(tab, "genre", "set", "Tech House")
    tab.page.locator("#edPreviewBtn").click()
    expect(tab.page.locator("#edCounts")).to_have_text("2 changes on 2 tracks")
    expect(tab.page.locator(".ed-row")).to_have_count(2)
    expect(tab.page.locator(".ed-row").first).to_contain_text("→ Tech House")
    # a preview writes nothing
    assert server.item(MIDNIGHT)["genre"] == "House"

    apply = tab.page.locator("#edApply")
    expect(apply).to_have_text("Change 2 tags on 2 tracks")
    apply.click()
    expect(tab.page.locator("#edResult")).to_have_text("Written to 2 files.")
    expect(tab.page.locator('.ed-row[data-state="applied"]')).to_have_count(2)
    expect(apply).to_be_hidden()
    assert server.item(MIDNIGHT)["genre"] == server.item(BLUE_HOUR)["genre"] == "Tech House"
    assert server.item("Late Train.mp3")["genre"] == "Disco"
    tab.page.locator("#edModal [data-close]").first.click()
    expect(row(tab, "Midnight Drive")).to_contain_text("Tech House")
    expect(bar(tab)).to_be_hidden()
    assert tab.errors == [] and tab.dialogs == []


def test_edit_tags_says_when_nothing_changes(open_tab, server):
    tab = open_tab("/#library", PHONE)
    long_press(tab, "Midnight Drive")
    bar(tab).locator('[data-bulk="edit"]').click()
    set_field(tab, "genre", "set", "House")
    tab.page.locator("#edPreviewBtn").click()
    expect(tab.page.locator("#edCounts")).to_contain_text("Nothing to change")
    expect(tab.page.locator("#edApply")).to_be_hidden()
    assert tab.page.evaluate("document.documentElement.scrollWidth") <= PHONE["width"]


# ------------------------------------------------ undo and the history (#48)
def test_an_edit_is_undone_from_the_panel_and_from_the_history(open_tab, server):
    tab = open_tab("/#library")
    row(tab, "Midnight Drive").click(modifiers=["Control"])
    bar(tab).locator('[data-bulk="edit"]').click()
    set_field(tab, "genre", "set", "Tech House")
    tab.page.locator("#edPreviewBtn").click()
    tab.page.locator("#edApply").click()
    expect(tab.page.locator("#edResult")).to_have_text("Written to 1 file.")
    assert server.item(MIDNIGHT)["genre"] == "Tech House"

    tab.page.locator("#edUndo").click()   # straight from the panel
    expect(tab.page.locator('.ed-row[data-state="applied"]')).to_contain_text("Tech House → House")
    assert server.item(MIDNIGHT)["genre"] == "House"
    tab.page.keyboard.press("Escape")

    tab.page.locator("#libHistoryBtn").click()
    lines = tab.page.locator("#edHistoryList .ed-line")
    expect(lines).to_have_count(2)
    expect(lines.nth(0)).to_contain_text("Undo: genre = Tech House")
    expect(lines.nth(1)).to_contain_text("Undone")
    lines.nth(0).locator("[data-undo]").click()   # undo the undo
    expect(lines.nth(0)).to_contain_text("Undo: Undo: genre = Tech House")
    assert server.item(MIDNIGHT)["genre"] == "Tech House"
    assert tab.errors == []


# ------------------------------------------------ field operations (#50)
def test_several_fields_and_the_whole_view_in_one_edit(open_tab, server):
    tab = open_tab("/#library")
    tab.page.locator(".lib-gchip", has_text="House").click()   # a view of one genre
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(1)
    tab.page.locator(".lib-gchip", has_text="House").click()   # back to all
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(len(TRACKS))
    row(tab, "Midnight Drive").click(modifiers=["Control"])
    bar(tab).locator('[data-bulk="edit"]').click()
    expect(tab.page.locator("#edScopeAll")).to_have_text(f"All {len(TRACKS)} tracks in this view")
    tab.page.locator('#edScope input[value="filter"]').check()
    set_field(tab, "album", "set", "Night Set")
    frow = tab.page.locator('.ed-frow[data-field="title"]')
    frow.locator(".ed-op").select_option("replace")
    frow.locator(".ed-find").fill("drive")
    frow.locator(".ed-with").fill("Ride")
    tab.page.locator("#edPreviewBtn").click()
    # every track gets the album; one title holds "Drive" (case is ignored by default)
    expect(tab.page.locator("#edCounts")).to_have_text(f"{len(TRACKS) + 1} changes on {len(TRACKS)} tracks")
    expect(tab.page.locator("#edNotes")).to_contain_text("downloads")
    tab.page.locator("#edApply").click()
    expect(tab.page.locator("#edResult")).to_have_text(f"Written to {len(TRACKS)} files.")
    assert server.item(MIDNIGHT)["title"] == "Midnight Ride"
    assert {i["album"] for i in server.items()} == {"Night Set"}
    assert tab.errors == []
