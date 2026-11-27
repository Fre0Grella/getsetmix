"""Batch editing, slice 4: rules in edits, rule sets, warnings and leaving
changes out (docs/design/batch-editing.md 3.4, 3.5, 4.2, 4.3)."""
import pytest
from mutagen.id3 import ID3
from test_edits import apply, ed, ids, preview, states  # noqa: F401 (ed is a fixture)

from app import library

SOURCE = "Source: https://example.test/x | via GetSetMix"


@pytest.fixture()
def messy(lib, music):
    music.mp3("a.mp3", seed=1, title="night drive (original mix) [free download]",
              artist="Nova ft Kito", genre="tech-house", comment=SOURCE)
    music.mp3("b.mp3", seed=2, title="Nova - Blue Hour (Extended Mix) www.promo.com",
              album="blue hour ep", genre="House")
    music.mp3("c.mp3", seed=3, title="Late Train  [Official Video]", artist="Sol x Moon",
              genre="drum n bass", comment="kept")
    music.mp3("d.mp3", seed=4, title="Clean", artist="Clean", genre="Disco Funk")
    lib.reconcile()
    return ids(lib)


def standard(ed):  # noqa: F811
    [rs] = [r for r in ed.rulesets() if r["builtin"]]
    return rs


def tags(music, name):
    t = ID3(music.path(name))
    return {k: str(t[f].text[0]) if f in t else "" for k, f in
            (("title", "TIT2"), ("artist", "TPE1"), ("album", "TALB"), ("genre", "TCON"))}


def test_the_built_in_set_cleans_messy_tracks_end_to_end(ed, music, messy):  # noqa: F811
    rs = standard(ed)
    assert rs["name"] == "Standard cleanup"
    out = ed.preview({"selection": {"ids": list(messy.values())}, "ruleset_id": rs["id"]})
    assert out["label"] == "Standard cleanup"
    apply(ed, out["id"])
    assert tags(music, "a.mp3") == {"title": "night drive (feat. Kito)", "artist": "Nova",
                                    "album": "", "genre": "Tech House"}
    assert tags(music, "b.mp3") == {"title": "Blue Hour (Extended Mix)", "artist": "Nova",
                                    "album": "Blue Hour EP", "genre": "House"}
    assert tags(music, "c.mp3") == {"title": "Late Train", "artist": "Sol, Moon",
                                    "album": "", "genre": "Drum & Bass"}
    assert tags(music, "d.mp3")["genre"] == "Disco Funk"
    # no rule touched a comment: the source link is where it was
    assert ID3(music.path("a.mp3")).getall("COMM")[0].text == [SOURCE]
    assert {c["field"] for c in ed.changes(out["id"])["items"]} <= {"title", "artist", "album", "genre"}


def test_each_change_names_the_rules_that_made_it(ed, messy):  # noqa: F811
    out = ed.preview({"selection": {"ids": [messy["a.mp3"]]}, "steps": [
        {"rule": "promo.remove"}, {"rule": "mix.remove_default"}, {"rule": "trim"}]})
    [title] = ed.changes(out["id"], field="title")["items"]
    assert title["new"] == "night drive"
    assert [b["rule"] for b in title["by"]] == ["promo.remove", "mix.remove_default"]


def test_a_rule_warning_comes_with_its_change(ed, messy):  # noqa: F811
    out = ed.preview({"selection": {"ids": [messy["d.mp3"]]}, "steps": [
        {"rule": "genre.map"}, {"op": "append", "field": "genre", "value": " Edit"}]})
    [change] = ed.changes(out["id"])["items"]
    assert change["warnings"] == ["not_in_genre_list"] and change["state"] == "pending"
    assert ed.changes(out["id"], warning="not_in_genre_list")["items"] == [change]


def test_steps_win_over_the_set_which_only_names_the_edit(ed, messy):  # noqa: F811
    rs = standard(ed)
    out = ed.preview({"selection": {"ids": [messy["c.mp3"]]}, "ruleset_id": rs["id"],
                      "steps": [{"rule": "artist.separators"}]})
    assert out["label"] == "Standard cleanup"
    assert {c["field"] for c in ed.changes(out["id"])["items"]} == {"artist"}
    with pytest.raises(library.LibraryError) as err:
        ed.preview({"selection": {"ids": [1]}, "ruleset_id": 999})
    assert err.value.status == 404


# --------------------------------------------------------------- rule sets
def test_the_built_in_set_cannot_be_changed_or_removed_but_a_copy_can(ed):  # noqa: F811
    rs = standard(ed)
    for call in (lambda: ed.save_ruleset({"name": "Mine"}, rs["id"]),
                 lambda: ed.delete_ruleset(rs["id"])):
        with pytest.raises(library.LibraryError) as err:
            call()
        assert err.value.status == 409
    copy = ed.save_ruleset({"name": "My cleanup", "steps": rs["steps"]})
    assert copy["builtin"] is False and copy["steps"] == rs["steps"]
    changed = ed.save_ruleset({"steps": list(reversed(rs["steps"]))[:3]}, copy["id"])
    assert changed["name"] == "My cleanup" and len(changed["steps"]) == 3
    renamed = ed.save_ruleset({"name": "Short"}, copy["id"])
    assert renamed["steps"] == changed["steps"]
    assert [r["name"] for r in ed.rulesets()] == ["Standard cleanup", "Short"]
    ed.delete_ruleset(copy["id"])
    assert [r["name"] for r in ed.rulesets()] == ["Standard cleanup"]


