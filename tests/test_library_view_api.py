"""What the Library view reads: facets, long lists, the audio with range requests,
and the cover, read and replaced (design 3.3, 4.5)."""
import os

import pytest
from test_library_api import _client, listing, rescan
from test_library_cover import JPEG, png

from app import tagger


@pytest.fixture()
def api(tmp_path, monkeypatch, music):
    with _client(tmp_path, monkeypatch) as c:
        yield c


@pytest.fixture()
def shelf(api, music):
    music.mp3("Bob - Zebra.mp3", seed=1, title="Zebra", artist="bob", genre="House")
    music.mp3("Ann - Apple.mp3", seed=2, title="Apple", artist="Ann", genre="Techno")
    music.mp3("House/Cid - Mango.mp3", seed=3, title="Mango", artist="Cid", genre="House")
    music.mp3("House/deep/Dee - Kiwi.mp3", seed=4, title="Kiwi", artist="Dee", genre="Techno")
    music.mp3("House/deep/Eve - Fig.mp3", seed=5, title="Fig", artist="Eve", genre="Deep")
    music.wav("Eve - Pear.wav", seed=6)
    rescan(api)
    return api


def fid(api, rel):
    return {i["path"]: i["id"] for i in listing(api, limit=500)["items"]}[rel]


# ---------------------------------------------------------------- facets
def test_facets_count_genres_and_the_files_directly_in_each_folder(shelf):
    r = shelf.get("/api/library/facets")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"rev", "genres", "folders"} and body["rev"] == 6
    assert body["genres"] == [{"name": "House", "count": 2}, {"name": "Techno", "count": 2},
                              {"name": "Deep", "count": 1}]  # most first; no untagged entry
    assert body["folders"] == [{"path": "House", "count": 1}, {"path": "House/deep", "count": 2}]
    # what a facet counts is what the filter finds
    assert listing(shelf, genre="Techno")["total"] == 2
    assert listing(shelf, folder="House/deep")["total"] == 2


def test_facets_follow_the_state_and_are_not_taken_for_an_id(shelf):
    shelf.delete(f"/api/library/{fid(shelf, 'House/Cid - Mango.mp3')}")
    assert shelf.get("/api/library/facets").json()["folders"] == [
        {"path": "House/deep", "count": 2}]
    trashed = shelf.get("/api/library/facets", params={"state": "trashed"}).json()
    assert trashed["genres"] == [{"name": "House", "count": 1}]
    assert trashed["folders"] == [{"path": "House", "count": 1}]
    assert shelf.get("/api/library/facets", params={"state": "gone"}).status_code == 400
    assert shelf.post("/api/library/facets").status_code == 405  # a path, not an id


def test_facets_of_an_empty_library(api):
    assert api.get("/api/library/facets").json() == {"rev": 0, "genres": [], "folders": []}


# ----------------------------------------------------- long lists and filters
@pytest.fixture()
def long_shelf(api):
    """450 rows, put in the index directly: three pages of 200, 200 and 50."""
    from app import library
    lib = library.current()
    with lib.db.transaction() as conn:
        for n in range(450):
            tags = {"title": f"Song {n:03d}", "artist": f"Artist {n % 7}",
                    "album": "", "genre": ("House", "Techno", "")[n % 3], "comment": "",
                    "year": None, "has_cover": 0, "multi": "", "duration": 200.0,
                    "bitrate": 320, "sample_rate": 44100}
            lib._insert(conn, f"{'Set A/' if n % 2 else ''}song{n:03d}.mp3", 10, n,
                        f"a1_{n:032x}", tags, f"2026-01-01T00:{n // 60:02d}:{n % 60:02d}+00:00",
                        "")
    return api


def test_the_default_page_is_200_and_the_cursor_walks_the_rest(long_shelf):
    first = listing(long_shelf)
    assert len(first["items"]) == 200 and first["total"] == 450 and first["next"]
    second = listing(long_shelf, cursor=first["next"])
    third = listing(long_shelf, cursor=second["next"])
    assert (len(second["items"]), len(third["items"]), third["next"]) == (200, 50, None)
    seen = [i["id"] for p in (first, second, third) for i in p["items"]]
    assert len(set(seen)) == 450 and seen == sorted(seen, reverse=True)  # newest first


