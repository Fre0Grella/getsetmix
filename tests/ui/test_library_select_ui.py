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


def test_filter_by_artist_select_all_untick_one_and_set_the_genre(open_tab, server):
    """The flow of design 4.5.2: an artist (main or featured), Select all,
    take one out, Edit tags, Set Genre."""
    server.music.mp3("Kito - Echo.mp3", seed=21, title="Echo", artist="Kito", genre="House")
    server.music.mp3("Nova - Glow.mp3", seed=22, title="Glow (feat. Kito)", artist="Nova", genre="Techno")
    server.music.mp3("Sol - Dust.mp3", seed=23, title="Dust", artist="Sol, Kito", genre="Disco")
    server.http.post("/api/library/rescan")
    server.wait_for_index(len(TRACKS) + 3)
    tab = open_tab("/#library")
    artist = tab.page.locator("#libArtist")
    artist.fill("Kito")
    artist.press("Enter")
    artist.dispatch_event("change")
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(3)
    link = tab.page.locator("#libCountAll")
    expect(link).to_be_visible()
    link.click()
    expect(tab.page.locator("#libSelCount")).to_have_text("All 3 selected")
    expect(tab.page.locator(".lib-row.is-selected")).to_have_count(3)
    row(tab, "Dust").click()     # take one out of "all"
    expect(tab.page.locator("#libSelCount")).to_have_text("2 selected")
    bar(tab).locator('[data-bulk="edit"]').click()
    expect(tab.page.locator("#edTitle")).to_have_text("Edit tags of 2 tracks")
    set_field(tab, "genre", "set", "Afro House")
    tab.page.locator("#edPreviewBtn").click()
    tab.page.locator("#edApply").click()
    expect(tab.page.locator("#edResult")).to_have_text("Written to 2 files.")
    genres = {i["title"]: i["genre"] for i in server.items()}
    assert genres["Echo"] == genres["Glow (feat. Kito)"] == "Afro House"
    assert genres["Dust"] == "Disco"
    assert tab.errors == []


def test_the_select_button_starts_selection_and_select_all_takes_the_view(open_tab, server):
    tab = open_tab("/#library")
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(len(TRACKS))
    tab.page.locator("#libSelectBtn").click()
    expect(bar(tab)).to_be_visible()
    expect(tab.page.locator("#libSelCount")).to_have_text("Pick tracks")
    expect(bar(tab).locator('[data-bulk="edit"]')).to_be_disabled()
    expect(tab.page.locator(".lib-check").first).to_be_visible()
    row(tab, "Blue Hour").click()            # in the mode a click picks, never opens
    expect(tab.page.locator("#libSheet")).to_be_hidden()
    expect(tab.page.locator("#libSelCount")).to_have_text("1 selected")
    tab.page.locator("#libSelAll").click()
    expect(tab.page.locator("#libSelCount")).to_have_text(f"All {len(TRACKS)} selected")
    tab.page.locator("#libSelectBtn").click()   # again: out of the mode
    expect(bar(tab)).to_be_hidden()
    row(tab, "Blue Hour").click()
    expect(tab.page.locator("#libSheet")).to_be_visible()


def test_the_hover_checkbox_picks_a_row_and_a_cover_click_opens_it(open_tab, server):
    tab = open_tab("/#library")
    target = row(tab, "Late Train")
    target.hover()
    target.locator(".lib-check").click()
    expect(tab.page.locator("#libSelCount")).to_have_text("1 selected")
    tab.page.keyboard.press("Escape")
    expect(bar(tab)).to_be_hidden()


def test_problem_filters_narrow_the_list(open_tab, server):
    server.music.mp3("raw.mp3", seed=31, title="late train [free download]", artist="sol ft moon")
    server.http.post("/api/library/rescan")
    server.wait_for_index(len(TRACKS) + 1)
    tab = open_tab("/#library")
    problem = tab.page.locator("#libProblem")
    expect(problem.locator('option[value="promo"]')).to_have_text("Promo text in the title (1)")
    problem.select_option("promo")
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(1)
    expect(tab.page.locator("#libCountAll")).to_be_visible()
    problem.select_option("")
    expect(tab.page.locator(".lib-row[data-id]")).to_have_count(len(TRACKS) + 1)


