"""The Downloads routes of app/main.py: pasting a link, editing a staged track
and its cover, retrying, settings, the cover search and the folder picker.
yt-dlp and the network are replaced at their seams (`metadata`, `outbound`)."""
import io
import json
import time

import pytest
from conftest import fresh_modules
from fastapi.testclient import TestClient

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _client(tmp_path, monkeypatch, token=""):
    fresh_modules(tmp_path, monkeypatch, "app.link", "app.worker", "app.main", token=token)
    import app.main
    return TestClient(app.main.app)


@pytest.fixture()
def api(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        yield c


@pytest.fixture()
def m():
    import app.main
    return app.main


def _wait_for(api, done, timeout=10.0):
    """Poll the track list until `done(tracks)`; the resolve runs in the background."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        tracks = api.get("/api/tracks").json()["tracks"]
        if done(tracks):
            return tracks
        time.sleep(0.02)
    raise AssertionError(f"not done in {timeout}s: {tracks}")


# ------------------------------------------------------------ pasting a link
def test_a_pasted_playlist_becomes_one_staged_track_per_video(api, m, monkeypatch):
    def probe(url):
        return {"kind": "playlist", "title": "Set", "entries": [
            {"url": "https://v/1", "title": "Nova - One", "uploader": "", "duration": 60.0,
             "thumbnail": "", "id": "1", "extractor": "Youtube"},
            {"url": "", "title": "deleted", "uploader": "", "duration": 0.0,
             "thumbnail": "", "id": "", "extractor": ""},
            {"url": "https://v/2", "title": "Two", "uploader": "Kito", "duration": 61.0,
             "thumbnail": "", "id": "2", "extractor": "Youtube"},
        ]}

    def fetch_single(url):
        n = url.rsplit("/", 1)[-1]
        return {"title": f"Song {n}", "artist": "Nova", "album": "", "genre": "House",
                "duration": 60.0, "thumbnail": "", "video_id": n, "source": "Youtube",
                "url": url}

    monkeypatch.setattr(m.metadata, "probe", probe)
    monkeypatch.setattr(m.metadata, "fetch_single", fetch_single)

    r = api.post("/api/tracks", json={"url": "https://youtube.com/playlist?list=x"})
    assert r.status_code == 201
    tracks = _wait_for(api, lambda ts: len(ts) == 2 and all(t["status"] == "staged" for t in ts))
    assert sorted((t["url"], t["title"], t["genre"]) for t in tracks) == [
        ("https://v/1", "Song 1", "House"), ("https://v/2", "Song 2", "House")]
    assert api.get("/api/history").json()["history"][0]["url"] == \
        "https://youtube.com/playlist?list=x"


def test_a_link_that_cannot_be_resolved_is_marked_fetch_error(api, m, monkeypatch):
    def probe(url):
        raise RuntimeError("ERROR: Unsupported URL: https://nothing.example/")

    monkeypatch.setattr(m.metadata, "probe", probe)
    tid = api.post("/api/tracks", json={"url": "https://nothing.example/"}).json()["ids"][0]
    [track] = _wait_for(api, lambda ts: ts and ts[0]["status"] != "fetching")
    assert track["id"] == tid and track["status"] == "fetch_error"
    assert "Unsupported URL" in track["error"]


def test_only_http_links_are_taken(api):
    assert api.post("/api/tracks", json={"url": "file:///etc/passwd"}).status_code == 400


# ---------------------------------------------------- editing a staged track
def test_every_track_route_answers_404_for_an_unknown_track(api):
    assert api.patch("/api/tracks/nope", json={"title": "x"}).status_code == 404
    assert api.post("/api/tracks/nope/cover",
                    files={"file": ("c.png", PNG, "image/png")}).status_code == 404
    assert api.get("/api/tracks/nope/cover").status_code == 404
    assert api.post("/api/tracks/nope/retry").status_code == 404
    assert api.delete("/api/tracks/nope").status_code == 204  # deleting is idempotent


def test_a_track_is_locked_while_it_downloads(api, m):
    tid = m.db.create_track("https://v/1", status="downloading", title="T", artist="A")
    assert api.patch(f"/api/tracks/{tid}", json={"title": "x"}).status_code == 409
    assert api.post(f"/api/tracks/{tid}/cover",
                    files={"file": ("c.png", PNG, "image/png")}).status_code == 409
    assert api.delete(f"/api/tracks/{tid}").status_code == 409
    assert m.db.get_track(tid)["title"] == "T"


def test_naming_a_failed_fetch_by_hand_stages_it(api, m):
    tid = m.db.create_track("https://v/1", status="fetch_error", error="Unsupported URL")
    body = api.patch(f"/api/tracks/{tid}", json={"title": "Night Drive", "artist": "Nova"}).json()
    assert (body["status"], body["error"], body["title"]) == ("staged", "", "Night Drive")


def test_only_failed_tracks_can_be_retried(api, m):
    tid = m.db.create_track("https://v/1", status="staged", title="T", artist="A")
    assert api.post(f"/api/tracks/{tid}/retry").status_code == 409


# ------------------------------------------------------- a staged track's cover
def test_a_staged_cover_that_is_not_an_image_is_refused(api, m):
    tid = m.db.create_track("https://v/1", status="staged", title="T", artist="A")
    for name, data, claimed in (("c.svg", SVG, "image/svg+xml"), ("c.png", b"hello", "image/png")):
        r = api.post(f"/api/tracks/{tid}/cover", files={"file": (name, data, claimed)})
        assert r.status_code == 400, name
    assert m.db.get_track(tid)["cover_path"] == ""


def test_a_staged_cover_over_10_mb_is_refused(api, m):
    tid = m.db.create_track("https://v/1", status="staged", title="T", artist="A")
    big = io.BytesIO(PNG + b"\x00" * (10 * 1024 * 1024))
    r = api.post(f"/api/tracks/{tid}/cover", files={"file": ("c.png", big, "image/png")})
    assert r.status_code == 413


def test_a_staged_cover_is_served_as_the_type_its_bytes_say(api, m):
    tid = m.db.create_track("https://v/1", status="staged", title="T", artist="A")
    r = api.post(f"/api/tracks/{tid}/cover", files={"file": ("c.jpg", PNG, "image/jpeg")})
    assert r.status_code == 200 and r.json()["cover_path"]
    got = api.get(f"/api/tracks/{tid}/cover")
    assert got.status_code == 200 and got.content == PNG
    assert got.headers["content-type"] == "image/png"  # not the jpeg the upload claimed
    assert got.headers["x-content-type-options"] == "nosniff"


def test_an_svg_kept_as_a_cover_is_never_served_as_svg(api, m, tmp_path):
    # A cover stored before uploads were checked.
    tid = m.db.create_track("https://v/1", status="staged", title="T", artist="A")
    stored = tmp_path / "data" / "covers" / f"{tid}.img"
    stored.write_bytes(SVG)
    m.db.update_track(tid, cover_path=str(stored))
    r = api.get(f"/api/tracks/{tid}/cover")
    assert r.status_code == 404
    assert "svg" not in r.headers.get("content-type", "")


# ------------------------------------------------------------------ settings
@pytest.mark.parametrize("patch", [
    {"output_format": "ogg"}, {"output_format": "MP3"}, {"language": "de"},
    {"concurrency": 0}, {"concurrency": 9}, {"trash_days": -1}, {"trash_days": 3651},
    {"filename_template": "   "},
])
def test_a_settings_value_outside_the_allowed_ones_is_refused(api, patch):
    before = api.get("/api/settings").json()
    r = api.put("/api/settings", json=patch)
    assert r.status_code == 400
    assert next(iter(patch)) in r.json()["detail"]
    assert api.get("/api/settings").json() == before


def test_stored_values_outside_the_allowed_ones_are_coerced_on_load(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "config.json").write_text(json.dumps({
        "output_format": "FLAC", "language": "de", "concurrency": 99, "trash_days": 99999,
        "filename_template": " "}), "utf-8")
    fresh_modules(tmp_path, monkeypatch)
    from app import config
    assert {k: config.settings[k] for k in
            ("output_format", "language", "concurrency", "trash_days", "filename_template")} == {
        "output_format": "flac", "language": "en", "concurrency": config.CONCURRENCY_MAX,
        "trash_days": config.TRASH_DAYS_MAX, "filename_template": "{artist} - {title}"}


# ---------------------------------------------------------------------- auth
def test_the_ui_token_is_read_from_a_bearer_header_in_any_case(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, token="sekret") as api:
        assert api.get("/api/tracks", headers={"Authorization": "bearer sekret"}).status_code == 200
        assert api.get("/api/tracks", headers={"Authorization": "Basic sekret"}).status_code == 401
        assert api.get("/api/tracks", headers={"Authorization": "Bearer nope"}).status_code == 401


# --------------------------------------------------------------- cover search
class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_cover_search_offers_large_artwork(api, m, monkeypatch):
    asked = []
    payload = {"results": [
        {"artworkUrl100": "https://a/100x100bb.jpg", "artistName": "Nova",
         "trackName": "Night Drive"},
        {"artistName": "No Art"},
    ]}
    monkeypatch.setattr(m.outbound, "open_url", lambda url, timeout=20: (
        asked.append(url), FakeResponse(json.dumps(payload).encode()))[1])
    body = api.get("/api/cover-search", params={"q": "nova night"}).json()
    assert body == {"results": [{"thumb": "https://a/100x100bb.jpg",
                                 "full": "https://a/600x600bb.jpg",
                                 "label": "Nova – Night Drive"}]}
    assert asked and "term=nova+night" in asked[0]


def test_a_failed_cover_search_answers_502(api, m, monkeypatch):
    def down(url, timeout=20):
        raise OSError("no route to host")

    monkeypatch.setattr(m.outbound, "open_url", down)
    r = api.get("/api/cover-search", params={"q": "x"})
    assert r.status_code == 502 and "no route to host" in r.json()["detail"]


# -------------------------------------------------------------- folder picker
def test_the_folder_picker_lists_visible_folders_of_a_pasted_file_path(api, tmp_path):
    base = tmp_path / "pick"
    (base / "House").mkdir(parents=True)
    (base / ".hidden").mkdir()
    (base / "track.mp3").write_bytes(b"x")
    body = api.get("/api/fs/list", params={"path": str(base / "track.mp3")}).json()
    assert body["path"] == str(base.resolve())
    assert [d["name"] for d in body["dirs"]] == ["House"]
    assert body["parent"] == str(base.resolve().parent)
