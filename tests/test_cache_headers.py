"""The page and its scripts are checked again on every load, so an update
shows at once (#106); covers keep their own long cache."""
import pytest
from test_library_api import _client, rescan


@pytest.fixture()
def api(tmp_path, monkeypatch, music):
    with _client(tmp_path, monkeypatch) as c:
        yield c


@pytest.mark.parametrize("path", ["/", "/static/app.js", "/static/library.js", "/static/styles.css",
                                  "/sw.js", "/manifest.webmanifest"])
def test_the_ui_is_revalidated_on_every_load(api, path):
    r = api.get(path)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"


def test_an_unchanged_script_is_a_cheap_304(api):
    first = api.get("/static/edits.js")
    again = api.get("/static/edits.js", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.headers["cache-control"] == "no-cache"


def test_covers_keep_their_long_cache(api, music):
    music.fixture("a.mp3", "mp3/all-tags.mp3")
    rescan(api)
    item = api.get("/api/library").json()["items"][0]
    r = api.get(f"/api/library/{item['id']}/cover", params={"v": item["content_rev"]})
    assert r.status_code == 200 and "no-cache" not in r.headers["cache-control"]
    assert "max-age" in r.headers["cache-control"]
