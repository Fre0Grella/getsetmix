"""GET and PATCH /api/library/{id}: one file, and its tag edit with every answer."""
import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from test_library_api import ITEM_KEYS, _client, rescan

DETAIL_KEYS = ITEM_KEYS | {"comment", "bitrate", "sample_rate", "source_url"}


@pytest.fixture()
def api(tmp_path, monkeypatch, music):
    with _client(tmp_path, monkeypatch) as c:
        yield c


@pytest.fixture()
def shelf(api, music):
    music.fixture("Night Drive.mp3", "mp3/all-tags.mp3")
    music.fixture("Night Drive.flac", "flac/cover.flac")
    music.wav("Take.wav")
    music.fixture("broken.mp3", "fallback/no-frames.mp3")
    rescan(api)
    return api


def ids(api):
    return {i["path"]: i["id"] for i in api.get("/api/library").json()["items"]}


def test_one_file_with_all_fields(shelf):
    item = shelf.get(f"/api/library/{ids(shelf)['Night Drive.mp3']}").json()
    assert set(item) == DETAIL_KEYS
    assert item["comment"].startswith("Source: https://example.test")
    assert item["artist"] == "Some Artist; Other Artist" and item["multi"] == ["artist"]
    assert item["year"] == 2019 and item["editable"] is True and item["has_cover"] is True
    assert shelf.get("/api/library/9999").status_code == 404


def test_fixed_paths_are_not_shadowed_by_the_id_routes(shelf):
    assert shelf.get("/api/library/rules").status_code == 200
    assert "genre_picks" in shelf.get("/api/library/rules").json()
    assert shelf.get("/api/library/status").status_code == 200
    assert shelf.patch("/api/library/rules", json={"title": "x"}).status_code == 405
    assert shelf.patch("/api/library/trash", json={"title": "x"}).status_code == 405
    assert shelf.get("/api/library/trash").status_code == 405


@pytest.mark.parametrize("name", ["Night Drive.mp3", "Night Drive.flac"])
def test_editing_per_format(shelf, music, name):
    fid = ids(shelf)[name]
    rev = shelf.get("/api/library/status").json()["rev"]
    r = shelf.patch(f"/api/library/{fid}", json={"genre": "Tech House", "year": 2021,
                                                 "comment": "kept for the gig"})
    assert r.status_code == 200, r.text
    item = r.json()
    assert set(item) == DETAIL_KEYS
    assert (item["genre"], item["year"], item["comment"]) == ("Tech House", 2021,
                                                             "kept for the gig")
    assert item["title"] == "Night Drive"  # not sent, not changed
    assert shelf.get("/api/library/status").json()["rev"] == rev + 1
    assert shelf.get(f"/api/library/{fid}").json() == item
    path = music.path(name)
    if name.endswith(".mp3"):
        tags = ID3(path)
        assert tags["TCON"].text == ["Tech House"] and str(tags["TDRC"].text[0]) == "2021"
    else:
        tags = FLAC(path)
        assert tags["genre"] == ["Tech House"] and tags["date"] == ["2021"]
        assert tags["comment"] == ["kept for the gig"]


def test_clearing_with_empty_values_and_null_year(shelf):
    fid = ids(shelf)["Night Drive.mp3"]
    item = shelf.patch(f"/api/library/{fid}", json={"album": "", "year": None}).json()
    assert item["album"] == "" and item["year"] is None


@pytest.mark.parametrize("body", [{"year": 999}, {"year": 10000}, {"year": "2019"},
                                  {"title": None}, {"title": 3}, {"bpm": "124"},
                                  {"expect": "nope"}, {"title": "x", "expect": {"key": "8A"}},
                                  {"title": "x", "expect": {"year": "2019"}}])
def test_bad_values_are_400(shelf, body):
    r = shelf.patch(f"/api/library/{ids(shelf)['Night Drive.mp3']}", json=body)
    assert r.status_code == 400, (body, r.text)


def test_unknown_id_is_404(shelf):
    assert shelf.patch("/api/library/9999", json={"title": "x"}).status_code == 404


@pytest.mark.parametrize("name", ["Take.wav", "broken.mp3"])
def test_read_only_formats_and_fallback_ids_are_409(shelf, music, name):
    before = music.path(name).read_bytes()
    r = shelf.patch(f"/api/library/{ids(shelf)[name]}", json={"title": "x"})
    assert r.status_code == 409
    assert music.path(name).read_bytes() == before


def test_a_trashed_or_gone_file_is_410(shelf):
    import app.db
    fid = ids(shelf)["Night Drive.mp3"]
    for state in ("trashed", "gone", "missing"):
        with app.db.db.transaction() as conn:
            conn.execute("UPDATE library_files SET state = ? WHERE id = ?", (state, fid))
        assert shelf.patch(f"/api/library/{fid}", json={"title": "x"}).status_code == 410, state


def test_a_file_deleted_through_the_api_is_410_and_keeps_its_tags(shelf, music):
    fid = ids(shelf)["Night Drive.mp3"]
    assert shelf.delete(f"/api/library/{fid}").status_code == 200
    assert shelf.patch(f"/api/library/{fid}", json={"title": "x"}).status_code == 410
    assert shelf.post(f"/api/library/{fid}/restore").status_code == 200
    assert shelf.get(f"/api/library/{fid}").json()["title"] == "Night Drive"


def test_a_file_missing_from_disk_is_410(shelf, music):
    fid = ids(shelf)["Night Drive.mp3"]
    music.remove("Night Drive.mp3")
    assert shelf.patch(f"/api/library/{fid}", json={"title": "x"}).status_code == 410


def test_expect_mismatch_is_412_with_the_file_values(shelf, music):
    fid = ids(shelf)["Night Drive.mp3"]
    before = music.path("Night Drive.mp3").read_bytes()
    r = shelf.patch(f"/api/library/{fid}",
                    json={"genre": "Tech House", "year": 2019, "expect": {"genre": "tech-house"}})
    assert r.status_code == 412
    assert r.json() == {"detail": "the file changed", "differs": {"genre": "House"}}
    assert music.path("Night Drive.mp3").read_bytes() == before
    ok = shelf.patch(f"/api/library/{fid}",
                     json={"genre": "Tech House", "expect": {"genre": "House"}})
    assert ok.status_code == 200 and ok.json()["genre"] == "Tech House"


def test_a_file_in_use_is_423(shelf, music, monkeypatch):
    from app import tagger

    def held(src, dst):
        raise PermissionError(32, "in use")

    monkeypatch.setattr(tagger.os, "replace", held)
    r = shelf.patch(f"/api/library/{ids(shelf)['Night Drive.mp3']}", json={"title": "x"})
    assert r.status_code == 423 and "in use" in r.json()["detail"]


def test_the_edit_needs_the_app_token(tmp_path, monkeypatch, music):
    music.mp3("a.mp3", title="a")
    with _client(tmp_path, monkeypatch, token="sekret") as c:
        from app import library
        assert library.current().wait(10)
        fid = library.current().select()[0]["id"]
        assert c.get(f"/api/library/{fid}").status_code == 401
        assert c.patch(f"/api/library/{fid}", json={"title": "b"}).status_code == 401
        ok = c.patch(f"/api/library/{fid}", json={"title": "b"},
                     headers={"X-Auth-Token": "sekret"})
        assert ok.status_code == 200 and ok.json()["title"] == "b"