@pytest.mark.parametrize("sort", ["added", "artist", "title", "genre"])
def test_paging_with_a_filter_and_a_sort_matches_the_whole_list(long_shelf, sort):
    params = {"genre": "House", "folder": "Set A", "sort": sort, "limit": 40}
    whole = [i["id"] for i in listing(long_shelf, **{**params, "limit": 500})["items"]]
    pages, cursor = [], None
    while True:
        body = listing(long_shelf, **params, **({"cursor": cursor} if cursor else {}))
        pages += [i["id"] for i in body["items"]]
        cursor = body["next"]
        if not cursor:
            break
    assert pages == whole and len(whole) == len(set(whole)) == 75  # odd n, n % 3 == 0
    assert listing(long_shelf, **{**params, "q": "song 003"})["total"] == 1


def test_a_cursor_from_another_filter_still_pages_by_its_own_sort(long_shelf):
    cursor = listing(long_shelf, sort="title", limit=3)["next"]
    page = listing(long_shelf, sort="title", limit=3, cursor=cursor)
    assert [i["title"] for i in page["items"]] == ["Song 003", "Song 004", "Song 005"]


# ----------------------------------------------------------------- audio
def audio_bytes(music, rel):
    return music.path(rel).read_bytes()


def test_the_audio_is_served_whole_with_its_type_and_ranges_announced(shelf, music):
    r = shelf.get(f"/api/library/{fid(shelf, 'Bob - Zebra.mp3')}/audio")
    data = audio_bytes(music, "Bob - Zebra.mp3")
    assert r.status_code == 200 and r.content == data
    assert r.headers["content-type"] == "audio/mpeg" and r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-length"] == str(len(data))
    assert "no-cache" in r.headers["cache-control"] and r.headers["etag"]
    wav = shelf.get(f"/api/library/{fid(shelf, 'Eve - Pear.wav')}/audio")
    assert wav.status_code == 200 and wav.headers["content-type"] == "audio/wav"


@pytest.mark.parametrize("header, first, last", [
    ("bytes=0-99", 0, 99), ("bytes=100-199", 100, 199), ("bytes=100-", 100, None),
    ("bytes=-50", None, None), ("bytes=0-0", 0, 0), ("bytes=10-99999999", 10, None),
])
def test_range_requests_answer_206_with_exactly_those_bytes(shelf, music, header, first, last):
    data = audio_bytes(music, "Bob - Zebra.mp3")
    size = len(data)
    if header == "bytes=-50":
        first, last = size - 50, size - 1
    first = first if first is not None else 0
    last = last if last is not None else size - 1
    r = shelf.get(f"/api/library/{fid(shelf, 'Bob - Zebra.mp3')}/audio",
                  headers={"Range": header})
    assert r.status_code == 206
    assert r.content == data[first:last + 1]
    assert r.headers["content-range"] == f"bytes {first}-{last}/{size}"
    assert r.headers["content-length"] == str(last - first + 1)
    assert r.headers["accept-ranges"] == "bytes"


def test_a_range_past_the_end_is_416_and_an_odd_one_is_ignored(shelf, music):
    url = f"/api/library/{fid(shelf, 'Bob - Zebra.mp3')}/audio"
    size = len(audio_bytes(music, "Bob - Zebra.mp3"))
    for header in (f"bytes={size}-", f"bytes={size + 100}-{size + 200}", "bytes=-0",
                   "bytes=50-10"):
        r = shelf.get(url, headers={"Range": header})
        assert r.status_code == 416, header
        assert r.headers["content-range"] == f"bytes */{size}"
    for header in ("bytes=0-1,5-6", "items=0-3", "bytes=abc", "bytes=-", ""):
        r = shelf.get(url, headers={"Range": header})
        assert r.status_code == 200 and len(r.content) == size, header