def test_on_a_phone_the_filters_are_a_sheet(open_tab, server):
    tab = open_tab("/#library", PHONE)
    expect(tab.page.locator("#libFilters")).to_be_hidden()
    tab.page.locator("#libFiltersBtn").click()
    expect(tab.page.locator("#libFilters")).to_be_visible()
    tab.page.locator("#libProblem").select_option("no_cover")
    expect(tab.page.locator("#libFiltersBadge")).to_have_text("1")
    tab.page.locator("#libFiltersClose").click()
    expect(tab.page.locator("#libFilters")).to_be_hidden()
    assert tab.page.evaluate("document.documentElement.scrollWidth") <= PHONE["width"]


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
    expect(bar(tab).locator('[data-bulk="edit"]')).to_be_hidden()
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
    expect(bar(tab).locator('[data-bulk="edit"]')).to_have_text("Modifica tag")
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


# ------------------------------------------------------- rule sets (#49)
def test_cleanup_with_a_rule_set_and_a_change_left_out(open_tab, server):
    server.music.mp3("Messy.mp3", seed=9, title="night drive (original mix) [free download]",
                     artist="Nova ft Kito", genre="tech-house")
    server.http.post("/api/library/rescan")
    server.wait_for_index(len(TRACKS) + 1)
    tab = open_tab("/#library")
    row(tab, "free download").click(modifiers=["Control"])
    bar(tab).locator('[data-bulk="edit"]').click()
    tab.page.locator('.ed-tab[data-tab="cleanup"]').click()
    expect(tab.page.locator("#edSet")).to_have_value(str(server.http.get("/api/library/rulesets").json()[0]["id"]))
    expect(tab.page.locator(".ed-rule")).to_have_count(11)
    expect(tab.page.locator("#edSetNote")).to_be_visible()   # built in: copy to change
    tab.page.locator("#edPreviewBtn").click()
    expect(tab.page.locator(".ed-track")).to_have_count(1)
    expect(tab.page.locator(".ed-row")).to_have_count(3)    # title, artist, genre
    expect(tab.page.locator(".ed-new mark").first).to_be_visible()   # the changed part is marked
    # leave the genre out
    genre = tab.page.locator(".ed-row", has_text="tech-house")
    genre.locator("input[data-change]").uncheck()
    expect(genre).to_have_attribute("data-state", "excluded")
    expect(tab.page.locator("#edApply")).to_have_text("Change 2 tags on 1 track")
    tab.page.locator("#edApply").click()
    expect(tab.page.locator("#edResult")).to_have_text("Written to 1 file.")
    item = server.item("Messy.mp3")
    assert (item["title"], item["artist"], item["genre"]) == ("night drive (feat. Kito)", "Nova", "tech-house")
    assert tab.errors == []


def test_a_copy_of_the_built_in_set_can_be_saved_changed_and_removed(open_tab, server):
    tab = open_tab("/#library")
    row(tab, "Midnight Drive").click(modifiers=["Control"])
    bar(tab).locator('[data-bulk="edit"]').click()
    tab.page.locator('.ed-tab[data-tab="cleanup"]').click()
    expect(tab.page.locator(".ed-rule")).to_have_count(11)
    tab.page.locator(".ed-rule").nth(0).locator("[data-on]").uncheck()
    tab.page.locator("#edSetCopy").click()
    tab.page.locator("#edSetName").fill("Mine")
    tab.page.locator("#edSetNewSave").click()
    expect(tab.page.locator(".ed-rule")).to_have_count(10)
    expect(tab.page.locator("#edSetSave")).to_be_visible()
    sets = server.http.get("/api/library/rulesets").json()
    assert [s["name"] for s in sets] == ["Standard cleanup", "Mine"] and len(sets[1]["steps"]) == 10
    tab.page.locator(".ed-rule").nth(1).locator('[data-move="-1"]').click()
    tab.page.locator("#edSetSave").click()
    expect(tab.page.locator("#toast")).to_have_text("Rule set saved")
    mine = server.http.get("/api/library/rulesets").json()[1]
    assert [s["rule"] for s in mine["steps"][:2]] == [sets[1]["steps"][1]["rule"], sets[1]["steps"][0]["rule"]]
    tab.page.locator("#edSetDelete").click()
    tab.page.locator("#confirmYes").click()
    expect(tab.page.locator("#edSet option")).to_have_count(1)
    assert tab.dialogs == [] and tab.errors == []


