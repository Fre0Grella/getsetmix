"""How a pasted link resolves into tracks (app/metadata.py), with yt-dlp
replaced at its seam (`ytdl.ydl`): no network."""
import pytest

from app import metadata, ytdl


class FakeYdl:
    """Stands in for a yt_dlp.YoutubeDL: answers extract_info with `info`."""

    def __init__(self, info: dict, opts: dict, calls: list) -> None:
        self.info, self.opts, self.calls = info, opts, calls

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        self.calls.append({"url": url, "download": download, "opts": self.opts})
        return self.info


@pytest.fixture()
def answers(monkeypatch):
    """Set what yt-dlp "finds" for a link; returns the calls it got."""
    calls: list = []
    state = {"info": {}}
    monkeypatch.setattr(ytdl, "ydl", lambda opts=None: FakeYdl(state["info"], opts or {}, calls))

    def answer(info: dict) -> list:
        state["info"] = info
        return calls

    return answer


def test_a_single_video_resolves_into_one_track_with_its_metadata(answers):
    calls = answers({"title": "Nova - Night Drive (Official Video)", "uploader": "NovaVEVO",
                     "duration": 241.5, "id": "abc", "extractor_key": "Youtube",
                     "webpage_url": "https://youtu.be/abc", "thumbnail": "https://i/abc.jpg",
                     "album": "Night EP", "genre": "House"})
    got = metadata.probe("https://youtu.be/abc")
    assert got == {"kind": "single", "meta": {
        "title": "Night Drive", "artist": "Nova", "album": "Night EP", "genre": "House",
        "duration": 241.5, "thumbnail": "https://i/abc.jpg", "video_id": "abc",
        "source": "Youtube", "url": "https://youtu.be/abc"}}
    assert calls[0]["download"] is False  # probing never downloads


def test_the_music_tags_a_site_gives_win_over_the_video_title(answers):
    answers({"title": "Some Upload - Whatever", "track": "Night Drive", "artist": "Nova"})
    meta = metadata.probe("https://music.example/x")["meta"]
    assert (meta["artist"], meta["title"]) == ("Nova", "Night Drive")


def test_without_a_separator_the_artist_is_the_cleaned_uploader(answers):
    answers({"title": "Night Drive [HD]", "uploader": "Nova - Topic"})
    meta = metadata.probe("https://youtu.be/x")["meta"]
    assert (meta["artist"], meta["title"]) == ("Nova", "Night Drive")


def test_a_genre_that_is_not_text_is_left_empty(answers):
    answers({"title": "A - B", "genre": ["House", "Techno"]})
    assert metadata.probe("https://x")["meta"]["genre"] == ""


def test_a_playlist_resolves_into_one_entry_per_video(answers):
    answers({"_type": "playlist", "title": "Set", "extractor_key": "YoutubeTab", "entries": [
        {"url": "https://youtu.be/1", "title": "Nova - One", "uploader": "Nova",
         "duration": 60, "id": "1", "ie_key": "Youtube",
         "thumbnails": [{"url": "small", "width": 120}, {"url": "big", "width": 1280}]},
        None,  # a deleted or private video
        {"webpage_url": "https://youtu.be/2", "title": "Two", "channel": "Kito", "id": "2"},
    ]})
    got = metadata.probe("https://youtube.com/playlist?list=x")
    assert got["kind"] == "playlist" and got["title"] == "Set"
    assert got["entries"] == [
        {"url": "https://youtu.be/1", "title": "Nova - One", "uploader": "Nova",
         "duration": 60.0, "thumbnail": "big", "id": "1", "extractor": "Youtube"},
        {"url": "https://youtu.be/2", "title": "Two", "uploader": "Kito",
         "duration": 0.0, "thumbnail": "", "id": "2", "extractor": "YoutubeTab"},
    ]


def test_fetching_a_link_that_turns_out_to_be_a_playlist_takes_its_first_video(answers):
    calls = answers({"entries": [None, {"title": "Nova - Night Drive", "id": "n1"}]})
    meta = metadata.fetch_single("https://youtu.be/n1?list=x")
    assert (meta["artist"], meta["title"], meta["video_id"]) == ("Nova", "Night Drive", "n1")
    assert calls[0]["opts"]["noplaylist"] is True


def test_an_unreachable_link_raises(monkeypatch):
    class Broken(FakeYdl):
        def extract_info(self, url, download=False):
            raise RuntimeError("ERROR: Unsupported URL")

    monkeypatch.setattr(ytdl, "ydl", lambda opts=None: Broken({}, {}, []))
    with pytest.raises(RuntimeError, match="Unsupported URL"):
        metadata.probe("https://nothing.example/")
