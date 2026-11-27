"""Batch editing, slice 6: year, comment and cover in edits
(docs/design/batch-editing.md 3.2, 4.5, 4.7)."""
import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from test_edits import apply, ids, preview, states
from test_library_cover import JPEG, png
from test_library_edit import rich_flac, rich_mp3  # noqa: F401 (fixtures)

from app import edits, library, rules, tagger

DAY = 24 * 3600
SOURCE = "Source: https://example.test/x | via GetSetMix"


@pytest.fixture()
def ed(lib, clock, tmp_path):
    return edits.Edits(lib.db, lib, clock=clock, history_days=lambda: 30,
                       store=tmp_path / "store")


@pytest.fixture()
def shelf(lib, music, rich_mp3):  # noqa: F811
    music.mp3("plain.mp3", seed=7, title="Night Drive (2019)", artist="Nova", genre="House",
              comment=SOURCE + " www.promo.com")
    lib.reconcile()
    return ids(lib)


def undo(ed, eid):
    out = ed.undo(eid)
    assert ed.wait(10)
    return out


# ------------------------------------------------------------------ covers
def test_a_new_cover_for_a_selection_and_its_undo(ed, music, shelf, rich_mp3):  # noqa: F811
    original = tagger.read_cover(rich_mp3)
    assert original and tagger.read_cover(music.path("plain.mp3")) is None
    source = ed.keep_image(png())["source"]
    out = preview(ed, [shelf["Night Drive.mp3"], shelf["plain.mp3"]],
                  [{"op": "set_cover", "source": source}])
    assert out["counts"]["by_field"] == {"cover": 2} and out["label"] == "cover = new image"
    apply(ed, out["id"])
    for path in (rich_mp3, music.path("plain.mp3")):
        assert tagger.read_cover(path) == (png(), "image/png")
    # the tags were left as they were, and one write per file carried the cover
    assert ID3(music.path("plain.mp3"))["TIT2"].text == ["Night Drive (2019)"]

    undo(ed, out["id"])
    assert tagger.read_cover(rich_mp3) == original
    assert tagger.read_cover(music.path("plain.mp3")) is None
    assert set(states(ed, out["id"]).values()) == {"undone"}


def test_a_cover_and_tags_go_in_one_write(ed, lib, shelf):
    source = ed.keep_image(JPEG)["source"]
    rev = lib.rev()
    out = preview(ed, [shelf["plain.mp3"]], [{"op": "set", "field": "genre", "value": "Techno"},
                                            {"op": "set_cover", "source": source}])
    apply(ed, out["id"])
    assert lib.rev() == rev + 1
    assert lib.file(shelf["plain.mp3"])["has_cover"] == 1


def test_clearing_counts_only_tracks_with_a_cover_and_undo_restores_it(ed, music, shelf, rich_mp3):  # noqa: F811
    original = tagger.read_cover(rich_mp3)
    out = preview(ed, [shelf["Night Drive.mp3"], shelf["plain.mp3"]], [{"op": "clear_cover"}])
    assert out["counts"]["changed"] == 1 and out["counts"]["unchanged"] == 1
    apply(ed, out["id"])
    assert tagger.read_cover(rich_mp3) is None
    undo(ed, out["id"])
    assert tagger.read_cover(rich_mp3) == original


def test_undo_leaves_a_cover_changed_since_alone(ed, lib, music, shelf):
    out = preview(ed, [shelf["plain.mp3"]], [{"op": "set_cover", "source": ed.keep_image(JPEG)["source"]}])
    apply(ed, out["id"])
    lib.write_cover(shelf["plain.mp3"], (png(shade=10), ""))   # someone chose another
    back = ed.get(undo(ed, out["id"])["id"])
    assert back["progress"]["files_conflict"] == 1
    assert tagger.read_cover(music.path("plain.mp3")) == (png(shade=10), "image/png")


