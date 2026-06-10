from pathlib import Path

from app.naming import render_filename, sanitize_component, unique_path

META = {
    "title": 'Stayin/ Alive: "Remix"',
    "artist": "MOONLGHT",
    "album": "",
    "genre": "House",
    "video_id": "abc123",
    "source": "youtube",
}


def test_illegal_chars_stripped():
    assert sanitize_component('a<b>:"/\\|?*c') == "abc"


def test_render_basic():
    assert render_filename("{artist} - {title}", META) == "MOONLGHT - Stayin Alive Remix"


def test_missing_token_collapses_separators():
    out = render_filename("{artist} - {album} - {title}", META)
    assert out == "MOONLGHT - Stayin Alive Remix"


def test_empty_brackets_removed():
    out = render_filename("{title} [{album}]", META)
    assert out == "Stayin Alive Remix"


def test_all_empty_falls_back():
    assert render_filename("{album}", META) == "untitled"


def test_unique_path_suffix(tmp_path: Path):
    (tmp_path / "x.mp3").write_bytes(b"1")
    p, suffixed = unique_path(tmp_path, "x", ".mp3")
    assert p.name == "x (2).mp3" and suffixed
    p2, suffixed2 = unique_path(tmp_path, "y", ".mp3")
    assert p2.name == "y.mp3" and not suffixed2