def test_the_audio_of_a_trashed_track_comes_from_the_trash_until_it_is_purged(shelf, music):
    from app import library
    i = fid(shelf, "Ann - Apple.mp3")
    data = audio_bytes(music, "Ann - Apple.mp3")
    shelf.delete(f"/api/library/{i}")
    r = shelf.get(f"/api/library/{i}/audio", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and r.content == data[:10]
    library.current().purge(everything=True)
    assert shelf.get(f"/api/library/{i}/audio").status_code == 410  # gone
    assert shelf.get(f"/api/library/{i}/cover").status_code == 410


def test_unknown_and_missing_and_unreadable_rows(shelf, music):
    assert shelf.get("/api/library/9999/audio").status_code == 404
    assert shelf.get("/api/library/9999/cover").status_code == 404
    i = fid(shelf, "Bob - Zebra.mp3")
    music.remove("Bob - Zebra.mp3")  # still `present` in the index until a pass
    assert shelf.get(f"/api/library/{i}/audio").status_code == 410
    rescan(shelf)
    assert shelf.get(f"/api/library/{i}/audio").status_code == 410  # now `missing`
    assert shelf.get(f"/api/library/{i}/cover").status_code == 410


def _set_path(rel_from, rel_to=None, trash_path=None, state=None):
    from app import library
    with library.current().db.transaction() as conn:
        if rel_to is not None:
            conn.execute("UPDATE library_files SET path = ? WHERE path = ?", (rel_to, rel_from))
        if trash_path is not None:
            conn.execute("UPDATE library_files SET trash_path = ?, state = ? WHERE path = ?",
                         (trash_path, state, rel_from))


@pytest.mark.parametrize("evil", ["../outside.mp3", "/etc/hostname", "a/../../outside.mp3",
                                  "..\\outside.mp3", ".hidden.mp3", "x/.part/y.mp3", ""])
def test_a_row_can_never_point_outside_the_library(shelf, music, tmp_path, evil):
    (tmp_path / "outside.mp3").write_bytes(b"secret")
    i = fid(shelf, "Bob - Zebra.mp3")
    _set_path("Bob - Zebra.mp3", evil)
    for kind in ("audio", "cover"):
        r = shelf.get(f"/api/library/{i}/{kind}")
        assert r.status_code in (404, 410) and b"secret" not in r.content, (evil, kind)


@pytest.mark.parametrize("evil", ["../outside.mp3", ".trash/../../outside.mp3", "Bob.mp3",
                                  ".trash/x", "/etc/hostname", ".trash/20260101T000000Z-1/../../../outside.mp3"])
def test_a_trash_path_can_never_point_outside_the_trash(shelf, music, tmp_path, evil):
    (tmp_path / "outside.mp3").write_bytes(b"secret")
    i = fid(shelf, "Bob - Zebra.mp3")
    _set_path("Bob - Zebra.mp3", trash_path=evil, state="trashed")
    for kind in ("audio", "cover"):
        r = shelf.get(f"/api/library/{i}/{kind}")
        assert r.status_code in (404, 410) and b"secret" not in r.content, (evil, kind)


def test_a_link_that_leaves_the_library_is_not_followed(shelf, music, tmp_path):
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"secret")
    link = music.path("Bob - Zebra.mp3")
    link.unlink()
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not allowed here")
    i = fid(shelf, "Bob - Zebra.mp3")
    r = shelf.get(f"/api/library/{i}/audio")
    assert r.status_code == 404 and b"secret" not in r.content


def test_audio_and_cover_answer_to_the_token_in_the_address(tmp_path, monkeypatch, music):
    music.fixture("a.mp3", "mp3/cover.mp3")
    with _client(tmp_path, monkeypatch, token="sekret") as c:
        from app import library
        assert library.current().wait(10)
        library.current().reconcile()
        i = library.current().list()["items"][0]["id"]
        for kind in ("audio", "cover"):
            assert c.get(f"/api/library/{i}/{kind}").status_code == 401
            assert c.get(f"/api/library/{i}/{kind}", params={"token": "sekret"}).status_code == 200
            assert c.get(f"/api/library/{i}/{kind}",
                         headers={"X-Auth-Token": "sekret"}).status_code == 200


# ----------------------------------------------------------------- cover
@pytest.fixture()
def covers(api, music):
    music.fixture("with.mp3", "mp3/cover.mp3")
    music.fixture("with.flac", "flac/cover.flac")
    music.fixture("with.m4a", "m4a/cover.m4a")
    music.mp3("without.mp3", seed=3, title="Plain")
    rescan(api)
    return api


def test_the_cover_is_served_as_stored_with_its_type(covers, music):
    for name in ("with.mp3", "with.flac", "with.m4a"):
        r = covers.get(f"/api/library/{fid(covers, name)}/cover")
        assert r.status_code == 200, name
        assert r.content == tagger.read_cover(music.path(name))[0]
        assert r.headers["content-type"] in ("image/png", "image/jpeg")
        assert r.headers["x-content-type-options"] == "nosniff"
    r = covers.get(f"/api/library/{fid(covers, 'without.mp3')}/cover")
    assert r.status_code == 404