# --------------------------------------------------------- the cover (#51)
def test_a_new_cover_for_the_selection_and_its_undo(open_tab, server, tmp_path):
    from app import tagger
    image = tmp_path / "cover.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes.fromhex(
        "0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201"
        "a5c2b4f10000000049454e44ae426082"))
    tab = open_tab("/#library")
    row(tab, "Midnight Drive").click(modifiers=["Control"])
    bar(tab).locator('[data-bulk="edit"]').click()
    frow = tab.page.locator('.ed-frow[data-field="cover"]')
    frow.locator(".ed-op").select_option("set_cover")
    tab.page.locator("#edPreviewBtn").click()
    expect(tab.page.locator("#toast")).to_have_text("Choose an image for the cover.")
    frow.locator(".ed-file-in").set_input_files(str(image))
    tab.page.locator("#edPreviewBtn").click()
    expect(tab.page.locator(".ed-row")).to_contain_text("Cover: no cover → new image")
    tab.page.locator("#edApply").click()
    expect(tab.page.locator("#edResult")).to_have_text("Written to 1 file.")
    assert tagger.read_cover(server.music.path(MIDNIGHT))[0] == image.read_bytes()
    tab.page.locator("#edUndo").click()
    expect(tab.page.locator(".ed-row")).to_contain_text("Cover: its cover → no cover")
    expect(tab.page.locator('.ed-row[data-state="applied"]')).to_have_count(1)
    assert tagger.read_cover(server.music.path(MIDNIGHT)) is None
    # A row may ask for its thumbnail just as undo removes the cover: that 404
    # is the "no cover" answer the list expects. Any other error still fails.
    assert [e for e in tab.errors if "404" not in e] == []


# ------------------------------------------------- the phone sheet (#52)
def test_on_a_phone_the_edit_is_three_steps_over_hundreds_of_changes(open_tab, server):
    for n in range(150):
        server.music.mp3(f"Bulk/{n:03}.mp3", seed=100 + n, title=f"Track {n}", artist="Nova", genre="House")
    server.http.post("/api/library/rescan")
    server.wait_for_index(len(TRACKS) + 150)
    tab = open_tab("/#library", PHONE)
    long_press(tab, "Track 149")   # the newest, so on screen
    bar(tab).locator('[data-bulk="edit"]').click()
    expect(tab.page.locator("#edStep")).to_have_text("1 of 3 · What")
    expect(tab.page.locator(".ed-quick-set")).to_have_count(1)
    expect(tab.page.locator(".ed-tabs")).to_be_hidden()
    tab.page.locator('#edScope input[value="filter"]').check()
    set_field(tab, "genre", "set", "Tech House")
    set_field(tab, "album", "set", "Bulk")
    tab.page.locator("#edPreviewBtn").click()

    expect(tab.page.locator("#edStep")).to_have_text("2 of 3 · Check")
    total = len(TRACKS) + 150
    expect(tab.page.locator("#edCounts")).to_have_text(f"{2 * total} changes on {total} tracks")
    expect(tab.page.locator(".ed-card")).to_have_count(total)
    assert tab.page.evaluate("document.documentElement.scrollWidth") <= PHONE["width"]
    # leave one track out with its switch, and one change of another with a tap
    first = tab.page.locator(".ed-card").nth(0)
    first.locator('input[role="switch"]').uncheck()
    expect(first.locator(".ed-card-change").first).to_have_attribute("aria-pressed", "false")
    second = tab.page.locator(".ed-card").nth(1)
    second.locator(".ed-card-change").first.click()
    expect(second.locator(".ed-card-change").first).to_have_attribute("aria-pressed", "false")
    apply = tab.page.locator("#edApply")
    expect(apply).to_have_text(f"Change {2 * total - 3} tags on {total - 1} tracks")
    apply.click()

    expect(tab.page.locator("#edStep")).to_have_text("3 of 3 · Apply")
    expect(tab.page.locator("#edResult")).to_have_text(f"Written to {total - 1} files.", timeout=60_000)
    expect(tab.page.locator(".ed-card")).to_have_count(0)    # nothing failed
    expect(tab.page.locator("#edUndo")).to_be_visible()
    # the first track left out whole, and the second without its album (its first change)
    assert sum(1 for i in server.items() if i["album"] == "Bulk") == total - 2
    assert tab.errors == []


def test_back_returns_to_the_first_step_and_rule_names_speak_italian(open_tab, server):
    assert server.http.put("/api/settings", json={"language": "it"}).status_code == 200
    tab = open_tab("/#library", PHONE)
    expect(tab.page.locator("html")).to_have_attribute("lang", "it")
    long_press(tab, "Midnight Drive")
    bar(tab).locator('[data-bulk="edit"]').click()
    expect(tab.page.locator("#edStep")).to_have_text("1 di 3 · Cosa")
    quick = tab.page.locator(".ed-quick-set")
    expect(quick).to_contain_text("Pulizia standard")
    expect(quick).to_contain_text("Togli il testo promozionale")
    quick.click()   # one tap: the set's preview
    expect(tab.page.locator("#edStep")).to_have_text("2 di 3 · Controlla")
    tab.page.locator("#edBack").click()
    expect(tab.page.locator("#edStep")).to_have_text("1 di 3 · Cosa")
    expect(quick).to_be_visible()
    assert tab.errors == []
