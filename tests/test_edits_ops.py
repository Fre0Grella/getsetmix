"""Batch editing, slice 5: the field operations, selection by filter and the
resend figure (docs/design/batch-editing.md 3.3, 3.4, 4.6)."""
import pytest
from mutagen.id3 import ID3
from test_edits import apply, ed, ids, preview  # noqa: F401 (ed is a fixture)

from app import library, rules


def run(fields, **step):
    return rules.run_steps(fields, [step]).fields


# ---------------------------------------------------------- the operations
@pytest.mark.parametrize("field,cleared", [("album", ""), ("genre", ""), ("comment", ""), ("year", None)])
def test_clear_empties_a_field(field, cleared):
    assert run({"album": "A", "genre": "G", "comment": "C", "year": 2019},
               op="clear", field=field)[field] == cleared


@pytest.mark.parametrize("field", ["title", "artist", "cover"])
def test_title_and_artist_cannot_be_cleared(field):
    with pytest.raises(rules.RuleError):
        run({"title": "T", "artist": "A"}, op="clear", field=field)


def test_append_and_prepend_add_the_value_as_given_and_nothing_to_an_empty_field():
    fields = {"title": "Night Drive", "album": ""}
    assert run(fields, op="append", field="title", value=" (Live)")["title"] == "Night Drive (Live)"
    assert run(fields, op="prepend", field="title", value="VIP ")["title"] == "VIP Night Drive"
    assert run(fields, op="append", field="album", value=" (Live)")["album"] == ""
    with pytest.raises(rules.RuleError):
        run(fields, op="append", field="year", value="1")
    with pytest.raises(rules.RuleError):
        run(fields, op="append", field="title", value=3)


def test_replace_is_plain_text_anywhere_by_default():
    fields = {"title": "Orig. Mix and orig. mix (a.b)"}
    assert run(fields, op="replace", field="title", find="Orig. Mix", **{"with": "Original Mix"})["title"] \
        == "Original Mix and orig. mix (a.b)"
    # no pattern: a dot is a dot, a backslash in the replacement is text
    assert run(fields, op="replace", field="title", find="a.b", **{"with": "\\1"})["title"] \
        == "Orig. Mix and orig. mix (\\1)"


def test_replace_by_whole_word_and_ignoring_case():
    fields = {"artist": "Nova x Kito, Xander X"}
    out = run(fields, op="replace", field="artist", find="x", match="word", ignore_case=True,
              **{"with": "&"})
    assert out["artist"] == "Nova & Kito, Xander &"
    out = run(fields, op="replace", field="artist", find="x", match="word", **{"with": "&"})
    assert out["artist"] == "Nova & Kito, Xander X"
    out = run(fields, op="replace", field="artist", find="x", **{"with": ""})
    assert out["artist"] == "Nova  Kito, Xander X"


@pytest.mark.parametrize("step", [
    {"op": "replace", "field": "title", "find": "", "with": "x"},
    {"op": "replace", "field": "title", "find": "a"},
    {"op": "replace", "field": "title", "find": "a", "with": "b", "match": "regex"},
    {"op": "replace", "field": "title", "find": "a", "with": "b", "ignore_case": "yes"},
    {"op": "replace", "field": "year", "find": "1", "with": "2"},
])
def test_a_replace_that_is_not_valid_is_refused(step):
    with pytest.raises(rules.RuleError):
        rules.run_steps({"title": "a", "year": 2019}, [step])


# ------------------------------------------------------- selection by filter
@pytest.fixture()
def shelf(lib, music):
    music.mp3("House/a.mp3", seed=1, title="Night Drive", artist="Nova", genre="House")
    music.mp3("House/b.mp3", seed=2, title="Day Drive", artist="Kito", genre="House")
    music.mp3("Techno/c.mp3", seed=3, title="Night Shift", artist="Sol", genre="Techno")
    music.wav("House/d.wav", seed=4)
    lib.reconcile()
    return ids(lib)


def by_filter(ed, **f):  # noqa: F811
    return ed.preview({"selection": {"filter": f},
                       "steps": [{"op": "append", "field": "title", "value": " (Edit)"}]})


def test_a_filter_is_resolved_and_frozen_when_the_preview_is_made(ed, lib, music, clock, shelf):  # noqa: F811
    out = by_filter(ed, genre="House")
    assert out["counts"]["selected"] == 2 and out["counts"]["changed"] == 2
    # a track that arrives later is not part of the edit
    music.mp3("House/e.mp3", seed=5, title="Late", genre="House", age=3600)
    lib.reconcile()
    apply(ed, out["id"])
    assert [c["path"] for c in ed.changes(out["id"])["items"]] == ["House/a.mp3", "House/b.mp3"]
    assert ID3(music.path("House/e.mp3"))["TIT2"].text == ["Late"]
    assert ID3(music.path("House/a.mp3"))["TIT2"].text == ["Night Drive (Edit)"]


def test_a_filter_takes_the_list_words_and_folder(ed, shelf):  # noqa: F811
    assert by_filter(ed, q="night")["counts"]["selected"] == 2
    folder = by_filter(ed, folder="House")
    assert folder["counts"]["selected"] == 3   # the WAV is in the folder, and skipped
    assert folder["counts"]["skipped_by_reason"] == {"read-only format": 1}
    assert by_filter(ed, q="nothing like this")["counts"]["selected"] == 0


def test_a_filter_over_the_limit_is_413(ed, shelf, monkeypatch):  # noqa: F811
    monkeypatch.setattr(library, "MAX_SELECTION", 2)
    with pytest.raises(library.LibraryError) as err:
        by_filter(ed, folder="House")
    assert err.value.status == 413


# ------------------------------------------------------------------ resend
def test_resend_counts_the_tracks_and_bytes_that_will_travel(ed, lib, music, shelf):  # noqa: F811
    out = preview(ed, [shelf["House/a.mp3"], shelf["House/b.mp3"], shelf["Techno/c.mp3"]],
                  [{"op": "set", "field": "genre", "value": "House"}])
    sizes = music.path("Techno/c.mp3").stat().st_size   # the only one that changes
    assert out["resend"] == {"tracks": 1, "bytes": sizes}
    apply(ed, out["id"])
    assert ed.get(out["id"])["resend"] == {"tracks": 0, "bytes": 0}   # nothing left to send


def test_operations_without_a_value_pass_the_request_check(ed, music, shelf):  # noqa: F811
    out = ed.preview({"selection": {"ids": [shelf["House/a.mp3"]]}, "steps": [
        {"op": "replace", "field": "title", "find": "Drive", "with": "Ride"},
        {"op": "clear", "field": "genre"}]})
    apply(ed, out["id"])
    tags = ID3(music.path("House/a.mp3"))
    assert tags["TIT2"].text == ["Night Ride"] and "TCON" not in tags