def test_the_cover_cache_is_keyed_by_the_revision_so_an_edit_refreshes(covers, music):
    i = fid(covers, "with.mp3")
    item = covers.get(f"/api/library/{i}").json()
    rev = item["content_rev"]
    url = f"/api/library/{i}/cover"

    fresh = covers.get(url, params={"v": rev})
    assert fresh.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert covers.get(url, params={"v": rev + 1}).headers["cache-control"] == "private, no-cache"
    assert covers.get(url).headers["cache-control"] == "private, no-cache"

    etag = fresh.headers["etag"]
    again = covers.get(url, params={"v": rev}, headers={"If-None-Match": etag})
    assert again.status_code == 304 and not again.content
    assert again.headers["etag"] == etag and "immutable" in again.headers["cache-control"]

    changed = covers.post(url, files={"file": ("c.png", png(24, 24, 40), "image/png")})
    assert changed.status_code == 200
    new_rev = changed.json()["content_rev"]
    assert new_rev > rev  # the old URL is no longer the fresh one
    stale = covers.get(url, params={"v": rev}, headers={"If-None-Match": etag})
    assert stale.status_code == 200 and stale.headers["etag"] != etag
    assert stale.headers["cache-control"] == "private, no-cache"
    assert stale.content == png(24, 24, 40)
    assert covers.get(url, params={"v": new_rev}).headers["cache-control"].endswith("immutable")


def test_a_tag_edit_changes_the_revision_too_so_the_image_is_asked_for_again(covers):
    i = fid(covers, "with.mp3")
    before = covers.get(f"/api/library/{i}").json()["content_rev"]
    covers.patch(f"/api/library/{i}", json={"title": "New"})
    assert covers.get(f"/api/library/{i}").json()["content_rev"] > before


def test_upload_a_cover(covers, music):
    i = fid(covers, "with.mp3")
    old = tagger.read_cover(music.path("with.mp3"))
    new = png(40, 40, 10)
    r = covers.post(f"/api/library/{i}/cover", files={"file": ("x.png", new, "image/png")})
    assert r.status_code == 200
    item = r.json()
    assert item["id"] == i and item["has_cover"] is True and "comment" in item
    assert tagger.read_cover(music.path("with.mp3")) == (new, "image/png")
    assert tagger.read_cover(music.path("with.mp3")) != old
    assert covers.get(f"/api/library/{i}/cover").content == new
    # the answer is the updated item, as GET shows it, and the old image is not returned
    assert covers.get(f"/api/library/{i}").json() == item
    j = fid(covers, "without.mp3")
    assert covers.post(f"/api/library/{j}/cover",
                       files={"file": ("x.jpg", JPEG, "image/jpeg")}).json()["has_cover"] is True


def test_the_cover_from_an_address(covers, music, monkeypatch):
    asked = []
    image = png(30, 30, 99)
    monkeypatch.setattr(tagger, "fetch_image", lambda url: asked.append(url) or (image, "image/png"))
    i = fid(covers, "with.flac")
    r = covers.post(f"/api/library/{i}/cover", json={"url": "https://img.example/600x600.jpg"})
    assert r.status_code == 200 and asked == ["https://img.example/600x600.jpg"]
    assert tagger.read_cover(music.path("with.flac")) == (image, "image/png")
    monkeypatch.setattr(tagger, "fetch_image", lambda url: None)
    assert covers.post(f"/api/library/{i}/cover",
                       json={"url": "https://img.example/x"}).status_code == 502


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x/y.jpg", "javascript:alert(1)", "",
                                 None, 5])
def test_only_http_addresses_are_fetched(covers, music, monkeypatch, url):
    monkeypatch.setattr(tagger, "fetch_image", lambda u: pytest.fail("fetched " + u))
    r = covers.post(f"/api/library/{fid(covers, 'with.mp3')}/cover", json={"url": url})
    assert r.status_code == 400


def test_bad_uploads_leave_the_file_alone(covers, music):
    i = fid(covers, "with.mp3")
    before = music.path("with.mp3").read_bytes()
    url = f"/api/library/{i}/cover"
    assert covers.post(url, files={"file": ("x", b"<html></html>", "image/png")}).status_code == 400
    assert covers.post(url, files={"file": ("x", b"", "image/png")}).status_code == 400
    assert covers.post(url, files={"other": ("x", png(), "image/png")}).status_code == 400
    assert covers.post(url, json={"nothing": 1}).status_code == 400
    big = JPEG + b"\x00" * tagger.MAX_COVER
    assert covers.post(url, files={"file": ("x.jpg", big, "image/jpeg")}).status_code == 413
    assert music.path("with.mp3").read_bytes() == before


def test_a_cover_cannot_replace_in_readonly_trashed_or_unknown_files(covers, music):
    files = {"file": ("x.png", png(), "image/png")}
    assert covers.post(f"/api/library/{fid(covers, 'with.m4a')}/cover",
                       files=files).status_code == 409
    assert covers.post("/api/library/9999/cover", files=files).status_code == 404
    i = fid(covers, "with.mp3")
    covers.delete(f"/api/library/{i}")
    assert covers.post(f"/api/library/{i}/cover", files=files).status_code == 410
    assert covers.post("/api/library/cover", files=files).status_code in (404, 405)
