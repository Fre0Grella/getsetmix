"""The Library API: list (search, filters, sorts, paging), status, rescan, auth."""
import pytest
from conftest import fresh_modules
from fastapi.testclient import TestClient

ITEM_KEYS = {"id", "audio_id", "path", "format", "title", "artist", "album", "genre", "year",
             "duration", "has_cover", "size", "added_at", "editable", "multi", "same_audio"}


def _client(tmp_path, monkeypatch, token=""):
    fresh_modules(tmp_path, monkeypatch, "app.worker", "app.main", token=token)
    import app.main
    return TestClient(app.main.app)


@pytest.fixture()
def api(tmp_path, monkeypatch, music):
    with _client(tmp_path, monkeypatch) as c:
        yield c


def rescan(api):
    """Index what is on disk now, the way the Library view asks for it."""
    from app import library
    lib = library.current()
    assert lib.wait(10)  # the pass the app started with
    r = api.post("/api/library/rescan")
    assert r.status_code == 202 and r.json() == {"started": True}
    assert lib.wait(10)


def listing(api, **params):
    r = api.get("/api/library", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def paths(body):
    return [item["path"] for item in body["items"]]


@pytest.fixture()
def shelf(api, music):
    music.mp3("Bob - Zebra.mp3", seed=1, title="Zebra", artist="bob", genre="House")
    music.mp3("Ann - Apple.mp3", seed=2, title="Apple", artist="Ann", genre="Techno")
    music.mp3("House/Cid - Mango.mp3", seed=3, title="Mango", artist="Cid", genre="House")
    music.mp3("House/deep/Dee - Kiwi.mp3", seed=4, title="Kiwi", artist="Dee", genre="House")
    music.wav("Eve - Pear.wav", seed=5)
    rescan(api)
    return api


def test_a_new_library_lists_nothing(api):
    assert listing(api) == {"rev": 0, "total": 0, "next": None, "items": []}


def test_an_item_has_the_shape_of_the_design(shelf):
    body = listing(shelf, q="zebra")
    assert body["total"] == 1 and body["rev"] == 5
    [item] = body["items"]
    assert set(item) == ITEM_KEYS
    assert item["path"] == "Bob - Zebra.mp3" and item["format"] == "mp3"
    assert item["editable"] is True and item["multi"] == [] and item["same_audio"] == []
    assert item["audio_id"].startswith("a1_") and item["has_cover"] is False


def test_search_genre_and_folder(shelf):
    assert sorted(paths(listing(shelf, q="MANGO cid"))) == ["House/Cid - Mango.mp3"]
    assert sorted(paths(listing(shelf, genre="House"))) == [
        "Bob - Zebra.mp3", "House/Cid - Mango.mp3", "House/deep/Dee - Kiwi.mp3"]
    assert listing(shelf, genre="house")["total"] == 0  # exact match
    assert paths(listing(shelf, folder="House")) == ["House/Cid - Mango.mp3"]
    assert paths(listing(shelf, folder="House/deep")) == ["House/deep/Dee - Kiwi.mp3"]
    assert paths(listing(shelf, folder="House", q="kiwi")) == []


def test_sorts(shelf):
    by_artist = paths(listing(shelf, sort="artist"))
    assert by_artist[:4] == ["Eve - Pear.wav", "Ann - Apple.mp3", "Bob - Zebra.mp3",
                             "House/Cid - Mango.mp3"]  # untagged first, case ignored
    assert paths(listing(shelf, sort="title", order="desc"))[:2] == [
        "Bob - Zebra.mp3", "House/Cid - Mango.mp3"]
    by_genre = listing(shelf, sort="genre")["items"]
    assert [i["genre"] for i in by_genre] == ["", "House", "House", "House", "Techno"]
    added = listing(shelf)["items"]  # added, newest first; ties by id
    assert [i["id"] for i in added] == sorted((i["id"] for i in added), reverse=True)


@pytest.mark.parametrize("sort", ["added", "artist", "title", "genre"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_paging_walks_every_item_once(shelf, sort, order):
    whole = paths(listing(shelf, sort=sort, order=order))
    seen, cursor = [], None
    while True:
        params = {"sort": sort, "order": order, "limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = listing(shelf, **params)
        assert body["total"] == 5
        seen += paths(body)
        cursor = body["next"]
        if not cursor:
            break
    assert seen == whole and len(seen) == 5


def test_bad_arguments_are_refused(shelf):
    for params in ({"sort": "bpm"}, {"order": "up"}, {"state": "gone"}, {"limit": 0},
                   {"limit": 501}, {"cursor": "nonsense"}):
        assert shelf.get("/api/library", params=params).status_code in (400, 422), params
    cursor = listing(shelf, sort="title", limit=1)["next"]
    r = shelf.get("/api/library", params={"sort": "artist", "cursor": cursor})
    assert r.status_code == 400  # a cursor only continues its own list


def test_editable_and_same_audio(api, music):
    music.mp3("a.mp3", seed=7)
    music.mp3("copy of a.mp3", seed=7)
    music.wav("b.wav")
    music.fixture("broken.mp3", "fallback/no-frames.mp3")
    rescan(api)
    items = {i["path"]: i for i in listing(api)["items"]}
    assert items["a.mp3"]["editable"] and not items["b.wav"]["editable"]
    assert not items["broken.mp3"]["editable"]  # fallback id
    assert items["a.mp3"]["same_audio"] == [items["copy of a.mp3"]["id"]]


def test_select_resolves_a_filter_to_every_id(shelf):
    from app import library
    chosen = library.current().select(genre="House")
    listed = {i["id"]: i["editable"] for i in listing(shelf, genre="House", limit=1)["items"]}
    assert len(chosen) == 3 and set(listed) <= {c["id"] for c in chosen}
    assert all(c["editable"] for c in chosen)
    everything = library.current().select()
    assert len(everything) == 5
    assert [c["editable"] for c in everything if c["id"] not in {x["id"] for x in chosen}
            ].count(False) == 1  # the WAV


def test_status(shelf, music):
    status = shelf.get("/api/library/status").json()
    assert status["rev"] == 5 and status["counts"] == {"present": 5}
    assert status["indexed"] is True and status["unavailable"] is False
    assert status["last_reconcile"] and status["indexing"]["running"] is False
    music.remove("Bob - Zebra.mp3")
    rescan(shelf)
    status = shelf.get("/api/library/status").json()
    assert status["counts"] == {"present": 4, "missing": 1} and status["rev"] == 6


def test_the_app_indexes_the_library_when_it_starts(tmp_path, monkeypatch, music):
    music.mp3("already here.mp3")
    with _client(tmp_path, monkeypatch) as c:
        from app import library
        assert library.current().wait(10)
        assert paths(listing(c)) == ["already here.mp3"]


def test_the_library_api_needs_the_app_token(tmp_path, monkeypatch, music):
    with _client(tmp_path, monkeypatch, token="sekret") as c:
        for method, url in (("get", "/api/library"), ("get", "/api/library/status"),
                            ("post", "/api/library/rescan")):
            assert getattr(c, method)(url).status_code == 401, url
            ok = getattr(c, method)(url, headers={"X-Auth-Token": "sekret"})
            assert ok.status_code in (200, 202), url
