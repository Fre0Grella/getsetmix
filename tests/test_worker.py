import asyncio
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
    monkeypatch.setattr(library.Library, "reconcile",
                        lambda self: pytest.fail("a download must not need a walk"))
    app.worker.worker._process(tid)

    items = lib.list()["items"]
    assert [i["path"] for i in items] == ["Some Artist - Night Drive.mp3"]
    assert items[0]["title"] == "Night Drive" and items[0]["artist"] == "Some Artist"
    assert lib.file(items[0]["id"])["source_url"] == "https://example.test/x"


def test_the_track_keeps_its_files_audio_id(env):
    # Issue #71: the Downloads view finds the file in the index by this id.
    app, tid, music = env
    from app import audiohash, library
    app.worker.worker._process(tid)

    track = app.db.db.get_track(tid)
    assert track["audio_id"] == audiohash.audio_id(track["file_path"])
    [item] = library.current().list()["items"]
    assert item["audio_id"] == track["audio_id"]


def test_the_audio_id_survives_an_index_failure(env, monkeypatch):
    app, tid, music = env
    from app import audiohash, library

    def broken(self, path, source_url=""):
        raise RuntimeError("index broke")

    monkeypatch.setattr(library.Library, "add_file", broken)
    app.worker.worker._process(tid)

    track = app.db.db.get_track(tid)
    assert track["status"] == "ingested"
    assert track["audio_id"] == audiohash.audio_id(track["file_path"])


async def _run_batch(worker, ids, concurrency=None) -> list[str]:
    """Queue `ids` as the API does and wait until the batch is done."""
    from app.db import db

    queued = await worker.start_batch(ids, concurrency)
    # Wait for every queued track to finish, not for `busy`: between one
    # track and the next the worker can look idle for a moment.
    for _ in range(1000):
        if all(db.get_track(t)["status"] in ("ingested", "error") for t in queued):
            break
        await asyncio.sleep(0.01)
    return queued


def test_a_failed_download_marks_its_track_error_and_the_batch_goes_on(env, monkeypatch):
    app, tid, music = env
    db = app.db.db
    db.update_track(tid, status="staged")
    gone = db.create_track("https://example.test/gone", status="staged", title="Gone",
                           artist="Nobody", source="Example")

    def download(self, track, tmpdir):
        if track["url"].endswith("/gone"):
            raise RuntimeError("ERROR: HTTP Error 404: Not Found")
        return _fake_download(tmpdir)

    monkeypatch.setattr(app.worker.Worker, "_download", download)
    queued = asyncio.run(_run_batch(app.worker.worker, [gone, tid], concurrency=1))

    assert queued == [gone, tid]
    assert db.get_track(gone)["status"] == "error"
    assert "404" in db.get_track(gone)["error"]
    assert db.get_track(tid)["status"] == "ingested"  # the one after it still ran
    assert db.counter("errors_source:Example") == 1


def test_placing_a_download_never_overwrites_a_file_already_there(env):
    app, tid, music = env
    music.mkdir(parents=True)
    taken = music / "Some Artist - Night Drive.mp3"
    taken.write_bytes(b"the DJ's own copy")

    app.worker.worker._process(tid)

    assert taken.read_bytes() == b"the DJ's own copy"
    final = Path(app.db.db.get_track(tid)["file_path"])
    assert final.name == "Some Artist - Night Drive (2).mp3"
    assert _title(final) == "Night Drive"
    assert sorted(p.name for p in music.iterdir()) == [
        "Some Artist - Night Drive (2).mp3", "Some Artist - Night Drive.mp3"]  # no .part left


def test_a_track_without_title_or_artist_is_not_queued(env):
    app, tid, music = env
    db = app.db.db
    nameless = db.create_track("https://example.test/y", status="staged", title="Untitled")

    queued = asyncio.run(_run_batch(app.worker.worker, [nameless]))

    assert queued == []
    track = db.get_track(nameless)
    assert track["status"] == "fetch_error"
    assert track["error"] == "Title and artist are required"


def test_cancelling_a_batch_puts_its_queued_tracks_back_to_staged(env):
    app, tid, music = env
    db = app.db.db
    db.update_track(tid, status="staged")
    other = db.create_track("https://example.test/z", status="staged", title="Z", artist="A")

    async def start_then_cancel():
        await app.worker.worker.start_batch([tid, other])
        return await app.worker.worker.cancel_batch()  # before any runner took one

    assert asyncio.run(start_then_cancel()) == 2
    assert [db.get_track(t)["status"] for t in (tid, other)] == ["staged", "staged"]


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
