"""GET /api/library/rules and the genre list that now comes from it."""
import importlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import genres, rules


def _client(tmp_path, monkeypatch, token=None):
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    if token:
        monkeypatch.setenv("GSM_AUTH_TOKEN", token)
    else:
        monkeypatch.delenv("GSM_AUTH_TOKEN", raising=False)
    import app.config
    import app.db
    import app.main
    import app.worker
    for mod in (app.config, app.db, app.worker, app.main):
        importlib.reload(mod)
    return TestClient(app.main.app)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        yield c


def test_rules_endpoint_returns_the_catalogue(client):
    r = client.get("/api/library/rules")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == rules.CATALOGUE_VERSION
    assert [x["id"] for x in body["rules"]] == [
        "trim", "promo.remove", "url.remove", "split.artist_title", "feat.normalise",
        "feat.move", "mix.remove_default", "mix.brackets", "artist.separators",
        "case.title", "genre.map", "year.extract",
    ]
    case = next(x for x in body["rules"] if x["id"] == "case.title")
    assert case["name"]["en"] and case["name"]["it"]
    assert case["description"]["en"] and case["description"]["it"]
    assert case["fields"] == ["title", "album"]
    assert {p["name"]: p["default"] for p in case["params"]}["scope"] == "lower"
    assert case["examples"]
    standard = body["rulesets"][0]
    assert standard["name"] == "Standard cleanup" and standard["builtin"] is True
    assert [s["rule"] for s in standard["steps"]][0] == "promo.remove"


def test_rules_endpoint_serves_the_genre_list_to_the_ui(client):
    body = client.get("/api/library/rules").json()
    assert body["genres"] == list(genres.GENRES)
    assert body["genre_picks"] == list(genres.GENRE_PICKS)
    assert len(body["genres"]) == 42


def test_rules_endpoint_is_behind_the_api_auth(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, token="sekret") as c:
        assert c.get("/api/library/rules").status_code == 401
        ok = c.get("/api/library/rules", headers={"x-auth-token": "sekret"})
        assert ok.status_code == 200 and ok.json()["version"] == rules.CATALOGUE_VERSION


def test_ui_no_longer_hard_codes_the_genre_list():
    js = (Path(__file__).parent.parent / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert "const GENRES" not in js and "const GENRE_PICKS" not in js
    assert "/api/library/rules" in js
    assert not re.search(r'"Afro House",\s*"Amapiano"', js)
