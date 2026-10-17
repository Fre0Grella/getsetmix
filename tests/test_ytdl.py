from datetime import date

import pytest

from app import ytdl

DENO = {"name": "deno", "path": "/usr/local/bin/deno", "version": "2.9.3"}


@pytest.fixture()
def runtime(monkeypatch):
    """Pin the detected JS runtime (None = nothing installed)."""
    def set_runtime(value):
        monkeypatch.setattr(ytdl, "js_runtime", lambda: value)
    return set_runtime


def test_base_opts_enables_detected_runtime(runtime):
    runtime(DENO)
    opts = ytdl.base_opts({"noplaylist": True})
    assert opts["js_runtimes"] == {"deno": {"path": "/usr/local/bin/deno"}}
    assert opts["noplaylist"] is True and opts["quiet"] is True


def test_base_opts_without_runtime_leaves_ytdlp_default(runtime):
    runtime(None)
    assert "js_runtimes" not in ytdl.base_opts()


def test_explain_turns_403_into_the_fix(runtime, monkeypatch):
    runtime(None)
    monkeypatch.setattr(ytdl, "ejs_installed", lambda: True)
    monkeypatch.setattr(ytdl, "ytdlp_age_days", lambda: 1)
    exc = Exception("ERROR: unable to download video data: HTTP Error 403: Forbidden\ntraceback")
    msg = ytdl.explain(exc)
    assert msg.startswith("ERROR: unable to download video data: HTTP Error 403")
    assert "Deno" in msg and "traceback" not in msg


def test_explain_leaves_403_alone_when_setup_is_fine(runtime, monkeypatch):
    runtime(DENO)
    monkeypatch.setattr(ytdl, "ejs_installed", lambda: True)
    monkeypatch.setattr(ytdl, "ytdlp_age_days", lambda: 1)
    assert ytdl.explain(Exception("HTTP Error 403: Forbidden")) == "HTTP Error 403: Forbidden"


def test_explain_ignores_unrelated_errors(runtime):
    runtime(None)
    assert ytdl.explain(Exception("Video unavailable")) == "Video unavailable"


def test_problems_flag_a_stale_ytdlp(runtime, monkeypatch):
    runtime(DENO)
    monkeypatch.setattr(ytdl, "ejs_installed", lambda: True)
    monkeypatch.setattr(ytdl, "ytdlp_age_days", lambda: ytdl.STALE_AFTER_DAYS + 30)
    [problem] = ytdl.problems()
    assert "days old" in problem


def test_age_is_read_from_the_calver(monkeypatch):
    monkeypatch.setattr(ytdl, "YTDLP_VERSION", "2026.07.04")
    assert ytdl.ytdlp_age_days(date(2026, 10, 17)) == 105
    monkeypatch.setattr(ytdl, "YTDLP_VERSION", "nightly")
    assert ytdl.ytdlp_age_days() == 0


def test_status_endpoint(client, monkeypatch):
    import app.ytdl
    monkeypatch.setattr(app.ytdl, "js_runtime", lambda: None)
    body = client.get("/api/status").json()
    assert body["ytdlp"]["js_runtime"] is None
    assert any("JavaScript runtime" in p for p in body["ytdlp"]["problems"])


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import importlib

    from fastapi.testclient import TestClient
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    monkeypatch.delenv("GSM_AUTH_TOKEN", raising=False)
    import app.config
    import app.db
    import app.main
    import app.worker
    for mod in (app.config, app.db, app.worker, app.main):
        importlib.reload(mod)
    with TestClient(app.main.app) as c:
        yield c
