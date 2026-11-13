import importlib
from pathlib import Path

import pytest
from mutagen.id3 import ID3

# A few silent MPEG-1 Layer III frames (128 kbps, 44.1 kHz): enough for mutagen.
MP3_BYTES = (b"\xff\xfb\x90\x64" + b"\x00" * 413) * 4


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("GSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GSM_LIBRARY_ROOT", str(tmp_path / "music"))
    monkeypatch.delenv("GSM_AUTH_TOKEN", raising=False)
    import app.config
    import app.db
    import app.worker
    for mod in (app.config, app.db, app.worker):
        importlib.reload(mod)
    monkeypatch.setitem(app.config.settings.data, "output_format", "mp3")
    monkeypatch.setitem(app.config.settings.data, "xml_path", str(tmp_path / "inbox.xml"))
    monkeypatch.setattr(
        app.worker.Worker, "_download",
        lambda self, track, tmpdir: _fake_download(tmpdir),
    )
    tid = app.db.db.create_track(
        "https://example.test/x", status="queued", title="Night Drive", artist="Some Artist",
    )
    return app, tid, tmp_path / "music"


def _fake_download(tmpdir: Path) -> Path:
    audio = tmpdir / "abc.mp3"
    audio.write_bytes(MP3_BYTES)
    return audio


def _title(path: Path) -> str | None:
    try:
        return str(ID3(path)["TIT2"])
    except Exception:
        return None


def test_file_is_tagged_before_it_is_placed(env, monkeypatch):
    app, tid, music = env
    seen = {}
    real_place = app.worker.Worker._place_in_library

    def spy_place(self, track, audio):
        # The first moment a paired computer could see the file is when
        # this returns, so the tags must be on `audio` already.
        seen["title_when_placed"] = _title(audio)
        seen["from"] = audio
        final = real_place(self, track, audio)
        seen["final_title"] = _title(final)
        return final

    monkeypatch.setattr(app.worker.Worker, "_place_in_library", spy_place)
    app.worker.worker._process(tid)

    assert app.db.db.get_track(tid)["status"] == "ingested"
    assert seen["title_when_placed"] == "Night Drive"
    assert seen["final_title"] == "Night Drive"
    assert seen["from"].parent.parent.name == "tmp"  # tagged in the temp folder
    final = Path(app.db.db.get_track(tid)["file_path"])
    assert final.parent == music
    assert ID3(final)["TPE1"].text == ["Some Artist"]


def test_a_placed_file_has_its_index_row_at_once(env, monkeypatch):
    app, tid, music = env
    from app import library
    lib = library.current()
    rows_when_xml_written = []
    real_add = app.worker.rekordbox.add_track

    def spy_add(*args, **kwargs):
        # The next step after placing: the row must already be there.
        rows_when_xml_written.append(lib.list()["items"])
        return real_add(*args, **kwargs)

    monkeypatch.setattr(app.worker.rekordbox, "add_track", spy_add)
    monkeypatch.setattr(library.Library, "reconcile",
                        lambda self: pytest.fail("a download must not need a walk"))
    app.worker.worker._process(tid)

    [items] = rows_when_xml_written
    assert [i["path"] for i in items] == ["Some Artist - Night Drive.mp3"]
    assert items[0]["title"] == "Night Drive" and items[0]["artist"] == "Some Artist"
    assert lib.file(items[0]["id"])["source_url"] == "https://example.test/x"


def test_tagging_failure_leaves_nothing_in_the_library(env, monkeypatch):
    app, tid, music = env

    def boom(path, meta):
        raise RuntimeError("tagging broke")

    monkeypatch.setattr(app.worker.tagger, "tag_file", boom)
    app.worker.worker._process(tid)

    track = app.db.db.get_track(tid)
    assert track["status"] == "error"
    assert "tagging broke" in track["error"]
    assert not music.exists() or list(music.iterdir()) == []