@pytest.mark.parametrize("body", [
    None, {"steps": [{"rule": "trim"}]}, {"name": " ", "steps": [{"rule": "trim"}]},
    {"name": "x" * 101, "steps": [{"rule": "trim"}]}, {"name": "A", "steps": []},
    {"name": "A", "steps": [{"rule": "nope"}]},
])
def test_a_rule_set_that_is_not_valid_is_400(ed, body):  # noqa: F811
    with pytest.raises(library.LibraryError) as err:
        ed.save_ruleset(body)
    assert err.value.status == 400


def test_names_are_unique(ed):  # noqa: F811
    ed.save_ruleset({"name": "A", "steps": [{"rule": "trim"}]})
    with pytest.raises(library.LibraryError) as err:
        ed.save_ruleset({"name": "Standard cleanup", "steps": [{"rule": "trim"}]})
    assert err.value.status == 409


# --------------------------------------------------------------- leave out
def test_leaving_out_and_putting_back_recomputes_and_only_pending_is_written(ed, music, messy):  # noqa: F811
    fids = [messy["a.mp3"], messy["c.mp3"]]
    out = ed.preview({"selection": {"ids": fids}, "ruleset_id": standard(ed)["id"]})
    pending = out["counts"]["by_state"]["pending"]
    genre_a = next(c for c in ed.changes(out["id"], field="genre")["items"]
                   if c["file_id"] == messy["a.mp3"])

    left = ed.leave_out(out["id"], {"exclude": {"files": [messy["c.mp3"]],
                                                "changes": [genre_a["change_id"]]}})
    c_changes = sum(1 for c in ed.changes(out["id"])["items"] if c["file_id"] == messy["c.mp3"])
    assert left["counts"]["by_state"]["excluded"] == c_changes + 1
    assert left["counts"]["by_state"]["pending"] == pending - c_changes - 1
    assert left["resend"]["tracks"] == 1

    back = ed.leave_out(out["id"], {"include": {"changes": [genre_a["change_id"]]}})
    assert back["counts"]["by_state"]["pending"] == pending - c_changes
    apply(ed, out["id"])
    assert tags(music, "a.mp3")["genre"] == "Tech House"
    assert tags(music, "c.mp3")["title"] == "Late Train  [Official Video]"   # left out: untouched
    assert set(states(ed, out["id"]).values()) == {"applied", "excluded"}
    with pytest.raises(library.LibraryError) as err:
        ed.leave_out(out["id"], {"include": {"files": [messy["c.mp3"]]}})
    assert err.value.status == 409


@pytest.mark.parametrize("body", [None, {"drop": {}}, {"exclude": {"files": "1"}},
                                  {"exclude": {"rows": [1]}}, {"include": {"changes": [True]}}])
def test_a_leave_out_that_is_not_valid_is_400(ed, messy, body):  # noqa: F811
    out = preview(ed, [messy["a.mp3"]])
    with pytest.raises(library.LibraryError) as err:
        ed.leave_out(out["id"], body)
    assert err.value.status == 400


def test_rule_sets_and_leave_out_over_http(tmp_path, monkeypatch, music):
    from test_library_api import _client, rescan
    music.mp3("a.mp3", seed=1, title="a b", genre="tech-house")
    with _client(tmp_path, monkeypatch) as api:
        rescan(api)
        sets = api.get("/api/library/rulesets").json()
        assert sets[0]["name"] == "Standard cleanup" and sets[0]["builtin"] is True
        made = api.post("/api/library/rulesets", json={"name": "Genres", "steps": [{"rule": "genre.map"}]})
        assert made.status_code == 201
        rid = made.json()["id"]
        assert api.put(f"/api/library/rulesets/{rid}", json={"name": "G"}).json()["name"] == "G"
        assert api.delete(f"/api/library/rulesets/{sets[0]['id']}").status_code == 409
        fid = api.get("/api/library").json()["items"][0]["id"]
        edit = api.post("/api/library/edits", json={"selection": {"ids": [fid]}, "ruleset_id": rid}).json()
        assert edit["label"] == "G"
        r = api.patch(f"/api/library/edits/{edit['id']}", json={"exclude": {"files": [fid]}})
        assert r.status_code == 200 and r.json()["counts"]["by_state"] == {"excluded": 1}
        assert api.delete(f"/api/library/rulesets/{rid}").status_code == 204
        assert api.put(f"/api/library/rulesets/{rid}", json={"name": "x"}).status_code == 404
