"""WebDAV delivery — path mapping into the remote tree, and error reporting."""
import importlib
import urllib.error
from pathlib import Path

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    import app.config
    import app.delivery
    importlib.reload(app.config)
    importlib.reload(app.delivery)
    app.config.ensure_dirs()
    app.config.settings.update({
        "delivery_mode": "webdav",
        "webdav_url": "https://cloud.example.com/remote.php/dav/files/marco",
        "webdav_user": "marco", "webdav_pass": "app-password",
        "webdav_root": "Music/DJ",
    })
    return app.config, app.delivery, tmp_path


class _Calls(list):
    def __call__(self, method, url, data=None, headers=None):
        self.append((method, url, dict(headers or {})))

        class _Resp:
            def close(self_inner):
                pass
        return _Resp()


def test_disabled_until_fully_configured(env):
    config, delivery, _ = env
    assert delivery.enabled() is True
    config.settings.update({"webdav_pass": ""})
    config.settings.data["webdav_pass"] = ""
    assert delivery.enabled() is False
    config.settings.data["webdav_pass"] = "x"
    config.settings.data["delivery_mode"] = "filesystem"
    assert delivery.enabled() is False


def test_library_path_maps_into_the_remote_tree(env):
    config, delivery, _ = env
    server = Path(config.settings["library_root"]) / "Hardstyle" / "A - B.mp3"
    assert delivery.remote_relative(str(server)) == "Music/DJ/Hardstyle/A - B.mp3"


def test_file_outside_the_library_is_not_uploaded(env):
    _, delivery, _ = env
    assert delivery.remote_relative("/elsewhere/a.mp3") is None
    assert delivery.deliver_file("/elsewhere/a.mp3") is None


def test_upload_creates_each_parent_collection_then_puts(env, monkeypatch):
    config, delivery, _ = env
    calls = _Calls()
    monkeypatch.setattr(delivery, "_request", calls)
    audio = Path(config.settings["library_root"]) / "Hardstyle" / "Sub" / "a.mp3"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"\xff\xfb\x90\x00")

    delivery.deliver_file(str(audio))

    methods = [c[0] for c in calls]
    assert methods == ["MKCOL", "MKCOL", "MKCOL", "MKCOL", "PUT"]
    assert calls[-1][1].endswith("/Music/DJ/Hardstyle/Sub/a.mp3")
    assert calls[-1][2]["Content-Length"] == "4"
    # Parents are created top-down so each level exists before the next.
    assert [c[1].rsplit("/marco/", 1)[-1] for c in calls[:4]] == [
        "Music", "Music/DJ", "Music/DJ/Hardstyle", "Music/DJ/Hardstyle/Sub"]


def test_existing_collection_is_not_an_error(env, monkeypatch):
    """405 from MKCOL means "already there" — the normal case after the first
    upload, and it must not fail the batch."""
    config, delivery, _ = env

    def raiser(method, url, data=None, headers=None):
        if method == "MKCOL":
            raise urllib.error.HTTPError(url, 405, "Not Allowed", {}, None)

        class _R:
            def close(self):
                pass
        return _R()

    monkeypatch.setattr(delivery, "_request", raiser)
    audio = Path(config.settings["library_root"]) / "a.mp3"
    audio.write_bytes(b"\xff")
    assert delivery.deliver_file(str(audio)) == "Music/DJ/a.mp3"


def test_upload_failure_is_reported_with_the_status(env, monkeypatch):
    config, delivery, _ = env

    def raiser(method, url, data=None, headers=None):
        if method == "PUT":
            raise urllib.error.HTTPError(url, 507, "Insufficient Storage", {}, None)

        class _R:
            def close(self):
                pass
        return _R()

    monkeypatch.setattr(delivery, "_request", raiser)
    audio = Path(config.settings["library_root"]) / "a.mp3"
    audio.write_bytes(b"\xff")
    with pytest.raises(delivery.DeliveryError, match="507"):
        delivery.deliver_file(str(audio))


def test_xml_outside_the_library_still_lands_in_the_remote_root(env, monkeypatch):
    """Rekordbox can't read an XML that never left the server."""
    _, delivery, tmp_path = env
    calls = _Calls()
    monkeypatch.setattr(delivery, "_request", calls)
    xml = tmp_path / "getsetmix.xml"
    xml.write_text("<DJ_PLAYLISTS/>")
    assert delivery.deliver_xml(str(xml)) == "Music/DJ/getsetmix.xml"


def test_check_names_the_app_password_problem(env, monkeypatch):
    _, delivery, _ = env

    def raiser(method, url, data=None, headers=None):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(delivery, "_request", raiser)
    ok, detail = delivery.check()
    assert ok is False and "app password" in detail


def test_check_names_a_missing_remote_folder(env, monkeypatch):
    _, delivery, _ = env

    def raiser(method, url, data=None, headers=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(delivery, "_request", raiser)
    ok, detail = delivery.check()
    assert ok is False and "Music/DJ" in detail


def test_health_flags_webdav_selected_but_unconfigured(env):
    config, _, _ = env
    import app.health
    importlib.reload(app.health)
    config.settings.data["webdav_url"] = ""
    report = app.health.run()
    assert any(c["id"] == "delivery" and c["level"] == "error" for c in report["checks"])


def test_url_quoting_handles_spaces_and_accents(env):
    _, delivery, _ = env
    assert delivery._url_for("Music/DJ/Björk – a b.mp3").endswith(
        "/Music/DJ/Bj%C3%B6rk%20%E2%80%93%20a%20b.mp3")