def test_a_cover_step_needs_an_upload_kept_here(ed, shelf):
    for step in ({"op": "set_cover"}, {"op": "set_cover", "source": "url:https://x.test/a.jpg"},
                 {"op": "set_cover", "source": "upload:" + "0" * 32},
                 {"op": "set_cover", "source": "upload:../../etc"}):
        with pytest.raises(library.LibraryError) as err:
            preview(ed, [shelf["plain.mp3"]], [step])
        assert err.value.status == 400, step
    with pytest.raises(library.LibraryError) as err:
        ed.keep_image(b"not an image")
    assert err.value.status == 400


def test_replaced_covers_and_unused_uploads_are_purged(ed, clock, tmp_path, shelf):
    kept = ed.keep_image(JPEG)["source"]
    ed.keep_image(png())   # never used
    out = preview(ed, [shelf["Night Drive.mp3"]], [{"op": "set_cover", "source": kept}])
    apply(ed, out["id"])
    store = tmp_path / "store"
    assert (store / str(out["id"])).is_dir()
    assert len(list((store / "uploads").iterdir())) == 2
    clock.advance(DAY + 1)
    import os
    for f in (store / "uploads").iterdir():   # the files' own age, as the clock says
        os.utime(f, (clock.now - DAY - 1, clock.now - DAY - 1))
    ed.purge()
    assert [f.name for f in (store / "uploads").iterdir()] == [kept.split(":")[1]]
    clock.advance(30 * DAY)
    ed.purge()
    assert not (store / str(out["id"])).exists()


def test_covers_over_http(tmp_path, monkeypatch, music):
    from test_library_api import _client, rescan
    music.mp3("a.mp3", seed=1, title="A")
    with _client(tmp_path, monkeypatch) as api:
        rescan(api)
        r = api.post("/api/library/edits/covers", files={"file": ("c.png", png(), "image/png")})
        assert r.status_code == 201 and r.json()["source"].startswith("upload:")
        assert api.post("/api/library/edits/covers",
                        files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 400
        fid = api.get("/api/library").json()["items"][0]["id"]
        edit = api.post("/api/library/edits", json={"selection": {"ids": [fid]},
                                                    "steps": [{"op": "set_cover", **r.json()}]}).json()
        api.post(f"/api/library/edits/{edit['id']}/apply")
        assert edits.current().wait(10)
        assert tagger.read_cover(music.path("a.mp3")) == (png(), "image/png")


# ------------------------------------------------------------ year, comment
def test_year_extract_in_an_edit_writes_the_year_to_the_file(ed, music, shelf):
    out = preview(ed, [shelf["plain.mp3"]], [{"rule": "year.extract", "params": {"remove": True}}])
    apply(ed, out["id"])
    tags = ID3(music.path("plain.mp3"))
    assert str(tags["TDRC"].text[0]) == "2019" and tags["TIT2"].text == ["Night Drive"]


def test_a_full_date_is_kept_when_the_year_is_not_edited(ed, lib, music, rich_flac):  # noqa: F811
    lib.reconcile()
    fid = ids(lib)["Night Drive.flac"]
    apply(ed, preview(ed, [fid], [{"op": "set", "field": "genre", "value": "Techno"}])["id"])
    assert FLAC(rich_flac)["date"] == ["2019-06-14"]
    apply(ed, preview(ed, [fid], [{"op": "set", "field": "year", "value": 2020}])["id"])
    assert FLAC(rich_flac)["date"] == ["2020"]


@pytest.mark.parametrize("rule", [r.id for r in rules.RULES])
def test_no_rule_touches_the_comment_unless_the_step_names_it(rule):
    fields = {"title": "night drive (2019) www.promo.com", "artist": "Nova ft Kito", "album": "",
              "genre": "tech-house", "year": None, "comment": SOURCE + " www.promo.com"}
    assert rules.run_steps(fields, [{"rule": rule}]).fields["comment"] == fields["comment"]
    standard = rules.BUILTIN_RULESETS[0]["steps"]
    assert rules.run_steps(fields, standard).fields["comment"] == fields["comment"]


def test_a_rule_aimed_at_the_comment_may_change_it():
    out = rules.run_steps({"comment": SOURCE + " www.promo.com"},
                          [{"rule": "url.remove", "fields": ["comment"]}])
    assert out.fields["comment"] != SOURCE + " www.promo.com"
