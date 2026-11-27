"""Finding tracks: the artist and problem filters, and the ids of a whole
view (docs/design/library.md 4.5.2)."""
import pytest
from test_library_api import _client, listing, rescan

from app import rules


# ----------------------------------------------------------------- the rules
@pytest.mark.parametrize("artist,title,names", [
    ("Nova ft Kito", "x", ["Nova", "Kito"]),
    ("Nova, Kito & Sol", "x", ["Nova", "Kito", "Sol"]),
    ("Sol x Moon", "x", ["Sol", "Moon"]),
    ("Sol vs. Moon", "x", ["Sol", "Moon"]),
    ("Nova", "Night Drive (feat. Kito)", ["Nova", "Kito"]),
    ("Nova", "Night [ft. Kito & Sol] (Extended Mix)", ["Nova", "Kito", "Sol"]),
    ("Nova", "Night feat. Kito", ["Nova", "Kito"]),
    ("Malcolm", "Xylophone", ["Malcolm"]),
    ("", "", []),
])
def test_every_artist_a_track_names(artist, title, names):
    assert rules.artists_of(artist, title) == names


def test_problems_come_from_the_rules_that_fix_them():
    messy = {"title": "night [free download]", "artist": "nova ft kito", "genre": "", "year": None}
    assert rules.problems_of(messy, has_cover=False) == [
        "no_genre", "no_year", "no_cover", "lowercase", "feat", "promo"]
    clean = {"title": "Night", "artist": "Nova", "genre": "House", "year": 2019}
    assert rules.problems_of(clean, has_cover=True) == []


# ------------------------------------------------------------ the filters
@pytest.fixture()
def api(tmp_path, monkeypatch, music):
    with _client(tmp_path, monkeypatch) as c:
        yield c


@pytest.fixture()
def shelf(api, music):
    music.mp3("a.mp3", seed=1, title="Night Drive", artist="Nova", genre="House", year="2019")
    music.mp3("b.mp3", seed=2, title="Blue Hour (feat. Kito)", artist="Élan", genre="House", year="2020")
    music.mp3("c.mp3", seed=3, title="late train [free download]", artist="kito ft nova")
    music.mp3("d.mp3", seed=4, title="Day", artist="Sol, KITO", genre="Disco", year="2021")
    music.mp3("e.mp3", seed=1, title="Night Drive copy", artist="Nova", genre="House", year="2019")
    rescan(api)
    return api


def paths(api, **params):
    return sorted(i["path"] for i in listing(api, **params)["items"])


def test_an_artist_is_found_as_main_collaborator_or_featured(shelf):
    assert paths(shelf, artist="Kito") == ["b.mp3", "c.mp3", "d.mp3"]
    assert paths(shelf, artist="kito") == paths(shelf, artist="KITO")
    assert paths(shelf, artist="elan") == ["b.mp3"]          # accents folded
    assert paths(shelf, artist="Nova") == ["a.mp3", "c.mp3", "e.mp3"]
    assert paths(shelf, artist="Kit") == []                   # a name, not a fragment
    assert paths(shelf, artist="Kito", genre="House") == ["b.mp3"]


@pytest.mark.parametrize("problem,expected", [
    ("no_genre", ["c.mp3"]), ("no_year", ["c.mp3"]), ("lowercase", ["c.mp3"]),
    ("feat", ["c.mp3"]), ("promo", ["c.mp3"]), ("same_audio", ["a.mp3", "e.mp3"]),
    ("no_cover", ["a.mp3", "b.mp3", "c.mp3", "d.mp3", "e.mp3"]),
])
def test_each_problem_filter_matches_what_its_rule_would_change(shelf, problem, expected):
    assert paths(shelf, problem=problem) == expected


def test_a_problem_that_does_not_exist_is_400(shelf):
    assert shelf.get("/api/library", params={"problem": "ugly"}).status_code == 400


def test_facets_count_artists_and_problems(shelf):
    f = shelf.get("/api/library/facets").json()
    artists = {a["name"]: a["count"] for a in f["artists"]}
    assert artists["Kito"] == 3     # "Kito", "kito", "KITO": the mixed-case one names it
    assert artists["Nova"] == 3 and artists["Élan"] == 1
    assert f["artists"][0]["count"] == 3
    problems = {p["id"]: p["count"] for p in f["problems"]}
    assert problems == {"no_genre": 1, "no_year": 1, "no_cover": 5, "lowercase": 1, "feat": 1,
                        "promo": 1, "same_audio": 2}


def test_an_edit_updates_what_the_filters_see(shelf):
    fid = next(i["id"] for i in listing(shelf)["items"] if i["path"] == "c.mp3")
    shelf.patch(f"/api/library/{fid}", json={"genre": "Techno", "artist": "Kito, Nova",
                                             "title": "Late Train"})
    assert paths(shelf, problem="no_genre") == []
    assert paths(shelf, problem="feat") == [] and paths(shelf, problem="lowercase") == []
    assert "c.mp3" in paths(shelf, artist="Nova")


def test_the_ids_of_a_whole_view(shelf):
    ids = shelf.get("/api/library/ids", params={"artist": "Kito"}).json()["ids"]
    assert len(ids) == 3
    assert shelf.get("/api/library/ids", params={"problem": "x"}).status_code == 400


def test_an_edit_can_take_the_artist_filter_as_its_selection(shelf):
    out = shelf.post("/api/library/edits", json={
        "selection": {"filter": {"artist": "Kito", "genre": "House"}},
        "steps": [{"op": "set", "field": "genre", "value": "Tech House"}]}).json()
    assert out["counts"]["selected"] == 1


def test_rows_from_before_the_columns_are_filled_once(shelf):
    import app.db
    from app import library
    with app.db.db.transaction() as conn:
        conn.execute("UPDATE library_files SET artists = NULL, problems = NULL")
    assert paths(shelf, artist="Kito") == []
    assert library.current()._backfill() == 5
    assert paths(shelf, artist="Kito") == ["b.mp3", "c.mp3", "d.mp3"]
    assert library.current()._backfill() == 0
